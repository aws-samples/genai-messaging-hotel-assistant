import os
import json
import boto3
import httpx
import asyncio
import logging

# Get global objects we'll use throughout the code
sm = boto3.client('secretsmanager')
WHATSAPP_API_KEY = sm.get_secret_value(SecretId=os.environ.get('SECRET_NAME')).get('SecretString', '__INVALID__')
WHATSAPP_API_VERIFY_TOKEN = sm.get_secret_value(SecretId=os.environ.get('WHATSAPP_VERIFY_TOKEN_NAME')).get('SecretString', '__INVALID__')


async def send_msg(bot_phone_number: str, recipient_phone_number: str, msg_text: str, token: str):
    """
    Send a text message to the given WhatsApp ID
    """
    async with httpx.AsyncClient() as client:
        return await client.post(f'https://graph.facebook.com/v20.0/{bot_phone_number}/messages',
                                 headers={'Authorization': f'Bearer {token}',
                                          'Content-Type': 'application/json'},
                                 data={'messaging_product': 'whatsapp',
                                       'to': recipient_phone_number,
                                       'type': 'text',
                                       'text': json.dumps({'preview_url': True,
                                                           'body': msg_text})})


async def main(event):
    # Handle the different cases
    match event['requestContext']['httpMethod']:
        case 'GET':
            # Used for message susbscription
            match event['queryStringParameters']['hub.mode']:
                case 'subscribe':
                    verify_token = event['queryStringParameters']['hub.verify_token']
                    if verify_token == WHATSAPP_API_VERIFY_TOKEN:
                        print('Subscription correct!!')
                        return {'statusCode': 200,
                                'body': int(event['queryStringParameters']['hub.challenge']),
                                'isBase64Encoded': False}
                    else:
                        print(f'Subscribe called with wrong verify token "{verify_token}"')
                        return {'statusCode': 403,
                                'body': 'Error, wrong validation token',
                                'isBase64Encoded': False}
                case _:
                    print(f'Provided wrong mode')
                    return {'statusCode': 403,
                            'body': 'Error, wrong mode',
                            'isBase64Encoded': False}
        case 'POST':
            # Get the text message and the sender phone number
            body = json.loads(event['body'])
            responses = []
            for entry in body['entry']:
                for change in entry['changes']:
                    wa_id = change['value']['contacts'][0]['wa_id']
                    bot_phone_number = change['value']['metadata']['phone_number_id']
                    for message in change['value']['messages']:
                        text = message['text']['body']
                        response = await send_msg(bot_phone_number, wa_id, text, WHATSAPP_API_KEY)
                        responses.append(response)
                        print(response)

            if any([r.status_code != 200 for r in responses]):
                return {'statusCode': 500,
                        'body': 'Internal Server error',
                        'isBase64Encoded': False}

            return {'statusCode': 200,
                    'body': 'Message sent!',
                    'isBase64Encoded': False}


def handler(event, _):
    logging.error(event)

    return asyncio.run(main(event))
