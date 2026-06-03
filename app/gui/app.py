"""Ventana principal del panel de atención WhatsApp."""

import queue
from typing import Optional

import customtkinter as ctk

from app.gui.chat_view import ChatView
from app.gui.new_chat_dialog import NewChatDialog
from app.gui.sidebar import Sidebar
from app.gui import styles as S
from app.persistence.database import Database
from app.services.conversation_service import ConversationService
from app.services.twilio_service import TwilioService
from app.services.message_sync import TwilioMessageSync
from app.services.webhook_server import WebhookServer
from app.utils.config import Settings, load_settings
from app.utils.logger import get_logger, setup_logging

logger = get_logger("gui")

POLL_INTERVAL_MS = 300


class WhatsAppPanelApp(ctk.CTk):
    """Aplicación de escritorio: lista de chats + conversación activa."""

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.title("Panel WhatsApp — Twilio")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.configure(fg_color=S.BG_DARK)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

        self.db = Database()
        self.twilio = TwilioService(settings)
        self.conversations = ConversationService(self.db, self.twilio)
        self.event_queue: queue.Queue = queue.Queue()
        self.webhook = WebhookServer(
            settings.webhook_host,
            settings.webhook_port,
            self.event_queue,
            public_base_url=settings.webhook_public_url,
        )
        self.message_sync = TwilioMessageSync(
            settings,
            self.twilio,
            self.conversations,
            self.event_queue,
            interval_seconds=settings.message_sync_interval,
        )

        self._selected_id: Optional[int] = None
        self._search_term = ""

        self._build_layout()
        self._refresh_sidebar()

        if settings.message_sync_enabled:
            self.message_sync.start()
        if settings.webhook_enabled:
            self.webhook.start()
        else:
            logger.info(
                "Webhook local desactivado (chatbot puede usar puerto %s). "
                "Recepción vía sincronización Twilio.",
                settings.webhook_port,
            )

        self._poll_events()
        self._show_status_hint()

        logger.info("Aplicación iniciada")

    def _build_layout(self):
        main = ctk.CTkFrame(self, fg_color=S.BG_DARK, corner_radius=0)
        main.pack(fill="both", expand=True)

        self.sidebar = Sidebar(
            main,
            on_select=self._on_select_conversation,
            on_new_chat=self._open_new_chat,
            on_search=self._on_search,
        )
        self.sidebar.pack(side="left", fill="y")

        sep = ctk.CTkFrame(main, width=1, fg_color=S.BG_INPUT, corner_radius=0)
        sep.pack(side="left", fill="y")

        self.chat_view = ChatView(main, on_send=self._on_send_message)
        self.chat_view.pack(side="left", fill="both", expand=True)
        self.chat_view.show_empty()

        self.footer = ctk.CTkLabel(
            self,
            text="",
            font=S.FONT_TINY,
            text_color=S.TEXT_MUTED,
            anchor="w",
        )
        self.footer.pack(fill="x", padx=S.PADDING, pady=4)

    def _show_status_hint(self):
        if self.settings.message_sync_enabled:
            sec = int(self.settings.message_sync_interval)
            self.footer.configure(
                text=(
                    f"Chat activo · sincronizando con Twilio cada {sec}s "
                    "(el chatbot puede seguir en /bot)"
                ),
                text_color=S.ACCENT,
            )
        elif self.settings.webhook_enabled:
            self.footer.configure(
                text=f"Webhook: {self.webhook.incoming_url}",
                text_color=S.ACCENT,
            )
        else:
            self.footer.configure(
                text="Activa MESSAGE_SYNC_ENABLED o WEBHOOK_ENABLED en .env",
                text_color=S.ERROR,
            )

    def _poll_events(self):
        try:
            while True:
                event_type, payload = self.event_queue.get_nowait()
                self._handle_event(event_type, payload)
        except queue.Empty:
            pass
        self.after(POLL_INTERVAL_MS, self._poll_events)

    def _handle_event(self, event_type: str, payload: dict):
        if event_type == "incoming":
            result = self.conversations.process_incoming_webhook(
                from_number=payload.get("from_number", ""),
                body=payload.get("body", ""),
                message_sid=payload.get("message_sid", ""),
                profile_name=payload.get("profile_name", ""),
            )
            self._refresh_sidebar()

            if self.conversations.is_same_conversation(
                self._selected_id, result.conversation.id
            ):
                self._selected_id = result.conversation.id
                self.chat_view.append_message(result.message)
                self.conversations.open_conversation(result.conversation.id)
                self._refresh_sidebar()
                self.footer.configure(
                    text=f"Recibido · {result.message.body[:40]}",
                    text_color=S.TEXT_SECONDARY,
                )
            else:
                preview = (result.message.body[:50] + "…") if len(result.message.body) > 50 else result.message.body
                self.footer.configure(
                    text=f"Nuevo mensaje de {result.conversation.display_name}: {preview}",
                    text_color=S.ACCENT,
                )
        elif event_type == "sync_outbound":
            conv_id = payload.get("conversation_id")
            if self.conversations.is_same_conversation(self._selected_id, conv_id):
                self._selected_id = conv_id
                conv = self.conversations.get_conversation(conv_id)
                if conv:
                    msgs = self.conversations.get_messages(conv_id)
                    self.chat_view.load_conversation(conv, msgs)
            self._refresh_sidebar()
        elif event_type == "status":
            sid = payload.get("message_sid", "")
            status = payload.get("status", "")
            if sid:
                self.conversations.update_message_status(sid, status)
                if self._selected_id:
                    conv = self.conversations.get_conversation(self._selected_id)
                    if conv:
                        msgs = self.conversations.get_messages(self._selected_id)
                        self.chat_view.load_conversation(conv, msgs)

    def _refresh_sidebar(self):
        convs = self.conversations.list_conversations(self._search_term)
        self.sidebar.refresh(convs, self._selected_id)

    def _on_search(self, term: str):
        self._search_term = term
        self._refresh_sidebar()

    def _on_select_conversation(self, conversation_id: int):
        self._selected_id = conversation_id
        conv = self.conversations.open_conversation(conversation_id)
        if not conv:
            return
        messages = self.conversations.get_messages(conversation_id)
        self.chat_view.load_conversation(conv, messages)
        self.chat_view.clear_status()
        self._refresh_sidebar()
        self._show_status_hint()

    def _on_send_message(self, body: str):
        if not self._selected_id:
            return
        self.chat_view.set_status("Enviando…")
        self.update_idletasks()

        result, message = self.conversations.send_message(self._selected_id, body)
        if result.success and message:
            self.chat_view.append_message(message)
            self.chat_view.clear_status()
            self._refresh_sidebar()
        elif result.success:
            conv = self.conversations.get_conversation(self._selected_id)
            if conv:
                msgs = self.conversations.get_messages(self._selected_id)
                self.chat_view.load_conversation(conv, msgs)
            self._refresh_sidebar()
        else:
            self.chat_view.set_status(result.error or "Error al enviar", is_error=True)

    def _open_new_chat(self):
        if not self.twilio.is_configured:
            self.chat_view.set_status(
                "Configura las variables Twilio en .env antes de enviar mensajes.",
                is_error=True,
            )
            self.chat_view.show_empty()
            return

        def on_new(data):
            self.chat_view.set_status("Enviando primer mensaje…")
            self.update_idletasks()
            conv, result = self.conversations.start_new_conversation(
                e164_number=data["e164"],
                first_message=data["message"],
                contact_name=data.get("name"),
            )
            if result.success and conv:
                self._selected_id = conv.id
                self._refresh_sidebar()
                messages = self.conversations.get_messages(conv.id)
                self.chat_view.load_conversation(conv, messages)
                self.chat_view.clear_status()
            else:
                self.chat_view.show_empty()
                self.chat_view.set_status(
                    result.error or "No se pudo iniciar la conversación",
                    is_error=True,
                )

        NewChatDialog(self, on_send_callback=on_new)


def run_app():
    settings = load_settings()
    setup_logging(settings.log_level)
    app = WhatsAppPanelApp(settings)
    app.mainloop()
