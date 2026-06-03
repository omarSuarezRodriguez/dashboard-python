"""Pruebas de lógica de conversaciones (sin Twilio ni GUI)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.persistence.database import Database
from app.services.conversation_service import ConversationService
from app.utils.config import Settings
from app.utils.phone_validator import contact_key


def _settings():
    return Settings(
        twilio_account_sid="ACtest",
        twilio_auth_token="token",
        twilio_whatsapp_from="whatsapp:+573242497352",
        webhook_port=5001,
        webhook_public_url="",
        webhook_enabled=False,
        message_sync_enabled=True,
        message_sync_interval=3,
    )


class ConversationLogicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "test.db"
        self.db = Database(db_path)
        self.twilio = MagicMock()
        self.twilio.settings = _settings()
        self.svc = ConversationService(self.db, self.twilio)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_inbound_new(self):
        msg, is_new = self.svc.import_twilio_message(
            "SM1",
            "whatsapp:+573001112233",
            "whatsapp:+573242497352",
            "Hola",
            "inbound",
        )
        self.assertTrue(is_new)
        self.assertEqual(msg.direction, "inbound")

    def test_import_inbound_duplicate(self):
        self.svc.import_twilio_message("SM1", "whatsapp:+573001112233", "whatsapp:+573242497352", "Hola", "inbound")
        msg, is_new = self.svc.import_twilio_message(
            "SM1", "whatsapp:+573001112233", "whatsapp:+573242497352", "Hola", "inbound"
        )
        self.assertFalse(is_new)
        self.assertEqual(msg.twilio_sid, "SM1")

    def test_import_outbound_bot(self):
        msg, is_new = self.svc.import_twilio_message(
            "SM2",
            "whatsapp:+573242497352",
            "whatsapp:+573001112233",
            "Respuesta bot",
            "outbound-api",
        )
        self.assertTrue(is_new)
        self.assertEqual(msg.source, "bot")

    def test_agent_not_overwritten_by_bot_import(self):
        conv = self.db.get_or_create_conversation("+573001112233")
        self.db.add_message(conv.id, "Yo", "outbound", "SM3", source="agent")
        msg, is_new = self.svc.import_twilio_message(
            "SM3",
            "whatsapp:+573242497352",
            "whatsapp:+573001112233",
            "Yo",
            "outbound-api",
        )
        self.assertFalse(is_new)
        self.assertEqual(msg.source, "agent")

    def test_dedupe_conversations(self):
        now = "2024-01-01 12:00:00"
        with self.db._cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (contact_number, last_message_at, created_at) VALUES (?, ?, ?)",
                ("+573009998887", now, now),
            )
            cur.execute(
                "INSERT INTO conversations (contact_number, last_message_at, created_at) VALUES (?, ?, ?)",
                ("whatsapp:+573009998887", now, now),
            )
        self.db.dedupe_conversations()
        matching = [
            c for c in self.db.list_conversations()
            if contact_key(c.contact_number) == "+573009998887"
        ]
        self.assertEqual(len(matching), 1)

    def test_is_same_conversation(self):
        c1 = self.db.get_or_create_conversation("+573001112233")
        now = "2024-01-01 12:00:00"
        with self.db._cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (contact_number, last_message_at, created_at) VALUES (?, ?, ?)",
                ("whatsapp:+573001112233", now, now),
            )
            c2_id = cur.lastrowid
        self.assertTrue(self.svc.is_same_conversation(c1.id, c2_id))


if __name__ == "__main__":
    unittest.main()
