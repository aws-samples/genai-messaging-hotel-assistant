from datetime import datetime
from whatsapp_api.message import TextMessage

ERROR_MSG_MALFORMED = ('Given request body does not conform to spec, see '
                       'https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components for details')


def _parseint(number: str | float, fallback_value=0):
    """
    Try to convert a given number to an integer, fail back to the fallback value if it cannot be done
    """
    try:
        return int(number)
    except (TypeError, ValueError):
        return fallback_value


def handle_subscription(body: dict):
    """
    Handle the subscription request and respond to it

    https://developers.facebook.com/docs/graph-api/webhooks/getting-started/

    Parameters
    ==========
    * body : Dictionary with the request
    """


def handle_request(body: dict) -> list[TextMessage]:
    """
    Parse a Webhook request containing new messages, returning the native Message data

    This function will try to do some message validation, but
    should not considered to be entirely safe to use.

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
        # Business ID the webhook is subscribed to, since each webhook could be shared by more than one application
        # and we might get more than one entry
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
                                                    sender=contacts.get(msg.get('from', '__INVALID__'), '__INVALID__'),
                                                    recipient=recipient,
                                                    recipient_id=recipient_id,
                                                    received_on=datetime.fromtimestamp(_parseint(msg.get('timestamp',
                                                                                                         0))),
                                                    text=msg.get('text', {'body': '__INVALID__'}).get('body')))
                    case _:
                        raise NotImplementedError(f'Cannot parse message of type "{msg.get("type")}"')

    return messages
