"""Validación y formato de números telefónicos E.164."""

import re
from dataclasses import dataclass

# Prefijos comunes para el selector
COUNTRY_PREFIXES = [
    ("+52", "México"),
    ("+1", "EE.UU. / Canadá"),
    ("+34", "España"),
    ("+54", "Argentina"),
    ("+57", "Colombia"),
    ("+56", "Chile"),
    ("+51", "Perú"),
    ("+593", "Ecuador"),
    ("+58", "Venezuela"),
    ("+55", "Brasil"),
    ("+49", "Alemania"),
    ("+33", "Francia"),
    ("+44", "Reino Unido"),
]


@dataclass
class PhoneValidationResult:
    valid: bool
    e164: str = ""
    whatsapp_to: str = ""
    error: str = ""


def normalize_digits(number: str) -> str:
    """Elimina espacios, guiones y paréntesis."""
    return re.sub(r"[^\d+]", "", number.strip())


def validate_and_format(prefix: str, local_number: str) -> PhoneValidationResult:
    """
    Valida y genera número E.164 y destino WhatsApp de Twilio.

    prefix: ej. +52
    local_number: dígitos sin prefijo
    """
    local = re.sub(r"\D", "", local_number.strip())
    prefix_clean = prefix.strip()
    if not prefix_clean.startswith("+"):
        prefix_clean = f"+{prefix_clean}"

    if not local:
        return PhoneValidationResult(valid=False, error="Ingresa el número telefónico.")

    if len(local) < 8:
        return PhoneValidationResult(
            valid=False,
            error="El número es demasiado corto (mínimo 8 dígitos).",
        )

    if len(local) > 15:
        return PhoneValidationResult(
            valid=False,
            error="El número es demasiado largo.",
        )

    e164 = f"{prefix_clean}{local}"

    if not re.match(r"^\+\d{10,16}$", e164):
        return PhoneValidationResult(
            valid=False,
            error="Formato inválido. Usa solo dígitos en el número local.",
        )

    whatsapp_to = f"whatsapp:{e164}"
    return PhoneValidationResult(valid=True, e164=e164, whatsapp_to=whatsapp_to)


def normalize_incoming_number(raw: str) -> str:
    """Normaliza número entrante de Twilio (whatsapp:+52...)."""
    raw = raw.strip()
    if raw.startswith("whatsapp:"):
        raw = raw[len("whatsapp:") :]
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return raw
    return f"+{digits}"


def contact_key(number: str) -> str:
    """Clave única para comparar el mismo contacto con formatos distintos."""
    return normalize_incoming_number(number)
