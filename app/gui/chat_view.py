"""Área principal de conversación: burbujas y envío."""

from typing import Callable, List, Optional, Set

import customtkinter as ctk

from app.gui import styles as S
from app.persistence.models import Conversation, Message
from app.utils.datetime_fmt import format_date_separator, format_message_time, message_date_key


class DateSeparator(ctk.CTkFrame):
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
    def __init__(self, master, message: Message):
        is_out = message.is_outbound
        bg = S.BG_BUBBLE_OUT if is_out else S.BG_BUBBLE_IN
        anchor_side = "e" if is_out else "w"
        pad_side = {"padx": (80, S.PADDING)} if is_out else {"padx": (S.PADDING, 80)}

        super().__init__(master, fg_color="transparent")
        self.pack(fill="x", pady=2, **pad_side)

        bubble = ctk.CTkFrame(self, fg_color=bg, corner_radius=8)
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
        label = message.sender_label
        meta = f"{label} · {time_str}" if label else time_str
        ctk.CTkLabel(
            bubble,
            text=meta,
            font=S.FONT_TINY,
            text_color=S.TEXT_MUTED,
            anchor="e",
        ).pack(anchor="e", padx=8, pady=(0, 6))


class ChatView(ctk.CTkFrame):
    """Panel derecho: cabecera, mensajes y compositor (widgets creados una sola vez)."""

    def __init__(self, master, on_send: Callable[[str], None]):
        super().__init__(master, fg_color=S.BG_CHAT, corner_radius=0)
        self._on_send = on_send
        self._current_conv: Optional[Conversation] = None
        self._shown_dates: Set[str] = set()
        self._displayed_ids: Set[int] = set()

        self.empty_label = ctk.CTkLabel(
            self,
            text="Selecciona una conversación\no inicia un chat nuevo (+)",
            font=S.FONT_SUBTITLE,
            text_color=S.TEXT_MUTED,
            justify="center",
        )

        self.header = ctk.CTkFrame(self, fg_color=S.BG_HEADER, corner_radius=0, height=60)
        self.header.pack_propagate(False)
        self.contact_label = ctk.CTkLabel(
            self.header, text="", font=S.FONT_TITLE, text_color=S.TEXT_PRIMARY, anchor="w"
        )
        self.contact_label.pack(side="left", padx=S.PADDING, pady=12)
        self.subtitle_label = ctk.CTkLabel(
            self.header, text="", font=S.FONT_SMALL, text_color=S.TEXT_SECONDARY, anchor="w"
        )
        self.subtitle_label.pack(side="left", padx=(0, S.PADDING))

        self.messages_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=S.BG_CHAT,
            corner_radius=0,
            scrollbar_button_color=S.BG_INPUT,
        )

        self.input_frame = ctk.CTkFrame(self, fg_color=S.BG_HEADER, corner_radius=0, height=70)
        self.input_frame.pack_propagate(False)
        input_inner = ctk.CTkFrame(self.input_frame, fg_color="transparent")
        input_inner.pack(fill="both", expand=True, padx=S.PADDING, pady=S.PADDING)
        self.message_entry = ctk.CTkTextbox(
            input_inner,
            height=44,
            fg_color=S.BG_INPUT,
            border_color=S.BG_INPUT,
            text_color=S.TEXT_PRIMARY,
            font=S.FONT_BODY,
            wrap="word",
        )
        self.message_entry.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.send_btn = ctk.CTkButton(
            input_inner,
            text="Enviar",
            width=90,
            fg_color=S.ACCENT,
            hover_color=S.ACCENT_HOVER,
            command=self._send_current,
        )
        self.send_btn.pack(side="right")

        self.status_label = ctk.CTkLabel(
            self, text="", font=S.FONT_TINY, text_color=S.TEXT_SECONDARY, anchor="w"
        )

        self.message_entry.bind("<Return>", self._on_enter)
        self.show_empty()

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
        self._current_conv = None
        self._displayed_ids.clear()
        self._hide_chat()
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

    def _hide_chat(self):
        self.empty_label.place_forget()
        self.header.pack_forget()
        self.messages_frame.pack_forget()
        self.input_frame.pack_forget()
        self.status_label.pack_forget()

    def _show_chat_layout(self):
        self.empty_label.place_forget()
        self.header.pack(fill="x")
        self.messages_frame.pack(fill="both", expand=True)
        self.input_frame.pack(fill="x", side="bottom")

    def _clear_message_list(self):
        for child in self.messages_frame.winfo_children():
            child.destroy()
        self._shown_dates.clear()
        self._displayed_ids.clear()

    def _render_message(self, message: Message):
        if message.id in self._displayed_ids:
            return
        self._maybe_add_date_separator(message.created_at)
        MessageBubble(self.messages_frame, message)
        self._displayed_ids.add(message.id)

    def _maybe_add_date_separator(self, created_at: str):
        key = message_date_key(created_at)
        if not key or key in self._shown_dates:
            return
        self._shown_dates.add(key)
        DateSeparator(self.messages_frame, format_date_separator(created_at)).pack(fill="x")

    def load_conversation(self, conversation: Conversation, messages: List[Message]):
        self._current_conv = conversation
        self.contact_label.configure(text=conversation.display_name)
        self.subtitle_label.configure(text=conversation.contact_number)
        self._show_chat_layout()
        self._clear_message_list()
        for msg in messages:
            self._render_message(msg)
        self.message_entry.focus_set()
        self.after(80, self._scroll_to_bottom)

    def append_message(self, message: Message) -> bool:
        if not self._current_conv:
            return False
        if message.conversation_id != self._current_conv.id:
            return False
        if message.id in self._displayed_ids:
            return False
        self._render_message(message)
        self.after(80, self._scroll_to_bottom)
        return True

    def _scroll_to_bottom(self):
        try:
            self.messages_frame._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def set_status(self, text: str, is_error: bool = False):
        color = S.ERROR if is_error else S.TEXT_SECONDARY
        self.status_label.configure(text=text, text_color=color)
        self.status_label.pack(fill="x", padx=S.PADDING, pady=4)

    def clear_status(self):
        self.status_label.configure(text="")
        self.status_label.pack_forget()
