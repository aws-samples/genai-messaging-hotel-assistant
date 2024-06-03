from pathlib import Path
from constructs import Construct
from aws_cdk import CfnParameter, Stack
from cdk.messaging_backend import MessagingBackend
from cdk.hotel_aoss_kb_stack import AgentWithAOSSKB


class HotelAssistantStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create the S3 Bucket (with deployment) + Agent + KB + AOSS Collection
        kb_stack = AgentWithAOSSKB(scope=self,
                                   construct_id='HotelAgentKB',
                                   agent_instructions=(Path('resources') / 'agent_prompt.txt').read_text())
        # Create the Messaging backend Lambda-powered API Gateway
        api_key = CfnParameter(self, 'TelegramAPIKey', type='String',
                               description='The Telegram API key', no_echo=True)
        backend = MessagingBackend(scope=self,
                                   construct_id='HotelAgentBackend',
                                   agent=kb_stack.agent,
                                   agent_alias=kb_stack.agent_alias,
                                   telegram_api_key=api_key)
