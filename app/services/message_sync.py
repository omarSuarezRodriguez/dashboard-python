"""Sincroniza mensajes desde la API de Twilio (entrantes + bot + panel)."""

import threading
from datetime import datetime, timedelta, timezone
from queue import Queue

from app.services.conversation_service import ConversationService
from app.services.twilio_service import TwilioService
from app.utils.config import Settings
from app.utils.datetime_fmt import twilio_datetime_to_local_str
from app.utils.logger import get_logger
from app.utils.phone_validator import contact_key

logger = get_logger("message_sync")

SYNC_LIMIT = 100


class TwilioMessageSync:
    """Consulta Twilio y notifica mensajes nuevos a la GUI."""

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
        # Mínimo 0.5s (evita saturar la API de Twilio)
        self.interval = max(0.5, interval_seconds)
        self._thread = None
        self._stop = threading.Event()
        self._our_number = contact_key(settings.twilio_whatsapp_from)
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self.twilio.is_configured:
            logger.warning("Sincronización Twilio desactivada: credenciales incompletas")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="TwilioSync")
        self._thread.start()
        logger.info("Sincronización Twilio cada %.0fs", self.interval)

    def stop(self) -> None:
        self._stop.set()

    def _run_loop(self) -> None:
        self._sync_once()
        while not self._stop.is_set():
            self._stop.wait(self.interval)
            if self._stop.is_set():
                break
            try:
                self._sync_once()
            except Exception:
                logger.exception("Error en sincronización Twilio")

    def _sync_once(self) -> None:
        with self._lock:
            client = self.twilio._get_client()
            since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
            messages = client.messages.list(limit=SYNC_LIMIT, date_sent_after=since)

            for msg in reversed(list(messages)):
                sid = msg.sid or ""
                if not sid:
                    continue

                body = self._extract_body(msg)
                if not body:
                    continue

                msg_from = contact_key(getattr(msg, "from_", "") or "")
                msg_to = contact_key(getattr(msg, "to", "") or "")
                direction = (msg.direction or "").lower()
                status = msg.status or "unknown"
                sent_at = twilio_datetime_to_local_str(
                    getattr(msg, "date_sent", None) or getattr(msg, "date_created", None)
                )

                imported = None
                is_new = False

                if direction == "inbound" and msg_to == self._our_number:
                    imported, is_new = self.conversations.import_twilio_message(
                        message_sid=sid,
                        from_number=getattr(msg, "from_", ""),
                        to_number=getattr(msg, "to", ""),
                        body=body,
                        direction="inbound",
                        status=status,
                        created_at=sent_at,
                    )
                elif direction.startswith("outbound") and msg_from == self._our_number:
                    imported, is_new = self.conversations.import_twilio_message(
                        message_sid=sid,
                        from_number=getattr(msg, "from_", ""),
                        to_number=getattr(msg, "to", ""),
                        body=body,
                        direction="outbound",
                        status=status,
                        created_at=sent_at,
                    )

                if is_new and imported:
                    self.event_queue.put(
                        (
                            "new_message",
                            {
                                "message_id": imported.id,
                                "conversation_id": imported.conversation_id,
                            },
                        )
                    )

    def resync_contact(self, contact_number: str, *, days: int = 7, limit: int = 200) -> int:
        """Reimporta mensajes de Twilio para un contacto (tras limpiar el chat)."""
        if not self.twilio.is_configured:
            return 0

        contact = contact_key(contact_number)
        imported_count = 0

        with self._lock:
            client = self.twilio._get_client()
            since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
            messages = client.messages.list(limit=limit, date_sent_after=since)

            for msg in reversed(list(messages)):
                sid = msg.sid or ""
                if not sid:
                    continue

                body = self._extract_body(msg)
                if not body:
                    continue

                msg_from = contact_key(getattr(msg, "from_", "") or "")
                msg_to = contact_key(getattr(msg, "to", "") or "")
                direction = (msg.direction or "").lower()
                status = msg.status or "unknown"
                sent_at = twilio_datetime_to_local_str(
                    getattr(msg, "date_sent", None) or getattr(msg, "date_created", None)
                )

                matches = False
                if direction == "inbound" and msg_from == contact and msg_to == self._our_number:
                    matches = True
                elif direction.startswith("outbound") and msg_from == self._our_number and msg_to == contact:
                    matches = True

                if not matches:
                    continue

                _imported, is_new = self.conversations.import_twilio_message(
                    message_sid=sid,
                    from_number=getattr(msg, "from_", ""),
                    to_number=getattr(msg, "to", ""),
                    body=body,
                    direction=direction,
                    status=status,
                    created_at=sent_at,
                )
                if is_new:
                    imported_count += 1

        return imported_count

    @staticmethod
    def _extract_body(msg) -> str:
        body = (getattr(msg, "body", None) or "").strip()
        if body:
            return body
        if int(getattr(msg, "num_media", 0) or 0) > 0:
            return "(archivo multimedia)"
        return ""
