from httpx import URL, AsyncClient


class WhatsAppApplication:
    def __init__(self, whatsapp_token: str, client: AsyncClient, protocol_version: str = 'v20.0'):
        """
        Application that can be used for talking to the WhatsApp-enable Meta application
        """
        self._base_url = URL(f'https://graph.facebook.com/{protocol_version}/messages')
        self._client = client
        self._token = whatsapp_token
