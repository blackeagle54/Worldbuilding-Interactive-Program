"""
app/theme/dark_theme.py -- Dark theme configuration.

Applies qt-material's dark_teal theme with custom QSS overrides for
the Worldbuilding Interactive Program.

Usage::

    from app.theme.dark_theme import apply_theme
    apply_theme(app)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

# Custom QSS overrides applied on top of qt-material
_CUSTOM_QSS = """
/* Dock widget title bars */
QDockWidget {
    font-weight: bold;
    font-size: 13px;
}

QDockWidget::title {
    padding: 6px 8px;
}

/* Status bar */
QStatusBar {
    font-size: 12px;
}

/* Scroll bars -- slightly wider for comfort */
QScrollBar:vertical {
    width: 12px;
}
QScrollBar:horizontal {
    height: 12px;
}

/* Tool tips */
QToolTip {
    padding: 4px 8px;
    font-size: 12px;
}

/* Menu bar spacing */
QMenuBar::item {
    padding: 4px 10px;
}

/* Placeholder text in line edits */
QLineEdit[placeholderText] {
    font-style: italic;
}
"""


def apply_theme(app: "QApplication") -> None:
    """Apply the dark teal material theme with custom overrides.

    Parameters
    ----------
    app : QApplication
        The application instance to theme.
    """
    try:
        from qt_material import apply_stylesheet
        apply_stylesheet(app, theme="dark_teal.xml")
        logger.info("Applied qt-material dark_teal theme")
    except Exception:
        logger.warning("qt-material theme failed, falling back to Fusion", exc_info=True)
        from PySide6.QtWidgets import QApplication
        QApplication.setStyle("Fusion")

    # Apply custom overrides on top
    existing = app.styleSheet() or ""
    app.setStyleSheet(existing + _CUSTOM_QSS)
