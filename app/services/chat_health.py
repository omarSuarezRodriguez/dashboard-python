"""Mantenimiento de chats principales: verificación periódica y reparación en segundo plano."""

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Callable, List, Optional, Tuple

from app.persistence.database import Database
from app.services.conversation_service import ConversationService
from app.services.message_sync import TwilioMessageSync
from app.utils.logger import get_logger
from app.utils.phone_validator import contact_key

logger = get_logger("chat_health")

# Chats que el usuario usa a diario (Martin + Mi número)
PRIMARY_CONTACTS: Tuple[Tuple[str, str], ...] = (
    ("+573001111032", "Martin"),
    ("+35699155990", "Mi numero"),
)

REBUILD_MARKER = Path(__file__).resolve().parents[2] / "data" / ".chats_rebuilt_v2"
MIN_REPAIR_INTERVAL_SEC = 3600


@dataclass
class ChatHealthResult:
    conversation_id: int
    contact_number: str
    issues: List[str]
    repaired: bool = False


class ChatHealthMonitor:
    """Verifica integridad sin bloquear la UI; repara solo si detecta problemas."""

    def __init__(
        self,
        database: Database,
        conversations: ConversationService,
        message_sync: TwilioMessageSync,
        event_queue: Queue,
        *,
        verify_interval_sec: float = 300.0,
        on_repair_done: Optional[Callable[[int], None]] = None,
    ):
        self.db = database
        self.conversations = conversations
        self.message_sync = message_sync
        self.event_queue = event_queue
        self.verify_interval = max(120.0, verify_interval_sec)
        self._on_repair_done = on_repair_done
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_repair: dict[int, float] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ChatHealth"
        )
        self._thread.start()
        logger.info("Verificación de chats cada %.0fs", self.verify_interval)

    def stop(self) -> None:
        self._stop.set()

    def ensure_primary_conversations(self) -> List[int]:
        """Garantiza que existan los dos contactos principales."""
        ids: List[int] = []
        for number, name in PRIMARY_CONTACTS:
            conv = self.db.get_or_create_conversation(number, name)
            ids.append(conv.id)
        self.db.dedupe_conversations()
        return ids

    def reset_and_resync_primary(self) -> List[ChatHealthResult]:
        """Limpia y vuelve a importar desde Twilio los dos chats principales."""
        results: List[ChatHealthResult] = []
        for number, name in PRIMARY_CONTACTS:
            conv = self.db.get_or_create_conversation(number, name)
            if name and not conv.contact_name:
                self.db._update_contact_name(conv.id, name)
            result = self._reset_conversation(conv.id, number)
            results.append(result)
        self.db.dedupe_conversations()
        REBUILD_MARKER.parent.mkdir(parents=True, exist_ok=True)
        REBUILD_MARKER.touch()
        return results

    def run_startup_maintenance_if_needed(self) -> bool:
        if REBUILD_MARKER.exists():
            return False
        logger.info("Primera limpieza de chats Martin y Mi numero")
        self.reset_and_resync_primary()
        return True

    def verify_primary_chats(self) -> List[ChatHealthResult]:
        results: List[ChatHealthResult] = []
        for number, name in PRIMARY_CONTACTS:
            conv = self.db.find_conversation_by_contact(number)
            if not conv:
                conv = self.db.get_or_create_conversation(number, name)
            issues = self.db.verify_conversation_integrity(conv.id)
            results.append(
                ChatHealthResult(
                    conversation_id=conv.id,
                    contact_number=conv.contact_number,
                    issues=issues,
                )
            )
        return results

    def repair_if_needed(self, conversation_id: int, issues: List[str]) -> bool:
        if not issues:
            return False
        now = time.monotonic()
        last = self._last_repair.get(conversation_id, 0.0)
        if now - last < MIN_REPAIR_INTERVAL_SEC:
            return False

        conv = self.db.get_conversation(conversation_id)
        if not conv:
            return False

        with self._lock:
            self._last_repair[conversation_id] = now
            self._reset_conversation(conversation_id, conv.contact_number)

        if self._on_repair_done:
            self._on_repair_done(conversation_id)
        self.event_queue.put(
            ("chat_repaired", {"conversation_id": conversation_id})
        )
        return True

    def _reset_conversation(self, conversation_id: int, contact_number: str) -> ChatHealthResult:
        removed = self.db.clear_conversation_messages(conversation_id)
        imported = 0
        if self.message_sync.twilio.is_configured:
            imported = self.message_sync.resync_contact(contact_number)
        logger.info(
            "Chat %s reiniciado: %s mensajes borrados, %s reimportados",
            contact_key(contact_number),
            removed,
            imported,
        )
        return ChatHealthResult(
            conversation_id=conversation_id,
            contact_number=contact_number,
            issues=[],
            repaired=True,
        )

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                for result in self.verify_primary_chats():
                    if result.issues:
                        logger.warning(
                            "Chat %s con problemas: %s",
                            result.contact_number,
                            ", ".join(result.issues),
                        )
                        self.repair_if_needed(result.conversation_id, result.issues)
            except Exception:
                logger.exception("Error en verificación de chats")
            self._stop.wait(self.verify_interval)
