"""
app/panels/chat_panel.py -- Chat & Streaming panel.

Displays the conversation with Claude, including streaming tokens,
tool call indicators, and message history.
Sprint 2: Placeholder with basic structure.
Sprint 3-4: Full implementation with markdown rendering and streaming.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class ChatPanel(QWidget):
    """Chat interface with Claude."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Placeholder for message area
        placeholder = QLabel(
            "Chat with Claude\n\n"
            "Streaming conversation\n"
            "will appear here.\n\n"
            "(Sprint 3-4)"
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(placeholder, 1)

        # Input bar
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a message...")
        self._input.setEnabled(False)  # Disabled until Sprint 4
        layout.addWidget(self._input)
