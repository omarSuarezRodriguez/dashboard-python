"""Limpia y reimporta los chats de Martin y Mi numero desde Twilio."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.persistence.database import Database
from app.services.chat_health import ChatHealthMonitor, REBUILD_MARKER
from app.services.conversation_service import ConversationService
from app.services.message_sync import TwilioMessageSync
from app.services.twilio_service import TwilioService
from app.utils.config import load_settings
from app.utils.logger import setup_logging
from queue import Queue


def main():
    settings = load_settings()
    setup_logging(settings.log_level)
    db = Database()
    twilio = TwilioService(settings)
    conversations = ConversationService(db, twilio)
    queue = Queue()
    sync = TwilioMessageSync(settings, twilio, conversations, queue)
    health = ChatHealthMonitor(db, conversations, sync, queue)

    if REBUILD_MARKER.exists():
        REBUILD_MARKER.unlink()

    results = health.reset_and_resync_primary()
    for r in results:
        count = db.count_messages(r.conversation_id)
        print(f"{r.contact_number}: reimportados, mensajes en BD = {count}")
    print("Listo. Reinicia la app para ver los chats limpios.")


if __name__ == "__main__":
    main()
