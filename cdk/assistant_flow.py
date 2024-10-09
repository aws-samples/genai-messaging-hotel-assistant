import aws_cdk
from pathlib import Path
from constructs import Construct
from aws_cdk import (aws_bedrock as bedrock,
                     aws_iam as iam,
                     aws_lambda as lambda_)
from cdk.utils import get_flow_definition


class AssistantFlow(Construct):
    def __init__(self,
                 scope: Construct,
                 construct_id: str,
                 flow_definition: Path,
                 knowledge_base: bedrock.CfnKnowledgeBase,
                 spa_availability_lambda: lambda_.FunctionBase):
        """
        Create the Bedrock Prompt Flow & grant it the appropriate IAM permissions
        """

        super().__init__(scope, construct_id)
        # Create the flow and grant it permissions to execute the full flow
        text_model_arn = bedrock.FoundationModel.from_foundation_model_id(
            scope=self,
            _id='TextModel',
            foundation_model_id=bedrock.FoundationModelIdentifier('anthropic.claude-3-haiku-20240307-v1:0')).model_arn
        flow_role = iam.Role(scope=self,
                             id='PromptFlowRole',
                             assumed_by=iam.ServicePrincipal('bedrock.amazonaws.com'))
        self.flow = bedrock.CfnFlow(scope=self,
                                    id='GenAIPromptFlow',
                                    execution_role_arn=flow_role.role_arn,
                                    name='hotel-assistant-prompt-flow',
                                    definition=get_flow_definition(definition_file=flow_definition,
                                                                   knowledge_base_id=knowledge_base.attr_knowledge_base_id,
                                                                   spa_availability_lambda_arn=spa_availability_lambda.function_arn))
        self.flow_version = bedrock.CfnFlowVersion(scope=self,
                                                   id='GenAIPromptFlowVersion',
                                                   flow_arn=self.flow.attr_arn)
        routing = [bedrock.CfnFlowAlias.FlowAliasRoutingConfigurationListItemProperty(
            flow_version=self.flow_version.attr_version)]
        self.flow_alias = bedrock.CfnFlowAlias(scope=self,
                                               flow_arn=self.flow.attr_arn,
                                               name='HotelGenAI-Production',
                                               id='GenAIPromptFlowAlias',
                                               routing_configuration=routing)
        flow_role.add_to_policy(iam.PolicyStatement(sid='AmazonBedrockFlowsGetFlowPolicyHotelGenAI',
                                                    effect=iam.Effect.ALLOW,
                                                    resources=[self.flow.attr_arn],
                                                    actions=['bedrock:GetFlow']))
        flow_role.add_to_policy(iam.PolicyStatement(sid='AmazonBedrockFlowRetrieveKnowledgeBasePolicyHotelGenAI',
                                                    effect=iam.Effect.ALLOW,
                                                    resources=[knowledge_base.attr_knowledge_base_arn],
                                                    actions=['bedrock:Retrieve', 'bedrock:RetrieveAndGenerate']))
        flow_role.add_to_policy(iam.PolicyStatement(sid='AmazonBedrockFlowsInvokeFoundationModelPolicyHotelGenAI',
                                                    effect=iam.Effect.ALLOW,
                                                    resources=[text_model_arn],
                                                    actions=['bedrock:InvokeModel']))
        flow_role.add_to_policy(iam.PolicyStatement(sid='AmazonBedrockFlowsInvokeSpaAvilabilityLambda',
                                                    effect=iam.Effect.ALLOW,
                                                    resources=[spa_availability_lambda.function_arn],
                                                    actions=['lambda:InvokeFunction']))

        # Declare the stack outputs
        aws_cdk.CfnOutput(scope=self, id='AssistantFlow', value=self.flow.attr_arn)