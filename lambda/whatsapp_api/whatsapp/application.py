import logging
from datetime import datetime
from httpx import URL, AsyncClient
from whatsapp.update import Update
from whatsapp.contact import Contact
from whatsapp.conversation import Conversation
from whatsapp.message import BaseMessage, MediaMessage, TextMessage, LocationMessage

ERROR_MSG_MALFORMED = ('Given request body does not conform to spec, see '
                       'https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components for details')


class WhatsAppApplication:
    def __init__(self, whatsapp_token: str, whatsapp_id: str, client: AsyncClient, protocol_version: str = 'v20.0'):
        """
        Application that can be used for talking to the WhatsApp-enable Meta application

        Parameters
        ----------
        whatsapp_token : API token for the application. Get this from the Meta developer App Dashboard
        whatsapp_id: Phone number ID to send messages from. Get this from the Meta developer App Dashboard
        client: Async client to use for communicating with Meta's servers
        protocol_version: WhatsApp API protocol version to use
        """
        self._base_url = URL(f'https://graph.facebook.com/{protocol_version}/')
        self._client = client
        self._whastapp_id = whatsapp_id
        self._token = whatsapp_token
        self._protocol_version = protocol_version
        self._conversations = {}
        self.contact = Contact(whatsapp_id=whatsapp_id)
        self._contacts = {}

    async def send_msg(self, msg: BaseMessage, conversation: Conversation = None, recipient_id: str = None):
        """
        Send a message to a conversation

        Parameters
        ----------
        msg: Message to send to the destination
        conversation: Conversation where the message should be sent to.
                      Cannot be `None` if `recipient_id` is also `None`.
        recipient_id: WhatsApp phone number of the recipient. Will only be used if `conversation` is `None`.
                      Cannot be `None` if `conversation` is also `None`.
        """
        if conversation is None and (recipient_id is None or len(recipient_id) == 0):
            raise ValueError('conversation and recipient_id cannot be both be empty')

        # Determine the conversation we should send the message to if not provided
        if conversation is None:
            conversation = self.get_conversations({Contact(whatsapp_id=recipient_id)})

        if isinstance(msg, (TextMessage, LocationMessage)):
            retval = await self._send_generic_msg(msg, conversation)
        elif isinstance(msg, MediaMessage):
            retval = await self._send_media_msg(msg, conversation)
        else:
            raise NotImplementedError(f'Cannot send message of type {type(msg)}')

        # Finally, register the message in the list of conversations
        self._conversations[conversation.frozen_participants].messages.append(Update(sender=self.contact,
                                                                                     msg=msg,
                                                                                     conversation=conversation))

        return retval

    async def _send_generic_msg(self, msg: BaseMessage, conversation: Conversation):
        """
        Send a generic message type that requires no specific handling other than serialization
        """
        # We will send the message to the first member of the conversation that is not the bot
        # This is probably fine, since WhatsApp bots send messages on a 1:1 basis and cannot
        # send messages to a group, but the method is a bit fragile.
        # This is because the WhatsApp API has no concept of conversations itself and we're
        # emulating those
        return await self._client.post(f'{self._base_url}/{self._whastapp_id}/messages',
                                       headers={'Authorization': f'Bearer {self._token}',
                                                'Content-Type': 'application/json'},
                                       data=msg.serialize(recipient=(conversation.participants - {self.contact}).pop()))

    async def _send_media_msg(self, msg: MediaMessage, conversation: Conversation):
        """
        Upload the image to Meta's servers, then send the message

        Only image/jpeg & image/png are supported by WhatsApp as described in
        https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
        """
        # First upload the image, that'll give us a media ID
        response = await self._client.post(f'{self._base_url}/{self._whastapp_id}/media',
                                           headers={'Authorization': f'Bearer {self._token}'},
                                           data={'type': msg.mime_type,
                                                 'messaging_product': 'whatsapp'},
                                           files={'file': (msg.media_name, msg.media, msg.mime_type)})
        response.raise_for_status()
        msg.media_id = response.json().get('id')
        # Now we can send the image normally
        return await self._send_generic_msg(msg, conversation)

    def parse_request(self, body: dict) -> list[Update]:
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
            raise ValueError('Cannot parse unknown message format')
        if 'entry' not in body:
            raise ValueError(ERROR_MSG_MALFORMED)

        # The list that will contain the message objects
        updates = []

        for entry in body['entry']:
            # Here we have a list of entries; for each entry the `id` field contains the WhatsApp
            # Business ID the webhook is subscribed to, since each webhook could be shared by more than
            # one application and we might get more than one entry
            # We'll ignore it for this simple usecase
            if 'changes' not in entry:
                raise ValueError(ERROR_MSG_MALFORMED)

            for change in entry.get('changes', []):
                if 'field' not in change or change.get('field') != 'messages':
                    raise ValueError('Cannot parse unknown message format')
                changes = change.get('value', {})
                if changes.get('messaging_product') != 'whatsapp':
                    raise ValueError(ERROR_MSG_MALFORMED)

                # metadata contains the info for the bot
                if 'metadata' not in changes:
                    raise ValueError(ERROR_MSG_MALFORMED)
                recipient = changes.get('metadata', {'display_phone_number': '__INVALID__'})['display_phone_number']
                recipient_id = changes.get('metadata', {'phone_number_id': '__INVALID__'})['phone_number_id']
                # Ignore status change (read notification) messages
                if 'statuses' in changes:
                    logging.debug(f'Skipping status message changes {changes}')
                    continue
                # contacts contains the sender data, we'll only get the first one
                if 'contacts' not in changes:
                    raise ValueError(ERROR_MSG_MALFORMED)
                for contact in changes.get('contacts', []):
                    # Store the contacts for the WhatsApp IDs that are provided
                    # These should match values in the messages -> from field
                    if 'profile' not in contact or 'name' not in contact.get('profile'):
                        raise ValueError(ERROR_MSG_MALFORMED)
                    # Continuously update the contact information based on the information we get
                    if contact['wa_id'] in self._contacts:
                        self._contacts[contact['wa_id']].name = contact['profile']['name']
                    else:
                        self._contacts[contact['wa_id']] = Contact(whatsapp_id=contact['wa_id'],
                                                                   name=contact['profile']['name'])
                if 'messages' not in changes:
                    raise ValueError(ERROR_MSG_MALFORMED)
                for msg in changes.get('messages', []):
                    sender_id = msg.get('from', '__INVALID__')
                    sender = self._contacts.get(sender_id)
                    if sender is None:
                        logging.error(f'Cannot find sender id {sender_id} for update in list of contacts, skipping')
                        continue
                    conversation = self.get_conversations({sender})
                    match msg.get('type'):
                        case 'text':
                            updates.append(Update(sender=sender,
                                                  instant=datetime.fromtimestamp(
                                                      WhatsAppApplication._parseint(msg.get('timestamp', 0))),
                                                  conversation=conversation,
                                                  msg=TextMessage(msg_id=msg.get('id', '__INVALID__'),
                                                                  date=datetime.fromtimestamp(
                                                                      WhatsAppApplication._parseint(
                                                                          msg.get('timestamp', 0))),
                                                                  text=msg.get('text', {'body': '__INVALID__'}).get(
                                                                      'body', ''))))
                        case _:
                            raise NotImplementedError(f'Cannot parse message of type "{msg.get("type")}"')

        return updates

    def get_conversations(self, contacts: set[Contact]):
        """
        Get the conversations currently in place with the provided contacts

        The conversations with the given contacts will be registered internally, if it does not exist
        """
        conversation = Conversation(contacts | {self.contact})
        if conversation.frozen_participants not in self._conversations:
            logging.debug(f'Starting new conversation with {contacts}')
            self._conversations[conversation.frozen_participants] = conversation

        return conversation

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
