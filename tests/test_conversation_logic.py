"""Pruebas de lógica de conversaciones (sin Twilio ni GUI)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.persistence.database import Database
from app.services.conversation_service import ConversationService
from app.utils.config import Settings
from app.utils.phone_validator import contact_key, local_number_key


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
        chat_verify_interval=300.0,
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

    def test_update_contact_name_and_number(self):
        conv = self.db.get_or_create_conversation("+573001112233", "Ana")
        ok, error, updated = self.svc.update_contact(conv.id, "María", "+573009998887")
        self.assertTrue(ok, error)
        self.assertEqual(updated.contact_name, "María")
        self.assertEqual(updated.contact_number, "+573009998887")

    def test_update_contact_duplicate_number_merges(self):
        c1 = self.db.get_or_create_conversation("+573001112233", "Contacto A")
        c2 = self.db.get_or_create_conversation("+573009998887", "Contacto B")
        ok, error, updated = self.svc.update_contact(c1.id, "Contacto A", "+573009998887")
        self.assertTrue(ok, error)
        self.assertEqual(updated.contact_number, "+573009998887")
        self.assertIsNone(self.db.get_conversation(c2.id))
        self.assertEqual(self.db.find_conversation_by_contact("+573009998887").id, c1.id)

    def test_dedupe_same_local_number_keeps_named_contact(self):
        now = "2024-01-01 12:00:00"
        with self.db._cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (contact_number, contact_name, last_message_at, created_at) VALUES (?, ?, ?, ?)",
                ("+5299155990", "Mi numero", now, now),
            )
            cur.execute(
                "INSERT INTO conversations (contact_number, last_message_at, created_at) VALUES (?, ?, ?)",
                ("+35699155990", now, now),
            )
        self.db.dedupe_conversations()
        matching = self.db.list_conversations()
        malta_locals = [
            c for c in matching if local_number_key(c.contact_number) == "99155990"
        ]
        self.assertEqual(len(malta_locals), 1)
        self.assertEqual(malta_locals[0].contact_name, "Mi numero")
        self.assertEqual(malta_locals[0].contact_number, "+35699155990")

    def test_import_uses_twilio_timestamp_and_keeps_order(self):
        conv = self.db.get_or_create_conversation("+573001112233")
        self.db.add_message(conv.id, "Reciente", "inbound", "SM-OLD", created_at="2026-06-03 10:00:00")
        msg, is_new = self.svc.import_twilio_message(
            "SM-LATE",
            "whatsapp:+573001112233",
            "whatsapp:+573242497352",
            "Antiguo",
            "inbound",
            created_at="2026-06-03 09:00:00",
        )
        self.assertTrue(is_new)
        self.assertEqual(msg.created_at, "2026-06-03 09:00:00")
        conv = self.db.get_conversation(conv.id)
        self.assertEqual(conv.last_message_preview, "Reciente")

        ordered = self.db.get_messages(conv.id)
        self.assertEqual([m.body for m in ordered], ["Antiguo", "Reciente"])

    def test_clear_and_verify_conversation(self):
        conv = self.db.get_or_create_conversation("+573001112233")
        self.db.add_message(conv.id, "Uno", "inbound", "SM-DUP", created_at="2026-06-03 10:00:00")
        self.db.add_message(conv.id, "Dos", "outbound", "SM-DUP", created_at="2026-06-03 10:01:00")
        issues = self.db.verify_conversation_integrity(conv.id)
        self.assertIn("duplicate_sids", issues)
        removed = self.db.clear_conversation_messages(conv.id)
        self.assertEqual(removed, 2)
        self.assertEqual(self.db.count_messages(conv.id), 0)
        self.assertEqual(self.db.verify_conversation_integrity(conv.id), [])

    def test_import_repairs_existing_timestamp(self):
        conv = self.db.get_or_create_conversation("+573001112233")
        self.db.add_message(
            conv.id,
            "Hola martin",
            "outbound",
            "SM-REPAIR",
            created_at="2026-06-03 08:00:00",
        )
        msg, is_new = self.svc.import_twilio_message(
            "SM-REPAIR",
            "whatsapp:+573242497352",
            "whatsapp:+573001112233",
            "Hola martin",
            "outbound",
            created_at="2026-06-03 03:15:00",
        )
        self.assertFalse(is_new)
        self.assertEqual(msg.created_at, "2026-06-03 03:15:00")


if __name__ == "__main__":
    unittest.main()
