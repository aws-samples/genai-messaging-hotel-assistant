import json
import mimetypes
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class BaseMessage:
    sender_id: str
    recipient_id: str

    async def serialize(self) -> dict[str: str | int]:
        raise NotImplementedError('This method must be implemented by derived classes')


@dataclass
class TextMessage(BaseMessage):
    text: str
    date: datetime = field(default_factory=datetime.now)
    msg_id: str = ''
    recipient: str = ''
    sender: str = ''
    preview_url: bool = True

    async def serialize(self) -> dict[str: str | int]:
        """
        Serialize the message into a dictionary that can be sent using the Meta API

        https://developers.facebook.com/docs/whatsapp/cloud-api/messages/text-messages
        """
        return {'messaging_product': 'whatsapp',
                'recipient_type': 'individual',
                'to': self.recipient_id,
                'type': 'text',
                'text': json.dumps({'preview_url': self.preview_url,
                                    'body': self.text})}


@dataclass
class MediaMessage(BaseMessage):
    media: bytes
    media_name: str
    media_id: str | None = None
    mime_type: str | None = None

    def __post_init__(self):
        """
        Assign calculated variables when needed
        """
        if self.mime_type is None:
            self.mime_type = mimetypes.guess_type(self.media_name)[0]


@dataclass
class ImageMessage(MediaMessage):
    caption: str = ''
    date: datetime = field(default_factory=datetime.now)
    msg_id: str = ''
    recipient: str = ''
    sender: str = ''

    async def serialize(self) -> dict[str: str | int]:
        """
        Serialize the message into a dictionary that can be sent using the Meta API

        The serialized message is not self-contained, since the message's image has to be
        uploaded to Meta's servers in advance and the returned reference is what is included
        in the serialized message, so this method will actually do that for you.

        https://developers.facebook.com/docs/whatsapp/cloud-api/messages/image-messages
        """
        # Cannot serialize the message if the image has not been uploaded to Meta's servers first
        # https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
        if self.media_id is None:
            raise RuntimeError("Please, upload the image to Meta before serializing the message")

        return {'messaging_product': 'whatsapp',
                'recipient_type': 'individual',
                'to': self.recipient_id,
                'type': 'image',
                'image': {'id': self.media_id,
                          'caption': self.caption}}
