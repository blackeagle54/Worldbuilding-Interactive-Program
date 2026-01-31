"""
app/widgets/toast.py -- Toast notification widget.

Slides in from the bottom-right of the parent window with auto-dismiss.
Supports info, success, warning, and error severities.
"""

from __future__ import annotations

import logging
from enum import Enum

from PySide6.QtCore import (
    QPoint,
    QPropertyAnimation,
    QEasingCurve,
    Qt,
    QTimer,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QWidget

logger = logging.getLogger(__name__)


class ToastSeverity(Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


_STYLES = {
    ToastSeverity.INFO: (
        "background-color: #263238; color: #ddd; "
        "border-left: 4px solid #2196F3;"
    ),
    ToastSeverity.SUCCESS: (
        "background-color: #1b3a1b; color: #ddd; "
        "border-left: 4px solid #4CAF50;"
    ),
    ToastSeverity.WARNING: (
        "background-color: #3a351b; color: #ddd; "
        "border-left: 4px solid #FFC107;"
    ),
    ToastSeverity.ERROR: (
        "background-color: #3a1b1b; color: #ddd; "
        "border-left: 4px solid #F44336;"
    ),
}

_BASE_STYLE = (
    "padding: 10px 16px; border-radius: 4px; "
    "font-size: 12px; font-family: 'Segoe UI', sans-serif;"
)

# Auto-dismiss durations (ms)
_DURATIONS = {
    ToastSeverity.INFO: 4000,
    ToastSeverity.SUCCESS: 3000,
    ToastSeverity.WARNING: 6000,
    ToastSeverity.ERROR: 8000,
}


class Toast(QLabel):
    """A single toast notification that auto-dismisses."""

    def __init__(
        self,
        message: str,
        severity: ToastSeverity = ToastSeverity.INFO,
        parent: QWidget | None = None,
    ):
        super().__init__(message, parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.setStyleSheet(f"{_BASE_STYLE} {_STYLES[severity]}")
        self.setWordWrap(True)
        self.setMinimumWidth(280)
        self.setMaximumWidth(400)
        self.adjustSize()

        self._severity = severity

    def mousePressEvent(self, event) -> None:
        """Dismiss on click."""
        self.close()


class ToastManager:
    """Manages a stack of toast notifications anchored to a parent widget.

    Usage::

        mgr = ToastManager(main_window)
        mgr.show_info("Saved successfully")
        mgr.show_error("Connection failed")
    """

    def __init__(self, parent: QWidget):
        self._parent = parent
        self._active: list[Toast] = []
        self._margin = 12
        self._spacing = 6

    def show_info(self, message: str) -> None:
        self._show(message, ToastSeverity.INFO)

    def show_success(self, message: str) -> None:
        self._show(message, ToastSeverity.SUCCESS)

    def show_warning(self, message: str) -> None:
        self._show(message, ToastSeverity.WARNING)

    def show_error(self, message: str) -> None:
        self._show(message, ToastSeverity.ERROR)

    def _show(self, message: str, severity: ToastSeverity) -> None:
        toast = Toast(message, severity, self._parent)

        duration = _DURATIONS[severity]
        dismiss_timer = QTimer(toast)
        dismiss_timer.setSingleShot(True)
        dismiss_timer.timeout.connect(lambda: self._dismiss(toast))
        dismiss_timer.start(duration)

        self._active.append(toast)
        self._reposition()
        toast.show()

        # Slide-in animation from off-screen right
        final_pos = toast.pos()
        start_pos = QPoint(final_pos.x() + toast.width() + self._margin, final_pos.y())
        toast.move(start_pos)
        anim = QPropertyAnimation(toast, b"pos", toast)
        anim.setStartValue(start_pos)
        anim.setEndValue(final_pos)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        toast._slide_in_anim = anim  # prevent garbage collection

    def _dismiss(self, toast: Toast) -> None:
        if toast in self._active:
            self._active.remove(toast)

            # Slide-out animation before closing
            start_pos = toast.pos()
            end_pos = QPoint(start_pos.x() + toast.width() + self._margin, start_pos.y())
            anim = QPropertyAnimation(toast, b"pos", toast)
            anim.setStartValue(start_pos)
            anim.setEndValue(end_pos)
            anim.setDuration(300)
            anim.setEasingCurve(QEasingCurve.Type.InCubic)
            anim.finished.connect(toast.close)
            anim.finished.connect(toast.deleteLater)
            anim.finished.connect(self._reposition)
            anim.start()
            toast._slide_out_anim = anim  # prevent garbage collection

    def _reposition(self) -> None:
        """Stack active toasts from the bottom-right of the parent.

        Clamps toast positions to the available screen geometry so they
        never appear off-screen (e.g. when the window is near a screen edge).
        """
        parent_rect = self._parent.rect()
        parent_global = self._parent.mapToGlobal(parent_rect.bottomRight())

        # Get the screen geometry for the parent widget
        screen = QGuiApplication.screenAt(parent_global)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        screen_rect = screen.availableGeometry() if screen else None

        y_offset = self._margin
        for toast in reversed(self._active):
            toast.adjustSize()
            x = parent_global.x() - toast.width() - self._margin
            y = parent_global.y() - toast.height() - y_offset

            # Clamp to screen bounds
            if screen_rect is not None:
                x = max(screen_rect.left(), min(x, screen_rect.right() - toast.width()))
                y = max(screen_rect.top(), min(y, screen_rect.bottom() - toast.height()))

            toast.move(QPoint(x, y))
            y_offset += toast.height() + self._spacing
