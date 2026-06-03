"""Acceso a SQLite para conversaciones y mensajes."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

from app.persistence.models import Conversation, Message
from app.utils.datetime_fmt import now_local_str
from app.utils.logger import get_logger
from app.utils.phone_validator import contact_key, local_number_key, split_e164

logger = get_logger("database")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_number TEXT NOT NULL UNIQUE,
    contact_name TEXT,
    last_message_at TEXT NOT NULL,
    last_message_preview TEXT DEFAULT '',
    unread_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('inbound', 'outbound')),
    twilio_sid TEXT,
    status TEXT DEFAULT 'received',
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_activity
    ON conversations(last_message_at DESC);
"""


class Database:
    """Repositorio SQLite thread-safe con una conexión por hilo."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "whatsapp_panel.db"
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self.dedupe_conversations()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _cursor(self):
        conn = self._connect()
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._cursor() as cur:
            cur.executescript(_SCHEMA)
            self._migrate_messages_source(cur)
        logger.info("Base de datos inicializada: %s", self.db_path)

    @staticmethod
    def _migrate_messages_source(cur: sqlite3.Cursor) -> None:
        cur.execute("PRAGMA table_info(messages)")
        cols = {row[1] for row in cur.fetchall()}
        if "source" not in cols:
            cur.execute("ALTER TABLE messages ADD COLUMN source TEXT DEFAULT ''")
            logger.info("Migración: columna messages.source añadida")

    def find_conversation_by_contact(self, contact_number: str) -> Optional[Conversation]:
        """Busca conversación comparando números normalizados."""
        key = contact_key(contact_number)
        for conv in self.list_conversations():
            if contact_key(conv.contact_number) == key:
                return conv
        return None

    def find_conversation_by_local_number(self, contact_number: str) -> Optional[Conversation]:
        """Busca por parte local (mismo teléfono con prefijo guardado distinto)."""
        local = local_number_key(contact_number)
        if len(local) < 8:
            return None
        matches = [
            conv
            for conv in self.list_conversations()
            if local_number_key(conv.contact_number) == local
        ]
        if not matches:
            return None
        return self._pick_primary_conversation(matches, prefer_named=True)

    def get_or_create_conversation(
        self,
        contact_number: str,
        contact_name: Optional[str] = None,
    ) -> Conversation:
        normalized = contact_key(contact_number)
        existing = self.find_conversation_by_contact(normalized)
        if not existing:
            existing = self.find_conversation_by_local_number(normalized)
        if existing:
            if len(normalized) > len(contact_key(existing.contact_number)):
                with self._cursor() as cur:
                    cur.execute(
                        "UPDATE conversations SET contact_number = ? WHERE id = ?",
                        (normalized, existing.id),
                    )
                existing = self.get_conversation(existing.id) or existing
            if contact_name and not existing.contact_name:
                self._update_contact_name(existing.id, contact_name)
                return self.get_conversation(existing.id) or existing
            return existing

        with self._cursor() as cur:
            now = now_local_str()
            cur.execute(
                """
                INSERT INTO conversations
                    (contact_number, contact_name, last_message_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (normalized, contact_name, now, now),
            )
            conv_id = cur.lastrowid
            cur.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
            row = cur.fetchone()
            logger.info("Nueva conversación: %s", normalized)
            return self._row_to_conversation(row)

    def _update_contact_name(self, conversation_id: int, name: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE conversations SET contact_name = ? WHERE id = ?",
                (name, conversation_id),
            )

    def update_conversation_contact(
        self,
        conversation_id: int,
        contact_name: Optional[str] = None,
        contact_number: Optional[str] = None,
        *,
        update_name: bool = False,
        update_number: bool = False,
    ) -> Optional[str]:
        """Actualiza nombre y/o número. Retorna mensaje de error o None si ok."""
        conv = self.get_conversation(conversation_id)
        if not conv:
            return "Conversación no encontrada."

        name_value = conv.contact_name
        number_value = conv.contact_number

        if update_name:
            name_value = (contact_name or "").strip() or None

        if update_number:
            if not contact_number or not contact_number.strip():
                return "Ingresa un número telefónico."
            number_value = contact_key(contact_number)
            existing = self.find_conversation_by_contact(number_value)
            if existing and existing.id != conversation_id:
                self.merge_conversations(conversation_id, existing.id)

        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE conversations
                SET contact_name = ?, contact_number = ?
                WHERE id = ?
                """,
                (name_value, number_value, conversation_id),
            )
        return None

    def add_message(
        self,
        conversation_id: int,
        body: str,
        direction: str,
        twilio_sid: Optional[str] = None,
        status: str = "received",
        update_preview: bool = True,
        increment_unread: bool = False,
        source: str = "",
        created_at: Optional[str] = None,
    ) -> Message:
        msg_time = created_at or now_local_str()
        preview = (body[:80] + "…") if len(body) > 80 else body

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages
                    (conversation_id, body, direction, twilio_sid, status, created_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, body, direction, twilio_sid, status, msg_time, source or ""),
            )
            msg_id = cur.lastrowid

            if update_preview:
                cur.execute(
                    "SELECT last_message_at FROM conversations WHERE id = ?",
                    (conversation_id,),
                )
                row = cur.fetchone()
                current_last = row["last_message_at"] if row else ""
                if not current_last or msg_time >= current_last:
                    unread_sql = ", unread_count = unread_count + 1" if increment_unread else ""
                    cur.execute(
                        f"""
                        UPDATE conversations
                        SET last_message_at = ?,
                            last_message_preview = ?
                            {unread_sql}
                        WHERE id = ?
                        """,
                        (msg_time, preview, conversation_id),
                    )

            cur.execute("SELECT * FROM messages WHERE id = ?", (msg_id,))
            return self._row_to_message(cur.fetchone())

    def update_message_created_at(self, twilio_sid: str, created_at: str) -> bool:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE messages SET created_at = ? WHERE twilio_sid = ?",
                (created_at, twilio_sid),
            )
            return cur.rowcount > 0

    def refresh_conversation_last_message(self, conversation_id: int) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT body, created_at FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (conversation_id,),
            )
            row = cur.fetchone()
            if not row:
                return
            body = row["body"] or ""
            preview = (body[:80] + "…") if len(body) > 80 else body
            cur.execute(
                """
                UPDATE conversations
                SET last_message_at = ?, last_message_preview = ?
                WHERE id = ?
                """,
                (row["created_at"], preview, conversation_id),
            )

    def list_conversations(self, search: str = "") -> List[Conversation]:
        query = """
            SELECT * FROM conversations
            ORDER BY last_message_at DESC
        """
        params: tuple = ()
        if search.strip():
            term = f"%{search.strip()}%"
            query = """
                SELECT * FROM conversations
                WHERE contact_number LIKE ? OR contact_name LIKE ?
                ORDER BY last_message_at DESC
            """
            params = (term, term)

        with self._cursor() as cur:
            cur.execute(query, params)
            return [self._row_to_conversation(r) for r in cur.fetchall()]

    def get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
            row = cur.fetchone()
            return self._row_to_conversation(row) if row else None

    def get_messages(self, conversation_id: int) -> List[Message]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (conversation_id,),
            )
            return [self._row_to_message(r) for r in cur.fetchall()]

    def mark_conversation_read(self, conversation_id: int) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE conversations SET unread_count = 0 WHERE id = ?",
                (conversation_id,),
            )

    def update_message_status(self, twilio_sid: str, status: str) -> bool:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE messages SET status = ? WHERE twilio_sid = ?",
                (status, twilio_sid),
            )
            return cur.rowcount > 0

    def get_message_by_id(self, message_id: int) -> Optional[Message]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
            row = cur.fetchone()
            return self._row_to_message(row) if row else None

    def merge_conversations(self, keep_id: int, remove_id: int) -> None:
        """Mueve mensajes de remove_id a keep_id y elimina el duplicado."""
        if keep_id == remove_id:
            return
        with self._cursor() as cur:
            cur.execute(
                "UPDATE messages SET conversation_id = ? WHERE conversation_id = ?",
                (keep_id, remove_id),
            )
            cur.execute(
                """
                UPDATE conversations
                SET unread_count = unread_count + COALESCE(
                    (SELECT unread_count FROM conversations WHERE id = ?), 0
                )
                WHERE id = ?
                """,
                (remove_id, keep_id),
            )
            cur.execute("DELETE FROM conversations WHERE id = ?", (remove_id,))
            logger.info("Fusionadas conversaciones %s -> %s", remove_id, keep_id)
        self.refresh_conversation_last_message(keep_id)

    def dedupe_conversations(self) -> None:
        """Fusiona conversaciones duplicadas del mismo número."""
        convs = self.list_conversations()
        key_groups: dict = {}
        for conv in convs:
            key_groups.setdefault(contact_key(conv.contact_number), []).append(conv)
        self._dedupe_groups(key_groups)
        local_groups: dict = {}
        for conv in self.list_conversations():
            local = local_number_key(conv.contact_number)
            if len(local) >= 8:
                local_groups.setdefault(local, []).append(conv)
        self._dedupe_groups(local_groups, prefer_named=True, use_best_number=True)

    def _dedupe_groups(
        self,
        groups: dict,
        *,
        prefer_named: bool = False,
        use_best_number: bool = False,
    ) -> None:
        for group in groups.values():
            if len(group) < 2:
                continue
            primary = self._pick_primary_conversation(group, prefer_named=prefer_named)
            best_number = contact_key(
                max((c.contact_number for c in group), key=lambda n: len(contact_key(n)))
            )
            for dup in group:
                if dup.id != primary.id:
                    self.merge_conversations(primary.id, dup.id)
            if use_best_number and contact_key(primary.contact_number) != best_number:
                with self._cursor() as cur:
                    cur.execute(
                        "UPDATE conversations SET contact_number = ? WHERE id = ?",
                        (best_number, primary.id),
                    )
            primary_conv = self.get_conversation(primary.id)
            if primary_conv and not primary_conv.contact_name:
                named = next((c for c in group if c.contact_name), None)
                if named and named.contact_name:
                    self._update_contact_name(primary.id, named.contact_name)

    @staticmethod
    def _pick_primary_conversation(group: List[Conversation], prefer_named: bool = False):
        if prefer_named:
            named = [c for c in group if c.contact_name]
            if named:
                return max(named, key=lambda c: c.last_message_at)
        return max(group, key=lambda c: (len(contact_key(c.contact_number)), c.last_message_at))

    def get_message_by_sid(self, twilio_sid: str) -> Optional[Message]:
        if not twilio_sid:
            return None
        with self._cursor() as cur:
            cur.execute("SELECT * FROM messages WHERE twilio_sid = ? LIMIT 1", (twilio_sid,))
            row = cur.fetchone()
            return self._row_to_message(row) if row else None

    def message_exists_by_sid(self, twilio_sid: str) -> bool:
        if not twilio_sid:
            return False
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM messages WHERE twilio_sid = ? LIMIT 1", (twilio_sid,))
            return cur.fetchone() is not None

    @staticmethod
    def _row_to_conversation(row: sqlite3.Row) -> Conversation:
        return Conversation(
            id=row["id"],
            contact_number=row["contact_number"],
            contact_name=row["contact_name"],
            last_message_at=row["last_message_at"],
            last_message_preview=row["last_message_preview"] or "",
            unread_count=row["unread_count"] or 0,
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Message:
        keys = row.keys()
        source = row["source"] if "source" in keys else ""
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            body=row["body"],
            direction=row["direction"],
            twilio_sid=row["twilio_sid"],
            status=row["status"] or "unknown",
            created_at=row["created_at"],
            source=source or "",
        )
