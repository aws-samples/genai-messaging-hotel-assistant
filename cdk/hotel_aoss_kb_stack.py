import json
import aws_cdk
import platform
from pathlib import Path
from constructs import Construct
from aws_cdk import (CustomResource,
                     RemovalPolicy,
                     aws_bedrock as bedrock,
                     aws_ecr_assets,
                     aws_iam as iam,
                     aws_lambda as lambda_,
                     aws_opensearchserverless as os_serverless,
                     aws_s3 as s3,
                     aws_s3_deployment as s3_deployment,
                     aws_s3_notifications as s3n,
                     custom_resources)
from .utils import get_flow_definition


class AgentWithAOSSKB(Construct):
    def __init__(self,
                 scope: Construct,
                 construct_id: str,
                 bucket_deployment_dir: Path = Path('docs'),
                 agent_model_id: str = 'anthropic.claude-3-haiku-20240307-v1:0',
                 agent_alias_name: str = 'v1',
                 embeddings_model_id: str = 'amazon.titan-embed-text-v2:0',
                 ambeddings_vector_size: int = 1024,
                 agent_instructions: str = 'You are a helpful hotel assistant',
                 flow_definition: Path = Path('resources/flow_definition.json'),
                 lambda_platform: aws_ecr_assets.Platform | None = None,
                 lambda_architecture: lambda_.Architecture | None = None):
        """
        Construct that will deploy a Bedrock Agent with OpenSearch Serverless-powered Knowledge Bases

        Parameters
        ----------
        scope : Construct scope (typically `self` from the caller)
        construct_id : Unique CDK ID for this construct
        bucket_deployment_dir : Path of the directory holding the files to be initially present in the KB
        agent_model_id : Bedrock model ID for the agent
                         (https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html)
        embeddings_model_id : Bedrock model ID for the agent
                         (https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html)
        ambeddings_vector_size : Dimension of the embeddings vector, depends on the embeddings model used
        agent_instructions : Base instructions for the agent
        flow_definition : Path for the JSON file with the flow definition.
        lambda_platform : Compute platform to use for Lambdas, will try to use the native machine architecture
        lambda_architecture : Architecture of the Lambdas, will try to use the native machine architecture
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

        # Role that will be used by the KB
        kb_role = iam.Role(scope=self,
                           id='AgentKBRole',
                           assumed_by=iam.ServicePrincipal('bedrock.amazonaws.com'))
        # The name for this role is a requirement for Bedrock
        agent_role = iam.Role(scope=self,
                              id='AgentRole',
                              role_name='AmazonBedrockExecutionRoleForAgents_HotelGenAI',
                              assumed_by=iam.ServicePrincipal('bedrock.amazonaws.com'))
        base_lambda_policy = iam.ManagedPolicy.from_aws_managed_policy_name(
            managed_policy_name='service-role/AWSLambdaBasicExecutionRole')
        index_lambda_role = iam.Role(scope=self,
                                     id='IndexCreatorLambdaRole',
                                     assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
                                     managed_policies=[base_lambda_policy])
        kb_lambda_role = iam.Role(scope=self,
                                  id='KBSyncLambdaRole',
                                  assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
                                  managed_policies=[base_lambda_policy])
        flow_role = iam.Role(scope=self,
                             id='PromptFlowRole',
                             role_name='AmazonBedrockExecutionRoleForFlows_HotelGenAI',
                             assumed_by=iam.ServicePrincipal('bedrock.amazonaws.com'))
        # S3 bucket that will be used for our storage needs
        self.bucket = s3.Bucket(scope=self,
                                id='AgentKBDocsBucket',
                                versioned=False,
                                encryption=s3.BucketEncryption.S3_MANAGED,
                                event_bridge_enabled=True,
                                removal_policy=RemovalPolicy.DESTROY,
                                enforce_ssl=True,
                                auto_delete_objects=True)
        bucket_deployment = s3_deployment.BucketDeployment(scope=self,
                                                           id='AgentKBDocsDeployment',
                                                           sources=[s3_deployment.Source.asset(
                                                               bucket_deployment_dir.as_posix(),
                                                               exclude=['*.pptx',
                                                                        '*.docx'])],
                                                           destination_bucket=self.bucket)
        # OpenSearch Serverless collection
        self.collection = os_serverless.CfnCollection(scope=self,
                                                      id='AgentCollection',
                                                      name='assistant-collection',
                                                      # the properties below are optional
                                                      description='Hotel Assistant Embeddings Store',
                                                      standby_replicas='DISABLED',
                                                      type='VECTORSEARCH')
        encryption_policy_document = json.dumps({'Rules': [{'ResourceType': 'collection',
                                                            'Resource': [f'collection/{self.collection.name}']}],
                                                 'AWSOwnedKey': True},
                                                separators=(',', ':'))
        encryption_policy = os_serverless.CfnSecurityPolicy(scope=self,
                                                            id='CollectionEncryptionPolicy',
                                                            name='assistant-col-encryption-policy',
                                                            type='encryption',
                                                            policy=encryption_policy_document)
        self.collection.add_dependency(encryption_policy)
        network_policy_document = json.dumps([{'Rules': [{'Resource': [f'collection/{self.collection.name}'],
                                                          'ResourceType': 'dashboard'},
                                                         {'Resource': [f'collection/{self.collection.name}'],
                                                          'ResourceType': 'collection'}],
                                               'AllowFromPublic': True}], separators=(',', ':'))
        network_policy = os_serverless.CfnSecurityPolicy(scope=self,
                                                         id='CollectionNetworkPolicy',
                                                         name='assistant-col-network-policy',
                                                         type='network',
                                                         policy=network_policy_document)
        self.collection.add_dependency(network_policy)
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

        # Bedrock
        embeddings_model_arn = bedrock.FoundationModel.from_foundation_model_id(
            scope=self,
            _id='EmbeddingsModel',
            foundation_model_id=bedrock.FoundationModelIdentifier(embeddings_model_id)).model_arn
        text_model_arn = bedrock.FoundationModel.from_foundation_model_id(
            scope=self,
            _id='TextModel',
            foundation_model_id=bedrock.FoundationModelIdentifier(agent_model_id)).model_arn
        # Create the rolw that the Bedrock Agent will use
        self.bucket.grant_read(kb_role)
        kb_role.add_to_policy(iam.PolicyStatement(sid='OpenSearchServerlessAPIAccessAllStatement',
                                                  effect=iam.Effect.ALLOW,
                                                  resources=[self.collection.attr_arn],
                                                  actions=['aoss:APIAccessAll']))
        kb_role.add_to_policy(iam.PolicyStatement(sid='BedrockInvokeModelStatement',
                                                  effect=iam.Effect.ALLOW,
                                                  resources=[embeddings_model_arn],
                                                  actions=['bedrock:InvokeModel']))

        # Opensearch data access policy
        policy = json.dumps([{'Rules':
                                  [{'Resource': [f'collection/{self.collection.name}'],
                                    'Permission': ['aoss:CreateCollectionItems',
                                                   'aoss:DeleteCollectionItems',
                                                   'aoss:UpdateCollectionItems',
                                                   'aoss:DescribeCollectionItems'],
                                    'ResourceType': 'collection'},
                                   {'Resource': [f'index/{self.collection.name}/*'],
                                    'Permission': ['aoss:CreateIndex',
                                                   'aoss:DeleteIndex',
                                                   'aoss:UpdateIndex',
                                                   'aoss:DescribeIndex',
                                                   'aoss:ReadDocument',
                                                   'aoss:WriteDocument'],
                                    'ResourceType': 'index'}],
                              'Principal': [kb_role.role_arn, index_lambda_role.role_arn, ],
                              'Description': 'Agent data policy'}], separators=(',', ':'))
        data_access_policy = os_serverless.CfnAccessPolicy(scope=self,
                                                           id='DataAccessPolicy',
                                                           name='assistant-col-access-policy',
                                                           type='data',
                                                           policy=policy)
        self.collection.add_dependency(data_access_policy)

        # Give permissions to the Lambda Role to execute the AWS API operations
        index_lambda_role.add_to_policy(iam.PolicyStatement(sid='IndexCreationLambdaAccessPolicy',
                                                            effect=iam.Effect.ALLOW,
                                                            resources=[self.collection.attr_arn],
                                                            actions=['aoss:APIAccessAll']))

        # Create the knowledge base in the collection using the provided FM model & role
        self.knowledge_base = bedrock.CfnKnowledgeBase(scope=self,
                                                       id='AgentKB',
                                                       name='HotelDataKB',
                                                       role_arn=kb_role.role_arn,
                                                       knowledge_base_configuration={'type': 'VECTOR',
                                                                                     'vectorKnowledgeBaseConfiguration': {
                                                                                         'embeddingModelArn': embeddings_model_arn}},
                                                       storage_configuration={'type': 'OPENSEARCH_SERVERLESS',
                                                                              'opensearchServerlessConfiguration': {
                                                                                  'collectionArn': self.collection.attr_arn,
                                                                                  'vectorIndexName': 'bedrock-knowledge-base-default-index',
                                                                                  'fieldMapping': {
                                                                                      'metadataField': 'AMAZON_BEDROCK_METADATA',
                                                                                      'textField': 'AMAZON_BEDROCK_TEXT_CHUNK',
                                                                                      'vectorField': 'bedrock-knowledge-base-default-vector'
                                                                                  }}})
        self.knowledge_base.node.add_dependency(index_creator)
        # Create the data source; we could also define the chunking strategy, but let's leave its default values
        self.data_source = bedrock.CfnDataSource(scope=self,
                                                 id='AgentKBDataSource',
                                                 name='HotelDataS3Source',
                                                 knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
                                                 data_source_configuration={'s3Configuration':
                                                                                {'bucketArn': self.bucket.bucket_arn},
                                                                            'type': 'S3'},
                                                 data_deletion_policy='RETAIN')

        # This lambda will take care of issuing an update command on the Knowledge Base if files
        # area added to/removed from the S3 bucket
        kb_sync_lambda = lambda_.DockerImageFunction(scope=self,
                                                     id='SyncKB',
                                                     code=lambda_.DockerImageCode.from_image_asset(
                                                         directory='lambda/kb_sync',
                                                         platform=lambda_platform),
                                                     architecture=lambda_architecture,
                                                     environment={'KNOWLEDGE_BASE_ID':
                                                                      self.knowledge_base.attr_knowledge_base_id,
                                                                  'DATA_SOURCE_ID':
                                                                      self.data_source.attr_data_source_id},
                                                     role=kb_lambda_role)
        kb_lambda_role.add_to_policy(iam.PolicyStatement(sid='SyncKBStatement',
                                                         effect=iam.Effect.ALLOW,
                                                         resources=[self.knowledge_base.attr_knowledge_base_arn],
                                                         actions=['bedrock:StartIngestionJob']))
        # Create the EventBridge rule so that the lambda is started when a
        # file is added to/removed from the S3 bucket
        self.bucket.add_event_notification(s3.EventType.OBJECT_CREATED, s3n.LambdaDestination(kb_sync_lambda))
        self.bucket.add_event_notification(s3.EventType.OBJECT_REMOVED, s3n.LambdaDestination(kb_sync_lambda))

        # Add an explicit dependency on the lambda, so that the bucket
        # deployment is started after the lambda is in place
        bucket_deployment.node.add_dependency(kb_sync_lambda)

        # Finally, create the Bedrock Agent for this knowledge base
        agent_model_arn = bedrock.FoundationModel.from_foundation_model_id(
            scope=self,
            _id='AgentModel',
            foundation_model_id=bedrock.FoundationModelIdentifier(agent_model_id)).model_arn
        agent_role.add_to_policy(iam.PolicyStatement(sid='InvokeModelStatement',
                                                     effect=iam.Effect.ALLOW,
                                                     resources=[agent_model_arn],
                                                     actions=['bedrock:InvokeModel']))
        agent_role.add_to_policy(iam.PolicyStatement(sid='RetrieveKBStatement',
                                                     effect=iam.Effect.ALLOW,
                                                     resources=[self.knowledge_base.attr_knowledge_base_arn],
                                                     actions=['bedrock:Retrieve']))
        self.agent = bedrock.CfnAgent(scope=self,
                                      id='GenAIAgent',
                                      agent_name='genai-assistant-agent',
                                      instruction=agent_instructions,
                                      agent_resource_role_arn=agent_role.role_arn,
                                      foundation_model=agent_model_id,
                                      knowledge_bases=[{'description': 'Main knowledge base',
                                                        'knowledgeBaseId': self.knowledge_base.attr_knowledge_base_id}])
        self.agent_alias = bedrock.CfnAgentAlias(scope=self,
                                                 id='GenAIAgentAlias',
                                                 agent_alias_name=agent_alias_name,
                                                 agent_id=self.agent.attr_agent_id)

        # Create the Bedrock Prompt Flow & grant it the appropriate IAM permissions
        self.flow = bedrock.CfnFlow(scope=self,
                                    id='GenAIPromptFlow',
                                    execution_role_arn=flow_role.role_arn,
                                    name='genai-assistant-prompt-flow',
                                    definition=get_flow_definition(knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
                                                                   definition_file=flow_definition))
        self.flow_version = bedrock.CfnFlowVersion(scope=self,
                                                   id='GenAIPromptFlowVersion',
                                                   flow_arn=self.flow.attr_arn)
        routing = [bedrock.CfnFlowAlias.FlowAliasRoutingConfigurationListItemProperty(flow_version=self.flow_version.attr_version)]
        self.flow_alias = bedrock.CfnFlowAlias(scope=self,
                                               flow_arn=self.flow.attr_arn,
                                               name='HotelGenAI-Production',
                                               id='GenAIPromptFlowAlias',
                                               routing_configuration=routing)
        flow_role.add_to_policy(iam.PolicyStatement(sid='AmazonBedrockFlowsGetFlowPolicyHotelGenAI',
                                                    effect=iam.Effect.ALLOW,
                                                    resources=[self.flow.attr_arn],
                                                    actions=['bedrock:GetFlow']))
        flow_role.add_to_policy(iam.PolicyStatement(sid='AmazonBedrockFlowsInvokeAgentPolicyHotelGenAI',
                                                    effect=iam.Effect.ALLOW,
                                                    resources=[self.agent.attr_agent_arn],
                                                    actions=['bedrock:InvokeAgent']))
        flow_role.add_to_policy(iam.PolicyStatement(sid='AmazonBedrockFlowsInvokeAgentPolicyHotelGenAI',
                                                    effect=iam.Effect.ALLOW,
                                                    resources=[self.agent.attr_agent_arn],
                                                    actions=['bedrock:InvokeAgent']))
        flow_role.add_to_policy(iam.PolicyStatement(sid='AmazonBedrockFlowRetrieveKnowledgeBasePolicyHotelGenAI',
                                                    effect=iam.Effect.ALLOW,
                                                    resources=[self.knowledge_base.attr_knowledge_base_arn],
                                                    actions=['bedrock:Retrieve', 'bedrock:RetrieveAndGenerate']))
        flow_role.add_to_policy(iam.PolicyStatement(sid='AmazonBedrockFlowsInvokeFoundationModelPolicyHotelGenAI',
                                                    effect=iam.Effect.ALLOW,
                                                    resources=[text_model_arn],
                                                    actions=['bedrock:InvokeModel']))

        # Declare the stack outputs
        aws_cdk.CfnOutput(scope=self, id='collection_id', value=self.collection.logical_id)
        aws_cdk.CfnOutput(scope=self, id='kb_bucket', value=self.bucket.bucket_name)
        aws_cdk.CfnOutput(scope=self, id='kb_id', value=self.knowledge_base.attr_knowledge_base_id)
        aws_cdk.CfnOutput(scope=self, id='agent_name', value=self.agent.agent_name)
