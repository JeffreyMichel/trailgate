import os
from unittest.mock import MagicMock, patch

from check_permits import send_email

AVAILABLE = {
    "Eagle Creek Trailhead": ["2026-07-04", "2026-07-05"],
    "Mirror Lake Trailhead": ["2026-08-01"],
}

TRAILHEAD_MAP = {
    "Eagle Creek Trailhead": "https://www.recreation.gov/permits/123",
    "Mirror Lake Trailhead": "https://www.recreation.gov/permits/456",
}

BASE_ENV = {
    "GMAIL_ADDRESS": "sender@gmail.com",
    "GMAIL_APP_PASSWORD": "secret-app-password",
}


def run_send_email(env_extra=None):
    env = {**BASE_ENV, **(env_extra or {})}
    with patch.dict(os.environ, env, clear=False):
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            send_email(AVAILABLE, TRAILHEAD_MAP)
            return mock_smtp_cls, mock_server


# ---------------------------------------------------------------------------
# 1. SMTP_SSL is used (no real email sent)
# ---------------------------------------------------------------------------


def test_smtp_ssl_is_used():
    mock_smtp_cls, _ = run_send_email()
    mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 465)


# ---------------------------------------------------------------------------
# 2. Email subject
# ---------------------------------------------------------------------------


def test_email_subject():
    env = {**BASE_ENV}
    with patch.dict(os.environ, env, clear=False):
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            send_email(AVAILABLE, TRAILHEAD_MAP)

            # Capture the message string passed to sendmail
            args = mock_server.sendmail.call_args
            raw_message = args[0][2]  # positional arg index 2
            assert "Subject: Trailgate: Permits Available!" in raw_message


# ---------------------------------------------------------------------------
# 3. Email body contains trailhead names, dates, and booking URLs
# ---------------------------------------------------------------------------


def test_email_body_contains_trailhead_names_dates_and_urls():
    import email as email_lib

    env = {**BASE_ENV}
    with patch.dict(os.environ, env, clear=False):
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            send_email(AVAILABLE, TRAILHEAD_MAP)

            raw_message = mock_server.sendmail.call_args[0][2]
            msg = email_lib.message_from_string(raw_message)
            body = ""
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    body = payload.decode("utf-8") if payload else part.get_payload()

            # Trailhead names
            assert "Eagle Creek Trailhead" in body
            assert "Mirror Lake Trailhead" in body

            # Dates
            assert "2026-07-04" in body
            assert "2026-07-05" in body
            assert "2026-08-01" in body

            # Booking URLs
            assert "https://www.recreation.gov/permits/123" in body
            assert "https://www.recreation.gov/permits/456" in body


# ---------------------------------------------------------------------------
# 4. Recipient: NOTIFY_EMAIL when set, else GMAIL_ADDRESS
# ---------------------------------------------------------------------------


def test_sends_to_notify_email_when_set():
    mock_smtp_cls, mock_server = run_send_email({"NOTIFY_EMAIL": "notify@example.com"})
    args = mock_server.sendmail.call_args[0]
    assert args[1] == "notify@example.com"


def test_sends_to_gmail_address_when_notify_email_not_set():
    # Ensure NOTIFY_EMAIL is absent
    env = {**BASE_ENV}
    with patch.dict(os.environ, env, clear=False):
        os.environ.pop("NOTIFY_EMAIL", None)
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            send_email(AVAILABLE, TRAILHEAD_MAP)
            args = mock_server.sendmail.call_args[0]
            assert args[1] == "sender@gmail.com"


# ---------------------------------------------------------------------------
# 5. Login uses correct credentials from env vars
# ---------------------------------------------------------------------------


def test_login_uses_correct_credentials():
    mock_smtp_cls, mock_server = run_send_email()
    mock_server.login.assert_called_once_with("sender@gmail.com", "secret-app-password")


def test_login_uses_env_var_credentials():
    mock_smtp_cls, mock_server = run_send_email(
        {
            "GMAIL_ADDRESS": "other@gmail.com",
            "GMAIL_APP_PASSWORD": "other-password",
        }
    )
    mock_server.login.assert_called_once_with("other@gmail.com", "other-password")
