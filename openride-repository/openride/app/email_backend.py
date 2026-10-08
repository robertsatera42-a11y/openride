from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class BrevoBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            name, address = parseaddr(message.from_email)
            payload = {
                'sender': {'name': name or 'OpenRide', 'email': address},
                'to': [{'email': recipient} for recipient in message.to],
                'subject': message.subject,
                'textContent': message.body,
            }
            try:
                response = requests.post(
                    'https://api.brevo.com/v3/smtp/email',
                    headers={
                        'api-key': settings.BREVO_API_KEY,
                        'accept': 'application/json',
                        'content-type': 'application/json',
                    },
                    json=payload,
                    timeout=10,
                )
                response.raise_for_status()
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent
