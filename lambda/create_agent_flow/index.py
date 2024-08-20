#!/usr/bin/env python3

import boto3
import cfnresponse


def handle_event(event, context):
    """
    Handle the Custom Resource events from CDK.

    In practice, this code will create an Agent Flow based on the parameters passed from the CDK CustomResource.

    This lambda expects that all the required resources are already created.

    Parameters
    ----------
    event : Event information
    """
    agent = boto3.client('bedrock-agent')
    # Handle the different actions required by the module
    if event['RequestType'] == 'Create':
        # Get Flow details
        request_id = event['RequestId']
        definition = event['ResourceProperties'].get('definition')
        description = event['ResourceProperties'].get('description')
        execution_role_arn = event['ResourceProperties'].get('execution_role_arn')
        name = event['ResourceProperties'].get('name')
        tags = event['ResourceProperties'].get('tags')
        alias = event['ResourceProperties'].get('alias')

        # Create the flow and, optionally, the alias
        response = agent.create_flow(clientToken=request_id,
                                     name=name,
                                     description=description,
                                     executionRoleArn=execution_role_arn,
                                     definition=definition,
                                     tags=tags)
        flow_id = response.get('id')
        agent.prepare_flow(flowIdentifier=flow_id)
        response = agent.create_flow_version(clientToken=f'{request_id}-version',
                                             flowIdentifier=flow_id)
        agent.create_flow_alias(clientToken=f'{request_id}-alias',
                                flowIdentifier=flow_id,
                                name=alias,
                                routingConfiguration=[{'flowVersion': response['version']}],
                                tags=tags)

        cfnresponse.send(event, context, cfnresponse.SUCCESS,
                         responseData={'flowId': flow_id},
                         physicalResourceId=flow_id)
    elif event['RequestType'] == 'Delete':
        flow_id = event['PhysicalResourceId']
        agent.delete_flow(flowIdentifier=flow_id)
        cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData={}, physicalResourceId=flow_id)

