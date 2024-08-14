from datetime import date
from bookings.guests import MemberType
from whatsapp.application import WhatsAppApplication
from . import agents_runtime, AGENT_ID, AGENT_ALIAS_ID
from bookings.sample import get_reservations_by_chat_id
from whatsapp.message import ImageMessage, LocationMessage, TextMessage


async def start_new_conversation(app: WhatsAppApplication, sender_id: str, recipient_id: str, recipient_name: str):
    """
    Introduce ourselves and present reservation info on new conversation request message.
    """
    # Invalidate any previous Bedrock Agents session
    agents_runtime.invoke_agent(agentId=AGENT_ID,
                                agentAliasId=AGENT_ALIAS_ID,
                                sessionId=f'{recipient_id}',
                                inputText='Hi',
                                endSession=True)
    # Get the ID of the user who sent the message
    user_reservations = get_reservations_by_chat_id(recipient_id,
                                                    fallback_name=recipient_name)
    if len(user_reservations) == 0:
        await app.send_msg(TextMessage(sender_id=sender_id,
                                       recipient_id=recipient_id,
                                       text=f'Thanks for getting in touch with me, '
                                            f'{recipient_name}. I cannot find any '
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
    msg += f'Here are the details of your reservation, {recipient_name}:\n'
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
        await app.send_msg(TextMessage(sender_id=sender_id,
                                       recipient_id=recipient_id,
                                       text=msg))
    else:
        await app.send_msg(ImageMessage(sender_id=sender_id,
                                        recipient_id=recipient_id,
                                        media=reservation.hotel.poster,
                                        media_name='poster.jpg',
                                        caption=msg))

    # Send the hotel location as a reply to the main message
    await app.send_msg(LocationMessage(sender_id=sender_id,
                                       recipient_id=recipient_id,
                                       latitude=reservation.hotel.location.lat,
                                       longitude=reservation.hotel.location.lon,
                                       name=f'{reservation.hotel.name} location',
                                       address=reservation.hotel.location.address))

    # If the user is a gold member or above, also send the room key and a welcome message
    if len([g for g in reservation.guests if g.member_level >= MemberType.GOLD]) > 0:
        msg = (f'Your room is number {reservation.room_number}, you can use this digital key '
               f'in your smartphone or smartwatch to enter your room.\n'
               f'You can also get a physical key in the hotel reception.\n'
               f'Since you are a distinguished member of our fidelity program, our Director of Guest Experience will '
               f'meet you in the hotel lobby and solve any doubts you might have.')

        # Send the room key file to the customer
        await app.send_msg(ImageMessage(sender_id=sender_id,
                                        recipient_id=recipient_id,
                                        media=reservation.digital_room_key,
                                        media_name=f'Room {reservation.room_number}.png',
                                        caption=msg))
