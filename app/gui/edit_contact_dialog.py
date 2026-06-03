"""Diálogo para editar nombre y número de un contacto."""

import customtkinter as ctk

from app.gui import styles as S
from app.persistence.models import Conversation
from app.utils.phone_validator import (
    PhoneValidationResult,
    prefix_menu_options,
    split_e164,
    validate_and_format,
)


class EditContactDialog(ctk.CTkToplevel):
    """Ventana modal para cambiar nombre y número de una conversación."""

    def __init__(self, parent, conversation: Conversation, on_save_callback, focus_field: str = ""):
        super().__init__(parent)
        self.conversation = conversation
        self.on_save = on_save_callback
        self._focus_field = focus_field

        self.title("Editar contacto")
        self.geometry("460x420")
        self.resizable(False, False)
        self.configure(fg_color=S.BG_DARK)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._update_preview()
        if self._focus_field == "number":
            self.number_entry.focus_set()
        else:
            self.name_entry.focus_set()
            self.name_entry.select_range(0, "end")

    def _build_ui(self):
        pad = {"padx": S.PADDING, "pady": 6}

        ctk.CTkLabel(
            self,
            text="Editar contacto",
            font=S.FONT_TITLE,
            text_color=S.TEXT_PRIMARY,
        ).pack(anchor="w", **pad)

        ctk.CTkLabel(
            self,
            text="Nombre para mostrar",
            font=S.FONT_SMALL,
            text_color=S.TEXT_SECONDARY,
        ).pack(anchor="w", padx=S.PADDING)

        self.name_entry = ctk.CTkEntry(
            self,
            placeholder_text="Nombre del contacto",
            fg_color=S.BG_INPUT,
            border_color=S.BG_INPUT,
            text_color=S.TEXT_PRIMARY,
        )
        self.name_entry.pack(fill="x", padx=S.PADDING, pady=4)
        if self.conversation.contact_name:
            self.name_entry.insert(0, self.conversation.contact_name)

        ctk.CTkLabel(
            self,
            text="Prefijo internacional",
            font=S.FONT_SMALL,
            text_color=S.TEXT_SECONDARY,
        ).pack(anchor="w", padx=S.PADDING)

        prefix_labels, default_prefix = prefix_menu_options(self.conversation.contact_number)
        self.prefix_var = ctk.StringVar(value=default_prefix)
        self.prefix_menu = ctk.CTkOptionMenu(
            self,
            variable=self.prefix_var,
            values=prefix_labels,
            fg_color=S.BG_INPUT,
            button_color=S.ACCENT,
            command=lambda _: self._update_preview(),
        )
        self.prefix_menu.pack(fill="x", padx=S.PADDING, pady=4)

        ctk.CTkLabel(
            self,
            text="Número (sin prefijo)",
            font=S.FONT_SMALL,
            text_color=S.TEXT_SECONDARY,
        ).pack(anchor="w", padx=S.PADDING)

        self.number_entry = ctk.CTkEntry(
            self,
            placeholder_text="Ej: 5512345678",
            fg_color=S.BG_INPUT,
            border_color=S.BG_INPUT,
            text_color=S.TEXT_PRIMARY,
        )
        self.number_entry.pack(fill="x", padx=S.PADDING, pady=4)
        _, local = split_e164(self.conversation.contact_number)
        self.number_entry.insert(0, local)
        self.number_entry.bind("<KeyRelease>", lambda _: self._update_preview())

        self.preview_label = ctk.CTkLabel(
            self,
            text="Número final: —",
            font=S.FONT_BODY,
            text_color=S.ACCENT,
        )
        self.preview_label.pack(anchor="w", **pad)

        self.error_label = ctk.CTkLabel(
            self,
            text="",
            font=S.FONT_SMALL,
            text_color=S.ERROR,
            wraplength=400,
        )
        self.error_label.pack(anchor="w", **pad)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=S.PADDING, pady=S.PADDING)

        ctk.CTkButton(
            btn_frame,
            text="Cancelar",
            fg_color=S.BG_INPUT,
            hover_color=S.BG_HOVER,
            command=self.destroy,
            width=120,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_frame,
            text="Guardar",
            fg_color=S.ACCENT,
            hover_color=S.ACCENT_HOVER,
            command=self._on_save,
            width=120,
        ).pack(side="right", padx=4)

    def _get_prefix(self) -> str:
        label = self.prefix_var.get()
        return label.split(" ")[0]

    def _validate(self) -> PhoneValidationResult:
        return validate_and_format(self._get_prefix(), self.number_entry.get())

    def _update_preview(self):
        result = self._validate()
        if result.valid:
            self.preview_label.configure(
                text=f"Número final: {result.e164}",
                text_color=S.ACCENT,
            )
            self.error_label.configure(text="")
        else:
            self.preview_label.configure(text="Número final: —", text_color=S.TEXT_MUTED)
            if self.number_entry.get().strip():
                self.error_label.configure(text=result.error)

    def _on_save(self):
        result = self._validate()
        if not result.valid:
            self.error_label.configure(text=result.error)
            return

        name = self.name_entry.get().strip() or None
        self.on_save(
            {
                "conversation_id": self.conversation.id,
                "name": name,
                "e164": result.e164,
            }
        )
        self.destroy()
