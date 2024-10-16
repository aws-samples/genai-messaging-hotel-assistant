import os
import json
import boto3
import httpx
import asyncio
import logging
from whatsapp.contact import Contact
from whatsapp.message import TextMessage
from whatsapp.application import WhatsAppApplication
from conversation.handler import start_new_conversation, respond_with_flow

# Get global objects we'll use throughout the code
sm = boto3.client('secretsmanager')
WHATSAPP_ID = os.environ.get('WHATSAPP_ID', '__INVALID__')
WHATSAPP_API_KEY = sm.get_secret_value(SecretId=os.environ.get('WHATSAPP_API_KEY_NAME')).get('SecretString',
                                                                                             '__INVALID__')
WHATSAPP_API_VERIFY_TOKEN = sm.get_secret_value(SecretId=os.environ.get('WHATSAPP_VERIFY_TOKEN_NAME')).get(
    'SecretString', '__INVALID__')


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
                    print(payload)
                    try:
                        updates = wa.parse_request(payload)
                    except ValueError:
                        return {'statusCode': 400, 'body': 'Bad request', 'isBase64Encoded': False}
                    for update in updates:
                        if not isinstance(update.msg, TextMessage):
                            logging.error(f'Cannot parse message of type {type(update.msg)}, skipping')
                        await respond_with_flow(update.msg, app=wa, conversation=update.conversation)

                    return {'statusCode': 200, 'body': 'Replied to the contact', 'isBase64Encoded': False}
                else:
                    return {'statusCode': 400, 'body': 'Bad request', 'isBase64Encoded': False}


def handler(event, _):
    return asyncio.run(main(event))
