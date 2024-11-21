import os
import json
import boto3
import httpx
import asyncio
import logging
from whatsapp.contact import Contact
from whatsapp.application import WhatsAppApplication
from whatsapp.message import InteractiveListReplyMessage, TextMessage
from conversation.handler import start_new_conversation, respond_with_flow

# Get global objects we'll use throughout the code
sm = boto3.client('secretsmanager')
lambda_ = boto3.client('lambda')
WHATSAPP_ID = os.environ.get('WHATSAPP_ID', '__INVALID__')
WHATSAPP_API_KEY = sm.get_secret_value(SecretId=os.environ.get('WHATSAPP_API_KEY_NAME')).get('SecretString',
                                                                                             '__INVALID__')
WHATSAPP_API_VERIFY_TOKEN = sm.get_secret_value(SecretId=os.environ.get('WHATSAPP_VERIFY_TOKEN_NAME')).get(
    'SecretString', '__INVALID__')
RESERVATIONS_LAMBDA_ARN = os.environ.get('RESERVATIONS_LAMBDA_ARN', '__INVALID__')


async def main(event):
    async with httpx.AsyncClient() as client:
        wa = WhatsAppApplication(whatsapp_token=WHATSAPP_API_KEY, whatsapp_id=WHATSAPP_ID, client=client)
        # Handle the different cases
        match event['requestContext']['httpMethod']:
            case 'GET':
                return wa.handle_subscription(event['queryStringParameters'], WHATSAPP_API_VERIFY_TOKEN)
            case 'POST':
                # Get the text message and the sender phone number
                payload = json.loads(event['body'])
                if payload.get('object') == 'new_conversation_request':
                    # Handle new conversation requests. This is user-initiated and not part of
                    # the normal WhatsApp WebHook functionality
                    recipient_id = payload.get('recipient_id')
                    recipient_name = payload.get('recipient_name')
                    await start_new_conversation(wa,
                                                 conversation=wa.get_conversations(
                                                     contacts={Contact(whatsapp_id=recipient_id, name=recipient_name)}))

                    return {'statusCode': 200, 'body': 'Conversation started with contact', 'isBase64Encoded': False}
                elif payload.get('object') == 'whatsapp_business_account':
                    # Handle WhatsApp webhook requests
                    try:
                        updates = wa.parse_request(payload)
                    except NotImplementedError:
                        return {'statusCode': 200, 'body': 'Ignoring unsupported message type',
                                'isBase64Encoded': False}
                    except ValueError:
                        return {'statusCode': 400, 'body': 'Bad request', 'isBase64Encoded': False}
                    for update in updates:
                        if isinstance(update.msg, TextMessage):
                            await respond_with_flow(update.msg, app=wa, conversation=update.conversation)
                        elif isinstance(update.msg, InteractiveListReplyMessage):
                            recipient_id = (update.conversation.participants - {wa.contact}).pop().whatsapp_id
                            time_slot = update.msg.reply.id
                            payload = json.dumps({'request_type': 'booking_request',
                                                  'time_slot': time_slot,
                                                  'customer_id': recipient_id})
                            response = lambda_.invoke(FunctionName=RESERVATIONS_LAMBDA_ARN, Payload=payload.encode())
                            if response['StatusCode'] == 200:
                                await wa.send_msg(TextMessage(text=f'Thank you. Your reservation for the Spa on '
                                                                   f'{time_slot} is now confirmed.'),
                                                  conversation=update.conversation)
                            else:
                                await wa.send_msg(TextMessage(text='Sorry, there was an error booking your slot. '
                                                                   'Please get in touch with the hotel reception to '
                                                                   'book your Spa session.'),
                                                  conversation=update.conversation)
                                raise RuntimeError(response['FunctionError'])
                        else:
                            logging.error(f'Cannot parse message of type {type(update.msg)}, skipping')

                    return {'statusCode': 200, 'body': 'Replied to the contact', 'isBase64Encoded': False}
                else:
                    return {'statusCode': 400, 'body': 'Bad request', 'isBase64Encoded': False}


def handler(event, _):
    return asyncio.run(main(event))
