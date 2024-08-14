import logging
from datetime import datetime
from httpx import URL, AsyncClient
from whatsapp.message import BaseMessage, MediaMessage, TextMessage

ERROR_MSG_MALFORMED = ('Given request body does not conform to spec, see '
                       'https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components for details')


class WhatsAppApplication:
    def __init__(self, whatsapp_token: str, client: AsyncClient, protocol_version: str = 'v20.0'):
        """
        Application that can be used for talking to the WhatsApp-enable Meta application
        """
        self._base_url = URL(f'https://graph.facebook.com/{protocol_version}/messages')
        self._client = client
        self._token = whatsapp_token
        self._protocol_version = protocol_version

    async def send_msg(self, msg: BaseMessage):
        """
        Send a message to the given WhatsApp ID
        """
        if isinstance(msg, TextMessage):
            return await self._send_generic_msg(msg)
        elif isinstance(msg, MediaMessage):
            return await self._send_media_msg(msg)

    async def _send_generic_msg(self, msg: BaseMessage):
        """
        Send a generic message type that requires no specific handling other than serialization
        """
        return await self._client.post(f'https://graph.facebook.com/{self._protocol_version}/{msg.sender_id}/messages',
                                       headers={'Authorization': f'Bearer {self._token}',
                                                'Content-Type': 'application/json'},
                                       data=msg.serialize())

    async def _send_media_msg(self, msg: MediaMessage):
        """
        Upload the image to Meta's servers, then send the message

        Only image/jpeg & image/png are supported by WhatsApp as described in
        https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
        """
        # First upload the image, that'll give us a media ID
        response = await self._client.post(f'https://graph.facebook.com/{self._protocol_version}/{msg.sender_id}/media',
                                           headers={'Authorization': f'Bearer {self._token}'},
                                           data={'type': msg.mime_type,
                                                 'messaging_product': 'whatsapp'},
                                           files={'file': (msg.media_name, msg.media, msg.mime_type)})
        response.raise_for_status()
        msg.media_id = response.json().get('id')
        # Now we can send the image normally
        return await self._send_generic_msg(msg)

    @staticmethod
    def parse_request(body: dict) -> list[TextMessage]:
        """
        Parse a Webhook request containing new messages, returning the native Message data

        This function will try to do some message validation, but
        should not be considered to be entirely safe to use.

        Parameters
        ==========
        * body : Webhook notification body, see
                 https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components
                 for details

        Raises
        ======
        * NotImplementedError if the object field is not `whatsapp_business_account`
        * ValueError in case the given body does not conform to spec
        """
        # Input data sanity check
        if body['object'] != 'whatsapp_business_account':
            raise NotImplementedError('Cannot parse unknown message format')
        if 'entry' not in body:
            raise ValueError(ERROR_MSG_MALFORMED)

        # The list that will contain the message objects
        messages = []

        for entry in body['entry']:
            # Here we have a list of entries; for each entry the `id` field contains the WhatsApp
            # Business ID the webhook is subscribed to, since each webhook could be shared by more than
            # one application and we might get more than one entry
            # We'll ignore it for this simple usecase
            if 'changes' not in entry:
                raise ValueError(ERROR_MSG_MALFORMED)

            for change in entry.get('changes', []):
                contacts = {}
                if 'field' not in change or change.get('field') != 'messages':
                    raise NotImplementedError('Cannot parse unknown message format')
                changes = change.get('value', {})
                if changes.get('messaging_product') != 'whatsapp':
                    raise ValueError(ERROR_MSG_MALFORMED)

                # metadata contains the info for the bot
                if 'metadata' not in changes:
                    raise ValueError(ERROR_MSG_MALFORMED)
                recipient = changes.get('metadata', {'display_phone_number': '__INVALID__'})['display_phone_number']
                recipient_id = changes.get('metadata', {'phone_number_id': '__INVALID__'})['phone_number_id']
                # contacts contains the sender data, we'll only get the first one
                if 'contacts' not in changes:
                    raise ValueError(ERROR_MSG_MALFORMED)
                for contact in changes.get('contacts', []):
                    # Store the user names for the WhatsApp IDs that are provided
                    # These should match values in the messages -> from field
                    if 'profile' not in contact or 'name' not in contact.get('profile'):
                        raise ValueError(ERROR_MSG_MALFORMED)
                    # Add the contact to the list of contacts
                    contacts[contact['wa_id']] = contact['profile']['name']
                if 'messages' not in changes:
                    raise ValueError(ERROR_MSG_MALFORMED)
                for msg in changes.get('messages', []):
                    match msg.get('type'):
                        case 'text':
                            messages.append(TextMessage(msg_id=msg.get('id', '__INVALID__'),
                                                        sender_id=msg.get('from', '__INVALID__'),
                                                        sender=contacts.get(msg.get('from', '__INVALID__'),
                                                                            '__INVALID__'),
                                                        recipient=recipient,
                                                        recipient_id=recipient_id,
                                                        date=datetime.fromtimestamp(
                                                            WhatsAppApplication._parseint(msg.get('timestamp', 0))),
                                                        text=msg.get('text', {'body': '__INVALID__'}).get('body')))
                        case _:
                            raise NotImplementedError(f'Cannot parse message of type "{msg.get("type")}"')

        return messages

    @staticmethod
    def handle_subscription(event: dict, whatsapp_verify_token: str):
        """
        Handle the subscription request and respond to it

        https://developers.facebook.com/docs/graph-api/webhooks/getting-started/

        Parameters
        ==========
        * event : Dictionary with the request
        * whatsapp_verify_token : Token expected to be present in the subscription request.
                                  You should provide this in the Meta Application pannel
                                  when creating your app.
        """
        match event['hub.mode']:
            case 'subscribe':
                verify_token = event['hub.verify_token']
                if verify_token == whatsapp_verify_token:
                    logging.debug('Subscription correct')
                    return {'statusCode': 200,
                            'body': int(event['hub.challenge']),
                            'isBase64Encoded': False}
                else:
                    logging.debug(f'Subscribe called with wrong verify token "{verify_token}"')
                    return {'statusCode': 403,
                            'body': 'Error, wrong validation token',
                            'isBase64Encoded': False}
            case _:
                logging.debug(f'Provided wrong value for hub.mode')
                return {'statusCode': 403,
                        'body': 'Error, wrong mode',
                        'isBase64Encoded': False}

    @staticmethod
    def _parseint(number: str | float, fallback_value=0):
        """
        Try to convert a given number to an integer, fail back to the fallback value if it cannot be done
        """
        try:
            return int(number)
        except (TypeError, ValueError):
            return fallback_value
