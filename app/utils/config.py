"""Carga de variables de entorno."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.utils.logger import get_logger

logger = get_logger("config")

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class Settings:
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str
    webhook_port: int
    webhook_host: str = "0.0.0.0"
    webhook_public_url: str = ""
    webhook_enabled: bool = False
    message_sync_enabled: bool = True
    message_sync_interval: float = 1.0
    notification_sound_enabled: bool = True
    chat_verify_interval: float = 300.0
    log_level: str = "INFO"

    @property
    def webhook_incoming_url(self) -> str:
        base = self.webhook_public_url.rstrip("/")
        if base:
            return f"{base}/webhook/whatsapp"
        return f"http://localhost:{self.webhook_port}/webhook/whatsapp"

    @property
    def webhook_status_url(self) -> str:
        base = self.webhook_public_url.rstrip("/")
        if base:
            return f"{base}/webhook/status"
        return f"http://localhost:{self.webhook_port}/webhook/status"


def load_settings() -> Settings:
    """Carga configuración desde .env y variables de entorno."""
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
    else:
        load_dotenv()

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    whatsapp_from = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
    port_str = os.getenv("WEBHOOK_PORT", "5000").strip()
    public_url = os.getenv("WEBHOOK_PUBLIC_URL", "").strip().rstrip("/")
    webhook_enabled = os.getenv("WEBHOOK_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    message_sync_enabled = os.getenv("MESSAGE_SYNC_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    sync_interval_str = os.getenv("MESSAGE_SYNC_INTERVAL", "1").strip()
    notification_sound_enabled = os.getenv(
        "NOTIFICATION_SOUND_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes", "on")
    chat_verify_str = os.getenv("CHAT_VERIFY_INTERVAL", "300").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip()

    missing = []
    if not account_sid:
        missing.append("TWILIO_ACCOUNT_SID")
    if not auth_token:
        missing.append("TWILIO_AUTH_TOKEN")
    if not whatsapp_from:
        missing.append("TWILIO_WHATSAPP_FROM")

    if missing:
        logger.warning(
            "Variables no configuradas: %s. Copia .env.example a .env",
            ", ".join(missing),
        )

    try:
        webhook_port = int(port_str)
    except ValueError:
        webhook_port = 5000
        logger.warning("WEBHOOK_PORT inválido, usando 5000")

    try:
        message_sync_interval = float(sync_interval_str)
    except ValueError:
        message_sync_interval = 1.0

    try:
        chat_verify_interval = float(chat_verify_str)
    except ValueError:
        chat_verify_interval = 300.0

    if not whatsapp_from.startswith("whatsapp:"):
        whatsapp_from = f"whatsapp:{whatsapp_from}" if whatsapp_from else ""

    if public_url and not public_url.startswith(("http://", "https://")):
        public_url = f"https://{public_url}"
        logger.warning("WEBHOOK_PUBLIC_URL sin esquema; se usó https://")

    return Settings(
        twilio_account_sid=account_sid,
        twilio_auth_token=auth_token,
        twilio_whatsapp_from=whatsapp_from,
        webhook_port=webhook_port,
        webhook_public_url=public_url,
        webhook_enabled=webhook_enabled,
        message_sync_enabled=message_sync_enabled,
        message_sync_interval=message_sync_interval,
        notification_sound_enabled=notification_sound_enabled,
        chat_verify_interval=chat_verify_interval,
        log_level=log_level,
    )
