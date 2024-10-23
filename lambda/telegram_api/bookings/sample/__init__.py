from pathlib import Path
from random import randint
from datetime import date, timedelta
from bookings.hotels import Hotel, Location
from bookings.guests import Guest, MemberType
from bookings.reservations import Reservation

# Create some sample data
sample_hotel = Hotel(name='AnyCompany Luxury Resort',
                     location=Location(lon=-6.1609661, lat=36.3407887, address='Chiclana de la Frontera, Cádiz'),
                     stars=5,
                     url='https://aws.amazon.com/bedrock/',
                     poster=(Path('bookings') / 'sample' / 'poster.jpg').read_bytes())


def get_reservations_by_chat_id(name: str | None = None) -> list[Reservation]:
    """
    Get the reservations (if any) for a given chat_id

    Please note that this function will always return a reservation, even if the chat_id
    has not been found.

    Parameters
    ----------
    name : Name to use if a reservation could not be found. Use this if you want to always return
           at least one reservation regardless of whether one can be found in `sample_reservations`.
    """
    if name is None:
        return []

    # Chat id not found, return default reservation
    return [Reservation(hotel=sample_hotel,
                        guests=[Guest(name=name,
                                      surnames=[],
                                      birth_date=date(year=1984, month=6, day=2),
                                      member_level=MemberType.GOLD,
                                      chat_id=114649997)],
                        start_date=date.today(),
                        end_date=date.today() + timedelta(days=randint(3, 7)),
                        room_number=randint(42, 215))]


def get_chatbot_session_attrs(main_guest_name: str | None = None) -> dict[str, str | int]:
    """
    Get the session attributes for the reservation in a format suitable to be used by Bedrock Agents
    """
    # Get the reservations details
    reservations = get_reservations_by_chat_id(name=main_guest_name)
    if len(reservations) == 0:
        return {}

    # Get the first reservation available
    reservation = sorted(reservations, key=lambda r: r.start_date)[0]

    return {'mainGuestName': main_guest_name,
            'hotelName': reservation.hotel.name,
            'roomNumber': f'{reservation.room_number}',
            "isLeapYear": False,
            'todayISOFormat': date.today().isoformat(),
            'todayWeekDay': date.today().strftime('%A'),
            'checkInDateISOFormat': reservation.start_date.isoformat(),
            'checkoutDateISOFormat': reservation.end_date.isoformat(),
            'numAdultGuests': len([g.name for g in reservation.guests if not g.is_minor]),
            'adultGuests': ', '.join([g.name for g in reservation.guests if not g.is_minor]),
            'numMinorGuests': len([g.name for g in reservation.guests if g.is_minor]),
            'minorGuests': ', '.join([g.name for g in reservation.guests if g.is_minor])}
