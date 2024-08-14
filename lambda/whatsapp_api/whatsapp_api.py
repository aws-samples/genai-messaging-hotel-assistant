import os
import json
import boto3
import httpx
import asyncio
import logging
from whatsapp.message import TextMessage
from whatsapp.application import WhatsAppApplication
from conversation.handler import start_new_conversation

# Get global objects we'll use throughout the code
sm = boto3.client('secretsmanager')
WHATSAPP_API_KEY = sm.get_secret_value(SecretId=os.environ.get('SECRET_NAME')).get('SecretString', '__INVALID__')
WHATSAPP_API_VERIFY_TOKEN = sm.get_secret_value(SecretId=os.environ.get('WHATSAPP_VERIFY_TOKEN_NAME')).get(
    'SecretString', '__INVALID__')


async def main(event):
    async with httpx.AsyncClient() as client:
        wa = WhatsAppApplication(whatsapp_token=WHATSAPP_API_KEY, client=client)
        # Handle the different cases
        match event['requestContext']['httpMethod']:
            case 'GET':
                return wa.handle_subscription(event['queryStringParameters'], WHATSAPP_API_VERIFY_TOKEN)
            case 'POST':
                # Get the text message and the sender phone number
                payload = json.loads(event['body'])
                # Handle new conversation requests separately from regular messages
                if payload.get('object') == 'new_conversation_request':
                    recipient_id = payload.get('recipient_id')
                    recipient_name = payload.get('recipient_name')
                    sender_id = payload.get('sender_id')
                    await start_new_conversation(wa,
                                                 sender_id=sender_id,
                                                 recipient_id=recipient_id,
                                                 recipient_name=recipient_name)

                    return {'statusCode': 200, 'body': 'Conversation started with contact', 'isBase64Encoded': False}
                elif payload.get('object') == 'whatsapp_business_account':
                    try:
                        messages = wa.parse_request(payload)
                    except ValueError:
                        return {'statusCode': 400, 'body': 'Bad request', 'isBase64Encoded': False}
                    responses = [await wa.send_msg(TextMessage(text=message.text,
                                                               sender_id=message.recipient_id,
                                                               recipient_id=message.sender_id))
                                 for message in messages]

                    if any([r.status_code != 200 for r in responses]):
                        return {'statusCode': 500, 'body': 'Internal Server error', 'isBase64Encoded': False}

                    return {'statusCode': 200, 'body': 'Replied to the contact', 'isBase64Encoded': False}
                else:
                    return {'statusCode': 400, 'body': 'Bad request', 'isBase64Encoded': False}


def handler(event, _):
    logging.error(event)

    return asyncio.run(main(event))
