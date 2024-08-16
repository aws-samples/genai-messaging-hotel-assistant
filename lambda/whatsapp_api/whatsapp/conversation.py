from whatsapp.contact import Contact
from dataclasses import dataclass, field
from whatsapp.message import BaseMessage


@dataclass
class Conversation:
    """
    Class for holding a WhatsApp conversation between several parties

    Conversations can also hold the list of messages exchanged between participants, but this
    list will typically not contain old messages, since these cannot be retrieved from the WhatsApp API
    """
    participants: set[Contact]
    messages: list[BaseMessage] = field(default_factory=lambda: [], repr=False, hash=False, compare=True)

    @property
    def frozen_participants(self):
        return frozenset(self.participants)
