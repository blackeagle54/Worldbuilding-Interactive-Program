"""
app/widgets/loading_overlay.py -- Loading overlay and busy-state widgets.

Provides a semi-transparent overlay with spinner text for panels that are
loading data, and a small inline spinner label for lighter indicators.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class LoadingOverlay(QWidget):
    """Semi-transparent overlay with a spinner message and optional cancel button.

    Usage::

        overlay = LoadingOverlay(parent_widget)
        overlay.cancelled.connect(my_cancel_handler)
        overlay.show_loading("Loading entities...", cancellable=True)
        # ... later ...
        overlay.hide_loading()
    """

    cancelled = Signal()

    _SPINNER_CHARS = ["|", "/", "-", "\\"]

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setVisible(False)
        parent.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label = QLabel("")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "color: #ddd; font-size: 14px; font-weight: bold; "
            "background: transparent;"
        )
        layout.addWidget(self._label)

        # Cancel button (hidden by default, shown when cancellable=True)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setMaximumWidth(80)
        self._cancel_btn.setStyleSheet(
            "background-color: #8B0000; color: #ddd; padding: 4px 12px; "
            "font-size: 12px; border-radius: 3px;"
        )
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._message = ""
        self._spinner_idx = 0

        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._tick)

    def show_loading(self, message: str = "Loading...", cancellable: bool = False) -> None:
        """Show the overlay with a spinning indicator.

        Parameters
        ----------
        message : str
            Text to display alongside the spinner.
        cancellable : bool
            If ``True``, show a Cancel button that emits :attr:`cancelled`.
        """
        self._message = message
        self._spinner_idx = 0
        self._cancel_btn.setVisible(cancellable)
        self._update_text()
        self.setGeometry(self.parent().rect())
        self.setVisible(True)
        self.raise_()
        self._timer.start()

    def hide_loading(self) -> None:
        """Hide the overlay."""
        self._timer.stop()
        self._cancel_btn.setVisible(False)
        self.setVisible(False)

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        self.cancelled.emit()
        self.hide_loading()

    def _tick(self) -> None:
        self._spinner_idx = (self._spinner_idx + 1) % len(self._SPINNER_CHARS)
        self._update_text()

    def _update_text(self) -> None:
        char = self._SPINNER_CHARS[self._spinner_idx]
        self._label.setText(f"{char}  {self._message}  {char}")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))
        painter.end()
        super().paintEvent(event)

    def resizeEvent(self, event) -> None:
        if self.isVisible() and self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            if self.isVisible():
                self.setGeometry(self.parent().rect())
        return super().eventFilter(obj, event)


class SpinnerLabel(QLabel):
    """Small inline label that shows an animated spinner when active.

    Usage::

        spinner = SpinnerLabel()
        layout.addWidget(spinner)
        spinner.start("Generating...")
        # ... later ...
        spinner.stop()
    """

    _FRAMES = [".", "..", "...", ".."]

    def __init__(self, parent: QWidget | None = None):
        super().__init__("", parent)
        self.setStyleSheet("color: #888; font-style: italic; font-size: 11px;")
        self._message = ""
        self._frame_idx = 0

        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._tick)

    def start(self, message: str = "Working") -> None:
        self._message = message
        self._frame_idx = 0
        self._update_text()
        self.setVisible(True)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.setVisible(False)
        self.setText("")

    def _tick(self) -> None:
        self._frame_idx = (self._frame_idx + 1) % len(self._FRAMES)
        self._update_text()

    def _update_text(self) -> None:
        dots = self._FRAMES[self._frame_idx]
        self.setText(f"{self._message}{dots}")
