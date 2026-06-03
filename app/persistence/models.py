"""Modelos de datos para conversaciones y mensajes."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Conversation:
    id: int
    contact_number: str
    contact_name: Optional[str]
    last_message_at: str
    last_message_preview: str
    unread_count: int
    created_at: str

    @property
    def display_name(self) -> str:
        return self.contact_name or self.contact_number


@dataclass
class Message:
    id: int
    conversation_id: int
    body: str
    direction: str  # inbound | outbound
    twilio_sid: Optional[str]
    status: str
    created_at: str
    source: str = ""  # bot | agent | vacío (contacto)

    @property
    def is_outbound(self) -> bool:
        return self.direction == "outbound"

    @property
    def sender_label(self) -> str:
        if self.direction == "inbound":
            return ""
        if self.source == "bot":
            return "Bot"
        if self.source == "agent":
            return "Tú"
        return ""
