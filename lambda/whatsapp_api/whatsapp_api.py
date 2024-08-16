import os
import json
import boto3
import httpx
import asyncio
from whatsapp.application import WhatsAppApplication
from conversation.handler import start_new_conversation, respond_with_agent

# Get global objects we'll use throughout the code
sm = boto3.client('secretsmanager')
WHATSAPP_ID = os.environ.get('WHATSAPP_ID', '__INVALID__')
WHATSAPP_API_KEY = sm.get_secret_value(SecretId=os.environ.get('SECRET_NAME')).get('SecretString', '__INVALID__')
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
                    for msg in messages:
                        await respond_with_agent(msg, app=wa, sender_id=msg.recipient_id, recipient_id=msg.sender_id)

                    return {'statusCode': 200, 'body': 'Replied to the contact', 'isBase64Encoded': False}
                else:
                    return {'statusCode': 400, 'body': 'Bad request', 'isBase64Encoded': False}


def handler(event, _):
    return asyncio.run(main(event))
