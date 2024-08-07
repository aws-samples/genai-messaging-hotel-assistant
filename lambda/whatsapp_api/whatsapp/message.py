import json
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class TextMessage:
    text: str
    sender_id: str
    recipient_id: str
    date: datetime = field(default_factory=datetime.now)
    msg_id: str = ''
    recipient: str = ''
    sender: str = ''

    def serialize(self) -> dict[str: str | int]:
        """
        Serialize the message into a dictionary that can be sent using the Meta API

        https://developers.facebook.com/docs/whatsapp/cloud-api/messages/text-messages
        """
        return {'messaging_product': 'whatsapp',
                'to': self.recipient_id,
                'type': 'text',
                'text': json.dumps({'preview_url': True,
                                    'body': self.text})}
