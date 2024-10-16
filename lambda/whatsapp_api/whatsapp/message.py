import json
import mimetypes
from enum import Enum
from datetime import datetime
from whatsapp.contact import Contact
from dataclasses import dataclass, field


class Status(Enum):
    """
    Enum for holding message status values
    """
    UNKNOWN = 0
    SENT = 1
    READ = 2


@dataclass(kw_only=True)
class BaseMessage:
    """
    Base class for all messages supported by this package
    """
    status = Status.UNKNOWN

    def serialize(self, recipient: Contact) -> dict[str: str | int]:
        raise NotImplementedError('This method must be implemented by derived classes')


@dataclass(kw_only=True)
class TextMessage(BaseMessage):
    text: str
    date: datetime = field(default_factory=datetime.now)
    msg_id: str = ''
    preview_links: bool = True

    def serialize(self, recipient: Contact) -> dict[str: str | int]:
        """
        Serialize the message into a dictionary that can be sent using the Meta API

        https://developers.facebook.com/docs/whatsapp/cloud-api/messages/text-messages
        """
        return {'messaging_product': 'whatsapp',
                'recipient_type': 'individual',
                'to': recipient.whatsapp_id,
                'type': 'text',
                'text': json.dumps({'preview_url': self.preview_links,
                                    'body': self.text})}


@dataclass(kw_only=True)
class MediaMessage(BaseMessage):
    media: bytes
    media_name: str
    media_id: str | None = None
    mime_type: str | None = None

    def __post_init__(self):
        """
        Assign guessed variables when needed
        """
        if self.mime_type is None:
            self.mime_type = mimetypes.guess_type(self.media_name)[0]


@dataclass(kw_only=True)
class ImageMessage(MediaMessage):
    caption: str = ''
    date: datetime = field(default_factory=datetime.now)
    msg_id: str = ''
    recipient: str = ''
    sender: str = ''

    def serialize(self, recipient: Contact) -> dict[str: str | int]:
        """
        Serialize the message into a dictionary that can be sent using the Meta API

        The serialized message is not self-contained, since the message's image has to be
        uploaded to Meta's servers in advance and the returned reference is what is included
        in the serialized message, so this method will fail if `media_id` has not been set.

        In order to send this kind of message use `WhatsAppApplication`'s `send_msg` method
        which will actually upload the media to Meta's servers before sending the message.

        https://developers.facebook.com/docs/whatsapp/cloud-api/messages/image-messages
        """
        # Cannot serialize the message if the image has not been uploaded to Meta's servers first
        # https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
        if self.media_id is None:
            raise RuntimeError("Please, upload the image to Meta before serializing the message")

        return {'messaging_product': 'whatsapp',
                'recipient_type': 'individual',
                'to': recipient.whatsapp_id,
                'type': 'image',
                'image': {'id': self.media_id,
                          'caption': self.caption}}


@dataclass(kw_only=True)
class LocationMessage(BaseMessage):
    latitude: float
    longitude: float
    name: str
    address: str

    def serialize(self, recipient: Contact) -> dict[str: str | int]:
        """
        Serialize the message into a dictionary that can be sent using the Meta API

        https://developers.facebook.com/docs/whatsapp/cloud-api/messages/location-messages
        """
        return {'messaging_product': 'whatsapp',
                'recipient_type': 'individual',
                'to': recipient.whatsapp_id,
                'type': 'location',
                'location': {'latitude': self.latitude,
                             'longitude': self.longitude,
                             'name': self.name,
                             'address': self.address}}


@dataclass
class Row:
    id: str
    title: str
    description: str | None = None

    def serialize(self):
        return {'id': self.id,
                'title': self.title,
                'description': self.description}


@dataclass
class Section:
    title: str
    rows: list[Row]

    def serialize(self):
        return {'title': self.title,
                'rows': [r.serialize() for r in self.rows]}


@dataclass(kw_only=True)
class InteractiveListMessage(BaseMessage):
    """
    Class representing an interactive message.

    These messages present the user with a list of nested options the user can choose from
    """
    msg_id: str = ''
    header: str | None = None
    body: str
    footer: str | None = None
    button: str
    sections: list[Section]

    def serialize(self, recipient: Contact) -> dict[str: str | int]:
        """
        Serialize the message into a dictionary that can be sent using the Meta API.

        Options can be divided into

        https://developers.facebook.com/docs/whatsapp/cloud-api/messages/location-messages
        """
        response = {'messaging_product': 'whatsapp',
                    'recipient_type': 'individual',
                    'to': recipient.whatsapp_id,
                    'type': 'interactive',
                    'interactive': {'type': 'list',
                                    'body': {'text': self.body},
                                    'action': {'sections': [s.serialize() for s in self.sections]}}}
        response['interactive']['action']['button'] = self.button

        # Add optional fields
        if self.header is not None:
            response['interactive']['header'] = {'type': 'text', 'text': self.header}
        if self.footer is not None:
            response['interactive']['footer'] = {'text': self.footer}

        return response


@dataclass(kw_only=True)
class InteractiveListReplyMessage(BaseMessage):
    """
    Class representing an interactive message.

    These messages present the user with a list of nested options the user can choose from
    """
    msg_id: str = ''
    reply: Row
