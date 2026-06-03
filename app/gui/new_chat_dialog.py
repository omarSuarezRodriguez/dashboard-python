"""Diálogo para iniciar conversación nueva."""

import customtkinter as ctk

from app.gui import styles as S
from app.utils.phone_validator import COUNTRY_PREFIXES, PhoneValidationResult, validate_and_format


class NewChatDialog(ctk.CTkToplevel):
    """Ventana modal: prefijo, número, mensaje inicial y vista previa E.164."""

    def __init__(self, parent, on_send_callback):
        super().__init__(parent)
        self.on_send = on_send_callback
        self.result_data = None

        self.title("Nueva conversación")
        self.geometry("480x520")
        self.resizable(False, False)
        self.configure(fg_color=S.BG_DARK)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._update_preview()

    def _build_ui(self):
        pad = {"padx": S.PADDING, "pady": 6}

        ctk.CTkLabel(
            self,
            text="Iniciar chat de WhatsApp",
            font=S.FONT_TITLE,
            text_color=S.TEXT_PRIMARY,
        ).pack(anchor="w", **pad)

        ctk.CTkLabel(
            self,
            text="Prefijo internacional",
            font=S.FONT_SMALL,
            text_color=S.TEXT_SECONDARY,
        ).pack(anchor="w", padx=S.PADDING)

        prefix_labels = [f"{p} ({n})" for p, n in COUNTRY_PREFIXES]
        self.prefix_var = ctk.StringVar(value=prefix_labels[0])
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
        self.number_entry.bind("<KeyRelease>", lambda _: self._update_preview())

        self.preview_label = ctk.CTkLabel(
            self,
            text="Número final: —",
            font=S.FONT_BODY,
            text_color=S.ACCENT,
        )
        self.preview_label.pack(anchor="w", **pad)

        ctk.CTkLabel(
            self,
            text="Nombre del contacto (opcional)",
            font=S.FONT_SMALL,
            text_color=S.TEXT_SECONDARY,
        ).pack(anchor="w", padx=S.PADDING)

        self.name_entry = ctk.CTkEntry(
            self,
            placeholder_text="Nombre para mostrar",
            fg_color=S.BG_INPUT,
            border_color=S.BG_INPUT,
            text_color=S.TEXT_PRIMARY,
        )
        self.name_entry.pack(fill="x", padx=S.PADDING, pady=4)

        ctk.CTkLabel(
            self,
            text="Primer mensaje",
            font=S.FONT_SMALL,
            text_color=S.TEXT_SECONDARY,
        ).pack(anchor="w", padx=S.PADDING)

        self.message_box = ctk.CTkTextbox(
            self,
            height=100,
            fg_color=S.BG_INPUT,
            border_color=S.BG_INPUT,
            text_color=S.TEXT_PRIMARY,
        )
        self.message_box.pack(fill="x", padx=S.PADDING, pady=4)
        self.message_box.insert("1.0", "Hola, ¿en qué puedo ayudarte?")

        self.error_label = ctk.CTkLabel(
            self,
            text="",
            font=S.FONT_SMALL,
            text_color=S.ERROR,
            wraplength=420,
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
            text="Enviar",
            fg_color=S.ACCENT,
            hover_color=S.ACCENT_HOVER,
            command=self._on_send,
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

    def _on_send(self):
        result = self._validate()
        if not result.valid:
            self.error_label.configure(text=result.error)
            return

        message = self.message_box.get("1.0", "end").strip()
        if not message:
            self.error_label.configure(text="Escribe el primer mensaje.")
            return

        name = self.name_entry.get().strip() or None
        self.result_data = {
            "e164": result.e164,
            "whatsapp_to": result.whatsapp_to,
            "message": message,
            "name": name,
        }
        self.on_send(self.result_data)
        self.destroy()
