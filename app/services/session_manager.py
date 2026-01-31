"""
app/services/session_manager.py -- Session lifecycle management.

Handles:
    - Engine initialization on launch
    - Auto-save every 5 minutes
    - Crash recovery (detect incomplete sessions)
    - Backup on session start
    - Clean shutdown
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from app.services.event_bus import EventBus
from app.services.state_store import StateStore

logger = logging.getLogger(__name__)

AUTO_SAVE_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes


class SessionManager(QObject):
    """Manages the application session lifecycle.

    Signals
    -------
    session_started()
        Emitted when session initialization is complete.
    session_saved()
        Emitted after each auto-save.
    crash_detected(str)
        Emitted if an incomplete prior session is detected.
    """

    session_started = Signal()
    session_saved = Signal()
    crash_detected = Signal(str)

    def __init__(
        self,
        engine_manager: Any,
        state_store: StateStore,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._engine = engine_manager
        self._store = state_store
        self._bus = EventBus.instance()
        self._session_id = ""

        # Auto-save timer
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setInterval(AUTO_SAVE_INTERVAL_MS)
        self._auto_save_timer.timeout.connect(self._auto_save)

    # ------------------------------------------------------------------
    # Session start
    # ------------------------------------------------------------------

    def start_session(self) -> None:
        """Initialize the session: backup, sync, detect crashes."""

        # 1. Create backup
        try:
            bm = self._engine.backup_manager
            self._engine.with_lock(
                "backup_manager",
                lambda b: b.create_backup("session_start"),
            )
            logger.info("Session start backup created")
        except Exception:
            logger.debug("Backup manager unavailable", exc_info=True)

        # 2. Sync SQLite
        try:
            ss = self._engine.sqlite_sync
            self._engine.with_lock("sqlite_sync", lambda s: s.full_sync())
            logger.info("SQLite sync complete")
        except Exception:
            logger.debug("SQLite sync unavailable", exc_info=True)

        # 3. Build knowledge graph
        try:
            wg = self._engine.world_graph
            self._engine.with_lock("world_graph", lambda g: g.build_graph())
            logger.info("Knowledge graph built")
        except Exception:
            logger.debug("WorldGraph unavailable", exc_info=True)

        # 4. Start bookkeeper session
        try:
            bk = self._engine.bookkeeper
            session = self._engine.with_lock(
                "bookkeeper", lambda b: b.start_session()
            )
            if isinstance(session, dict):
                self._session_id = session.get("session_id", "")
            elif isinstance(session, str):
                self._session_id = session
            logger.info("Bookkeeper session started: %s", self._session_id)
        except Exception:
            logger.debug("Bookkeeper unavailable", exc_info=True)

        # 5. Detect crash (incomplete prior session)
        try:
            self._detect_crash()
        except Exception:
            logger.debug("Crash detection failed", exc_info=True)

        # 6. Start auto-save timer
        self._auto_save_timer.start()

        self._bus.status_message.emit("Session started")
        self.session_started.emit()

    def _detect_crash(self) -> None:
        """Check for signs of an incomplete prior session."""
        # Check if state has in-progress steps with no session
        in_progress = self._store.in_progress_steps
        if in_progress:
            msg = (
                f"Found {len(in_progress)} in-progress step(s) from a "
                f"previous session: {in_progress}. "
                "This may indicate an incomplete session."
            )
            logger.warning(msg)
            self.crash_detected.emit(msg)

    # ------------------------------------------------------------------
    # Auto-save
    # ------------------------------------------------------------------

    def _auto_save(self) -> None:
        """Periodic auto-save of state and engine data."""
        try:
            # Save state.json
            self._store.save()

            # Sync SQLite (incremental)
            try:
                self._engine.with_lock("sqlite_sync", lambda s: s.full_sync())
            except Exception:
                pass

            self._bus.status_message.emit("Auto-saved")
            self.session_saved.emit()
            logger.debug("Auto-save complete")

        except Exception:
            logger.exception("Auto-save failed")
            self._bus.error_occurred.emit("Auto-save failed")

    # ------------------------------------------------------------------
    # Step advancement
    # ------------------------------------------------------------------

    def check_step_completion(self, step_number: int) -> dict:
        """Check if a step's requirements are met.

        Returns
        -------
        dict
            {
                "complete": bool,
                "entity_count": int,
                "message": str,
            }
        """
        try:
            dm = self._engine.data_manager
            entities = self._engine.with_lock(
                "data_manager", lambda d: d.list_entities()
            )

            # Count entities created for this step
            # (In a full implementation this checks template_registry
            # for which templates belong to this step)
            step_entities = [
                e for e in entities
                if e.get("step_created") == step_number
                or e.get("_meta", {}).get("step") == step_number
            ]

            # Basic completion: at least one entity created for the step
            # (Steps 1-5 are planning steps that may not require entities)
            is_planning = step_number <= 5
            has_entities = len(step_entities) > 0

            if is_planning or has_entities:
                return {
                    "complete": True,
                    "entity_count": len(step_entities),
                    "message": (
                        f"Step {step_number} complete with "
                        f"{len(step_entities)} entities."
                    ),
                }
            else:
                return {
                    "complete": False,
                    "entity_count": len(step_entities),
                    "message": (
                        f"Step {step_number}: no entities created yet. "
                        "Create at least one entity to advance."
                    ),
                }

        except Exception as e:
            return {
                "complete": False,
                "entity_count": 0,
                "message": f"Could not check completion: {e}",
            }

    def advance_step(self) -> bool:
        """Advance to the next step if current step is complete.

        Returns True if advancement succeeded.
        """
        current = self._store.current_step
        check = self.check_step_completion(current)

        if not check["complete"]:
            self._bus.status_message.emit(check["message"])
            return False

        # Mark current step as completed
        self._store.add_completed_step(current)

        # Advance
        next_step = current + 1
        if next_step > 52:
            self._bus.status_message.emit(
                "All 52 steps complete! Worldbuilding journey finished."
            )
            return False

        self._store.set_current_step(next_step)

        # Determine phase for new step
        phase = self._step_to_phase(next_step)
        if phase:
            self._store.set_current_phase(phase)

        # Log advancement
        try:
            self._engine.with_lock(
                "bookkeeper",
                lambda b: b.log_event("step_status_changed", {
                    "from_step": current,
                    "to_step": next_step,
                    "phase": phase,
                }),
            )
        except Exception:
            pass

        self._bus.step_changed.emit(next_step)
        self._bus.status_message.emit(
            f"Advanced to Step {next_step}"
        )
        return True

    def _step_to_phase(self, step: int) -> str:
        """Map step number to phase name."""
        phases = [
            (1, 5, "foundation"),
            (6, 11, "cosmology"),
            (12, 15, "land"),
            (16, 24, "life"),
            (25, 30, "civilization"),
            (31, 34, "society"),
            (35, 39, "supernatural"),
            (40, 42, "history"),
            (43, 45, "language"),
            (46, 48, "travel"),
            (49, 50, "finishing"),
            (51, 52, "integration"),
        ]
        for start, end, name in phases:
            if start <= step <= end:
                return name
        return "foundation"

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def end_session(self) -> None:
        """Clean shutdown: stop timer, save, end bookkeeper session."""
        self._auto_save_timer.stop()

        # Final save
        self._store.save()

        # End bookkeeper session
        try:
            self._engine.with_lock(
                "bookkeeper",
                lambda b: b.end_session(),
            )
            logger.info("Bookkeeper session ended")
        except Exception:
            logger.debug("Bookkeeper end_session failed", exc_info=True)

        logger.info("Session ended")
