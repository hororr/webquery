"""E-mail értesítés smtplib-bel; az SMTP-adatok a .env fájlból jönnek."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

REQUIRED = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO"]


def load_env(path: str | Path) -> None:
    """Egyszerű KULCS=érték betöltő; a már beállított környezeti változót nem írja felül."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def missing_settings() -> list[str]:
    return [k for k in REQUIRED if not os.environ.get(k)]


def send_mail(subject: str, body: str) -> None:
    missing = missing_settings()
    if missing:
        raise RuntimeError("Hiányzó SMTP-beállítás a .env fájlban: " + ", ".join(missing))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["MAIL_FROM"]
    msg["To"] = os.environ["MAIL_TO"]
    msg.set_content(body)

    host, port = os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls(context=context)
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
