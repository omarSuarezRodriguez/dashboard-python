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
    ("+356", "Malta"),
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


def split_e164(e164: str) -> tuple[str, str]:
    """Separa un E.164 en prefijo internacional y número local."""
    normalized = contact_key(e164)
    for prefix, _ in sorted(COUNTRY_PREFIXES, key=lambda item: len(item[0]), reverse=True):
        if normalized.startswith(prefix) and len(normalized) > len(prefix):
            return prefix, normalized[len(prefix) :]
    if normalized.startswith("+"):
        for length in (3, 2, 1):
            prefix = normalized[: 1 + length]
            local = normalized[1 + length :]
            if local:
                return prefix, local
    return "+57", normalized.lstrip("+")


def local_number_key(number: str) -> str:
    """Parte local del número para detectar duplicados con prefijo distinto."""
    return split_e164(number)[1]


def prefix_menu_options(e164: str) -> tuple[list[str], str]:
    """Opciones del selector de prefijo; incluye el detectado si no está en la lista."""
    prefix, _ = split_e164(e164)
    labels = [f"{p} ({n})" for p, n in COUNTRY_PREFIXES]
    match = next((label for label in labels if label.startswith(f"{prefix} ")), None)
    if match:
        return labels, match
    custom = f"{prefix} (detectado)"
    return [custom, *labels], custom
