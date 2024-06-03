from enum import IntEnum
from datetime import date
from dataclasses import dataclass, field


# The different member levels
class MemberType(IntEnum):
    NON_MEMBER = 0
    WHITE = 1
    SILVER = 2
    GOLD = 3
    PLATINUM = 4


@dataclass
class Guest:
    """
    Class holding the guest information
    """
    name: str
    surnames: list[str]
    birth_date: date
    member_level: MemberType
    chat_id: int | None = field(default=None, hash=False)

    @property
    def is_minor(self):
        return date(year=self.birth_date.year + 18, month=self.birth_date.month, day=self.birth_date.day) > date.today()
