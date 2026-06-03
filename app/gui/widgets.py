"""Utilidades visuales compartidas para la GUI."""

from typing import Callable, Optional


def bind_click(widget, callback: Callable) -> None:
    """Enlaza clic en un widget y todos sus hijos (CTkLabel no propaga solo)."""
    widget.bind("<Button-1>", callback)
    for child in widget.winfo_children():
        bind_click(child, callback)


def bind_right_click(widget, callback: Callable) -> None:
    """Enlaza clic derecho en un widget y todos sus hijos."""
    widget.bind("<Button-3>", callback)
    for child in widget.winfo_children():
        bind_right_click(child, callback)


def bind_hover(widget, on_enter: Callable, on_leave: Callable) -> None:
    """Enlaza hover estable en un widget y todos sus hijos."""
    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)
    for child in widget.winfo_children():
        bind_hover(child, on_enter, on_leave)


def widget_contains_pointer(widget) -> bool:
    """True si el puntero está sobre el widget o alguno de sus hijos."""
    try:
        x, y = widget.winfo_pointerxy()
        current = widget.winfo_containing(x, y)
        while current is not None:
            if current == widget:
                return True
            current = current.master
    except Exception:
        pass
    return False


def hide_scrollbar(scrollable_frame) -> None:
    """Oculta la barra de scroll visual; el scroll con rueda sigue funcionando."""
    try:
        scrollbar = scrollable_frame._scrollbar
        scrollbar.configure(
            width=0,
            fg_color=scrollable_frame.cget("fg_color"),
            button_color=scrollable_frame.cget("fg_color"),
            button_hover_color=scrollable_frame.cget("fg_color"),
        )
        scrollbar.grid_remove()
        scrollable_frame._parent_canvas.configure(highlightthickness=0)
    except Exception:
        pass


def style_scrollbar(
    scrollable_frame,
    *,
    width: int = 12,
    track_color: str,
    button_color: str,
    button_hover_color: str,
) -> None:
    """Muestra y estiliza la barra de scroll del panel de mensajes."""
    try:
        scrollbar = scrollable_frame._scrollbar
        scrollbar.configure(
            width=width,
            fg_color=track_color,
            button_color=button_color,
            button_hover_color=button_hover_color,
        )
        if not scrollbar.winfo_ismapped():
            scrollbar.grid()
        scrollable_frame._parent_canvas.configure(highlightthickness=0)
    except Exception:
        pass
