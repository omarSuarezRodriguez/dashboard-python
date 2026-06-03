"""Pruebas del sonido de notificación."""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from app.utils.notification_sound import _write_messenger_like_wav, is_recent_incoming_message


class NotificationSoundTests(unittest.TestCase):
    def test_is_recent_incoming_message(self):
        recent = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        old = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        self.assertTrue(is_recent_incoming_message(recent))
        self.assertFalse(is_recent_incoming_message(old, max_age_sec=90.0))

    def test_generates_wav_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incoming_message.wav"
            _write_messenger_like_wav(path)
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
