#!/usr/bin/env python3

import os

import aws_cdk as cdk

from stacks.knowledge_mcp_stack import KnowledgeMcpStack

app = cdk.App()

environment_name = os.getenv("ENVIRONMENT", "dev")
aws_region = os.getenv("AWS_REGION", "sa-east-1")

stack = KnowledgeMcpStack(
    app,
    f"knowledge-mcp-{environment_name}",
    env=cdk.Environment(account=os.getenv("AWS_ACCOUNT_ID"), region=aws_region),
    environment_name=environment_name,
)

app.synth()
