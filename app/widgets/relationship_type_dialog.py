"""
app/widgets/relationship_type_dialog.py -- Relationship type picker dialog.

A small modal dialog that lets the user choose a relationship type when
creating a relationship via drag-to-connect in the knowledge graph.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.widgets.relationship_editor import RELATIONSHIP_TYPES, _display_rel_type


class RelationshipTypeDialog(QDialog):
    """Modal dialog for selecting a relationship type.

    Parameters
    ----------
    source_name : str
        Display name of the source entity.
    target_name : str
        Display name of the target entity.
    parent : QWidget | None
        Parent widget.
    """

    def __init__(
        self,
        source_name: str = "",
        target_name: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Choose Relationship Type")
        self.setMinimumSize(320, 300)
        self.setModal(True)

        self._selected_type: str = ""

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header
        header = QLabel(f"{source_name}  ->  {target_name}")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-weight: bold; font-size: 13px; padding: 6px;")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Relationship type list
        self._list = QListWidget()
        for rel_type in RELATIONSHIP_TYPES:
            item = QListWidgetItem(_display_rel_type(rel_type))
            item.setData(Qt.ItemDataRole.UserRole, rel_type)
            self._list.addItem(item)
        self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(self._on_accept)
        layout.addWidget(self._list, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        btn_row.addStretch()

        ok_btn = QPushButton("Create Relationship")
        ok_btn.setStyleSheet(
            "background-color: #2E7D32; padding: 6px 16px; font-weight: bold;"
        )
        ok_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

    def _on_accept(self) -> None:
        """Accept with the currently selected type."""
        current = self._list.currentItem()
        if current:
            self._selected_type = current.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def selected_type(self) -> str:
        """Return the selected relationship type string, or empty if cancelled."""
        return self._selected_type
