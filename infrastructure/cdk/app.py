#!/usr/bin/env python3

import os

import aws_cdk as cdk

from stacks.knowledge_mcp_stack import KnowledgeMcpStack

app = cdk.App()

environment_name = os.getenv("ENVIRONMENT", "dev")
# Bedrock Titan Embeddings has no sa-east-1 endpoint; the rest of the stack
# (DynamoDB, Lambda, EventBridge) stays in sa-east-1 and calls Bedrock
# cross-region via BEDROCK_REGION instead of moving the whole stack.
aws_region = os.getenv("AWS_REGION", "sa-east-1")
bedrock_region = os.getenv("BEDROCK_REGION", "us-east-1")

stack = KnowledgeMcpStack(
    app,
    f"knowledge-mcp-{environment_name}",
    env=cdk.Environment(account=os.getenv("AWS_ACCOUNT_ID"), region=aws_region),
    environment_name=environment_name,
    bedrock_region=bedrock_region,
)

app.synth()
