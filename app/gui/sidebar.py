"""Barra lateral: búsqueda y lista de conversaciones."""

from typing import Callable, List, Optional

import customtkinter as ctk

from app.gui import styles as S
from app.persistence.models import Conversation
from app.utils.datetime_fmt import format_time_short


class ConversationListItem(ctk.CTkFrame):
    """Fila de conversación en la barra lateral."""

    def __init__(
        self,
        master,
        conversation: Conversation,
        is_selected: bool,
        on_click: Callable[[int], None],
    ):
        bg = S.BG_SELECTED if is_selected else S.BG_SIDEBAR
        super().__init__(master, fg_color=bg, corner_radius=0, height=S.CHAT_LIST_ITEM_HEIGHT)
        self.conversation_id = conversation.id
        self._on_click = on_click

        self.bind("<Button-1>", self._click)
        self.configure(cursor="hand2")

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=8)
        inner.bind("<Button-1>", self._click)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        top.bind("<Button-1>", self._click)

        name = conversation.display_name
        ctk.CTkLabel(
            top,
            text=name[:28] + ("…" if len(name) > 28 else ""),
            font=S.FONT_SUBTITLE,
            text_color=S.TEXT_PRIMARY,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            top,
            text=format_time_short(conversation.last_message_at),
            font=S.FONT_TINY,
            text_color=S.TEXT_SECONDARY,
        ).pack(side="right")

        bottom = ctk.CTkFrame(inner, fg_color="transparent")
        bottom.pack(fill="x", pady=(4, 0))
        bottom.bind("<Button-1>", self._click)

        preview = conversation.last_message_preview or "Sin mensajes"
        ctk.CTkLabel(
            bottom,
            text=preview[:40] + ("…" if len(preview) > 40 else ""),
            font=S.FONT_SMALL,
            text_color=S.TEXT_MUTED,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        if conversation.unread_count > 0:
            badge = ctk.CTkLabel(
                bottom,
                text=str(min(conversation.unread_count, 99)),
                font=S.FONT_TINY,
                text_color="white",
                fg_color=S.BADGE,
                width=22,
                height=22,
                corner_radius=11,
            )
            badge.pack(side="right", padx=(4, 0))

    def _click(self, _event=None):
        self._on_click(self.conversation_id)

    def set_selected(self, selected: bool):
        self.configure(fg_color=S.BG_SELECTED if selected else S.BG_SIDEBAR)


class Sidebar(ctk.CTkFrame):
    """Panel izquierdo con buscador y chats."""

    def __init__(
        self,
        master,
        on_select: Callable[[int], None],
        on_new_chat: Callable[[], None],
        on_search: Callable[[str], None],
    ):
        super().__init__(master, fg_color=S.BG_SIDEBAR, width=S.SIDEBAR_WIDTH, corner_radius=0)
        self.pack_propagate(False)
        self._on_select = on_select
        self._on_search = on_search
        self._items: List[ConversationListItem] = []
        self._selected_id: Optional[int] = None

        header = ctk.CTkFrame(self, fg_color=S.BG_HEADER, corner_radius=0, height=60)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="Chats",
            font=S.FONT_TITLE,
            text_color=S.TEXT_PRIMARY,
        ).pack(side="left", padx=S.PADDING, pady=S.PADDING)

        ctk.CTkButton(
            header,
            text="+",
            width=36,
            height=36,
            font=("Segoe UI", 20),
            fg_color=S.ACCENT,
            hover_color=S.ACCENT_HOVER,
            command=on_new_chat,
        ).pack(side="right", padx=S.PADDING)

        search_frame = ctk.CTkFrame(self, fg_color=S.BG_SIDEBAR, corner_radius=0)
        search_frame.pack(fill="x", padx=S.PADDING, pady=8)

        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Buscar conversaciones…",
            fg_color=S.BG_INPUT,
            border_color=S.BG_INPUT,
            text_color=S.TEXT_PRIMARY,
            height=36,
        )
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", self._on_search_key)

        self.list_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=S.BG_SIDEBAR,
            corner_radius=0,
            scrollbar_button_color=S.BG_INPUT,
        )
        self.list_frame.pack(fill="both", expand=True)

    def _on_search_key(self, _event=None):
        self._on_search(self.search_entry.get())

    def refresh(self, conversations: List[Conversation], selected_id: Optional[int] = None):
        for item in self._items:
            item.destroy()
        self._items.clear()
        for child in self.list_frame.winfo_children():
            child.destroy()
        self._selected_id = selected_id

        if not conversations:
            ctk.CTkLabel(
                self.list_frame,
                text="No hay conversaciones",
                font=S.FONT_BODY,
                text_color=S.TEXT_MUTED,
            ).pack(pady=40)
            return

        for conv in conversations:
            item = ConversationListItem(
                self.list_frame,
                conv,
                is_selected=(conv.id == selected_id),
                on_click=self._on_select,
            )
            item.pack(fill="x")
            self._items.append(item)
