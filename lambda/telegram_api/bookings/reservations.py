from pathlib import Path
from datetime import date
from bookings.hotels import Hotel
from bookings.guests import Guest
from dataclasses import dataclass


@dataclass
class Reservation:
    hotel: Hotel
    guests: list[Guest]
    start_date: date
    end_date: date
    room_number: int

    @property
    def digital_room_key(self) -> bytes:
        """
        Generate a dummy hotel key
        """
        return (Path('bookings') / 'sample' / 'qr-code.png').read_bytes()
