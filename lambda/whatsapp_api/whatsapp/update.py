from datetime import datetime
from whatsapp.contact import Contact
from whatsapp.message import BaseMessage
from dataclasses import dataclass, field
from whatsapp.conversation import Conversation


@dataclass
class Update:
    """
    Class for holding conversation changes (new messages sent to conversations, for example)
    """
    sender: Contact
    conversation: Conversation
    msg: BaseMessage
    instant: datetime = field(default_factory=lambda: datetime.now())
