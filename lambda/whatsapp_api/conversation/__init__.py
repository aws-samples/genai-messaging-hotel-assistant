import os
import boto3

agents_runtime = boto3.client('bedrock-agent-runtime')
AGENT_ID = os.environ.get('AGENT_ID')
AGENT_ALIAS_ID = os.environ.get('AGENT_ALIAS_ID')
