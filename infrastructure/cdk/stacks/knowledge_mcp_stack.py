import os

import aws_cdk as cdk
from aws_cdk import (
    aws_dynamodb,
    aws_events,
    aws_events_targets,
    aws_iam,
    aws_lambda,
    aws_logs,
    aws_secretsmanager,
)
from constructs import Construct


class KnowledgeMcpStack(cdk.Stack):
    """Two-Lambda stack: a batch indexer and a stateless MCP server.

    Indexing never happens on-request (see PLAN.md) — the indexer Lambda
    writes to DynamoDB on a schedule/webhook, the MCP server Lambda only
    reads at query time.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment_name: str = "dev",
        bedrock_region: str = "us-east-1",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.bedrock_region = bedrock_region

        if environment_name.startswith("pr-"):
            cdk.Tags.of(self).add("Ephemeral", "true")
            cdk.Tags.of(self).add("PRNumber", environment_name.removeprefix("pr-"))

        content_table = self._create_content_index_table()
        usage_table = self._create_usage_tracking_table()
        indexer_state_table = self._create_indexer_state_table()
        webhook_secret = self._create_webhook_secret()

        indexer_function = self._create_indexer_function(
            content_table, usage_table, indexer_state_table, webhook_secret
        )
        self._create_indexer_schedule(indexer_function)
        self._create_indexer_function_url(indexer_function)

        mcp_function = self._create_mcp_server_function(content_table, usage_table)
        self._create_function_url(mcp_function)

    def _create_content_index_table(self) -> aws_dynamodb.Table:
        # PK: article_path groups chunks per article; SK: chunk_id lets a
        # single article's chunks be fetched in one Query (get_article_context)
        # while search_concept still needs a table-wide Scan for brute-force
        # cosine similarity at this KB's scale (see PLAN.md 1.2).
        table = aws_dynamodb.Table(
            self,
            "ContentIndexTable",
            table_name=f"knowledge-mcp-{self.environment_name}-content-index",
            partition_key=aws_dynamodb.Attribute(
                name="article_path", type=aws_dynamodb.AttributeType.STRING
            ),
            sort_key=aws_dynamodb.Attribute(
                name="chunk_id", type=aws_dynamodb.AttributeType.STRING
            ),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=(
                cdk.RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else cdk.RemovalPolicy.DESTROY
            ),
            point_in_time_recovery_specification=(
                aws_dynamodb.PointInTimeRecoverySpecification(
                    point_in_time_recovery_enabled=self.environment_name == "prod"
                )
            ),
        )
        cdk.Tags.of(table).add("Environment", self.environment_name)
        cdk.Tags.of(table).add("Application", "knowledge-mcp")
        return table

    def _create_usage_tracking_table(self) -> aws_dynamodb.Table:
        # PK: article_path. Powers find_weak_concepts / suggest_review_queue,
        # and is written back to by log_query_feedback (see PLAN.md 1.3, 3.8).
        table = aws_dynamodb.Table(
            self,
            "UsageTrackingTable",
            table_name=f"knowledge-mcp-{self.environment_name}-usage-tracking",
            partition_key=aws_dynamodb.Attribute(
                name="article_path", type=aws_dynamodb.AttributeType.STRING
            ),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=(
                cdk.RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else cdk.RemovalPolicy.DESTROY
            ),
            point_in_time_recovery_specification=(
                aws_dynamodb.PointInTimeRecoverySpecification(
                    point_in_time_recovery_enabled=self.environment_name == "prod"
                )
            ),
        )
        cdk.Tags.of(table).add("Environment", self.environment_name)
        cdk.Tags.of(table).add("Application", "knowledge-mcp")
        return table

    def _create_indexer_state_table(self) -> aws_dynamodb.Table:
        # Single-item-per-repo table holding the last-indexed commit SHA, so
        # the webhook-triggered indexer can diff and re-index only changed
        # files (PLAN.md 1.4).
        table = aws_dynamodb.Table(
            self,
            "IndexerStateTable",
            table_name=f"knowledge-mcp-{self.environment_name}-indexer-state",
            partition_key=aws_dynamodb.Attribute(
                name="repo", type=aws_dynamodb.AttributeType.STRING
            ),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=(
                cdk.RemovalPolicy.RETAIN
                if self.environment_name == "prod"
                else cdk.RemovalPolicy.DESTROY
            ),
        )
        cdk.Tags.of(table).add("Environment", self.environment_name)
        cdk.Tags.of(table).add("Application", "knowledge-mcp")
        return table

    def _create_webhook_secret(self) -> aws_secretsmanager.Secret:
        # HMAC secret shared with the GitHub webhook config, used to verify
        # X-Hub-Signature-256 on incoming push events (PLAN.md 1.4).
        return aws_secretsmanager.Secret(
            self,
            "GithubWebhookSecret",
            secret_name=f"knowledge-mcp-{self.environment_name}-github-webhook-secret",
            generate_secret_string=aws_secretsmanager.SecretStringGenerator(
                exclude_punctuation=True,
                password_length=40,
            ),
        )

    def _create_indexer_function(
        self,
        content_table: aws_dynamodb.Table,
        usage_table: aws_dynamodb.Table,
        indexer_state_table: aws_dynamodb.Table,
        webhook_secret: aws_secretsmanager.Secret,
    ) -> aws_lambda.Function:
        repo_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")

        role = aws_iam.Role(
            self,
            "IndexerLambdaRole",
            assumed_by=aws_iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        content_table.grant_read_write_data(role)
        usage_table.grant_read_write_data(role)
        indexer_state_table.grant_read_write_data(role)
        webhook_secret.grant_read(role)
        role.add_to_policy(
            aws_iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )
        role.add_managed_policy(
            aws_iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        log_group = aws_logs.LogGroup(
            self,
            "IndexerFunctionLogs",
            retention=aws_logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        function = aws_lambda.Function(
            self,
            "IndexerFunction",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            code=aws_lambda.Code.from_docker_build(
                path=repo_root, file="indexer/Dockerfile"
            ),
            handler="index.handler",
            # GitHub fetch + chunking + embedding calls run well past the
            # default 3s/128MB Lambda ceiling for anything but a trivial KB.
            timeout=cdk.Duration.minutes(5),
            memory_size=1024,
            role=role,
            environment={
                "ENVIRONMENT": self.environment_name,
                "BEDROCK_REGION": self.bedrock_region,
                "LOG_LEVEL": "INFO" if self.environment_name == "prod" else "DEBUG",
                "GITHUB_WEBHOOK_SECRET_ARN": webhook_secret.secret_arn,
            },
            log_group=log_group,
        )

        cdk.Tags.of(function).add("Environment", self.environment_name)
        cdk.Tags.of(function).add("Application", "knowledge-mcp")
        return function

    def _create_indexer_function_url(
        self, indexer_function: aws_lambda.Function
    ) -> None:
        # Public endpoint the GitHub webhook posts push events to. Auth is
        # the HMAC signature (X-Hub-Signature-256), not IAM — GitHub can't
        # sign SigV4 requests.
        function_url = indexer_function.add_function_url(
            auth_type=aws_lambda.FunctionUrlAuthType.NONE,
        )
        cdk.CfnOutput(
            self,
            "IndexerWebhookUrl",
            value=function_url.url,
            description="GitHub webhook target (Settings -> Webhooks -> Payload URL)",
            export_name=f"knowledge-mcp-indexer-webhook-url-{self.environment_name}",
        )

    def _create_indexer_schedule(self, indexer_function: aws_lambda.Function) -> None:
        # Daily EventBridge rule as a fallback safety net alongside the
        # (not-yet-built) GitHub webhook trigger (PLAN.md 1.4).
        rule = aws_events.Rule(
            self,
            "IndexerScheduleRule",
            rule_name=f"knowledge-mcp-{self.environment_name}-indexer-schedule",
            schedule=aws_events.Schedule.rate(cdk.Duration.days(1)),
        )
        rule.add_target(aws_events_targets.LambdaFunction(indexer_function))

    def _create_mcp_server_function(
        self,
        content_table: aws_dynamodb.Table,
        usage_table: aws_dynamodb.Table,
    ) -> aws_lambda.Function:
        repo_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")

        role = aws_iam.Role(
            self,
            "McpServerLambdaRole",
            assumed_by=aws_iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        content_table.grant_read_data(role)
        # log_query_feedback (PLAN.md 3.8) writes back to usage tracking.
        usage_table.grant_read_write_data(role)
        role.add_to_policy(
            aws_iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )
        role.add_managed_policy(
            aws_iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        log_group = aws_logs.LogGroup(
            self,
            "McpServerFunctionLogs",
            retention=aws_logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        function = aws_lambda.Function(
            self,
            "McpServerFunction",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            code=aws_lambda.Code.from_docker_build(
                path=repo_root, file="mcp_server/Dockerfile"
            ),
            handler="index.handler",
            timeout=cdk.Duration.seconds(30),
            memory_size=512,
            role=role,
            environment={
                "ENVIRONMENT": self.environment_name,
                "BEDROCK_REGION": self.bedrock_region,
                "LOG_LEVEL": "INFO" if self.environment_name == "prod" else "DEBUG",
            },
            log_group=log_group,
        )

        cdk.Tags.of(function).add("Environment", self.environment_name)
        cdk.Tags.of(function).add("Application", "knowledge-mcp")
        return function

    def _create_function_url(self, mcp_function: aws_lambda.Function) -> None:
        # Function URL, not API Gateway: simplest fronting for a personal MCP
        # server (PLAN.md 2.2). Auth is the bearer-token middleware inside
        # the app, not IAM, since the client is a generic MCP client.
        function_url = mcp_function.add_function_url(
            auth_type=aws_lambda.FunctionUrlAuthType.NONE,
        )

        cdk.CfnOutput(
            self,
            "McpServerUrl",
            value=function_url.url,
            description="MCP server Lambda Function URL (streamable-http endpoint)",
            export_name=f"knowledge-mcp-server-url-{self.environment_name}",
        )
