from __future__ import annotations

from copy import deepcopy

from django.conf import settings
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend


class RedirectEmailBackend(BaseEmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redirect_to = [addr.strip() for addr in getattr(settings, 'AGILE_EMAIL_REDIRECT_TO', []) if addr.strip()]
        self.real_backend = getattr(
            settings,
            'AGILE_EMAIL_REAL_BACKEND',
            'django.core.mail.backends.smtp.EmailBackend',
        )
        self.connection = get_connection(self.real_backend, fail_silently=self.fail_silently, **kwargs)

    def open(self):
        return self.connection.open()

    def close(self):
        return self.connection.close()

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.redirect_to:
            return self.connection.send_messages(email_messages)

        redirected_messages = []
        for message in email_messages:
            redirected = deepcopy(message)
            original_to = list(getattr(message, 'to', []) or [])
            original_cc = list(getattr(message, 'cc', []) or [])
            original_bcc = list(getattr(message, 'bcc', []) or [])
            redirected.to = list(self.redirect_to)
            redirected.cc = []
            redirected.bcc = []
            redirected.extra_headers = dict(getattr(message, 'extra_headers', {}) or {})
            redirected.extra_headers['X-Agile-Redirected-To'] = ', '.join(self.redirect_to)
            redirected.extra_headers['X-Agile-Original-To'] = ', '.join(original_to)
            redirected.extra_headers['X-Agile-Original-Cc'] = ', '.join(original_cc)
            redirected.extra_headers['X-Agile-Original-Bcc'] = ', '.join(original_bcc)
            redirected.subject = f'[REDIRECT] {redirected.subject}'
            redirected_messages.append(redirected)

        return self.connection.send_messages(redirected_messages)
