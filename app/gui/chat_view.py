"""Área principal de conversación: burbujas y envío."""

from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from app.gui import styles as S
from app.gui.widgets import style_scrollbar
from app.persistence.models import Conversation, Message
from app.utils.datetime_fmt import format_date_separator, format_message_time, message_date_key

RENDER_BATCH_SIZE = 50
MAX_CACHED_PANELS = 6
AUTO_FOLLOW_THRESHOLD = 0.92
SCROLL_RETRY_MS = 50


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
    """Panel derecho: burbujas, scroll y envío."""

    def __init__(self, master, on_send: Callable[[str], None]):
        super().__init__(master, fg_color=S.BG_CHAT, corner_radius=0)
        self._on_send = on_send
        self._current_conv: Optional[Conversation] = None
        self._panels: Dict[int, dict] = {}
        self._active_panel: Optional[dict] = None
        self._render_job: Optional[str] = None
        self._scroll_job: Optional[str] = None
        self._pending_load_id: Optional[int] = None
        self._auto_follow = True

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
        self._messages_host = ctk.CTkFrame(
            self.messages_frame,
            fg_color=S.BG_CHAT,
            corner_radius=0,
        )
        self._messages_host.pack(fill="x", anchor="nw")

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
        style_scrollbar(
            self.messages_frame,
            width=12,
            track_color=S.BG_CHAT,
            button_color=S.BG_INPUT,
            button_hover_color=S.BG_HOVER,
        )
        self._bind_scroll_tracking()
        self.show_empty()

    # --- Entrada / layout vacío ---

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
        self._cancel_render_job()
        self._cancel_scroll_job()
        self._current_conv = None
        self._hide_active_panel()
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

    # --- Scroll ---

    def _cancel_render_job(self):
        if self._render_job is not None:
            self.after_cancel(self._render_job)
            self._render_job = None

    def _cancel_scroll_job(self):
        if self._scroll_job is not None:
            try:
                self.after_cancel(self._scroll_job)
            except Exception:
                pass
            self._scroll_job = None

    def _bind_scroll_tracking(self):
        try:
            canvas = self.messages_frame._parent_canvas
            canvas.bind("<ButtonRelease-1>", self._on_user_scroll, add="+")
            canvas.bind("<MouseWheel>", self._on_user_scroll, add="+")
            canvas.bind("<Button-4>", self._on_user_scroll, add="+")
            canvas.bind("<Button-5>", self._on_user_scroll, add="+")
            self.messages_frame._scrollbar.bind(
                "<ButtonRelease-1>", self._on_user_scroll, add="+"
            )
        except Exception:
            pass

    def _on_user_scroll(self, _event=None):
        self.after(50, self._refresh_auto_follow)

    def _refresh_auto_follow(self):
        try:
            canvas = self.messages_frame._parent_canvas
            self._auto_follow = canvas.yview()[1] >= AUTO_FOLLOW_THRESHOLD
        except Exception:
            pass

    def _update_scroll_region(self) -> bool:
        try:
            canvas = self.messages_frame._parent_canvas
            host = self._messages_host
            if self._active_panel is not None:
                self._active_panel["frame"].update_idletasks()
            host.update_idletasks()
            height = host.winfo_reqheight()
            width = max(host.winfo_reqwidth(), canvas.winfo_width(), 1)
            if height <= 0:
                return False
            canvas.configure(scrollregion=(0, 0, width, height))
            return True
        except Exception:
            return False

    def _scroll_to_bottom(self, *, force: bool = False):
        """Baja al último mensaje. Si force=False, solo si el usuario estaba abajo."""
        if not force and not self._auto_follow:
            return

        self._cancel_scroll_job()

        def apply():
            self._scroll_job = None
            try:
                if self._update_scroll_region():
                    self.messages_frame._parent_canvas.yview_moveto(1.0)
                    if force:
                        self._auto_follow = True
            except Exception:
                pass

        apply()
        self._scroll_job = self.after(SCROLL_RETRY_MS, apply)

    # --- Paneles por conversación ---

    @staticmethod
    def _messages_fingerprint(messages: List[Message]) -> Tuple[Tuple[int, str], ...]:
        return tuple((m.id, m.created_at) for m in messages)

    @staticmethod
    def _can_incremental_sync(panel: dict, messages: List[Message]) -> bool:
        prev = panel.get("fingerprint")
        if not prev or not panel.get("built"):
            return False
        current = ChatView._messages_fingerprint(messages)
        if len(current) < len(prev):
            return False
        return current[: len(prev)] == prev

    def _create_panel(self, conversation_id: int) -> dict:
        frame = ctk.CTkFrame(self._messages_host, fg_color=S.BG_CHAT, corner_radius=0)
        return {
            "conversation_id": conversation_id,
            "frame": frame,
            "displayed_ids": set(),
            "shown_dates": set(),
            "built": False,
            "fingerprint": (),
            "empty_label": None,
        }

    def _get_panel(self, conversation_id: int) -> dict:
        panel = self._panels.get(conversation_id)
        if panel is None:
            panel = self._create_panel(conversation_id)
            self._panels[conversation_id] = panel
        return panel

    def _evict_old_panels(self, keep_id: int):
        if len(self._panels) <= MAX_CACHED_PANELS:
            return
        for conv_id in list(self._panels):
            if conv_id == keep_id:
                continue
            panel = self._panels.pop(conv_id)
            panel["frame"].destroy()
            if len(self._panels) <= MAX_CACHED_PANELS:
                break

    def _hide_active_panel(self):
        if self._active_panel is not None:
            self._active_panel["frame"].pack_forget()
            self._active_panel = None

    def _show_panel(self, panel: dict):
        self._cancel_scroll_job()
        self._hide_active_panel()
        panel["frame"].pack(fill="x", anchor="nw")
        self._active_panel = panel
        self._auto_follow = True
        self.after_idle(lambda: self._scroll_to_bottom(force=True))

    def _clear_panel_widgets(self, panel: dict):
        for child in panel["frame"].winfo_children():
            child.destroy()
        panel["displayed_ids"].clear()
        panel["shown_dates"].clear()
        panel["empty_label"] = None
        panel["built"] = False
        panel["fingerprint"] = ()

    def _render_message(self, panel: dict, message: Message):
        if message.id in panel["displayed_ids"]:
            return
        master = panel["frame"]
        key = message_date_key(message.created_at)
        if key and key not in panel["shown_dates"]:
            panel["shown_dates"].add(key)
            DateSeparator(master, format_date_separator(message.created_at)).pack(
                fill="x", padx=S.PADDING
            )
        MessageBubble(master, message)
        panel["displayed_ids"].add(message.id)

    def _show_no_messages_placeholder(self, panel: dict):
        if panel.get("empty_label") is not None:
            return
        placeholder = ctk.CTkLabel(
            panel["frame"],
            text="No hay mensajes en esta conversación",
            font=S.FONT_BODY,
            text_color=S.TEXT_MUTED,
            fg_color=S.BG_CHAT,
        )
        placeholder.pack(pady=40, padx=S.PADDING)
        panel["empty_label"] = placeholder

    def _finish_panel(self, panel: dict, messages: List[Message]):
        panel["built"] = True
        panel["fingerprint"] = self._messages_fingerprint(messages)

    def _rebuild_panel(self, panel: dict, messages: List[Message]):
        self._clear_panel_widgets(panel)
        if not messages:
            self._show_no_messages_placeholder(panel)
        else:
            for msg in messages:
                self._render_message(panel, msg)
        self._finish_panel(panel, messages)

    def _append_new_messages(self, panel: dict, messages: List[Message]):
        if panel.get("empty_label") is not None:
            panel["empty_label"].destroy()
            panel["empty_label"] = None
        for msg in messages:
            if msg.id not in panel["displayed_ids"]:
                self._render_message(panel, msg)
        self._finish_panel(panel, messages)

    def _build_panel_batch(
        self,
        panel: dict,
        messages: List[Message],
        start: int = 0,
        *,
        scroll_when_done: bool = True,
        track_load: bool = True,
    ):
        if track_load and self._pending_load_id != panel["conversation_id"]:
            return

        end = min(start + RENDER_BATCH_SIZE, len(messages))
        for msg in messages[start:end]:
            self._render_message(panel, msg)

        if end < len(messages):
            self._render_job = self.after(
                1,
                lambda p=panel, m=messages, e=end, sw=scroll_when_done, tl=track_load: (
                    self._build_panel_batch(p, m, e, scroll_when_done=sw, track_load=tl)
                ),
            )
            return

        self._render_job = None
        self._finish_panel(panel, messages)
        if scroll_when_done and self._active_panel is panel:
            self._scroll_to_bottom(force=True)
            self.message_entry.focus_set()

    def warm_conversation_cache(self, conversation: Conversation, messages: List[Message]):
        """Preconstruye el panel (hilo UI) para abrir el chat al instante después."""
        panel = self._get_panel(conversation.id)
        self._evict_old_panels(conversation.id)

        if panel["built"] and self._can_incremental_sync(panel, messages):
            self._append_new_messages(panel, messages)
            return

        if panel["built"]:
            self._rebuild_panel(panel, messages)
            return

        self._clear_panel_widgets(panel)
        if not messages:
            self._show_no_messages_placeholder(panel)
            self._finish_panel(panel, messages)
            return

        self._build_panel_batch(
            panel, messages, 0, scroll_when_done=False, track_load=False
        )

    def invalidate_all_panels(self):
        for conv_id in list(self._panels):
            self.invalidate_conversation(conv_id)

    # --- API pública ---

    def prepare_conversation_header(self, conversation: Conversation):
        self._show_chat_widgets()
        self.contact_label.configure(text=conversation.display_name)
        self.subtitle_label.configure(text=conversation.contact_number)

    def load_conversation(self, conversation: Conversation, messages: List[Message]):
        self._cancel_render_job()
        self._cancel_scroll_job()
        self._pending_load_id = conversation.id
        self._current_conv = conversation
        self.prepare_conversation_header(conversation)

        panel = self._get_panel(conversation.id)
        self._evict_old_panels(conversation.id)

        if panel["built"] and self._can_incremental_sync(panel, messages):
            self._append_new_messages(panel, messages)
            self._show_panel(panel)
            self.message_entry.focus_set()
            return

        if panel["built"]:
            self._rebuild_panel(panel, messages)
            self._show_panel(panel)
            self.message_entry.focus_set()
            return

        self._clear_panel_widgets(panel)
        if not messages:
            self._show_no_messages_placeholder(panel)
            self._finish_panel(panel, messages)
            self._show_panel(panel)
            self.message_entry.focus_set()
            return

        self._show_panel(panel)
        self._build_panel_batch(panel, messages, 0, scroll_when_done=True, track_load=True)

    def set_current_conversation(self, conversation: Conversation):
        self._current_conv = conversation

    def update_contact_info(self, conversation: Conversation):
        if not self._current_conv or self._current_conv.id != conversation.id:
            return
        self._current_conv = conversation
        self.contact_label.configure(text=conversation.display_name)
        self.subtitle_label.configure(text=conversation.contact_number)

    def invalidate_conversation(self, conversation_id: int):
        panel = self._panels.pop(conversation_id, None)
        if panel is None:
            return
        if self._active_panel is panel:
            self._active_panel = None
        panel["frame"].destroy()

    def append_message(self, message: Message) -> bool:
        if not self._current_conv:
            return False

        conv_id = self._current_conv.id
        if message.conversation_id != conv_id:
            return False

        panel = self._get_panel(conv_id)
        if message.id in panel["displayed_ids"]:
            return False

        if panel.get("empty_label") is not None:
            panel["empty_label"].destroy()
            panel["empty_label"] = None

        if self._active_panel is not panel:
            self._show_panel(panel)

        self._render_message(panel, message)
        fp = list(panel.get("fingerprint") or ())
        fp.append((message.id, message.created_at))
        panel["fingerprint"] = tuple(fp)
        panel["built"] = True

        self._scroll_to_bottom(force=self._auto_follow)
        return True

    def set_status(self, text: str, is_error: bool = False):
        color = S.ERROR if is_error else S.TEXT_SECONDARY
        self.status_label.configure(text=text, text_color=color)
        self.status_label.grid(row=3, column=0, sticky="ew", padx=S.PADDING, pady=(0, 4))

    def clear_status(self):
        self.status_label.configure(text="")
        self.status_label.grid_forget()
