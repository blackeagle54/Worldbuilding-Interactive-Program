"""
app/theme/dark_theme.py -- Dark theme configuration.

Applies a modern dark theme with custom QSS overrides for
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

# Modern dark theme QSS
_CUSTOM_QSS = """
/* ===== Global ===== */
* {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #1a1a2e;
}

QWidget {
    background-color: #1a1a2e;
    color: #d0d0e0;
}

/* ===== Menu Bar ===== */
QMenuBar {
    background-color: #1a1a2e;
    border-bottom: 1px solid #2a2a4a;
    padding: 2px 0;
    font-size: 12px;
}

QMenuBar::item {
    padding: 4px 10px;
    background: transparent;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #2a4a5e;
}

QMenu {
    background-color: #16213e;
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #2a4a5e;
}

QMenu::separator {
    height: 1px;
    background-color: #2a2a4a;
    margin: 4px 8px;
}

/* ===== Toolbar ===== */
QToolBar {
    background-color: #1a1a2e;
    border-bottom: 1px solid #2a2a4a;
    spacing: 4px;
    padding: 2px 4px;
}

QToolButton {
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    color: #d0d0e0;
    font-size: 12px;
}

QToolButton:hover {
    background-color: #2a4a5e;
}

QToolButton:checked {
    background-color: #2a4a5e;
}

/* ===== Splitter ===== */
QSplitter::handle {
    background-color: #2a2a4a;
}

QSplitter::handle:horizontal {
    width: 2px;
}

QSplitter::handle:vertical {
    height: 2px;
}

QSplitter::handle:hover {
    background-color: #3a5a7e;
}

/* ===== Sidebar Panels ===== */
QWidget#leftSidebar, QWidget#rightSidebar {
    background-color: #1a1a2e;
}

/* ===== Scroll Bars ===== */
QScrollBar:vertical {
    width: 8px;
    background: transparent;
    border: none;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #2a2a4a;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #3a5a7e;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    border: none;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    height: 8px;
    background: transparent;
    border: none;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #2a2a4a;
    border-radius: 4px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #3a5a7e;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    border: none;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

/* ===== Buttons ===== */
QPushButton {
    background-color: #2a4a5e;
    color: #d0d0e0;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #3a5a7e;
}

QPushButton:pressed {
    background-color: #1a3a4e;
}

QPushButton:disabled {
    background-color: #1a2a3e;
    color: #555;
}

/* ===== Input Fields ===== */
QLineEdit {
    background-color: #0f0f1a;
    color: #d0d0e0;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: #3a5a7e;
}

QLineEdit:focus {
    border-color: #3a5a7e;
}

QPlainTextEdit {
    background-color: #0f0f1a;
    color: #d0d0e0;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 14px;
    selection-background-color: #3a5a7e;
}

QPlainTextEdit:focus {
    border-color: #3a5a7e;
}

QTextEdit {
    background-color: #0f0f1a;
    color: #d0d0e0;
    border: none;
    selection-background-color: #3a5a7e;
}

/* ===== Combo Boxes ===== */
QComboBox {
    background-color: #0f0f1a;
    color: #d0d0e0;
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
}

QComboBox:hover {
    border-color: #3a5a7e;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #16213e;
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    selection-background-color: #2a4a5e;
}

/* ===== Labels ===== */
QLabel {
    background: transparent;
    color: #d0d0e0;
}

/* ===== Table Views ===== */
QTableView {
    background-color: #16213e;
    alternate-background-color: #1a2040;
    color: #d0d0e0;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    gridline-color: #2a2a4a;
    selection-background-color: #2a4a5e;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #16213e;
    color: #8888aa;
    border: none;
    border-bottom: 1px solid #2a2a4a;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: bold;
}

/* ===== Tree Widget ===== */
QTreeWidget {
    background-color: #16213e;
    color: #d0d0e0;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    outline: none;
}

QTreeWidget::item {
    padding: 2px 4px;
    border-radius: 4px;
}

QTreeWidget::item:selected {
    background-color: #2a4a5e;
}

QTreeWidget::item:hover {
    background-color: #1a3a4e;
}

QTreeWidget::branch {
    background: transparent;
}

/* ===== Progress Bar ===== */
QProgressBar {
    background-color: #0f0f1a;
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    text-align: center;
    color: #d0d0e0;
    font-size: 11px;
}

QProgressBar::chunk {
    background-color: #2a4a5e;
    border-radius: 3px;
}

/* ===== Status Bar ===== */
QStatusBar {
    background-color: #1a1a2e;
    border-top: 1px solid #2a2a4a;
    color: #8888aa;
    font-size: 11px;
}

/* ===== Scroll Area ===== */
QScrollArea {
    background-color: transparent;
    border: none;
}

/* ===== Check Boxes ===== */
QCheckBox {
    background: transparent;
    spacing: 4px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #2a2a4a;
    background-color: #0f0f1a;
}

QCheckBox::indicator:checked {
    background-color: #2a4a5e;
    border-color: #3a5a7e;
}

/* ===== Tool Tips ===== */
QToolTip {
    background-color: #16213e;
    color: #d0d0e0;
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ===== Graphics View ===== */
QGraphicsView {
    background-color: #0f0f1a;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
}

/* ===== Tab Widget (if any) ===== */
QTabWidget::pane {
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    background-color: #1a1a2e;
}

QTabBar::tab {
    background-color: #16213e;
    color: #8888aa;
    border: none;
    padding: 6px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #1a1a2e;
    color: #d0d0e0;
}

QTabBar::tab:hover {
    background-color: #2a4a5e;
    color: #d0d0e0;
}
"""


def apply_theme(app: "QApplication") -> None:
    """Apply the modern dark theme with custom overrides.

    Parameters
    ----------
    app : QApplication
        The application instance to theme.
    """
    try:
        from qt_material import apply_stylesheet
        apply_stylesheet(app, theme="dark_teal.xml")
        logger.info("Applied qt-material dark_teal base theme")
    except Exception:
        logger.warning("qt-material theme failed, falling back to Fusion", exc_info=True)
        from PySide6.QtWidgets import QApplication
        QApplication.setStyle("Fusion")

    # Apply custom overrides on top (overrides qt-material styles)
    existing = app.styleSheet() or ""
    app.setStyleSheet(existing + _CUSTOM_QSS)
