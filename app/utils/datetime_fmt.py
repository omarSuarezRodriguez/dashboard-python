"""Fechas y horas con la zona horaria local del sistema."""

from datetime import datetime
from typing import Optional


def now_local_str() -> str:
    """Marca de tiempo local para guardar en BD."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def twilio_datetime_to_local_str(value) -> str:
    """Convierte date_sent/date_created de Twilio a hora local almacenada."""
    if value is None:
        return now_local_str()
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(text[:19], fmt)
                break
            except ValueError:
                continue
        if dt is None:
            return now_local_str()
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_stored_datetime(value: str) -> Optional[datetime]:
    """Interpreta valor guardado (local o UTC legado sin zona)."""
    if not value:
        return None
    text = value.strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            # Registros antiguos en UTC: si termina en Z o tiene offset, tratar aparte
            return dt
        except ValueError:
            continue
    return None


def format_time_short(value: str) -> str:
    """Hora para lista lateral: HH:MM hoy, Ayer o fecha."""
    dt = parse_stored_datetime(value)
    if not dt:
        return value[:16] if value else ""

    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if (now.date() - dt.date()).days == 1:
        return "Ayer"
    return dt.strftime("%d/%m/%Y")


def format_message_time(value: str) -> str:
    """Hora en burbuja: siempre HH:MM del reloj local."""
    dt = parse_stored_datetime(value)
    if not dt:
        return ""
    return dt.strftime("%H:%M")


def format_date_separator(value: str) -> str:
    """Separador de día en el hilo del chat."""
    dt = parse_stored_datetime(value)
    if not dt:
        return ""

    now = datetime.now()
    if dt.date() == now.date():
        return "Hoy"
    if (now.date() - dt.date()).days == 1:
        return "Ayer"
    return dt.strftime("%d/%m/%Y")


def message_date_key(value: str) -> str:
    """Clave de día para agrupar mensajes."""
    dt = parse_stored_datetime(value)
    return dt.strftime("%Y-%m-%d") if dt else ""
