"""
app/widgets/option_card.py -- Single option card widget.

Displays one worldbuilding option with title, description, inspirations,
canon connections, and a validation badge.  Used inside the
OptionComparisonPanel.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class OptionCard(QFrame):
    """A card displaying a single worldbuilding option.

    Signals
    -------
    selected(str)
        Emitted when the user clicks Select.  Payload is the option ID.
    """

    selected = Signal(str)

    def __init__(
        self,
        option_id: str,
        title: str,
        description: str,
        canon_connections: str = "",
        future_implications: list[str] | None = None,
        inspirations: dict | None = None,
        validation_passed: bool = True,
        validation_warnings: list[str] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._option_id = option_id

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setLineWidth(2)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(250)

        self._build_ui(
            title, description, canon_connections,
            future_implications or [],
            inspirations or {},
            validation_passed,
            validation_warnings or [],
        )

    @property
    def option_id(self) -> str:
        return self._option_id

    def _build_ui(
        self,
        title: str,
        description: str,
        canon_connections: str,
        future_implications: list[str],
        inspirations: dict,
        validation_passed: bool,
        validation_warnings: list[str],
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Header row: badge + title
        header = QHBoxLayout()

        # Validation badge
        if validation_passed:
            badge = QLabel("VALID")
            badge.setStyleSheet(
                "background-color: #2E7D32; color: white; "
                "padding: 2px 6px; border-radius: 3px; font-size: 10px;"
            )
        else:
            badge = QLabel("ISSUES")
            badge.setStyleSheet(
                "background-color: #C62828; color: white; "
                "padding: 2px 6px; border-radius: 3px; font-size: 10px;"
            )
        header.addWidget(badge)

        # Option ID label
        id_label = QLabel(self._option_id.upper())
        id_label.setStyleSheet("color: #888; font-size: 10px;")
        header.addWidget(id_label)
        header.addStretch()
        layout.addLayout(header)

        # Title
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Description
        desc = QTextEdit()
        desc.setReadOnly(True)
        desc.setPlainText(description)
        desc.setMaximumHeight(120)
        desc.setStyleSheet("background-color: transparent; border: none;")
        layout.addWidget(desc)

        # Canon connections
        if canon_connections:
            conn_label = QLabel(f"Canon: {canon_connections}")
            conn_label.setWordWrap(True)
            conn_label.setStyleSheet("color: #4FC3F7; font-size: 11px;")
            layout.addWidget(conn_label)

        # Inspirations
        if inspirations:
            myths = inspirations.get("mythologies", "")
            authors = inspirations.get("authors", "")
            parts = []
            if myths:
                parts.append(f"Myths: {myths}")
            if authors:
                parts.append(f"Authors: {authors}")
            if parts:
                insp_label = QLabel(" | ".join(parts))
                insp_label.setWordWrap(True)
                insp_label.setStyleSheet("color: #CE93D8; font-size: 11px;")
                layout.addWidget(insp_label)

        # Future implications
        if future_implications:
            impl_text = ", ".join(future_implications[:3])
            if len(future_implications) > 3:
                impl_text += f" (+{len(future_implications) - 3} more)"
            impl_label = QLabel(f"Implications: {impl_text}")
            impl_label.setWordWrap(True)
            impl_label.setStyleSheet("color: #FFB74D; font-size: 11px;")
            layout.addWidget(impl_label)

        # Validation warnings
        if validation_warnings:
            for warn in validation_warnings[:2]:
                w_label = QLabel(f"Warning: {warn}")
                w_label.setWordWrap(True)
                w_label.setStyleSheet("color: #FFA726; font-size: 10px;")
                layout.addWidget(w_label)

        layout.addStretch()

        # Select button
        btn_row = QHBoxLayout()
        self._select_btn = QPushButton("Select This Option")
        self._select_btn.setStyleSheet(
            "background-color: #1565C0; padding: 6px 16px; font-weight: bold;"
        )
        self._select_btn.clicked.connect(lambda: self.selected.emit(self._option_id))
        btn_row.addStretch()
        btn_row.addWidget(self._select_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def set_selected(self, is_selected: bool) -> None:
        """Visually highlight this card as selected."""
        if is_selected:
            self.setStyleSheet("QFrame { border: 2px solid #1565C0; }")
        else:
            self.setStyleSheet("")
