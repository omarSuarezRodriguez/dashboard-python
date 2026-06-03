"""Cliente para envío de mensajes vía API de Twilio."""

from dataclasses import dataclass
from typing import Optional

from twilio.base.exceptions import TwilioException
from twilio.rest import Client

from app.utils.config import Settings
from app.utils.logger import get_logger

logger = get_logger("twilio")


@dataclass
class SendResult:
    success: bool
    sid: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None
    to_number: str = ""


class TwilioService:
    """Envía mensajes de WhatsApp usando Twilio REST API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Optional[Client] = None

    @property
    def is_configured(self) -> bool:
        return bool(
            self.settings.twilio_account_sid
            and self.settings.twilio_auth_token
            and self.settings.twilio_whatsapp_from
        )

    def _get_client(self) -> Client:
        if not self.is_configured:
            raise ValueError(
                "Twilio no está configurado. Completa TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN y TWILIO_WHATSAPP_FROM en el archivo .env"
            )
        if self._client is None:
            self._client = Client(
                self.settings.twilio_account_sid,
                self.settings.twilio_auth_token,
            )
        return self._client

    def send_message(self, to_whatsapp: str, body: str) -> SendResult:
        """Envía un mensaje de WhatsApp."""
        if not body.strip():
            return SendResult(success=False, error="El mensaje no puede estar vacío.")

        to_addr = to_whatsapp if to_whatsapp.startswith("whatsapp:") else f"whatsapp:{to_whatsapp}"

        try:
            client = self._get_client()
            message = client.messages.create(
                body=body.strip(),
                from_=self.settings.twilio_whatsapp_from,
                to=to_addr,
            )
            logger.info("Mensaje enviado SID=%s to=%s", message.sid, to_addr)
            return SendResult(
                success=True,
                sid=message.sid,
                status=message.status,
                to_number=to_addr.replace("whatsapp:", ""),
            )
        except TwilioException as exc:
            friendly = self._friendly_error(exc)
            logger.error("Error Twilio: %s", exc)
            return SendResult(success=False, error=friendly, to_number=to_addr.replace("whatsapp:", ""))
        except ValueError as exc:
            return SendResult(success=False, error=str(exc))
        except Exception as exc:
            logger.exception("Error inesperado al enviar")
            return SendResult(
                success=False,
                error=f"Error inesperado: {exc}",
                to_number=to_addr.replace("whatsapp:", ""),
            )

    @staticmethod
    def _friendly_error(exc: TwilioException) -> str:
        msg = str(exc)
        lower = msg.lower()
        if "authenticate" in lower or "20003" in msg:
            return "Credenciales de Twilio inválidas. Verifica ACCOUNT_SID y AUTH_TOKEN."
        if "21608" in msg or "unverified" in lower:
            return "El número de destino no está verificado (cuenta de prueba Twilio)."
        if "63016" in msg or "outside" in lower:
            return "Ventana de 24h cerrada. El usuario debe escribir primero o usar plantilla aprobada."
        if "21211" in msg:
            return "Número de teléfono inválido. Revisa el formato E.164."
        if "63007" in msg:
            return "El canal de WhatsApp no está habilitado en tu cuenta Twilio."
        return f"Error de Twilio: {msg}"
