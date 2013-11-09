from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import ssl
from backlash._compat import string_types, bytes_


class EmailReporter(object):
    def __init__(self, smtp_server=None, from_address=None, error_email=None,
                 smtp_username=None, smtp_password=None, smtp_use_tls=False,
                 error_subject_prefix='', dump_request=False, dump_request_size=50000,
                 **unused):
        self.smtp_server = smtp_server
        self.from_address = from_address

        self.smtp_username = smtp_username
        self.smtp_password = smtp_password

        self.smtp_use_tls = smtp_use_tls

        if isinstance(error_email, string_types):
            error_email = [error_email]
        self.error_email = error_email

        self.error_subject_prefix = error_subject_prefix
        self.dump_request = dump_request
        self.dump_request_size = dump_request_size

    def report(self, traceback):
        if not self.smtp_server or not self.from_address or not self.error_email:
            return

        msg = self.assemble_email(traceback)

        server = smtplib.SMTP(self.smtp_server)
        if self.smtp_use_tls:
            server.ehlo()
            server.starttls()
            server.ehlo()

        if self.smtp_username and self.smtp_password:
            server.login(self.smtp_username, self.smtp_password)

        result = server.sendmail(self.from_address, self.error_email, msg.as_string())

        try:
            server.quit()
        except ssl.SSLError:
            # SSLError is raised in tls connections on closing sometimes
            pass

    def _format_cgi(self, environ):
        return '\n'.join(('\t%s: %s' % (k, v) for k, v in environ.items() if k.upper() == k))

    def _format_wsgi(self, environ):
        return '\n'.join(('\t%s: %s' % (k, v) for k, v in environ.items() if k.upper() != k))

    def email_body(self, traceback):
        body = 'TRACEBACK:\n%s' % traceback.plaintext
        body += '\n\n\nENVIRON:\n%s' % self._format_cgi(traceback.context['environ'])
        body += '\n\n\nWSGI:\n%s' % self._format_wsgi(traceback.context['environ'])

        for entry, value in traceback.context.items():
            if entry == 'environ':
                continue

            body += '\n\n\n%s:\n\t%r' % (entry.upper(), value)

        return body

    def assemble_email(self, traceback):
        msg = MIMEMultipart()

        subject = bytes_('%s: %s' % (traceback.exc_type, traceback.exc_value))

        msg['Subject'] = bytes_(self.error_subject_prefix + subject)
        msg['From'] = bytes_(self.from_address)
        msg['To'] = bytes_(', '.join(self.error_email))

        text = MIMEText(bytes_(self.email_body(traceback)))
        text.set_type('text/plain')
        text.set_param('charset', 'UTF-8')
        msg.attach(text)

        request = traceback.context.get('request')
        if self.dump_request and request is not None:
            part = MIMEApplication(request.as_bytes(self.dump_request_size))
            part.add_header('Content-Disposition', 'attachment; filename="request.txt"')
            msg.attach(part)

        return msg