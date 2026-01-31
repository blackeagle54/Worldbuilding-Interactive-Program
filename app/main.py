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

import os
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

import logging
import sys
import traceback

# Ensure project root is on sys.path
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.paths import get_project_root, is_frozen, get_bundle_dir, get_user_data_dir, ensure_user_data


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

    # Resolve project root (handles frozen/dev mode)
    project_root = get_project_root()
    logger.info("Project root: %s (frozen=%s)", project_root, is_frozen())

    # On first frozen run, copy bundled data to user data dir
    if is_frozen():
        ensure_user_data(get_bundle_dir(), get_user_data_dir())

    # Must create QApplication before anything else Qt-related
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    # Apply theme
    from app.theme.dark_theme import apply_theme
    apply_theme(app)

    # Initialize the engine manager
    engine = None
    try:
        from engine.engine_manager import EngineManager
        engine = EngineManager.get_instance(project_root)
        logger.info("Engine manager initialized")
    except Exception:
        logger.exception("Failed to initialize engine manager")

    # Initialize state store
    store = None
    try:
        from app.services.state_store import StateStore
        store = StateStore.instance(project_root)
        logger.info("State store initialized")
    except Exception:
        logger.exception("Failed to initialize state store")

    # Create and show the main window
    from app.main_window import MainWindow
    window = MainWindow(project_root=project_root)

    # Inject dependencies into panels
    if engine is not None:
        window.inject_engine(engine)
    if store is not None:
        window.inject_state_store(store)

    # Initialize enforcement service
    enforcement = None
    try:
        from app.services.enforcement import EnforcementService
        current_step = store.current_step if store else 1
        enforcement = EnforcementService(
            engine_manager=engine,
            current_step=current_step,
        )
        window.inject_enforcement(enforcement)
        logger.info("Enforcement service initialized")
    except Exception:
        logger.exception("Failed to initialize enforcement service")

    # Initialize Claude client
    try:
        from app.services.claude_client import ClaudeClient
        claude_client = ClaudeClient(
            engine_manager=engine,
            current_step=store.current_step if store else 1,
        )
        window.inject_claude(claude_client)
        logger.info("Claude client initialized (backend: %s)", claude_client.backend.name)
    except Exception:
        logger.exception("Failed to initialize Claude client")

    # Initialize session manager
    session_mgr = None
    if engine is not None and store is not None:
        try:
            from app.services.session_manager import SessionManager
            session_mgr = SessionManager(engine, store)
            window.inject_session_manager(session_mgr)
            session_mgr.start_session()
            logger.info("Session manager started")
        except Exception:
            logger.exception("Failed to initialize session manager")

    window.show()
    logger.info("Main window displayed")

    # Show welcome dialog on first run
    from app.widgets.welcome_dialog import should_show_welcome, WelcomeDialog
    if should_show_welcome():
        welcome = WelcomeDialog(window)
        welcome.exec()

    # Run the event loop
    exit_code = app.exec()

    # Shutdown
    logger.info("Shutting down...")
    if session_mgr is not None:
        try:
            session_mgr.end_session()
        except Exception:
            logger.exception("Error during session shutdown")

    try:
        store = StateStore.instance()
        store.shutdown()
    except Exception:
        logger.exception("Error during state store shutdown")

    logger.info("Goodbye!")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
