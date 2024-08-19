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
    recipients: set[Contact] = field(init=False)

    def __post_init__(self):
        # Create the convenience attribute holding the list of message recipients
        # These are all the members of the conversation who are not the sender
        self.recipients = self.conversation.participants - {self.sender}
