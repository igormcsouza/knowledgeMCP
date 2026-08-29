import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("ENVIRONMENT", "test")


@pytest.fixture
def dynamodb_tables():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        resource.create_table(
            TableName="knowledge-mcp-test-content-index",
            KeySchema=[
                {"AttributeName": "article_path", "KeyType": "HASH"},
                {"AttributeName": "chunk_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "article_path", "AttributeType": "S"},
                {"AttributeName": "chunk_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        resource.create_table(
            TableName="knowledge-mcp-test-usage-tracking",
            KeySchema=[{"AttributeName": "article_path", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "article_path", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield resource
