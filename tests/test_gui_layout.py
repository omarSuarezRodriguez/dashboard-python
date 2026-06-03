"""Pruebas de layout GUI (sin Twilio)."""

import unittest

import customtkinter as ctk

from app.gui.chat_view import ChatView
from app.gui.sidebar import _format_preview
from app.persistence.models import Conversation, Message


class GUILayoutTests(unittest.TestCase):
    def setUp(self):
        self.root = ctk.CTk()
        self.root.withdraw()
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_chat_load_shows_message_widgets(self):
        chat = ChatView(self.root, lambda _b: None)
        chat.pack(fill="both", expand=True)
        conv = Conversation(
            id=1,
            contact_number="+573001112233",
            contact_name="Test",
            last_message_at="2024-06-01 12:00:00",
            last_message_preview="Hola",
            unread_count=0,
            created_at="2024-06-01 12:00:00",
        )
        messages = [
            Message(1, 1, "Hola", "inbound", "SM1", "received", "2024-06-01 12:00:00", ""),
            Message(2, 1, "Respuesta", "outbound", "SM2", "sent", "2024-06-01 12:01:00", "bot"),
        ]
        chat.load_conversation(conv, messages)
        self.root.update_idletasks()

        self.assertIsNotNone(chat._current_conv)
        self.assertEqual(len(chat._displayed_ids), 2)
        self.assertGreater(len(chat.messages_frame.winfo_children()), 0)

    def test_preview_single_line(self):
        self.assertEqual(
            _format_preview("Hola\nmundo"),
            "Hola mundo",
        )
        long_text = "a" * 50
        self.assertTrue(_format_preview(long_text).endswith("…"))
        self.assertEqual(_format_preview(None), "Sin mensajes")

if __name__ == "__main__":
    unittest.main()
