"""Área principal de conversación: burbujas y envío."""

from typing import Callable, List, Optional, Set

import customtkinter as ctk

from app.gui import styles as S
from app.persistence.models import Conversation, Message
from app.utils.datetime_fmt import format_date_separator, format_message_time, message_date_key


class DateSeparator(ctk.CTkFrame):
    def __init__(self, master, label: str):
        super().__init__(master, fg_color=S.BG_CHAT, corner_radius=0)
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
        pad_side = {"padx": (48, S.PADDING)} if is_out else {"padx": (S.PADDING, 48)}

        super().__init__(master, fg_color=S.BG_CHAT, corner_radius=0)
        self.pack(fill="x", pady=3, **pad_side)

        bubble = ctk.CTkFrame(self, fg_color=bg, corner_radius=10)
        bubble.pack(anchor=anchor_side)

        ctk.CTkLabel(
            bubble,
            text=message.body,
            font=S.FONT_BODY,
            text_color=S.TEXT_PRIMARY,
            wraplength=S.BUBBLE_MAX_WIDTH,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(10, 2))

        time_str = format_message_time(message.created_at)
        label = message.sender_label
        meta = f"{label} · {time_str}" if label else time_str
        ctk.CTkLabel(
            bubble,
            text=meta,
            font=S.FONT_TINY,
            text_color=S.TEXT_MUTED,
            anchor="e",
        ).pack(anchor="e", padx=10, pady=(0, 8))


class ChatView(ctk.CTkFrame):
    """Panel derecho con layout en grid (estable en Windows/CTk)."""

    def __init__(self, master, on_send: Callable[[str], None]):
        super().__init__(master, fg_color=S.BG_CHAT, corner_radius=0)
        self._on_send = on_send
        self._current_conv: Optional[Conversation] = None
        self._shown_dates: Set[str] = set()
        self._displayed_ids: Set[int] = set()

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.empty_label = ctk.CTkLabel(
            self,
            text="Selecciona una conversación\no inicia un chat nuevo (+)",
            font=S.FONT_SUBTITLE,
            text_color=S.TEXT_MUTED,
            justify="center",
            fg_color=S.BG_CHAT,
        )

        self.header = ctk.CTkFrame(self, fg_color=S.BG_HEADER, corner_radius=0, height=64)
        self.header.grid_propagate(False)
        self.header.grid_columnconfigure(0, weight=1)

        self.contact_label = ctk.CTkLabel(
            self.header,
            text="",
            font=S.FONT_TITLE,
            text_color=S.TEXT_PRIMARY,
            anchor="w",
        )
        self.contact_label.grid(row=0, column=0, sticky="w", padx=S.PADDING, pady=(10, 0))

        self.subtitle_label = ctk.CTkLabel(
            self.header,
            text="",
            font=S.FONT_SMALL,
            text_color=S.TEXT_SECONDARY,
            anchor="w",
        )
        self.subtitle_label.grid(row=1, column=0, sticky="w", padx=S.PADDING, pady=(0, 10))

        self.messages_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=S.BG_CHAT,
            corner_radius=0,
            scrollbar_button_color=S.BG_INPUT,
            scrollbar_fg_color=S.BG_CHAT,
            label_fg_color=S.BG_CHAT,
        )

        self.input_frame = ctk.CTkFrame(self, fg_color=S.BG_HEADER, corner_radius=0, height=76)
        self.input_frame.grid_propagate(False)
        self.input_frame.grid_columnconfigure(0, weight=1)

        input_inner = ctk.CTkFrame(self.input_frame, fg_color="transparent")
        input_inner.grid(row=0, column=0, sticky="nsew", padx=S.PADDING, pady=S.PADDING)
        input_inner.grid_columnconfigure(0, weight=1)

        self.message_entry = ctk.CTkTextbox(
            input_inner,
            height=48,
            fg_color=S.BG_INPUT,
            border_color=S.BG_INPUT,
            text_color=S.TEXT_PRIMARY,
            font=S.FONT_BODY,
            wrap="word",
        )
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.send_btn = ctk.CTkButton(
            input_inner,
            text="Enviar",
            width=96,
            height=40,
            fg_color=S.ACCENT,
            hover_color=S.ACCENT_HOVER,
            command=self._send_current,
        )
        self.send_btn.grid(row=0, column=1, sticky="e")

        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=S.FONT_TINY,
            text_color=S.TEXT_SECONDARY,
            anchor="w",
            fg_color=S.BG_CHAT,
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
        self._hide_chat_widgets()
        self.empty_label.grid(row=0, column=0, rowspan=4, sticky="nsew")

    def _hide_chat_widgets(self):
        self.empty_label.grid_forget()
        self.header.grid_forget()
        self.messages_frame.grid_forget()
        self.input_frame.grid_forget()
        self.status_label.grid_forget()

    def _show_chat_widgets(self):
        self.empty_label.grid_forget()
        self.header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        self.messages_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.input_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=0)

    def _clear_message_list(self):
        for child in self.messages_frame.winfo_children():
            child.destroy()
        self._shown_dates.clear()
        self._displayed_ids.clear()

    def _update_scroll_region(self):
        try:
            self.messages_frame.update_idletasks()
            canvas = self.messages_frame._parent_canvas
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _show_no_messages_placeholder(self):
        ctk.CTkLabel(
            self.messages_frame,
            text="No hay mensajes en esta conversación",
            font=S.FONT_BODY,
            text_color=S.TEXT_MUTED,
            fg_color=S.BG_CHAT,
        ).pack(pady=40, padx=S.PADDING)

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
        DateSeparator(self.messages_frame, format_date_separator(created_at)).pack(
            fill="x", padx=S.PADDING
        )

    def load_conversation(self, conversation: Conversation, messages: List[Message]):
        self._current_conv = conversation
        self.contact_label.configure(text=conversation.display_name)
        self.subtitle_label.configure(text=conversation.contact_number)

        self._show_chat_widgets()
        self._clear_message_list()

        if not messages:
            self._show_no_messages_placeholder()
        else:
            for msg in messages:
                self._render_message(msg)

        self.update_idletasks()
        self._update_scroll_region()
        self.message_entry.focus_set()

    def append_message(self, message: Message) -> bool:
        if not self._current_conv:
            return False
        if message.conversation_id != self._current_conv.id:
            return False
        if message.id in self._displayed_ids:
            return False
        self._render_message(message)
        self.update_idletasks()
        self.after(50, self._update_scroll_region)
        return True

    def set_status(self, text: str, is_error: bool = False):
        color = S.ERROR if is_error else S.TEXT_SECONDARY
        self.status_label.configure(text=text, text_color=color)
        self.status_label.grid(row=3, column=0, sticky="ew", padx=S.PADDING, pady=(0, 4))

    def clear_status(self):
        self.status_label.configure(text="")
        self.status_label.grid_forget()
