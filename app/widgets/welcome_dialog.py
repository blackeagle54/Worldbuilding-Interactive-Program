"""
app/widgets/welcome_dialog.py -- First-run welcome dialog.

Shows on first launch to introduce the application, detect prerequisites
(Claude CLI, API key), and provide a brief panel tour.
"""

from __future__ import annotations

import logging
import shutil
import os

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_ORG_NAME = "WorldbuildingApp"
_APP_NAME = "WorldbuildingInteractiveProgram"
_SETTING_KEY = "first_run_complete"


def should_show_welcome() -> bool:
    """Return True if the welcome dialog should be shown."""
    settings = QSettings(_ORG_NAME, _APP_NAME)
    return not settings.value(_SETTING_KEY, False, type=bool)


def mark_welcome_complete() -> None:
    """Record that the user has seen the welcome dialog."""
    settings = QSettings(_ORG_NAME, _APP_NAME)
    settings.setValue(_SETTING_KEY, True)


def _check_claude_cli() -> tuple[bool, str]:
    """Check if the Claude CLI is available."""
    path = shutil.which("claude")
    if path:
        return True, f"Found: {path}"
    return False, "Not found in PATH"


def _check_api_key() -> tuple[bool, str]:
    """Check if the Anthropic API key is set."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        masked = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
        return True, f"Set ({masked})"
    return False, "ANTHROPIC_API_KEY not set"


class _StatusRow(QWidget):
    """A single prerequisite status row with icon + text."""

    def __init__(self, label: str, ok: bool, detail: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        icon = QLabel("\u2713" if ok else "\u2717")
        icon.setStyleSheet(
            f"color: {'#4CAF50' if ok else '#F44336'}; "
            "font-weight: bold; font-size: 14px;"
        )
        icon.setFixedWidth(20)
        layout.addWidget(icon)

        text = QLabel(f"<b>{label}:</b>  {detail}")
        text.setStyleSheet("font-size: 12px;")
        layout.addWidget(text, 1)


class WelcomeDialog(QDialog):
    """First-run welcome and prerequisite check dialog."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Worldbuilding Interactive Program")
        self.setMinimumSize(520, 480)
        self.resize(560, 520)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Welcome to the\nWorldbuilding Interactive Program")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ddd;")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "A guided 52-step worldbuilding tool powered by Claude AI,\n"
            "based on 'The Complete Art of World Building' by Randy Ellefson.\n\n"
            "This application helps you build rich, consistent fictional worlds\n"
            "through structured creation, AI-assisted generation, and\n"
            "automatic cross-referencing."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("font-size: 12px; color: #aaa;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Prerequisites
        prereq_label = QLabel("Prerequisites")
        prereq_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(prereq_label)

        cli_ok, cli_detail = _check_claude_cli()
        api_ok, api_detail = _check_api_key()

        layout.addWidget(_StatusRow("Claude CLI", cli_ok, cli_detail))
        layout.addWidget(_StatusRow("API Key", api_ok, api_detail))

        if not cli_ok and not api_ok:
            hint = QLabel(
                "Neither Claude CLI nor API key detected. "
                "The app will run in offline mode.\n"
                "Install the Claude CLI or set ANTHROPIC_API_KEY for AI features."
            )
            hint.setStyleSheet("color: #FFC107; font-size: 11px;")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        elif cli_ok or api_ok:
            hint = QLabel("AI features are available. You're ready to go.")
            hint.setStyleSheet("color: #4CAF50; font-size: 11px;")
            layout.addWidget(hint)

        # Panel tour
        tour_label = QLabel("Your Workspace")
        tour_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(tour_label)

        panels = [
            ("Entity Browser (left)", "Browse, search, and filter all world entities"),
            ("Knowledge Graph (center)", "Visual map of entity relationships"),
            ("Progress Sidebar (right)", "Track your journey through all 52 steps"),
            ("Chat Panel (bottom)", "Converse with Claude for guided worldbuilding"),
            ("Options Panel (bottom tab)", "Compare AI-generated options side by side"),
        ]
        for name, desc_text in panels:
            row = QLabel(f"  \u2022  <b>{name}</b> -- {desc_text}")
            row.setStyleSheet("font-size: 11px; color: #bbb;")
            row.setWordWrap(True)
            layout.addWidget(row)

        layout.addStretch()

        # Button
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        get_started = QPushButton("Get Started")
        get_started.setStyleSheet(
            "background-color: #1565C0; padding: 8px 32px; "
            "font-weight: bold; font-size: 13px;"
        )
        get_started.clicked.connect(self._on_get_started)
        btn_row.addWidget(get_started)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_get_started(self) -> None:
        mark_welcome_complete()
        self.accept()
