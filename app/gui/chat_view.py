"""Área principal de conversación: burbujas y envío."""

from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from app.gui import styles as S
from app.gui.widgets import hide_scrollbar, style_scrollbar
from app.persistence.models import Conversation, Message
from app.utils.datetime_fmt import format_date_separator, format_message_time, message_date_key

RENDER_BATCH_SIZE = 15
MAX_CACHED_PANELS = 10
SCROLL_ANIM_STEPS = 10
SCROLL_ANIM_MS = 18
SWITCH_FADE_MS = 40


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
        self._panels: Dict[int, dict] = {}
        self._active_panel: Optional[dict] = None
        self._render_job: Optional[str] = None
        self._scroll_job: Optional[str] = None
        self._tail_job: Optional[str] = None
        self._pending_load_id: Optional[int] = None
        self._auto_follow = True
        self._switch_overlay = ctk.CTkFrame(self, fg_color=S.BG_CHAT, corner_radius=0)

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
        style_scrollbar(
            self.messages_frame,
            width=12,
            track_color=S.BG_CHAT,
            button_color=S.BG_INPUT,
            button_hover_color=S.BG_HOVER,
        )
        self._bind_scroll_tracking()
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
        self._cancel_render_job()
        self._cancel_scroll_job()
        self._cancel_tail_job()
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

    def _cancel_render_job(self):
        if self._render_job is not None:
            self.after_cancel(self._render_job)
            self._render_job = None

    def _cancel_scroll_job(self):
        if self._scroll_job is not None:
            self.after_cancel(self._scroll_job)
            self._scroll_job = None

    def _cancel_tail_job(self):
        if self._tail_job is not None:
            self.after_cancel(self._tail_job)
            self._tail_job = None

    def _bind_scroll_tracking(self):
        try:
            canvas = self.messages_frame._parent_canvas
            canvas.bind("<MouseWheel>", lambda _e: self.after(10, self._update_auto_follow))
            canvas.bind("<ButtonRelease-1>", lambda _e: self.after(10, self._update_auto_follow))
            self.messages_frame._scrollbar.bind(
                "<ButtonRelease-1>", lambda _e: self.after(10, self._update_auto_follow)
            )
        except Exception:
            pass

    def _update_auto_follow(self):
        try:
            canvas = self.messages_frame._parent_canvas
            self._auto_follow = canvas.yview()[1] >= 0.95
        except Exception:
            pass

    def _prepare_scroll_region(self):
        try:
            canvas = self.messages_frame._parent_canvas
            panel = self._active_panel["frame"] if self._active_panel else None
            if panel is not None:
                panel.update_idletasks()
            self.messages_frame.update_idletasks()
            canvas.update_idletasks()
            bbox = canvas.bbox("all")
            if bbox:
                canvas.configure(scrollregion=bbox)
        except Exception:
            pass

    def _ensure_tail_visible(self, *, force: bool = False):
        """Mantiene la vista al final cuando llegan mensajes nuevos."""
        if not force and not self._auto_follow:
            return

        self._cancel_tail_job()

        def attempt(step: int = 0):
            self._tail_job = None
            self._prepare_scroll_region()
            try:
                canvas = self.messages_frame._parent_canvas
                canvas.yview_moveto(1.0)
            except Exception:
                pass
            if step < 5:
                self._tail_job = self.after(30, lambda: attempt(step + 1))

        attempt(0)

    def _scroll_to_bottom(self, animated: bool = True):
        self._cancel_scroll_job()
        self._prepare_scroll_region()
        try:
            canvas = self.messages_frame._parent_canvas
            if not animated:
                canvas.yview_moveto(1.0)
                return

            start = canvas.yview()[0]

            def step(index: int = 0):
                self._scroll_job = None
                if index >= SCROLL_ANIM_STEPS:
                    canvas.yview_moveto(1.0)
                    return
                progress = (index + 1) / SCROLL_ANIM_STEPS
                eased = 1.0 - (1.0 - progress) ** 2
                canvas.yview_moveto(start + (1.0 - start) * eased)
                self._scroll_job = self.after(SCROLL_ANIM_MS, lambda: step(index + 1))

            if start >= 0.92:
                canvas.yview_moveto(1.0)
            else:
                step(0)
        except Exception:
            pass

    def _create_panel(self, conversation_id: int) -> dict:
        frame = ctk.CTkFrame(self.messages_frame, fg_color=S.BG_CHAT, corner_radius=0)
        return {
            "conversation_id": conversation_id,
            "frame": frame,
            "displayed_ids": set(),
            "shown_dates": set(),
            "built": False,
            "scroll_y": 1.0,
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

    def _show_panel(self, panel: dict, *, smooth: bool = False):
        switching = (
            smooth
            and self._active_panel is not None
            and self._active_panel is not panel
            and self.messages_frame.winfo_ismapped()
        )
        if switching:
            self._switch_overlay.grid(row=1, column=0, sticky="nsew")
            self._switch_overlay.lift()

        self._hide_active_panel()
        panel["frame"].pack(fill="both", expand=True)
        self._active_panel = panel
        panel["scroll_y"] = 1.0
        self._auto_follow = True

        def finish():
            if switching and self._switch_overlay.winfo_ismapped():
                self._switch_overlay.grid_forget()
            self._scroll_to_bottom(animated=smooth or switching)

        delay = SWITCH_FADE_MS if switching else 0
        self.after(delay, finish)

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

    def _sync_panel_messages(self, panel: dict, messages: List[Message]):
        if panel.get("empty_label") is not None:
            panel["empty_label"].destroy()
            panel["empty_label"] = None
        new_messages = [m for m in messages if m.id not in panel["displayed_ids"]]
        for msg in new_messages:
            self._render_message(panel, msg)
        panel["built"] = True

    def _build_panel_batch(self, panel: dict, messages: List[Message], start: int = 0):
        if self._pending_load_id != panel["conversation_id"]:
            return

        if start == 0 and not self._switch_overlay.winfo_ismapped():
            self._switch_overlay.grid(row=1, column=0, sticky="nsew")
            self._switch_overlay.lift()

        end = min(start + RENDER_BATCH_SIZE, len(messages))
        for msg in messages[start:end]:
            self._render_message(panel, msg)

        if end < len(messages):
            self._render_job = self.after(
                1, lambda: self._build_panel_batch(panel, messages, end)
            )
            return

        self._render_job = None
        panel["built"] = True
        if self._active_panel is panel:
            if self._switch_overlay.winfo_ismapped():
                self._switch_overlay.grid_forget()
            self._scroll_to_bottom(animated=True)
            self.message_entry.focus_set()

    def prepare_conversation_header(self, conversation: Conversation):
        """Actualiza el encabezado al instante al seleccionar un chat."""
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

        if panel["built"]:
            self._sync_panel_messages(panel, messages)
            self._show_panel(panel, smooth=True)
            self.message_entry.focus_set()
            return

        if not messages:
            self._show_no_messages_placeholder(panel)
            panel["built"] = True
            self._show_panel(panel, smooth=True)
            self.message_entry.focus_set()
            return

        self._show_panel(panel, smooth=True)
        self._build_panel_batch(panel, messages, 0)

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
            self._show_panel(panel, smooth=False)

        self._render_message(panel, message)
        panel["built"] = True
        self._ensure_tail_visible(force=True)
        return True

    def set_status(self, text: str, is_error: bool = False):
        color = S.ERROR if is_error else S.TEXT_SECONDARY
        self.status_label.configure(text=text, text_color=color)
        self.status_label.grid(row=3, column=0, sticky="ew", padx=S.PADDING, pady=(0, 4))

    def clear_status(self):
        self.status_label.configure(text="")
        self.status_label.grid_forget()
