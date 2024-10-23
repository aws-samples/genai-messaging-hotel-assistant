import json
from datetime import date
from bookings.guests import MemberType
from whatsapp.conversation import Conversation
from whatsapp.application import WhatsAppApplication
from . import agents_runtime, FLOW_ID, FLOW_ALIAS_ID
from bookings.sample import get_reservations_by_chat_id, get_chatbot_session_attrs
from whatsapp.message import ImageMessage, InteractiveListMessage, LocationMessage, Row, Section, TextMessage


async def start_new_conversation(app: WhatsAppApplication,
                                 conversation: Conversation) -> None:
    """
    Introduce ourselves and present reservation info on new conversation request message.
    """
    # Get the ID of the user who sent the message
    recipient = (conversation.participants - {app.contact}).pop()
    user_reservations = get_reservations_by_chat_id(name=recipient.name)
    if len(user_reservations) == 0:
        await app.send_msg(TextMessage(text=f'Thanks for getting in touch with me, '
                                            f'{recipient.name}. I cannot find any '
                                            'reservations for you; you can book a room in our website.'))
        return

    # Get the next reservation
    reservation = sorted(user_reservations, key=lambda r: r.start_date)[0]
    hotel_reference = reservation.hotel.name
    msg = f"*We'll be expecting you in {hotel_reference} on {reservation.start_date}*\n\n"
    if reservation.start_date == date.today():
        msg = f'*Your stay in {hotel_reference} starts today*\n\n'

    # Send basic reservation details
    minors = [g for g in reservation.guests if g.is_minor]
    adults = [g for g in reservation.guests if not g.is_minor]
    msg += f'Here are the details of your reservation, {recipient.name}:\n'
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
        await app.send_msg(TextMessage(text=msg),
                           conversation=conversation)
    else:
        await app.send_msg(ImageMessage(media=reservation.hotel.poster,
                                        media_name='poster.jpg',
                                        caption=msg),
                           conversation=conversation)

    # Send the hotel location as a reply to the main message
    await app.send_msg(LocationMessage(latitude=reservation.hotel.location.lat,
                                       longitude=reservation.hotel.location.lon,
                                       name=f'{reservation.hotel.name} location',
                                       address=reservation.hotel.location.address),
                       conversation=conversation)

    # If the user is a gold member or above, also send the room key and a welcome message
    if len([g for g in reservation.guests if g.member_level >= MemberType.GOLD]) > 0:
        msg = (f'Your room is number {reservation.room_number}, you can use this digital key '
               f'in your smartphone or smartwatch to enter your room.\n'
               f'You can also get a physical key in the hotel reception.\n'
               f'Since you are a distinguished member of our fidelity program, our Director of Guest Experience will '
               f'meet you in the hotel lobby and solve any doubts you might have.')

        # Send the room key file to the customer
        await app.send_msg(ImageMessage(media=reservation.digital_room_key,
                                        media_name=f'Room {reservation.room_number}.png',
                                        caption=msg),
                           conversation=conversation)


async def respond_with_flow(msg: TextMessage,
                            app: WhatsAppApplication,
                            conversation: Conversation) -> None:
    """
    Process a normal user message using the given Bedrock Agent
    """
    # Get the session attributes. I guess I could send these only once, but since
    # the lambda is stateless I have no good way of knowing if I have already sent them
    recipient = (conversation.participants - {app.contact}).pop()
    details = get_chatbot_session_attrs(main_guest_name=recipient.name)
    for _ in range(2):
        response_stream = agents_runtime.invoke_flow(flowAliasIdentifier=FLOW_ALIAS_ID,
                                                     flowIdentifier=FLOW_ID,
                                                     inputs=[{'content': {'document': json.dumps({'query': msg.text,
                                                                                                  'reservation_details': json.dumps(
                                                                                                      details)})},
                                                              'nodeName': 'FlowInputNode',
                                                              'nodeOutputName': 'document'}])
        msgs = []
        for event in response_stream:
            if event == 'responseStream':
                for i in response_stream['responseStream']:
                    if 'flowOutputEvent' not in i:
                        continue
                    document = i.get('flowOutputEvent', {}).get('content', {}).get('document', {})
                    if isinstance(document, dict):
                        if document.get('response_type', '') == 'spa_availability':
                            slots = document.get('available_slots', [])
                            day = document.get('date')
                            if len(slots) == 0:
                                msgs.append(TextMessage(text=f'There are no available Spa slots for the {day}, '
                                                             f'please contact the hotel reception to check '
                                                             f'other options.'))
                            else:
                                rows = [Row(id=slot, title=slot) for slot in slots]
                                msgs.append(InteractiveListMessage(header='Hotel Spa',
                                                                   body='Please, choose your desired Spa slot',
                                                                   button='Available slots',
                                                                   sections=[Section(title=f'{day}', rows=rows)]))
                        else:
                            print(f'ERROR: Cannot interpret backend message: "{document}"')
                    elif isinstance(document, str):
                        msgs.append(TextMessage(text=document))
                    else:
                        print(f'Cannot intepret output from flow "{document}"')

        for msg in msgs:
            await app.send_msg(msg, conversation=conversation)
        return

    await app.send_msg(TextMessage(text="I'm sorry, I cannot find that information. You can find out more "
                                        "about this in the hotel reception.",
                                   preview_links=True),
                       conversation=conversation)
