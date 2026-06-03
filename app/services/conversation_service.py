"""Lógica de negocio para conversaciones y mensajes."""

from dataclasses import dataclass
from typing import List, Optional

from app.persistence.database import Database
from app.persistence.models import Conversation, Message
from app.services.twilio_service import SendResult, TwilioService
from app.utils.logger import get_logger
from app.utils.phone_validator import contact_key, normalize_incoming_number

logger = get_logger("conversation")


@dataclass
class IncomingMessageResult:
    conversation: Conversation
    message: Message
    is_new_conversation: bool


class ConversationService:
    """Orquesta persistencia y Twilio."""

    def __init__(self, database: Database, twilio: TwilioService):
        self.db = database
        self.twilio = twilio

    def list_conversations(self, search: str = "") -> List[Conversation]:
        return self.db.list_conversations(search)

    def get_messages(self, conversation_id: int) -> List[Message]:
        return self.db.get_messages(conversation_id)

    def get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        return self.db.get_conversation(conversation_id)

    def open_conversation(self, conversation_id: int) -> Optional[Conversation]:
        self.db.mark_conversation_read(conversation_id)
        return self.db.get_conversation(conversation_id)

    def process_incoming_webhook(
        self,
        from_number: str,
        body: str,
        message_sid: str,
        profile_name: str = "",
    ) -> IncomingMessageResult:
        """Guarda mensaje entrante y actualiza conversación."""
        if message_sid and self.db.message_exists_by_sid(message_sid):
            contact = normalize_incoming_number(from_number)
            conv = self.db.get_or_create_conversation(contact, profile_name or None)
            messages = self.db.get_messages(conv.id)
            last = messages[-1]
            return IncomingMessageResult(
                conversation=conv,
                message=last,
                is_new_conversation=False,
            )

        contact = normalize_incoming_number(from_number)
        name = profile_name.strip() or None

        is_new = self.db.find_conversation_by_contact(contact) is None

        conv = self.db.get_or_create_conversation(contact, name)
        msg = self.db.add_message(
            conversation_id=conv.id,
            body=body or "(sin contenido)",
            direction="inbound",
            twilio_sid=message_sid or None,
            status="received",
            increment_unread=True,
        )
        conv = self.db.get_conversation(conv.id) or conv
        return IncomingMessageResult(
            conversation=conv,
            message=msg,
            is_new_conversation=is_new,
        )

    def send_message(self, conversation_id: int, body: str) -> tuple:
        """Devuelve (SendResult, Message | None)."""
        conv = self.db.get_conversation(conversation_id)
        if not conv:
            return SendResult(success=False, error="Conversación no encontrada."), None

        to_whatsapp = f"whatsapp:{conv.contact_number}"
        result = self.twilio.send_message(to_whatsapp, body)

        if result.success:
            msg = self.db.add_message(
                conversation_id=conv.id,
                body=body,
                direction="outbound",
                twilio_sid=result.sid,
                status=result.status or "queued",
                increment_unread=False,
            )
            return result, msg
        return result, None

    def is_same_conversation(self, selected_id: Optional[int], conversation_id: int) -> bool:
        if not selected_id:
            return False
        if selected_id == conversation_id:
            return True
        selected = self.db.get_conversation(selected_id)
        incoming = self.db.get_conversation(conversation_id)
        if not selected or not incoming:
            return False
        return contact_key(selected.contact_number) == contact_key(incoming.contact_number)

    def start_new_conversation(
        self,
        e164_number: str,
        first_message: str,
        contact_name: Optional[str] = None,
    ) -> tuple:
        """Crea o reutiliza conversación y envía primer mensaje."""
        conv = self.db.get_or_create_conversation(e164_number, contact_name)
        result = self.send_message(conv.id, first_message)
        if result.success:
            conv = self.db.get_conversation(conv.id)
        return conv, result

    def update_message_status(self, twilio_sid: str, status: str) -> bool:
        return self.db.update_message_status(twilio_sid, status)
