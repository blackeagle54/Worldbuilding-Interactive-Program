"""
app/widgets/loading_overlay.py -- Loading overlay and busy-state widgets.

Provides a semi-transparent overlay with spinner text for panels that are
loading data, and a small inline spinner label for lighter indicators.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class LoadingOverlay(QWidget):
    """Semi-transparent overlay with a spinner message.

    Usage::

        overlay = LoadingOverlay(parent_widget)
        overlay.show_loading("Loading entities...")
        # ... later ...
        overlay.hide_loading()
    """

    _SPINNER_CHARS = ["|", "/", "-", "\\"]

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label = QLabel("")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "color: #ddd; font-size: 14px; font-weight: bold; "
            "background: transparent;"
        )
        layout.addWidget(self._label)

        self._message = ""
        self._spinner_idx = 0

        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._tick)

    def show_loading(self, message: str = "Loading...") -> None:
        """Show the overlay with a spinning indicator."""
        self._message = message
        self._spinner_idx = 0
        self._update_text()
        self.setGeometry(self.parent().rect())
        self.setVisible(True)
        self.raise_()
        self._timer.start()

    def hide_loading(self) -> None:
        """Hide the overlay."""
        self._timer.stop()
        self.setVisible(False)

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
        super().resizeEvent(event)


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
