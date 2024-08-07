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


def parse_request(body: dict):
    """
    Parse a Webhook request, returning the native Message data

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


if __name__ == '__main__':
    parse_request({'object': 'whatsapp_business_account',
                   'entry': [{'id': '329941153545846',
                              'changes': [{'value': {
                                  'messaging_product': 'whatsapp',
                                  'metadata': {'display_phone_number': '15555555555',
                                               'phone_number_id': '333333333333333'},
                                  'contacts': [{'profile': {'name': 'Joseba Echevarría'},
                                                'wa_id': '34611111111'}],
                                  'messages': [{'from': '34611111111',
                                                'id': 'wamid.HBgLMzQ2MTc5OTc0NjkVAgASGBYzRUIwOTA4RTRFMzVFNTVDMUIzQTQzAA==',
                                                'timestamp': '1722857807',
                                                'text': {'body': 'Hello!'},
                                                'type': 'text'},
                                               {'from': '34611111111',
                                                'id': 'wamid.HBgLMzQ2MTc5OTc0NjkVAgASGBYzRUIwOTA4RTRFMzVFNTVDMUIzQTQzAA==',
                                                'timestamp': '1722857807',
                                                'text': {'body': 'World!'},
                                                'type': 'text'}
                                               ]},
                                  'field': 'messages'}],
                              },
                             {'id': '329941153545847',
                              'changes': [{'value': {
                                  'messaging_product': 'whatsapp',
                                  'metadata': {'display_phone_number': '15555555555',
                                               'phone_number_id': '333333333333333'},
                                  'contacts': [{'profile': {'name': 'Joseba García'},
                                                'wa_id': '34611111111'}],
                                  'messages': [{'from': '34611111111',
                                                'id': 'wamid.HBgLMzQ2MTc5OTc0NjkVAgASGBYzRUIwOTA4RTRFMzVFNTVDMUIzQTQzAA==',
                                                'timestamp': '1722857807',
                                                'text': {'body': 'Hola'},
                                                'type': 'text'},
                                               {'from': '34611111111',
                                                'id': 'wamid.HBgLMzQ2MTc5OTc0NjkVAgASGBYzRUIwOTA4RTRFMzVFNTVDMUIzQTQzAA==',
                                                'timestamp': '1722857807',
                                                'text': {'body': 'Mundo!'},
                                                'type': 'text'}
                                               ]},
                                  'field': 'messages'}],
                              }]})
