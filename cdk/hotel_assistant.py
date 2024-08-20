from pathlib import Path
from constructs import Construct
from aws_cdk import CfnParameter, Stack
import aws_cdk.aws_bedrock as bedrock
from cdk.messaging_backend import MessagingBackend
from cdk.hotel_aoss_kb_stack import AgentWithAOSSKB


class HotelAssistantStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create the S3 Bucket (with deployment) + Agent + KB + AOSS Collection
        kb_stack = AgentWithAOSSKB(scope=self,
                                   construct_id='HotelAgentKB',
                                   agent_instructions=(Path('resources') / 'agent_prompt.txt').read_text())
        # Lambda CustomResource for creating the index in the Collection
        image = lambda_.DockerImageCode.from_image_asset('lambda/collections',
                                                         platform=lambda_platform)
        cust_res_lambda = lambda_.DockerImageFunction(scope=self,
                                                      id='CollectionIndexCreator',
                                                      code=image,
                                                      architecture=lambda_architecture,
                                                      timeout=aws_cdk.Duration.seconds(60),
                                                      role=index_lambda_role)

        res_provider = custom_resources.Provider(scope=self,
                                                 id='CustomResourceIndexCreator',
                                                 on_event_handler=cust_res_lambda)

        index_creator = CustomResource(scope=self,
                                       id='CustomCollectionIndexCreator',
                                       service_token=res_provider.service_token,
                                       properties={'collection': self.collection.name,
                                                   'endpoint': self.collection.attr_collection_endpoint,
                                                   'vector_index_name': 'bedrock-knowledge-base-default-index',
                                                   'vector_size': ambeddings_vector_size,  # Depends on embeddings model
                                                   'metadata_field': 'AMAZON_BEDROCK_METADATA',
                                                   'text_field': 'AMAZON_BEDROCK_TEXT_CHUNK',
                                                   'vector_field': 'bedrock-knowledge-base-default-vector'})
        index_creator.node.add_dependency(self.collection)
        # Create the Messaging backend Lambda-powered API Gateway
        telegram_api_key = CfnParameter(self, 'TelegramAPIKey',
                                        type='String',
                                        description='The Telegram API key',
                                        no_echo=True)
        whatsapp_api_key = CfnParameter(self, 'WhatsaAppAPIKey',
                                        type='String',
                                        description='The WhatsApp API key',
                                        no_echo=True)
        whatsapp_id = CfnParameter(self, 'WhatsaAppPhoneID',
                                   type='String',
                                   description='The WhatsApp Phone ID for the bot to use',
                                   no_echo=True)
        backend = MessagingBackend(scope=self,
                                   construct_id='HotelAgentBackend',
                                   agent=kb_stack.agent,
                                   agent_alias=kb_stack.agent_alias,
                                   telegram_api_key=telegram_api_key,
                                   whatsapp_api_key=whatsapp_api_key,
                                   whatsapp_id=whatsapp_id)
