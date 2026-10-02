import email
from email.header import decode_header

from src.collector.notifier import send_email


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def sendmail(self, from_addr, to_addrs, message):
        self.sent = (from_addr, to_addrs, message)


def _send(**overrides):
    _FakeSMTP.instances = []
    kwargs = {
        "subject": "件名",
        "html_body": "<p>本文</p>",
        "from_addr": "from@example.com",
        "to_addr": "to@example.com",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "user",
        "smtp_password": "pass",
        "smtp_client_factory": _FakeSMTP,
    }
    kwargs.update(overrides)
    send_email(**kwargs)
    return _FakeSMTP.instances[0]


def test_send_email_connects_to_configured_host_and_port():
    smtp = _send(smtp_host="smtp.gmail.com", smtp_port=587)

    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 587


def test_send_email_starts_tls_and_logs_in():
    smtp = _send(smtp_username="user@example.com", smtp_password="app-password")

    assert smtp.started_tls is True
    assert smtp.login_args == ("user@example.com", "app-password")


def test_send_email_sends_to_recipient_with_subject_and_html_body():
    smtp = _send(
        subject="BtoBマーケティング情報まとめ 2026-08-20",
        html_body="<h1>まとめ</h1><p>本文</p>",
        from_addr="from@example.com",
        to_addr="to@example.com",
    )

    from_addr, to_addrs, raw_message = smtp.sent
    assert from_addr == "from@example.com"
    assert to_addrs == ["to@example.com"]

    parsed = email.message_from_string(raw_message)
    subject_parts = decode_header(parsed["Subject"])
    subject = "".join(
        part.decode(encoding or "ascii") if isinstance(part, bytes) else part
        for part, encoding in subject_parts
    )
    assert subject == "BtoBマーケティング情報まとめ 2026-08-20"

    html_part = parsed.get_payload()[0]
    assert html_part.get_payload(decode=True).decode("utf-8") == "<h1>まとめ</h1><p>本文</p>"
