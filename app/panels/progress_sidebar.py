"""
app/panels/progress_sidebar.py -- Progress Sidebar dock panel.

Displays the 52-step progression with phase grouping, completion status,
and step navigation.
Sprint 2: Placeholder with basic structure.
Sprint 3: Full implementation with tree view, icons, and click-to-navigate.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)


class ProgressSidebarPanel(QWidget):
    """52-step progression tracker."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        title = QLabel("Progress")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        placeholder = QLabel(
            "52-step progression\n"
            "with phase grouping\n"
            "will appear here.\n\n"
            "(Sprint 3)"
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(placeholder, 1)
