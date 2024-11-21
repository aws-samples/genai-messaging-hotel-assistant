import os
import json
import boto3
import asyncio
import logging
from datetime import date
import telegram.constants
from bookings.guests import MemberType
from telegram.ext._contexttypes import ContextTypes
from bookings.sample import get_reservations_by_chat_id, get_chatbot_session_attrs
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters, \
    CallbackContext
from telegram import Update, InputMediaDocument, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup

# Get global objects we'll use throughout the code
sm = boto3.client('secretsmanager')
lambda_ = boto3.client('lambda')
TELEGRAM_API_KEY = sm.get_secret_value(SecretId=os.environ.get('SECRET_NAME')).get('SecretString', '__INVALID__')
agents_runtime = boto3.client('bedrock-agent-runtime')
FLOW_ID = os.environ.get('FLOW_ID', '__INVALID__')
FLOW_ALIAS_ID = os.environ.get('FLOW_ALIAS_ID', '__INVALID__')
RESERVATIONS_LAMBDA_ARN = os.environ.get('RESERVATIONS_LAMBDA_ARN', '__INVALID__')


async def handle_telegram_msg(telegram_app: telegram.ext.Application, body: str):
    """
    Handle incoming Telegram messages by parsing the request body and processing the update.

    Args:
        telegram_app: The Telegram application instance
        body: The raw request body containing the Telegram update data

    Returns:
        The result of processing the Telegram update

    Raises:
        Returns 400 status code if request body cannot be parsed
    """
    try:
        req = json.loads(body)
    except BaseException as e:
        logging.exception(e)
        return {'statusCode': 400,
                'body': json.dumps('Bad request')}
    update = Update.de_json(req, telegram_app.bot)

    return await telegram_app.process_update(update)


# Example handler
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Introduce ourselves and present reservation info on /start message."""
    # Set the typing indicator
    await update.message.chat.send_chat_action(telegram.constants.ChatAction.TYPING)

    # Get the ID of the user who sent the message
    user_reservations = get_reservations_by_chat_id(name=update.message.from_user.first_name)
    if len(user_reservations) == 0:
        await update.message.reply_text(f'Thanks for getting in touch with me, '
                                        f'{update.message.from_user.first_name}. I cannot find any '
                                        'reservations for you; you can book a room in our website.')
        return

    # Get the next reservation
    reservation = sorted(user_reservations, key=lambda r: r.start_date)[0]
    hotel_reference = reservation.hotel.name
    if reservation.hotel.url is not None:
        hotel_reference = f'<a href="{reservation.hotel.url}">{hotel_reference}</a>'
    msg = f"<b>We'll be expecting you in {hotel_reference} on {reservation.start_date}</b>\n\n"
    if reservation.start_date == date.today():
        msg = f'<b>Your stay in {hotel_reference} starts today</b>\n\n'

    # Send basic reservation details
    minors = [g for g in reservation.guests if g.is_minor]
    adults = [g for g in reservation.guests if not g.is_minor]
    msg += f'Here are the details of your reservation, {update.message.from_user.first_name}:\n'
    msg += f'  • {(reservation.end_date - reservation.start_date).days} nights\n'
    msg += (f'  • {len(adults)} adult{"s" if len(adults) > 1 else ""} '
            f'({", ".join([g.name for g in reservation.guests if not g.is_minor])})\n')
    match len(minors):
        case 1:
            msg += f'  • 1 minor ({", ".join([g.name for g in reservation.guests if g.is_minor])})\n'
        case n if n > 1:
            msg += f'  • {n} minors ({", ".join([g.name for g in reservation.guests if g.is_minor])})\n'
    # Send the main message
    if reservation.hotel.poster is None:
        main_msg = await update.message.chat.send_message(msg, parse_mode='HTML',
                                                          disable_web_page_preview=True)
    else:
        msgs = await update.message.chat.send_media_group([InputMediaPhoto(reservation.hotel.poster,
                                                                           filename='poster.jpg')],
                                                          caption=msg, parse_mode='HTML')
        main_msg = msgs[0]

    # Send the hotel location as a reply to the main message
    await update.message.chat.send_location(longitude=reservation.hotel.location.lon,
                                            latitude=reservation.hotel.location.lat,
                                            reply_to_message_id=main_msg.message_id,
                                            horizontal_accuracy=0)

    # If the user is a gold member or above, also send the room key and a welcome message
    if len([g for g in reservation.guests if g.member_level >= MemberType.GOLD]) > 0:
        msg = (f'Your room is number {reservation.room_number}, you can use this digital key '
               f'in your smartphone or smartwatch to enter your room.\n'
               f'You can also get a physical key in the hotel reception.\n'
               f'Since you are a distinguished member of our fidelity program, our Director of Guest Experience will '
               f'meet you in the hotel lobby and solve any doubts you might have.')

        # Send the room key file to the customer
        await update.message.chat.send_media_group([InputMediaDocument(reservation.digital_room_key,
                                                                       filename=f'Room {reservation.room_number}'
                                                                                f'.png')],
                                                   caption=msg,
                                                   parse_mode='HTML',
                                                   reply_to_message_id=main_msg.message_id)


async def respond_callback(update: Update, _: CallbackContext) -> None:
    """
    Respond to message callbacks.

    We will typically get these when the user is answering to Spa booking slot requests.
    Please note that this method does not check for the validity of the provided timeslot.
    """
    time_slot = update.callback_query.data
    recipient_id = f'{update.callback_query.from_user.id}'
    payload = json.dumps({'request_type': 'booking_request',
                          'time_slot': time_slot,
                          'customer_id': recipient_id})
    response = lambda_.invoke(FunctionName=RESERVATIONS_LAMBDA_ARN, Payload=payload.encode())
    if response['StatusCode'] == 200:
        # Try to remove the inline keyboard so that the user can only book a single Spa slot,
        # this is not guaranteed to work
        await update.callback_query.message.edit_reply_markup(None)
        await update.callback_query.message.edit_text(f'[This mesage contained the available Spa slots]')
        await update.callback_query.message.reply_text(f'Thank you. Your reservation for the Spa on '
                                                       f'{time_slot} is now confirmed.')
    else:
        await update.callback_query.message.reply_text('Sorry, there was an error booking your slot. Please get in '
                                                       'touch with the hotel reception to book your Spa session.')
        raise RuntimeError(response['FunctionError'])

    return


async def respond_with_flow(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Process a normal user message using the given Bedrock Agent
    """
    # Set the typing indicator, then invoke agent and return its response
    await update.message.chat.send_chat_action(telegram.constants.ChatAction.TYPING)

    # Get the session attributes. I guess I could send these only once, but since
    # the lambda is stateless I have no good way of knowing if I have already sent them
    details = get_chatbot_session_attrs(main_guest_name=update.message.from_user.first_name)

    for _ in range(2):
        response = agents_runtime.invoke_flow(flowAliasIdentifier=FLOW_ALIAS_ID,
                                              flowIdentifier=FLOW_ID,
                                              inputs=[{'content': {'document': {'query': update.message.text,
                                                                                'reservation_details': json.dumps(
                                                                                    details)}},
                                                       'nodeName': 'FlowInputNode',
                                                       'nodeOutputName': 'document'}])
        completion = ''
        for event in response:
            if event == 'responseStream':
                for i in response[event]:
                    document = i.get('flowOutputEvent', {}).get('content', {}).get('document', {})
                    if isinstance(document, dict):
                        if document.get('response_type', '') == 'spa_availability':
                            slots = document.get('available_slots', [])
                            day = document.get('date')
                            if len(slots) == 0:
                                completion += (f'There are no available Spa slots for the {day}, please contact '
                                               'the hotel reception to check other options.')
                            else:
                                keyboard = [[InlineKeyboardButton(slot, callback_data=slot)] for slot in slots]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                await update.message.reply_text('<b>Please, choose your desired Spa slot:</b>',
                                                                parse_mode='HTML',
                                                                reply_markup=reply_markup)

                                return
                        else:
                            print(f'ERROR: Cannot interpret backend message: "{document}"')
                    elif isinstance(document, str):
                        completion += document
                    else:
                        print(f'Cannot intepret output from flow "{document}"')

        await update.message.chat.send_message(completion, parse_mode='HTML', disable_web_page_preview=False)
        return

    await update.message.chat.send_message("I'm sorry, I cannot find that information. You can find out more "
                                           "about this in the hotel reception.")


async def main(event):
    # Initialize python telegram bot
    telegram_app = (ApplicationBuilder()
                    .updater(None)
                    .token(TELEGRAM_API_KEY)
                    .read_timeout(7)
                    .get_updates_read_timeout(42)
                    .build())
    await telegram_app.initialize()
    # Set the Telegram handlers for the commands and regular text messages
    telegram_app.add_handler(CommandHandler('start', start))
    telegram_app.add_handler(CallbackQueryHandler(respond_callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, respond_with_flow))

    # Handle the different cases
    match event['requestContext']['httpMethod']:
        case 'POST':
            return {'statusCode': 200,
                    'body': await handle_telegram_msg(telegram_app, event['body'])}

    return {'statusCode': 400, 'body': json.dumps('Bad request')}


def handler(event, _):
    return asyncio.run(main(event))
