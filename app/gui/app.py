"""Ventana principal del panel de atención WhatsApp."""

import queue
import threading
from typing import Callable, Optional, TypeVar
import customtkinter as ctk

from app.gui.chat_view import ChatView
from app.gui.edit_contact_dialog import EditContactDialog
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
from app.utils.notification_sound import is_recent_incoming_message, play_incoming_message_sound

logger = get_logger("gui")

POLL_INTERVAL_MS = 300

T = TypeVar("T")


class WhatsAppPanelApp(ctk.CTk):
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
            logger.info("Webhook local off; sync Twilio activo")

        self._poll_events()
        self._show_status_hint()
        logger.info("Aplicación iniciada")

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        main = ctk.CTkFrame(self, fg_color=S.BG_DARK, corner_radius=0)
        main.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=0)
        main.grid_columnconfigure(1, weight=0)
        main.grid_columnconfigure(2, weight=1)

        self.sidebar = Sidebar(
            main,
            on_select=self._on_select_conversation,
            on_new_chat=self._open_new_chat,
            on_search=self._on_search,
            on_edit=self._on_edit_contact,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=0, pady=0)

        ctk.CTkFrame(main, width=1, fg_color=S.BG_INPUT, corner_radius=0).grid(
            row=0, column=1, sticky="ns", padx=0, pady=0
        )

        self.chat_view = ChatView(main, on_send=self._on_send_message)
        self.chat_view.grid(row=0, column=2, sticky="nsew", padx=0, pady=0)
        self.chat_view.show_empty()

        self.footer = ctk.CTkLabel(
            self, text="", font=S.FONT_TINY, text_color=S.TEXT_MUTED, anchor="w"
        )
        # Footer oculto: conserva actualizaciones de estado sin reservar espacio en pantalla.

    def _run_in_background(self, work: Callable[[], T], on_done: Callable[[T], None]) -> None:
        """Ejecuta trabajo bloqueante sin congelar la interfaz."""
        def runner():
            try:
                result = work()
            except Exception:
                logger.exception("Error en tarea en segundo plano")
                result = None
            self.after(0, lambda: on_done(result))

        threading.Thread(target=runner, daemon=True, name="BackgroundTask").start()

    def _show_status_hint(self):
        if self.settings.message_sync_enabled:
            sec = self.settings.message_sync_interval
            interval_txt = f"{int(sec)}s" if sec >= 1 and sec == int(sec) else f"{sec:.1f}s"
            self.footer.configure(
                text=f"Chat activo · sincroniza mensajes cada {interval_txt}",
                text_color=S.ACCENT,
            )
        elif self.settings.webhook_enabled:
            self.footer.configure(text=f"Webhook: {self.webhook.incoming_url}", text_color=S.ACCENT)
        else:
            self.footer.configure(
                text="Activa MESSAGE_SYNC_ENABLED en .env",
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
        if event_type == "new_message":
            self._on_new_message(payload)
        elif event_type == "incoming":
            # Webhook legacy
            try:
                result = self.conversations.process_incoming_webhook(
                    from_number=payload.get("from_number", ""),
                    body=payload.get("body", ""),
                    message_sid=payload.get("message_sid", ""),
                    profile_name=payload.get("profile_name", ""),
                )
                if result.is_new:
                    self._on_new_message(
                        {
                            "message_id": result.message.id,
                            "conversation_id": result.conversation.id,
                        }
                    )
            except Exception:
                logger.exception("Error procesando webhook entrante")
        elif event_type == "status":
            sid = payload.get("message_sid", "")
            if sid:
                self.conversations.update_message_status(sid, payload.get("status", ""))

    def _on_new_message(self, payload: dict):
        message_id = payload.get("message_id")
        conv_id = payload.get("conversation_id")
        if not message_id:
            return

        msg = self.db.get_message_by_id(message_id)
        if not msg:
            return

        if (
            msg.direction == "inbound"
            and self.settings.notification_sound_enabled
            and is_recent_incoming_message(msg.created_at)
        ):
            play_incoming_message_sound()

        if not self.conversations.is_same_conversation(self._selected_id, conv_id):
            self.after_idle(self._refresh_sidebar)
            conv = self.db.get_conversation(conv_id)
            if conv:
                preview = (msg.body[:45] + "…") if len(msg.body) > 45 else msg.body
                who = "Bot" if msg.source == "bot" else conv.display_name
                self.footer.configure(text=f"{who}: {preview}", text_color=S.ACCENT)
            return

        if self._selected_id != conv_id:
            self._selected_id = conv_id

        conv = self.db.get_conversation(conv_id)
        if conv:
            self.chat_view.set_current_conversation(conv)

        if self.chat_view.append_message(msg):
            if msg.direction == "inbound":
                self.conversations.open_conversation(conv_id)
            self.after_idle(self._refresh_sidebar)
            label = "Bot" if msg.source == "bot" else ("Tú" if msg.source == "agent" else "Recibido")
            self.footer.configure(text=f"{label} · {msg.body[:50]}", text_color=S.TEXT_SECONDARY)
        else:
            self.after_idle(self._refresh_sidebar)

    def _refresh_sidebar(self):
        self.sidebar.refresh(
            self.conversations.list_conversations(self._search_term),
            self._selected_id,
        )

    def _on_search(self, term: str):
        self._search_term = term
        self._refresh_sidebar()

    def _on_select_conversation(self, conversation_id: int):
        if conversation_id == self._selected_id:
            return

        self._selected_id = conversation_id
        self.sidebar.set_selection(conversation_id)

        conv = self.conversations.get_conversation(conversation_id)
        if conv:
            self.chat_view.prepare_conversation_header(conv)

        self.after(0, lambda cid=conversation_id: self._load_selected_conversation(cid))

    def _load_selected_conversation(self, conversation_id: int):
        if self._selected_id != conversation_id:
            return

        conv = self.conversations.open_conversation(conversation_id)
        if not conv:
            return

        self.sidebar.update_conversation(conv)
        messages = self.conversations.get_messages(conversation_id)
        self.chat_view.load_conversation(conv, messages)
        self.chat_view.clear_status()
        self.after_idle(self._show_status_hint)

    def _on_edit_contact(self, conversation_id: int, focus_field: str = "both"):
        conv = self.conversations.get_conversation(conversation_id)
        if not conv:
            return

        focus = "" if focus_field == "both" else focus_field

        def on_save(data):
            ok, error, updated = self.conversations.update_contact(
                data["conversation_id"],
                data["name"],
                data["e164"],
            )
            if not ok or not updated:
                self.chat_view.set_status(error or "No se pudo actualizar el contacto", is_error=True)
                return

            self.sidebar.update_conversation(updated)
            if self._selected_id == updated.id:
                self.chat_view.update_contact_info(updated)
            self._refresh_sidebar()
            self.chat_view.clear_status()

        EditContactDialog(self, conv, on_save, focus_field=focus)

    def _on_send_message(self, body: str):
        if not self._selected_id:
            return

        conv_id = self._selected_id

        def work():
            return self.conversations.send_message(conv_id, body)

        def on_done(result):
            if conv_id != self._selected_id:
                return
            if not result:
                self.chat_view.set_status("Error al enviar", is_error=True)
                return
            send_result, message = result
            if send_result.success and message:
                self.chat_view.append_message(message)
                self.chat_view.clear_status()
                self._refresh_sidebar()
            else:
                self.chat_view.set_status(send_result.error or "Error al enviar", is_error=True)

        self._run_in_background(work, on_done)

    def _open_new_chat(self):
        if not self.twilio.is_configured:
            self.chat_view.set_status(
                "Configura Twilio en .env antes de enviar.",
                is_error=True,
            )
            self.chat_view.show_empty()
            return

        def on_new(data):
            def work():
                return self.conversations.start_new_conversation(
                    e164_number=data["e164"],
                    first_message=data["message"],
                    contact_name=data.get("name"),
                )

            def on_done(result):
                if not result:
                    self.chat_view.set_status("Error al iniciar la conversación", is_error=True)
                    return
                conv, send_result = result
                if send_result.success and conv:
                    self._selected_id = conv.id
                    self._refresh_sidebar()
                    self.chat_view.load_conversation(
                        conv, self.conversations.get_messages(conv.id)
                    )
                    self.chat_view.clear_status()
                else:
                    self.chat_view.show_empty()
                    self.chat_view.set_status(
                        send_result.error or "No se pudo iniciar la conversación",
                        is_error=True,
                    )

            self._run_in_background(work, on_done)

        NewChatDialog(self, on_send_callback=on_new)


def run_app():
    settings = load_settings()
    setup_logging(settings.log_level)
    app = WhatsAppPanelApp(settings)
    app.mainloop()
