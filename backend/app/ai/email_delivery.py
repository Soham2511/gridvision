"""SMTP delivery for user-requested report emails."""

from __future__ import annotations

import logging
import smtplib
import socket
import ssl
from email.message import EmailMessage
from typing import Any


logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    """Safe error raised when report email delivery is unavailable."""


def send_report_email(
    *,
    config: dict[str, Any],
    recipient: str,
    subject: str,
    body: str,
    attachment_name: str,
    attachment_bytes: bytes,
    attachment_mime: str,
) -> None:
    """Send a report email using Gmail SMTP or another SMTP provider."""

    host = str(config.get("REPORT_EMAIL_SMTP_HOST", "")).strip()
    sender = str(config.get("REPORT_EMAIL_FROM_ADDRESS", "")).strip()

    if not host or not sender:
        raise EmailDeliveryError(
            "Report email delivery is not configured. "
            "Set SMTP host and from address."
        )

    try:
        port = int(config.get("REPORT_EMAIL_SMTP_PORT", 587))
    except (TypeError, ValueError) as exc:
        raise EmailDeliveryError("Invalid SMTP port configuration.") from exc

    username = str(
        config.get("REPORT_EMAIL_SMTP_USERNAME", "")
    ).strip()

    # Gmail App Passwords are 16 characters.
    # Remove spaces and surrounding whitespace for safe parsing.
    password = str(
        config.get("REPORT_EMAIL_SMTP_PASSWORD", "")
    ).replace(" ", "").strip()

    if bool(username) != bool(password):
        raise EmailDeliveryError(
            "SMTP username and password must be configured together."
        )

    if port not in (465, 587):
        raise EmailDeliveryError(
            "Unsupported SMTP port. Use 587 (STARTTLS) or 465 (SSL/TLS)."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    try:
        maintype, subtype = attachment_mime.split("/", 1)
    except ValueError as exc:
        raise EmailDeliveryError(
            "Invalid report attachment MIME type."
        ) from exc

    message.add_attachment(
        attachment_bytes,
        maintype=maintype,
        subtype=subtype,
        filename=attachment_name,
    )

    tls_context = ssl.create_default_context()

    try:
        logger.info(
            "Connecting to SMTP server %s on port %s",
            host,
            port,
        )

        if port == 465:
            # Implicit SSL/TLS
            with smtplib.SMTP_SSL(
                host,
                port,
                timeout=30,
                context=tls_context,
            ) as server:

                if username:
                    logger.info("Authenticating with SMTP server.")
                    server.login(username, password)

                logger.info("Sending report email.")
                server.send_message(message)

        else:
            # STARTTLS
            with smtplib.SMTP(
                host,
                port,
                timeout=30,
            ) as server:

                server.ehlo()

                server.starttls(context=tls_context)
                server.ehlo()

                if username:
                    logger.info("Authenticating with SMTP server.")
                    server.login(username, password)

                logger.info("Sending report email.")
                server.send_message(message)

        logger.info(
            "Report email successfully sent to %s",
            recipient,
        )

    except smtplib.SMTPAuthenticationError as exc:
        logger.error("SMTP authentication failed: %s", exc.smtp_code)

        raise EmailDeliveryError(
            "SMTP authentication failed. Check the SMTP username, "
            "Gmail App Password, and Google account settings."
        ) from exc

    except smtplib.SMTPNotSupportedError as exc:
        logger.exception("SMTP TLS or authentication feature unavailable.")

        raise EmailDeliveryError(
            "The SMTP server does not support the requested TLS "
            "or authentication feature."
        ) from exc

    except socket.gaierror as exc:
        logger.exception("SMTP DNS resolution failed.")

        raise EmailDeliveryError(
            "The SMTP host could not be resolved. "
            "Check SMTP host and DNS settings."
        ) from exc

    except (socket.timeout, TimeoutError) as exc:
        logger.exception("SMTP connection timed out.")

        raise EmailDeliveryError(
            "The SMTP connection timed out. "
            "Check host, port, firewall, and outbound network access."
        ) from exc

    except smtplib.SMTPRecipientsRefused as exc:
        logger.exception("SMTP recipient rejected.")

        raise EmailDeliveryError(
            "The SMTP server rejected the report recipient. "
            "Check the recipient address."
        ) from exc

    except smtplib.SMTPConnectError as exc:
        logger.exception("SMTP connection rejected.")

        raise EmailDeliveryError(
            "The SMTP server refused the connection. "
            "Check SMTP host, port, and network access."
        ) from exc

    except smtplib.SMTPServerDisconnected as exc:
        logger.exception("SMTP server disconnected.")

        raise EmailDeliveryError(
            "The SMTP server closed the connection. "
            "Check SMTP host, port, TLS settings, and network access."
        ) from exc

    except ssl.SSLError as exc:
        logger.exception("SMTP TLS/SSL error.")

        raise EmailDeliveryError(
            "SMTP TLS/SSL handshake failed. "
            "Check the SMTP port and TLS configuration."
        ) from exc

    except (OSError, smtplib.SMTPException) as exc:
        logger.exception("SMTP email delivery failed.")

        raise EmailDeliveryError(
            "The SMTP server rejected the send or a network error occurred. "
            "Check SMTP configuration and server logs."
        ) from exc