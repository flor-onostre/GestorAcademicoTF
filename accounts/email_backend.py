import os
import smtplib

from django.core.mail.backends.smtp import EmailBackend
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail import EmailMultiAlternatives


class MailtrapBackend(EmailBackend):
    """
    Backend SMTP simple para Mailtrap que evita pasar keyfile/certfile
    (issue con Python 3.12). Soporta STARTTLS si EMAIL_USE_TLS=True.
    """

    def open(self):
        if self.connection:
            return False
        try:
            self.connection = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            self.connection.ehlo()
            if self.use_tls:
                self.connection.starttls()
                self.connection.ehlo()
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except Exception:
            self.close()
            raise


def _sender_payload(message):
    name = getattr(message, "from_name", None) or os.environ.get("EMAIL_FROM_NAME")
    email = message.from_email
    payload = {"email": email}
    if name:
        payload["name"] = name
    return payload


class BrevoEmailBackend(BaseEmailBackend):
    """
    Backend de envío vía API v3 de Brevo (Sendinblue).
    Usa la API key BREVO_API_KEY y EMAIL_FROM_ADDRESS/EMAIL_FROM_NAME como remitente.
    """

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        api_key = os.environ.get("BREVO_API_KEY")
        if not api_key:
            return 0
        try:
            import sib_api_v3_sdk
        except ImportError:
            if not self.fail_silently:
                raise
            return 0

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key["api-key"] = api_key
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )
        sent = 0
        for message in email_messages:
            html_content = None
            text_content = message.body or ""
            if isinstance(message, EmailMultiAlternatives) and message.alternatives:
                html_content = message.alternatives[0][0]
            elif getattr(message, "alternatives", None):
                html_content = message.alternatives[0][0]
            payload = sib_api_v3_sdk.SendSmtpEmail(
                to=[{"email": addr} for addr in message.to or []],
                cc=[{"email": addr} for addr in message.cc or []],
                bcc=[{"email": addr} for addr in message.bcc or []],
                subject=message.subject or "",
                html_content=html_content,
                text_content=text_content if not html_content else None,
                sender=_sender_payload(message),
            )
            try:
                api_instance.send_transac_email(payload)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent
