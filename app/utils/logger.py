"""Configuración de logging centralizada."""

import logging
import sys
from pathlib import Path


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configura el logger raíz de la aplicación."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_dir = Path(__file__).resolve().parents[2] / "logs"
    log_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger("whatsapp_panel")
    root.setLevel(log_level)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"whatsapp_panel.{name}")
