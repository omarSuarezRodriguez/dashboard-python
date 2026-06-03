"""Barra lateral: búsqueda y lista de conversaciones."""

import tkinter as tk
from typing import Callable, List, Optional

import customtkinter as ctk

from app.gui import styles as S
from app.gui.widgets import bind_click, bind_hover, bind_right_click, hide_scrollbar, widget_contains_pointer
from app.persistence.models import Conversation
from app.utils.datetime_fmt import format_time_short


def _format_preview(text: Optional[str], max_len: int = 42) -> str:
    """Una sola línea de preview (sin saltos que rompan el layout)."""
    raw = (text or "Sin mensajes").replace("\n", " ").replace("\r", " ")
    clean = " ".join(raw.split())
    if len(clean) > max_len:
        return clean[:max_len] + "…"
    return clean


def _format_name(name: str, max_len: int = 28) -> str:
    if len(name) > max_len:
        return name[:max_len] + "…"
    return name


class ConversationListItem(ctk.CTkFrame):
    """Fila clickeable de conversación."""

    def __init__(
        self,
        master,
        conversation: Conversation,
        is_selected: bool,
        on_click: Callable[[int], None],
        on_edit: Callable[[int, str], None],
    ):
        bg = S.BG_SELECTED if is_selected else "transparent"
        super().__init__(
            master,
            fg_color=bg,
            corner_radius=S.SIDEBAR_ITEM_RADIUS,
            height=S.CHAT_LIST_ITEM_HEIGHT,
            border_width=0,
        )
        self.pack_propagate(False)
        self.conversation_id = conversation.id
        self._bg_normal = "transparent"
        self._bg_selected = S.BG_SELECTED
        self._is_selected = is_selected
        self._on_click = on_click
        self._badge: Optional[ctk.CTkLabel] = None
        self._hover_after_id: Optional[str] = None
        self._is_hovered = False

        def handle_click(_event=None):
            on_click(self.conversation_id)

        def handle_right_click(event):
            self._show_context_menu(event)

        self._handle_click = handle_click
        self._handle_right_click = handle_right_click
        self._on_edit = on_edit
        self.configure(cursor="hand2")
        bind_click(self, handle_click)
        bind_right_click(self, handle_right_click)

        inner = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        inner.pack(fill="both", expand=True, padx=14, pady=6)
        bind_click(inner, handle_click)
        bind_right_click(inner, handle_right_click)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        top.grid_columnconfigure(0, weight=1)
        bind_click(top, handle_click)
        bind_right_click(top, handle_right_click)

        self._name_lbl = ctk.CTkLabel(
            top,
            text=_format_name(conversation.display_name),
            font=S.FONT_SUBTITLE,
            text_color=S.TEXT_PRIMARY,
            anchor="w",
            cursor="hand2",
        )
        self._name_lbl.grid(row=0, column=0, sticky="w")
        bind_click(self._name_lbl, handle_click)
        bind_right_click(self._name_lbl, handle_right_click)

        self._time_lbl = ctk.CTkLabel(
            top,
            text=format_time_short(conversation.last_message_at),
            font=S.FONT_TINY,
            text_color=S.TEXT_SECONDARY,
            cursor="hand2",
        )
        self._time_lbl.grid(row=0, column=1, sticky="e", padx=(8, 0))
        bind_click(self._time_lbl, handle_click)
        bind_right_click(self._time_lbl, handle_right_click)

        bottom = ctk.CTkFrame(inner, fg_color="transparent", height=S.BADGE_SIZE + 4)
        bottom.pack(fill="x", pady=(2, 0))
        bottom.pack_propagate(False)
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_rowconfigure(0, minsize=S.BADGE_SIZE + 2)
        bind_click(bottom, handle_click)
        bind_right_click(bottom, handle_right_click)
        self._bottom = bottom

        self._prev_lbl = ctk.CTkLabel(
            bottom,
            text=_format_preview(conversation.last_message_preview),
            font=S.FONT_SMALL,
            text_color=S.TEXT_MUTED,
            anchor="w",
            cursor="hand2",
            wraplength=self._preview_wraplength(conversation.unread_count > 0),
        )
        self._prev_lbl.grid(row=0, column=0, sticky="w", pady=(1, 0))
        bind_click(self._prev_lbl, handle_click)
        bind_right_click(self._prev_lbl, handle_right_click)

        self._update_badge(conversation.unread_count)
        self._apply_bg()
        self._sync_hover_bindings()

    def _apply_bg(self):
        if self._is_selected:
            color = self._bg_selected
        elif self._is_hovered:
            color = S.BG_HOVER
        else:
            color = self._bg_normal
        self.configure(fg_color=color)

    def _hover_enter(self, _event=None):
        if self._is_selected:
            return
        if self._hover_after_id is not None:
            self.after_cancel(self._hover_after_id)
            self._hover_after_id = None
        self._is_hovered = True
        self._apply_bg()

    def _hover_leave(self, _event=None):
        if self._is_selected:
            return
        if self._hover_after_id is not None:
            self.after_cancel(self._hover_after_id)
        self._hover_after_id = self.after(30, self._finish_hover_leave)

    def _finish_hover_leave(self):
        self._hover_after_id = None
        if self._is_selected:
            return
        if widget_contains_pointer(self):
            return
        self._is_hovered = False
        self._apply_bg()

    def _preview_wraplength(self, has_badge: bool) -> int:
        reserve = 56 if has_badge else 28
        return S.SIDEBAR_WIDTH - (S.SIDEBAR_LIST_PADX * 2) - reserve

    def _show_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.configure(
            bg=S.BG_HEADER,
            fg=S.TEXT_PRIMARY,
            activebackground=S.BG_HOVER,
            activeforeground=S.TEXT_PRIMARY,
            borderwidth=0,
        )
        menu.add_command(
            label="Cambiar nombre",
            command=lambda: self._on_edit(self.conversation_id, "name"),
        )
        menu.add_command(
            label="Cambiar número",
            command=lambda: self._on_edit(self.conversation_id, "number"),
        )
        menu.add_separator()
        menu.add_command(
            label="Editar contacto…",
            command=lambda: self._on_edit(self.conversation_id, "both"),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _update_badge(self, unread_count: int):
        has_badge = unread_count > 0
        self._prev_lbl.configure(wraplength=self._preview_wraplength(has_badge))

        if has_badge:
            text = str(min(unread_count, 99))
            if self._badge is not None:
                self._badge.configure(text=text)
                return
            self._badge = ctk.CTkLabel(
                self._bottom,
                text=text,
                font=S.FONT_TINY,
                text_color="white",
                fg_color=S.BADGE,
                width=S.BADGE_SIZE,
                height=S.BADGE_SIZE,
                corner_radius=S.BADGE_SIZE // 2,
                cursor="hand2",
            )
            self._badge.grid(row=0, column=1, sticky="ne", padx=(6, 0), pady=(0, 1))
            bind_click(self._badge, self._handle_click)
            bind_right_click(self._badge, self._handle_right_click)
        elif self._badge is not None:
            self._badge.destroy()
            self._badge = None
        if not self._is_selected:
            self._sync_hover_bindings()

    def _sync_hover_bindings(self):
        self._unbind_hover_tree(self)
        if not self._is_selected:
            bind_hover(self, self._hover_enter, self._hover_leave)

    def _unbind_hover_tree(self, widget):
        widget.unbind("<Enter>")
        widget.unbind("<Leave>")
        for child in widget.winfo_children():
            self._unbind_hover_tree(child)

    def set_selected(self, is_selected: bool):
        if self._is_selected == is_selected:
            return
        self._is_selected = is_selected
        if is_selected:
            self._is_hovered = False
            if self._hover_after_id is not None:
                self.after_cancel(self._hover_after_id)
                self._hover_after_id = None
        elif widget_contains_pointer(self):
            self._is_hovered = True
        self._apply_bg()
        self._sync_hover_bindings()

    def update_conversation(self, conversation: Conversation):
        self._name_lbl.configure(text=_format_name(conversation.display_name))
        self._time_lbl.configure(text=format_time_short(conversation.last_message_at))
        self._prev_lbl.configure(text=_format_preview(conversation.last_message_preview))
        self._update_badge(conversation.unread_count)


class Sidebar(ctk.CTkFrame):
    """Panel izquierdo con buscador y chats."""

    def __init__(
        self,
        master,
        on_select: Callable[[int], None],
        on_new_chat: Callable[[], None],
        on_search: Callable[[str], None],
        on_edit: Callable[[int, str], None],
    ):
        super().__init__(master, fg_color=S.BG_SIDEBAR, width=S.SIDEBAR_WIDTH, corner_radius=0)
        self.pack_propagate(False)
        self._on_select = on_select
        self._on_search = on_search
        self._on_edit = on_edit
        self._items: List[ConversationListItem] = []
        self._selected_id: Optional[int] = None
        self._empty_label: Optional[ctk.CTkLabel] = None

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
        search_frame.pack(fill="x", padx=S.SIDEBAR_LIST_PADX, pady=(6, 8))

        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Buscar conversaciones…",
            fg_color=S.BG_INPUT,
            border_color=S.BG_INPUT,
            text_color=S.TEXT_PRIMARY,
            height=38,
            corner_radius=10,
        )
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", self._on_search_key)

        self.list_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=S.BG_SIDEBAR,
            corner_radius=0,
            border_width=0,
            scrollbar_button_color=S.BG_SIDEBAR,
            scrollbar_fg_color=S.BG_SIDEBAR,
        )
        self.list_frame.pack(fill="both", expand=True, padx=0, pady=(0, 4))
        hide_scrollbar(self.list_frame)

    def _on_search_key(self, _event=None):
        self._on_search(self.search_entry.get())

    def set_selection(self, selected_id: Optional[int]):
        if selected_id == self._selected_id:
            return
        self._selected_id = selected_id
        for item in self._items:
            item.set_selected(item.conversation_id == selected_id)

    def update_conversation(self, conversation: Conversation):
        for item in self._items:
            if item.conversation_id == conversation.id:
                item.update_conversation(conversation)
                break

    def _clear_list(self):
        for item in self._items:
            item.destroy()
        self._items.clear()
        if self._empty_label is not None:
            self._empty_label.destroy()
            self._empty_label = None
        for child in self.list_frame.winfo_children():
            child.destroy()

    def _rebuild_list(self, conversations: List[Conversation], selected_id: Optional[int]):
        self._clear_list()
        for conv in conversations:
            item = ConversationListItem(
                self.list_frame,
                conv,
                is_selected=(conv.id == selected_id),
                on_click=self._on_select,
                on_edit=self._on_edit,
            )
            item.pack(fill="x", padx=S.SIDEBAR_LIST_PADX, pady=S.SIDEBAR_ITEM_GAP)
            self._items.append(item)

    def refresh(self, conversations: List[Conversation], selected_id: Optional[int] = None):
        self._selected_id = selected_id

        if not conversations:
            if self._items or self._empty_label is None:
                self._clear_list()
                self._empty_label = ctk.CTkLabel(
                    self.list_frame,
                    text="No hay conversaciones",
                    font=S.FONT_BODY,
                    text_color=S.TEXT_MUTED,
                )
                self._empty_label.pack(pady=40, padx=S.SIDEBAR_LIST_PADX)
            return

        if self._empty_label is not None:
            self._empty_label.destroy()
            self._empty_label = None

        new_ids = [c.id for c in conversations]
        current_ids = [item.conversation_id for item in self._items]

        if new_ids == current_ids:
            for item, conv in zip(self._items, conversations):
                item.update_conversation(conv)
                item.set_selected(conv.id == selected_id)
            return

        self._rebuild_list(conversations, selected_id)
