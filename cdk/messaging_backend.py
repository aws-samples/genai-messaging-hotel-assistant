import aws_cdk
import platform
from pathlib import Path
from constructs import Construct
from aws_cdk import (aws_apigateway as api_gw,
                     aws_bedrock as bedrock,
                     aws_ecr_assets,
                     aws_iam as iam,
                     aws_lambda as lambda_,
                     aws_logs as logs,
                     aws_secretsmanager as sm,
                     custom_resources,
                     CfnParameter,
                     CustomResource,
                     SecretValue)


class MessagingBackend(Construct):
    def __init__(self,
                 scope: Construct,
                 construct_id: str,
                 telegram_api_key: CfnParameter,
                 whatsapp_api_key: CfnParameter,
                 whatsapp_id: CfnParameter,
                 assistant_flow_alias: bedrock.CfnFlowAlias,
                 spa_availability_lambda: lambda_.FunctionBase,
                 telegram_backend_lamda_dir: Path = Path('lambda') / 'telegram_api',
                 whatsapp_backend_lamda_dir: Path = Path('lambda') / 'whatsapp_api',
                 webhook_registration_lamda_dir: Path = Path('lambda') / 'set_webhook',
                 lambda_platform: aws_ecr_assets.Platform | None = None,
                 lambda_architecture: lambda_.Architecture | None = None):
        """
        Construct for the Telegram API, fronted by an API gateway

        Parameters
        ----------
        scope : Construct scope (typically `self` from the caller)
        construct_id : Unique CDK ID for this construct
        telegram_api_key : API key to use for the Telegram client to be able to send messages
        whatsapp_api_key : Temporary or permanent API key for communicating with the WhatsApp servers
        whatsapp_id : WhatsApp phone number ID for the bot to use for sending messages
        assistant_flow_alias : Assistant flow alias
        spa_availability_lambda : Lambda function for handling the Spa reservations
        telegram_backend_lamda_dir : Path to the directory containing the source code for the
                                     Lambda backend for Telegram communications
        whatsapp_backend_lamda_dir : Path to the directory containing the source code for the
                                     Lambda backend for WhatsApp communications
        webhook_registration_lamda_dir : Path to the directory containing the source code for the
                                         Lambda that will set the webhook URL to the new API Gateway.
        lambda_platform : Platform to use for the lambdas. If not provided, use the platform of the current computer.
        lambda_architecture : Architecture for the lambda to run in. If not provided, use the platform of the
                              current computer. Must be coherent with `lambda_platform`.
        """
        super().__init__(scope, construct_id)

        # Default to current platform, useful since we'll compile the docker images
        if lambda_architecture is None or lambda_architecture is None:
            match platform.machine():
                case 'arm64':
                    lambda_platform = aws_ecr_assets.Platform.LINUX_ARM64
                    lambda_architecture = lambda_.Architecture.ARM_64
                case _:
                    lambda_platform = aws_ecr_assets.Platform.LINUX_AMD64
                    lambda_architecture = lambda_.Architecture.X86_64

        # Create the Lambda resource from the code in lambda/telegram_api
        # Lambda CustomResource for creating the index in the Collection
        telegram_secret = sm.Secret(self, 'TelegramAPIKeySecret',
                                    secret_string_value=SecretValue.unsafe_plain_text(telegram_api_key.value_as_string))
        whatsapp_secret = sm.Secret(self, 'WhatsAppAPIKeySecret',
                                    secret_string_value=SecretValue.unsafe_plain_text(whatsapp_api_key.value_as_string))
        whatsapp_verify_token_secret = sm.Secret(self, 'WhatsAppAPIVerifyToken',
                                                 secret_name='WhatsAppAPIVerifyToken')
        invoke_flow_statement = iam.PolicyStatement(sid='BedrockInvokeFlowStatement',
                                                    effect=iam.Effect.ALLOW,
                                                    resources=[assistant_flow_alias.attr_arn],
                                                    actions=['bedrock:InvokeFlow'])
        base_lambda_policy = iam.ManagedPolicy.from_aws_managed_policy_name(
            managed_policy_name='service-role/AWSLambdaBasicExecutionRole')
        telegram_lambda_role = iam.Role(scope=self,
                                        id='BackendTelegramLambdaRole',
                                        assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
                                        managed_policies=[base_lambda_policy])
        telegram_lambda_role.add_to_policy(invoke_flow_statement)
        spa_availability_lambda.grant_invoke(telegram_lambda_role)
        telegram_secret.grant_read(telegram_lambda_role)
        whatsapp_lambda_role = iam.Role(scope=self,
                                        id='BackendWhatsAppLambdaRole',
                                        assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
                                        managed_policies=[base_lambda_policy])
        whatsapp_lambda_role.add_to_policy(invoke_flow_statement)
        whatsapp_secret.grant_read(whatsapp_lambda_role)
        spa_availability_lambda.grant_invoke(whatsapp_lambda_role)
        whatsapp_verify_token_secret.grant_read(whatsapp_lambda_role)
        # Telegram API-related resources
        image = lambda_.DockerImageCode.from_image_asset(telegram_backend_lamda_dir.as_posix(),
                                                         platform=lambda_platform)
        self.telegram_lambda = lambda_.DockerImageFunction(scope=self,
                                                           id='TelegramAPI',
                                                           code=image,
                                                           architecture=lambda_architecture,
                                                           environment={'FLOW_ID': assistant_flow_alias.attr_flow_id,
                                                                        'FLOW_ALIAS_ID': assistant_flow_alias.attr_id,
                                                                        'SECRET_NAME': telegram_secret.secret_name,
                                                                        'RESERVATIONS_LAMBDA_ARN': spa_availability_lambda.function_arn},
                                                           timeout=aws_cdk.Duration.seconds(30),
                                                           role=telegram_lambda_role,
                                                           log_retention=logs.RetentionDays.THREE_DAYS)
        self.telegram_lambda.grant_invoke(iam.ServicePrincipal('apigateway.amazonaws.com'))

        # Create the API Gateway with the resource pointing to the Telegram lambda
        self.api = api_gw.RestApi(scope, 'GenAIAssistantMessagingAPI')
        self.api.root.add_cors_preflight(allow_origins=['*'],
                                         allow_methods=['GET', 'POST'],
                                         allow_headers=['*'])
        telegram_api = self.api.root.add_resource('telegram',
                                                  default_integration=api_gw.LambdaIntegration(self.telegram_lambda,
                                                                                               allow_test_invoke=False))
        telegram_api.add_method('POST')

        # WhatsApp API-related resources
        image = lambda_.DockerImageCode.from_image_asset(whatsapp_backend_lamda_dir.as_posix(),
                                                         platform=lambda_platform)
        self.whatsapp_lambda = lambda_.DockerImageFunction(scope=self,
                                                           id='WhatsAppAPI',
                                                           code=image,
                                                           architecture=lambda_architecture,
                                                           environment={
                                                               'WHATSAPP_VERIFY_TOKEN_NAME': whatsapp_verify_token_secret.secret_name,
                                                               'WHATSAPP_ID': whatsapp_id.value_as_string,
                                                               'FLOW_ID': assistant_flow_alias.attr_flow_id,
                                                               'FLOW_ALIAS_ID': assistant_flow_alias.attr_id,
                                                               'WHATSAPP_API_KEY_NAME': whatsapp_secret.secret_name,
                                                               'RESERVATIONS_LAMBDA_ARN': spa_availability_lambda.function_arn},
                                                           timeout=aws_cdk.Duration.seconds(30),
                                                           role=whatsapp_lambda_role,
                                                           log_retention=logs.RetentionDays.THREE_DAYS)
        self.whatsapp_lambda.grant_invoke(iam.ServicePrincipal('apigateway.amazonaws.com'))

        # Create the API Gateway resource to the WhatsApp lambda
        whatsapp_api = self.api.root.add_resource('whatsapp',
                                                  default_integration=api_gw.LambdaIntegration(self.whatsapp_lambda,
                                                                                               allow_test_invoke=False))
        whatsapp_api.add_method('POST')
        whatsapp_api.add_method('GET')

        # Finally, register the API Gateway webhook with the Telegram Servers
        # https://core.telegram.org/bots/api#getting-updates
        # Lambda CustomResource for creating the index in the Collection
        webhook_registration_role = iam.Role(scope=self,
                                             id='WebhookRegistrationLambdaRole',
                                             assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
                                             managed_policies=[base_lambda_policy])
        telegram_secret.grant_read(webhook_registration_role)
        image = lambda_.DockerImageCode.from_image_asset(webhook_registration_lamda_dir.as_posix(),
                                                         platform=lambda_platform)
        cust_res_lambda = lambda_.DockerImageFunction(scope=self,
                                                      id='WebhookRegistrationLambda',
                                                      code=image,
                                                      architecture=lambda_architecture,
                                                      timeout=aws_cdk.Duration.seconds(30),
                                                      role=webhook_registration_role,
                                                      log_retention=logs.RetentionDays.THREE_DAYS)
        res_provider = custom_resources.Provider(scope=self,
                                                 id='CustomResourceProviderWebhookRegistration',
                                                 on_event_handler=cust_res_lambda)
        webhook_registerer = CustomResource(scope=self,
                                            id='CustomResourceWebhookRegistration',
                                            service_token=res_provider.service_token,
                                            properties={'secret_name': telegram_secret.secret_name,
                                                        'webhook_uri': f'{self.api.url}telegram'})
        webhook_registerer.node.add_dependency(telegram_api)
