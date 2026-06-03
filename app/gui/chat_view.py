"""Área principal de conversación: burbujas y envío."""

from typing import Callable, List, Optional, Set

import customtkinter as ctk

from app.gui import styles as S
from app.persistence.models import Conversation, Message
from app.utils.datetime_fmt import format_date_separator, format_message_time, message_date_key


class DateSeparator(ctk.CTkFrame):
    """Etiqueta de día (Hoy, Ayer, fecha)."""

    def __init__(self, master, label: str):
        super().__init__(master, fg_color="transparent")
        wrap = ctk.CTkFrame(self, fg_color=S.BG_BUBBLE_IN, corner_radius=4)
        wrap.pack(pady=8)
        ctk.CTkLabel(
            wrap,
            text=label,
            font=S.FONT_TINY,
            text_color=S.TEXT_SECONDARY,
            padx=12,
            pady=4,
        ).pack()


class MessageBubble(ctk.CTkFrame):
    """Burbuja de mensaje enviado o recibido."""

    def __init__(self, master, message: Message):
        is_out = message.is_outbound
        bg = S.BG_BUBBLE_OUT if is_out else S.BG_BUBBLE_IN
        anchor_side = "e" if is_out else "w"
        pad_side = {"padx": (80, S.PADDING)} if is_out else {"padx": (S.PADDING, 80)}

        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=2, **pad_side)
        self._row = row

        bubble = ctk.CTkFrame(row, fg_color=bg, corner_radius=8)
        bubble.pack(anchor=anchor_side)

        ctk.CTkLabel(
            bubble,
            text=message.body,
            font=S.FONT_BODY,
            text_color=S.TEXT_PRIMARY,
            wraplength=S.BUBBLE_MAX_WIDTH,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=10, pady=(8, 2))

        time_str = format_message_time(message.created_at)
        ctk.CTkLabel(
            bubble,
            text=time_str,
            font=S.FONT_TINY,
            text_color=S.TEXT_MUTED,
            anchor="e",
        ).pack(anchor="e", padx=8, pady=(0, 6))

    @property
    def widget_row(self):
        return self._row


class ChatView(ctk.CTkFrame):
    """Panel derecho: cabecera, mensajes y compositor."""

    def __init__(self, master, on_send: Callable[[str], None]):
        super().__init__(master, fg_color=S.BG_CHAT, corner_radius=0)
        self._on_send = on_send
        self._current_conv: Optional[Conversation] = None
        self._shown_dates: Set[str] = set()
        self._last_message_id: Optional[int] = None

        self.empty_label = ctk.CTkLabel(
            self,
            text="Selecciona una conversación\no inicia un chat nuevo (+)",
            font=S.FONT_SUBTITLE,
            text_color=S.TEXT_MUTED,
            justify="center",
        )
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

        self.header = ctk.CTkFrame(self, fg_color=S.BG_HEADER, corner_radius=0, height=60)
        self.contact_label = ctk.CTkLabel(
            self.header,
            text="",
            font=S.FONT_TITLE,
            text_color=S.TEXT_PRIMARY,
            anchor="w",
        )
        self.subtitle_label = ctk.CTkLabel(
            self.header,
            text="",
            font=S.FONT_SMALL,
            text_color=S.TEXT_SECONDARY,
            anchor="w",
        )

        self.messages_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=S.BG_CHAT,
            corner_radius=0,
            scrollbar_button_color=S.BG_INPUT,
        )

        self.input_frame = ctk.CTkFrame(self, fg_color=S.BG_HEADER, corner_radius=0, height=70)
        self.message_entry = ctk.CTkTextbox(
            self.input_frame,
            height=44,
            fg_color=S.BG_INPUT,
            border_color=S.BG_INPUT,
            text_color=S.TEXT_PRIMARY,
            font=S.FONT_BODY,
            wrap="word",
        )
        self.send_btn = ctk.CTkButton(
            self.input_frame,
            text="Enviar",
            width=90,
            fg_color=S.ACCENT,
            hover_color=S.ACCENT_HOVER,
            command=self._send_current,
        )
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=S.FONT_TINY,
            text_color=S.TEXT_SECONDARY,
            anchor="w",
        )

        self.message_entry.bind("<Return>", self._on_enter)
        self.message_entry.bind("<Shift-Return>", lambda e: None)

    def _on_enter(self, event):
        if not event.state & 0x1:
            self._send_current()
            return "break"
        return None

    def _send_current(self):
        if not self._current_conv:
            return
        text = self.message_entry.get("1.0", "end").strip()
        if not text:
            return
        self.message_entry.delete("1.0", "end")
        self._on_send(text)

    def show_empty(self):
        self._hide_chat_widgets()
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

    def _hide_chat_widgets(self):
        self.empty_label.place_forget()
        for w in (self.header, self.messages_frame, self.input_frame, self.status_label):
            w.pack_forget()

    def _clear_messages(self):
        for child in self.messages_frame.winfo_children():
            child.destroy()
        self._shown_dates.clear()
        self._last_message_id = None

    def _maybe_add_date_separator(self, created_at: str):
        key = message_date_key(created_at)
        if not key or key in self._shown_dates:
            return
        self._shown_dates.add(key)
        DateSeparator(self.messages_frame, format_date_separator(created_at)).pack(fill="x")

    def _render_message(self, message: Message):
        self._maybe_add_date_separator(message.created_at)
        MessageBubble(self.messages_frame, message)
        self._last_message_id = message.id

    def load_conversation(self, conversation: Conversation, messages: List[Message]):
        self._current_conv = conversation
        self._hide_chat_widgets()
        self.empty_label.place_forget()

        self.contact_label.configure(text=conversation.display_name)
        self.subtitle_label.configure(text=conversation.contact_number)

        self.header.pack(fill="x")
        self.contact_label.pack(side="left", padx=S.PADDING, pady=(8, 0))
        self.subtitle_label.pack(side="left", padx=S.PADDING, pady=(0, 8))

        self.messages_frame.pack(fill="both", expand=True, padx=0, pady=0)
        self._clear_messages()

        for msg in messages:
            self._render_message(msg)

        self.input_frame.pack(fill="x", side="bottom")
        inner = ctk.CTkFrame(self.input_frame, fg_color="transparent")
        inner.pack(fill="x", padx=S.PADDING, pady=S.PADDING)
        self.message_entry.pack(in_=inner, side="left", fill="x", expand=True, padx=(0, 8))
        self.send_btn.pack(in_=inner, side="right")
        self.message_entry.focus_set()

        self.after(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        try:
            canvas = self.messages_frame._parent_canvas
            canvas.yview_moveto(1.0)
        except Exception:
            pass

    def append_message(self, message: Message) -> bool:
        """Añade un mensaje al hilo si pertenece al chat abierto."""
        if not self._current_conv:
            return False
        if message.conversation_id != self._current_conv.id:
            return False
        if self._last_message_id == message.id:
            return False

        self._render_message(message)
        self.after(50, self._scroll_to_bottom)
        return True

    def set_status(self, text: str, is_error: bool = False):
        color = S.ERROR if is_error else S.TEXT_SECONDARY
        self.status_label.configure(text=text, text_color=color)
        self.status_label.pack(fill="x", padx=S.PADDING, pady=4)

    def clear_status(self):
        self.status_label.configure(text="")
