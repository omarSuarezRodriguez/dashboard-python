"""Lógica de negocio para conversaciones y mensajes."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

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
    is_new: bool


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

    def import_twilio_message(
        self,
        message_sid: str,
        from_number: str,
        to_number: str,
        body: str,
        direction: str,
        status: str = "received",
        profile_name: str = "",
        created_at: Optional[str] = None,
    ) -> Tuple[Optional[Message], bool]:
        """
        Importa un mensaje desde Twilio (sync o webhook).
        Retorna (mensaje, True si es nuevo en la BD).
        """
        if message_sid and self.db.message_exists_by_sid(message_sid):
            existing = self.db.get_message_by_sid(message_sid)
            if existing and created_at and existing.created_at != created_at:
                self.db.update_message_created_at(message_sid, created_at)
                self.db.refresh_conversation_last_message(existing.conversation_id)
                existing = self.db.get_message_by_sid(message_sid)
            return existing, False

        text = (body or "").strip() or "(sin contenido)"
        dir_lower = (direction or "").lower()

        if dir_lower == "inbound" or dir_lower.startswith("inbound"):
            contact = normalize_incoming_number(from_number)
            name = (profile_name or "").strip() or None
            conv = self.db.get_or_create_conversation(contact, name)
            msg = self.db.add_message(
                conversation_id=conv.id,
                body=text,
                direction="inbound",
                twilio_sid=message_sid or None,
                status=status,
                increment_unread=True,
                source="",
                created_at=created_at,
            )
            return msg, True

        if dir_lower.startswith("outbound"):
            contact = normalize_incoming_number(to_number)
            conv = self.db.get_or_create_conversation(contact)
            msg = self.db.add_message(
                conversation_id=conv.id,
                body=text,
                direction="outbound",
                twilio_sid=message_sid or None,
                status=status,
                increment_unread=False,
                source="bot",
                created_at=created_at,
            )
            return msg, True

        logger.warning("Dirección Twilio no reconocida: %s", direction)
        return None, False

    def process_incoming_webhook(
        self,
        from_number: str,
        body: str,
        message_sid: str,
        profile_name: str = "",
    ) -> IncomingMessageResult:
        """Compatibilidad webhook: delega en import_twilio_message."""
        our = self.twilio.settings.twilio_whatsapp_from
        msg, is_new = self.import_twilio_message(
            message_sid=message_sid,
            from_number=from_number,
            to_number=our,
            body=body,
            direction="inbound",
            status="received",
            profile_name=profile_name,
        )
        if not msg:
            raise ValueError("No se pudo importar mensaje entrante")
        conv = self.db.get_conversation(msg.conversation_id)
        return IncomingMessageResult(conversation=conv, message=msg, is_new=is_new)

    def send_message(self, conversation_id: int, body: str) -> Tuple[SendResult, Optional[Message]]:
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
                source="agent",
            )
            return result, msg
        return result, None

    def is_same_conversation(
        self, selected_id: Optional[int], conversation_id: Optional[int]
    ) -> bool:
        if not selected_id or not conversation_id:
            return False
        if selected_id == conversation_id:
            return True
        selected = self.db.get_conversation(selected_id)
        other = self.db.get_conversation(conversation_id)
        if not selected or not other:
            return False
        return contact_key(selected.contact_number) == contact_key(other.contact_number)

    def start_new_conversation(
        self,
        e164_number: str,
        first_message: str,
        contact_name: Optional[str] = None,
    ) -> Tuple[Optional[Conversation], SendResult]:
        conv = self.db.get_or_create_conversation(e164_number, contact_name)
        send_result, _msg = self.send_message(conv.id, first_message)
        if send_result.success:
            conv = self.db.get_conversation(conv.id)
        return conv, send_result

    def update_message_status(self, twilio_sid: str, status: str) -> bool:
        return self.db.update_message_status(twilio_sid, status)

    def update_contact(
        self,
        conversation_id: int,
        contact_name: Optional[str],
        contact_number_e164: Optional[str],
    ) -> Tuple[bool, str, Optional[Conversation]]:
        """Actualiza nombre y número del contacto."""
        error = self.db.update_conversation_contact(
            conversation_id,
            contact_name=contact_name,
            contact_number=contact_number_e164,
            update_name=True,
            update_number=True,
        )
        if error:
            return False, error, None
        conv = self.db.get_conversation(conversation_id)
        return True, "", conv
