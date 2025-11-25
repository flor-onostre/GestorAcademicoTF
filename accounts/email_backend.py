import smtplib

from django.core.mail.backends.smtp import EmailBackend


class MailtrapBackend(EmailBackend):
    """
    Backend SMTP simple para Mailtrap que evita pasar keyfile/certfile
    (issue con Python 3.12). Soporta STARTTLS si EMAIL_USE_TLS=True.
    """

    def open(self):
        if self.connection:
            return False
        try:
            # Conexión SMTP normal
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
