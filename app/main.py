"""
app/main.py -- Application entry point.

Initializes the QApplication, applies the dark theme, creates the
MainWindow, and runs the event loop.

Usage::

    python -m app.main
    # or
    python app/main.py
"""

from __future__ import annotations

import logging
import os
import sys
import traceback

# Ensure project root is on sys.path
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _setup_logging() -> None:
    """Configure logging for the desktop application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _global_exception_hook(exc_type, exc_value, exc_tb):
    """Last-resort handler for uncaught exceptions.

    Logs the traceback and shows a message box (if a QApplication exists).
    """
    logger = logging.getLogger("app")
    logger.critical(
        "Uncaught exception: %s",
        "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
    )

    # Try to show a message box
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance()
        if app is not None:
            QMessageBox.critical(
                None,
                "Unexpected Error",
                f"An unexpected error occurred:\n\n{exc_value}\n\n"
                "The application will attempt to continue.\n"
                "Please check the logs for details.",
            )
    except Exception:
        pass  # Can't show GUI -- already logged above


def main() -> int:
    """Launch the Worldbuilding Interactive Program."""
    _setup_logging()
    logger = logging.getLogger("app")
    logger.info("Starting Worldbuilding Interactive Program")

    # Install global exception hook
    sys.excepthook = _global_exception_hook

    # Must create QApplication before anything else Qt-related
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    # Apply theme
    from app.theme.dark_theme import apply_theme
    apply_theme(app)

    # Initialize the engine manager
    try:
        from engine.engine_manager import EngineManager
        EngineManager(project_root=_PROJECT_ROOT)
        logger.info("Engine manager initialized")
    except Exception:
        logger.exception("Failed to initialize engine manager")

    # Initialize state store
    try:
        from app.services.state_store import StateStore
        StateStore.instance(_PROJECT_ROOT)
        logger.info("State store initialized")
    except Exception:
        logger.exception("Failed to initialize state store")

    # Create and show the main window
    from app.main_window import MainWindow
    window = MainWindow(project_root=_PROJECT_ROOT)
    window.show()
    logger.info("Main window displayed")

    # Run the event loop
    exit_code = app.exec()

    # Shutdown
    logger.info("Shutting down...")
    try:
        store = StateStore.instance()
        store.shutdown()
    except Exception:
        logger.exception("Error during state store shutdown")

    logger.info("Goodbye!")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
