#!/usr/bin/env python3

import boto3
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder


async def set_webhook(telegram_api_key: str, webhook_uri: str):
    """
    Set the Webhook URI for a particular Telegram bot to the given one
    """
    telegram_app = (ApplicationBuilder()
                    .updater(None)
                    .token(telegram_api_key)
                    .read_timeout(7)
                    .get_updates_read_timeout(42)
                    .build())
    info = await telegram_app.bot.get_webhook_info()
    if info.url == webhook_uri:
        print(f'Webhook URL in Telegram ({info.url}) is correct')
    else:
        print(f'Updating Telegram Webhook URL to {webhook_uri}')
        await telegram_app.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(2)
        await telegram_app.bot.setWebhook(webhook_uri)

    if info.last_error_date is None:
        print('\tNo last known errors')
    else:
        print(f'\tLast error: {info.last_error_date} - {info.last_error_message}')


def handle_event(event, context):
    """
    Handle the Custom Resource events from CDK.

    In practice, it will only create the index in the Collection provided in the event ResourceProperties

    This lambda expects the Collection to be created already, but will wait for it
    to be available if status is 'CREATING'

    Parameters
    ----------
    event : Event information
    """
    # Ignore all non-create events
    if event['RequestType'] != 'Create':
        return

    # Get the operational params
    secret_name = event.get('ResourceProperties', {}).get('secret_name')
    webhook_uri = event.get('ResourceProperties', {}).get('webhook_uri')
    print(webhook_uri)
    sm = boto3.client('secretsmanager')
    telegram_api_key = sm.get_secret_value(SecretId=secret_name).get('SecretString', '__INVALID__')

    # Set the Webhook for the bot in Telegram
    asyncio.run(set_webhook(telegram_api_key=telegram_api_key, webhook_uri=webhook_uri))
