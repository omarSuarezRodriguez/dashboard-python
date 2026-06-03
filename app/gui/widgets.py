"""Utilidades visuales compartidas para la GUI."""

from typing import Callable


def bind_click(widget, callback: Callable) -> None:
    """Enlaza clic en un widget y todos sus hijos (CTkLabel no propaga solo)."""
    widget.bind("<Button-1>", callback)
    for child in widget.winfo_children():
        bind_click(child, callback)

