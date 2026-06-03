"""Acceso a SQLite para conversaciones y mensajes."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

from app.persistence.models import Conversation, Message
from app.utils.datetime_fmt import now_local_str
from app.utils.logger import get_logger
from app.utils.phone_validator import contact_key

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
        logger.info("Base de datos inicializada: %s", self.db_path)

    def find_conversation_by_contact(self, contact_number: str) -> Optional[Conversation]:
        """Busca conversación comparando números normalizados."""
        key = contact_key(contact_number)
        for conv in self.list_conversations():
            if contact_key(conv.contact_number) == key:
                return conv
        return None

    def get_or_create_conversation(
        self,
        contact_number: str,
        contact_name: Optional[str] = None,
    ) -> Conversation:
        normalized = contact_key(contact_number)
        existing = self.find_conversation_by_contact(normalized)
        if existing:
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

    def add_message(
        self,
        conversation_id: int,
        body: str,
        direction: str,
        twilio_sid: Optional[str] = None,
        status: str = "received",
        update_preview: bool = True,
        increment_unread: bool = False,
    ) -> Message:
        now = now_local_str()
        preview = (body[:80] + "…") if len(body) > 80 else body

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages
                    (conversation_id, body, direction, twilio_sid, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, body, direction, twilio_sid, status, now),
            )
            msg_id = cur.lastrowid

            if update_preview:
                unread_sql = ", unread_count = unread_count + 1" if increment_unread else ""
                cur.execute(
                    f"""
                    UPDATE conversations
                    SET last_message_at = ?,
                        last_message_preview = ?
                        {unread_sql}
                    WHERE id = ?
                    """,
                    (now, preview, conversation_id),
                )

            cur.execute("SELECT * FROM messages WHERE id = ?", (msg_id,))
            return self._row_to_message(cur.fetchone())

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
                ORDER BY created_at ASC
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
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            body=row["body"],
            direction=row["direction"],
            twilio_sid=row["twilio_sid"],
            status=row["status"] or "unknown",
            created_at=row["created_at"],
        )
