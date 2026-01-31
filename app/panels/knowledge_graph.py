"""
app/panels/knowledge_graph.py -- Knowledge Graph visualization panel.

Displays an interactive node-edge graph of entities and their relationships.
Sprint 2: Placeholder with basic structure.
Sprint 3: Full QGraphicsView implementation with NetworkX layout.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)


class KnowledgeGraphPanel(QWidget):
    """Interactive knowledge graph visualization."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        placeholder = QLabel(
            "Knowledge Graph\n\n"
            "Interactive entity relationship map\n"
            "will appear here.\n\n"
            "(Sprint 3)"
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #888; font-style: italic; font-size: 14px;")
        layout.addWidget(placeholder, 1)
