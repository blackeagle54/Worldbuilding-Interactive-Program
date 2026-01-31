"""
app/panels/option_comparison.py -- Option Comparison Panel.

Displays 2-4 option cards side-by-side after the option generation
pipeline runs.  The user can select an option, request regeneration,
or enter custom data.  Selected option flows into entity creation.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.event_bus import EventBus
from app.widgets.option_card import OptionCard

logger = logging.getLogger(__name__)


class OptionComparisonPanel(QWidget):
    """Side-by-side comparison of generated options.

    Signals
    -------
    option_selected(str, dict)
        Emitted when user selects an option: (option_id, option_data).
    regenerate_requested()
        Emitted when user clicks Regenerate All.
    custom_entry_requested()
        Emitted when user clicks Custom Entry.
    """

    option_selected = Signal(str, dict)
    regenerate_requested = Signal()
    custom_entry_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bus = EventBus.instance()
        self._options: list[dict] = []
        self._cards: list[OptionCard] = []
        self._selected_id: str = ""
        self._enforcement = None
        self._setup_ui()

    def set_enforcement(self, enforcement: Any) -> None:
        """Inject the enforcement service."""
        self._enforcement = enforcement

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        self._title_label = QLabel("Compare Options")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(self._title_label)

        header.addStretch()

        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("color: #888; font-size: 11px;")
        header.addWidget(self._stats_label)

        layout.addLayout(header)

        # Scrollable card area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._card_container = QWidget()
        self._card_layout = QHBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(12)
        self._scroll.setWidget(self._card_container)

        layout.addWidget(self._scroll, 1)

        # Empty state
        self._empty_label = QLabel(
            "No options to display.\n"
            "Generate options from the chat panel\n"
            "or click 'Generate' below."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self._empty_label)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._regen_btn = QPushButton("Regenerate All")
        self._regen_btn.clicked.connect(self.regenerate_requested.emit)
        btn_row.addWidget(self._regen_btn)

        self._custom_btn = QPushButton("Custom Entry")
        self._custom_btn.clicked.connect(self.custom_entry_requested.emit)
        btn_row.addWidget(self._custom_btn)

        btn_row.addStretch()

        self._confirm_btn = QPushButton("Confirm Selection")
        self._confirm_btn.setStyleSheet(
            "background-color: #2E7D32; padding: 6px 20px; font-weight: bold;"
        )
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self._confirm_btn)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def show_options(self, options: list[dict]) -> None:
        """Display a set of options as cards.

        Parameters
        ----------
        options : list[dict]
            Each dict should have: id, title, description, and optionally
            canon_connections, future_implications, inspirations.
        """
        self._options = options
        self._selected_id = ""
        self._confirm_btn.setEnabled(False)

        # Clear existing cards
        for card in self._cards:
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        if not options:
            self._empty_label.setVisible(True)
            self._scroll.setVisible(False)
            self._stats_label.setText("0 options")
            return

        self._empty_label.setVisible(False)
        self._scroll.setVisible(True)

        # Validate options if enforcement available
        valid_count = 0
        for opt in options:
            warnings = []
            passed = True

            if self._enforcement:
                from app.services.validation_pipeline import ValidationResult
                result = self._enforcement.pipeline.validate_entity(
                    opt.get("template_data", {}),
                    opt.get("template_data", {}).get("$id", ""),
                )
                passed = result.passed
                warnings = [w.message for w in result.warnings]

            if passed:
                valid_count += 1

            card = OptionCard(
                option_id=opt.get("id", f"opt-{len(self._cards) + 1}"),
                title=opt.get("title", opt.get("name", "(Untitled)")),
                description=opt.get("description", ""),
                canon_connections=opt.get("canon_connections", ""),
                future_implications=opt.get("future_implications", []),
                inspirations=opt.get("inspirations", {}),
                validation_passed=passed,
                validation_warnings=warnings,
            )
            card.selected.connect(self._on_card_selected)
            self._card_layout.addWidget(card)
            self._cards.append(card)

        self._stats_label.setText(
            f"{valid_count}/{len(options)} valid options"
        )

    def _on_card_selected(self, option_id: str) -> None:
        """Handle card selection."""
        self._selected_id = option_id
        self._confirm_btn.setEnabled(True)

        # Update visual selection
        for card in self._cards:
            card.set_selected(card.option_id == option_id)

    def _on_confirm(self) -> None:
        """Handle confirm button."""
        if not self._selected_id:
            return

        # Find the selected option data
        for opt in self._options:
            if opt.get("id") == self._selected_id:
                self.option_selected.emit(self._selected_id, opt)

                # Log user decision
                if self._enforcement:
                    self._enforcement.log_user_decision("option_chosen", {
                        "option_id": self._selected_id,
                        "option_title": opt.get("title", ""),
                    })

                self._bus.status_message.emit(
                    f"Selected option: {opt.get('title', self._selected_id)}"
                )
                break

    def clear(self) -> None:
        """Clear all options."""
        self.show_options([])
