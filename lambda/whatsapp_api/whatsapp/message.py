from datetime import datetime
from dataclasses import dataclass


@dataclass
class TextMessage:
    msg_id: str
    text: str
    received_on: datetime
    sender: str
    sender_id: str
    recipient: str
    recipient_id: str


