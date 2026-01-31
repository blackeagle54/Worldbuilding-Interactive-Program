"""
app/panels/entity_browser.py -- Entity Browser dock panel.

Displays a searchable, filterable list of all entities in the world.
Sprint 2: Placeholder with basic structure.
Sprint 3: Full implementation with QSortFilterProxyModel, delegates, etc.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class EntityBrowserPanel(QWidget):
    """Searchable entity list panel."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search entities...")
        layout.addWidget(self._search)

        # Placeholder
        placeholder = QLabel("Entity list will appear here.\n\n(Sprint 3)")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(placeholder, 1)
