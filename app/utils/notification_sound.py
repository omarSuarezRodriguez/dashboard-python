"""Sonido de notificación al recibir mensajes (estilo pop suave tipo messenger)."""

import math
import struct
import subprocess
import sys
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger("notification_sound")

SAMPLE_RATE = 22050
_SOUND_PATH = Path(__file__).resolve().parents[1] / "assets" / "incoming_message.wav"
_last_play_at = 0.0
_play_lock = threading.Lock()
_MIN_INTERVAL_SEC = 0.35


def _write_messenger_like_wav(path: Path) -> None:
    """Genera un pop corto de dos tonos, similar a notificaciones de chat."""
    duration = 0.32
    samples = int(SAMPLE_RATE * duration)
    frames = bytearray()

    for i in range(samples):
        t = i / SAMPLE_RATE
        attack = min(1.0, t / 0.008)
        decay = math.exp(-t * 11.0)
        envelope = attack * decay

        tone = (
            0.62 * math.sin(2 * math.pi * 880.0 * t) * math.exp(-t * 16.0)
            + 0.38
            * math.sin(2 * math.pi * 1174.0 * max(0.0, t - 0.018))
            * math.exp(-max(0.0, t - 0.018) * 22.0)
            + 0.18 * math.sin(2 * math.pi * 660.0 * t) * math.exp(-t * 9.0)
        )
        sample = int(max(-1.0, min(1.0, tone * envelope)) * 32767 * 0.75)
        frames.extend(struct.pack("<h", sample))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(bytes(frames))


def _sound_file() -> Path:
    if not _SOUND_PATH.exists():
        _write_messenger_like_wav(_SOUND_PATH)
    return _SOUND_PATH


def _play_file(path: Path) -> None:
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return

    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                ["afplay", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["aplay", "-q", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        logger.debug("No se pudo reproducir sonido en esta plataforma", exc_info=True)


def is_recent_incoming_message(created_at: str, max_age_sec: float = 90.0) -> bool:
    """Evita sonidos al importar historial antiguo al abrir la app."""
    try:
        created = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - created).total_seconds() <= max_age_sec
    except ValueError:
        return True


def play_incoming_message_sound() -> None:
    """Reproduce el pop de mensaje entrante sin bloquear la interfaz."""
    global _last_play_at

    with _play_lock:
        now = time.monotonic()
        if now - _last_play_at < _MIN_INTERVAL_SEC:
            return
        _last_play_at = now

    try:
        _play_file(_sound_file())
    except Exception:
        logger.debug("Error reproduciendo sonido de notificación", exc_info=True)
