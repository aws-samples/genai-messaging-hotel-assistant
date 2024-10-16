import os
import boto3

agents_runtime = boto3.client('bedrock-agent-runtime')
FLOW_ID = os.environ.get('FLOW_ID', '__INVALID__')
FLOW_ALIAS_ID = os.environ.get('FLOW_ALIAS_ID', '__INVALID__')
