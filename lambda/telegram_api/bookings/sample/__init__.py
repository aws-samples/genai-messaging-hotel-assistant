from pathlib import Path
from datetime import date
from bookings.hotels import Hotel, Location
from bookings.guests import Guest, MemberType
from bookings.reservations import Reservation

# Create some sample data
sample_hotel = Hotel(name='Costa Tartessos Luxury Resort',
                     location=Location(lon=-6.1609661, lat=36.3407887, address='Chiclana de la Frontera, Cádiz'),
                     stars=5,
                     url='https://aws.amazon.com/bedrock/',
                     poster=(Path('bookings') / 'sample' / 'poster.jpg').read_bytes())

sample_guests = [Guest(name='Joseba',
                       surnames=['Echevarría', 'García'],
                       birth_date=date(year=1984, month=6, day=2),
                       member_level=MemberType.GOLD,
                       chat_id=6449557216),
                 Guest(name='María',
                       surnames=['García', 'Rodríguez'],
                       birth_date=date(year=1985, month=9, day=15),
                       member_level=MemberType.NON_MEMBER),
                 Guest(name='Iker',
                       surnames=['García', 'Echevarría'],
                       birth_date=date(year=2019, month=2, day=28),
                       member_level=MemberType.NON_MEMBER)]
sample_guests_2 = [Guest(name='Antonkio',
                         surnames=['Campos', 'Rodríguez'],
                         birth_date=date(year=1986, month=9, day=12),
                         member_level=MemberType.SILVER,
                         chat_id=1522147268),
                   Guest(name='Elena',
                         surnames=['Díez', 'Vázquez'],
                         birth_date=date(year=1986, month=1, day=21),
                         member_level=MemberType.NON_MEMBER)]
sample_guests_3 = [Guest(name='Joseba',
                         surnames=['Echevarría', 'García'],
                         birth_date=date(year=1984, month=6, day=2),
                         member_level=MemberType.GOLD,
                         chat_id=114649997),
                   Guest(name='María',
                         surnames=['García', 'Rodríguez'],
                         birth_date=date(year=1985, month=9, day=15),
                         member_level=MemberType.NON_MEMBER)]

sample_reservations = [Reservation(hotel=sample_hotel,
                                   guests=sample_guests,
                                   start_date=date(year=2024, month=5, day=29),
                                   end_date=date(year=2024, month=6, day=5),
                                   room_number=126),
                       Reservation(hotel=sample_hotel,
                                   guests=sample_guests,
                                   start_date=date(year=2024, month=6, day=1),
                                   end_date=date(year=2024, month=6, day=5),
                                   room_number=215),
                       Reservation(hotel=sample_hotel,
                                   guests=sample_guests_2,
                                   start_date=date(year=2024, month=5, day=29),
                                   end_date=date(year=2024, month=7, day=3),
                                   room_number=307),
                       Reservation(hotel=sample_hotel,
                                   guests=sample_guests_3,
                                   start_date=date(year=2024, month=5, day=29),
                                   end_date=date(year=2024, month=6, day=6),
                                   room_number=306)]


def get_reservations_by_chat_id(chat_id: int | str,
                                fallback_name: str | None = None) -> list[Reservation]:
    """
    Get the reservations (if any) for a given chat_id

    Please note that this function will always return a reservation, even if the chat_id
    has not been found.

    Parameters
    ----------
    chat_id : ID of the chat for the person whose reservation we want to retrieve
    fallback_name : Name to use if a reservation could not be found. Use this if you want to always return
                    at least one reservation regardless of whether one can be found in `sample_reservations`.
    """
    reservations = [r for r in sample_reservations if any([g.chat_id == chat_id for g in r.guests])]
    if len(reservations) > 0 or fallback_name is None:
        return reservations

    # Chat id not found, return default reservation
    return [Reservation(hotel=sample_hotel,
                        guests=[Guest(name=fallback_name,
                                      surnames=[],
                                      birth_date=date(year=1984, month=6, day=2),
                                      member_level=MemberType.GOLD,
                                      chat_id=114649997)],
                        start_date=date(year=2024, month=7, day=5),
                        end_date=date(year=2024, month=7, day=12),
                        room_number=126)]


def get_chatbot_session_attrs(chat_id: int,
                              main_guest_name: str | None = None) -> dict[str, str]:
    """
    Get the session attributes for the reservation in a format suitable to be used by Bedrock Agents
    """
    # Get the reservations details
    reservations = get_reservations_by_chat_id(chat_id=chat_id, fallback_name=main_guest_name)
    if len(reservations) == 0:
        return {}

    # Get the first reservation available
    # TODO: this might be in the past!
    reservation = sorted(reservations, key=lambda r: r.start_date)[0]

    return {'mainGuestName': main_guest_name,
            'hotelName': reservation.hotel.name,
            'roomNumber': f'{reservation.room_number}',
            'checkInDate': reservation.start_date.isoformat(),
            'checkoutDate': reservation.end_date.isoformat(),
            'adultGuests': ', '.join([g.name for g in reservation.guests if not g.is_minor]),
            'minorGuests': ', '.join([g.name for g in reservation.guests if g.is_minor])}
