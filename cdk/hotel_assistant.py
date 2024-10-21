from pathlib import Path
from constructs import Construct
from cdk.aoss_kb_stack import AOSSKB
from aws_cdk import CfnParameter, Stack
from cdk.reservations import Reservations
from cdk.assistant_flow import AssistantFlow
from cdk.messaging_backend import MessagingBackend


class HotelAssistantStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create the S3 Bucket (with deployment) + Agent + KB + AOSS Collection
        kb_stack = AOSSKB(scope=self,
                          construct_id='HotelAgentKB')
        # Create the Messaging backend Lambda-powered API Gateway
        telegram_api_key = CfnParameter(self, 'TelegramAPIKey',
                                        type='String',
                                        description='The Telegram API key',
                                        no_echo=True)
        whatsapp_api_key = CfnParameter(self, 'WhatsaAppAPIKey',
                                        type='String',
                                        description='The WhatsApp API key',
                                        no_echo=True)
        whatsapp_id = CfnParameter(self, 'WhatsAppPhoneID',
                                   type='String',
                                   description='The WhatsApp Phone ID for the bot to use',
                                   no_echo=True)
        # Create the resources for handling the reservations API
        reservations_stack = Reservations(scope=self,
                                          construct_id='HotelAgentReservations')
        assistant_flow = AssistantFlow(scope=self,
                                       construct_id='HotelAgentAssistantFlow',
                                       flow_definition=Path('resources') / 'flow_definition.json',
                                       knowledge_base=kb_stack.knowledge_base,
                                       spa_availability_lambda=reservations_stack.spa_lambda)
        backend = MessagingBackend(scope=self,
                                   construct_id='HotelAgentBackend',
                                   telegram_api_key=telegram_api_key,
                                   whatsapp_api_key=whatsapp_api_key,
                                   whatsapp_id=whatsapp_id,
                                   assistant_flow_alias=assistant_flow.flow_alias,
                                   spa_availability_lambda=reservations_stack.spa_lambda)
