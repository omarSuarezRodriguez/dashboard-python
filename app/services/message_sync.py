"""Sincroniza mensajes entrantes/salientes desde la API de Twilio.

Permite chatear en el panel aunque el webhook de Twilio apunte al chatbot (/bot).
"""

import threading
import time
from datetime import datetime, timedelta, timezone
from queue import Queue

from app.services.conversation_service import ConversationService
from app.services.twilio_service import TwilioService
from app.utils.config import Settings
from app.utils.logger import get_logger
from app.utils.phone_validator import contact_key, normalize_incoming_number

logger = get_logger("message_sync")


class TwilioMessageSync:
    """Consulta Twilio periódicamente y publica mensajes nuevos en la cola de la GUI."""

    def __init__(
        self,
        settings: Settings,
        twilio: TwilioService,
        conversations: ConversationService,
        event_queue: Queue,
        interval_seconds: float = 3.0,
    ):
        self.settings = settings
        self.twilio = twilio
        self.conversations = conversations
        self.event_queue = event_queue
        self.interval = max(2.0, interval_seconds)
        self._thread = None
        self._stop = threading.Event()
        self._our_number = contact_key(settings.twilio_whatsapp_from)

    def start(self) -> None:
        if not self.twilio.is_configured:
            logger.warning("Sincronización Twilio desactivada: credenciales incompletas")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="TwilioSync")
        self._thread.start()
        logger.info("Sincronización Twilio activa cada %.0fs", self.interval)

    def stop(self) -> None:
        self._stop.set()

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._sync_once()
            except Exception:
                logger.exception("Error en sincronización Twilio")
            self._stop.wait(self.interval)

    def _sync_once(self) -> None:
        client = self.twilio._get_client()
        since = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
        messages = client.messages.list(limit=40, date_sent_after=since)

        for msg in reversed(list(messages)):
            sid = msg.sid or ""
            if not sid or self.conversations.db.message_exists_by_sid(sid):
                continue

            body = (msg.body or "").strip()
            if not body:
                continue

            msg_from = contact_key(getattr(msg, "from_", "") or "")
            msg_to = contact_key(getattr(msg, "to", "") or "")
            direction = (msg.direction or "").lower()
            status = msg.status or "unknown"

            if direction == "inbound" and msg_to == self._our_number:
                self._emit_incoming(
                    from_number=getattr(msg, "from_", ""),
                    body=body,
                    message_sid=sid,
                )
            elif direction == "outbound" and msg_from == self._our_number:
                self._import_outbound(
                    to_number=getattr(msg, "to", ""),
                    body=body,
                    message_sid=sid,
                    status=status,
                )

    def _emit_incoming(self, from_number: str, body: str, message_sid: str) -> None:
        self.event_queue.put(
            (
                "incoming",
                {
                    "from_number": from_number,
                    "body": body,
                    "message_sid": message_sid,
                    "profile_name": "",
                },
            )
        )
        logger.info("Sync entrante SID=%s from=%s", message_sid, from_number)

    def _import_outbound(
        self, to_number: str, body: str, message_sid: str, status: str
    ) -> None:
        contact = normalize_incoming_number(to_number)
        conv = self.conversations.db.get_or_create_conversation(contact)
        self.conversations.db.add_message(
            conversation_id=conv.id,
            body=body,
            direction="outbound",
            twilio_sid=message_sid,
            status=status,
            increment_unread=False,
        )
        self.event_queue.put(
            (
                "sync_outbound",
                {
                    "conversation_id": conv.id,
                    "message_sid": message_sid,
                },
            )
        )
        logger.info("Sync saliente SID=%s to=%s", message_sid, contact)
