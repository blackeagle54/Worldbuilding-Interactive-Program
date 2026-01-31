"""
app/services/event_bus.py -- Application-wide event bus using Qt signals.

Singleton that provides typed signals for cross-panel communication.
All panels connect to the EventBus rather than directly to each other,
keeping the architecture loosely coupled.

Usage::

    from app.services.event_bus import EventBus

    bus = EventBus.instance()
    bus.entity_selected.connect(my_handler)
    bus.entity_selected.emit("thor-001")
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    """Application-wide signal bus for cross-panel communication.

    Signals
    -------
    entity_selected(str)
        Fired when the user selects an entity. Payload is the entity ID.
    entity_created(str)
        Fired when a new entity is created. Payload is the entity ID.
    entity_updated(str)
        Fired when an entity is modified. Payload is the entity ID.
    entity_deleted(str)
        Fired when an entity is deleted. Payload is the entity ID.
    step_changed(int)
        Fired when the active progression step changes.
    generation_started(str)
        Fired when option generation begins. Payload is template_id.
    generation_finished(str)
        Fired when option generation completes. Payload is template_id.
    claude_token(str)
        Fired for each streaming token from Claude. Payload is the token.
    claude_message(str)
        Fired for a complete Claude message.
    error_occurred(str)
        Fired when an error needs to be shown to the user.
    status_message(str)
        Fired to update the status bar message.
    """

    # Entity lifecycle
    entity_selected = Signal(str)
    entity_created = Signal(str)
    entity_updated = Signal(str)
    entity_deleted = Signal(str)

    # Step navigation
    step_changed = Signal(int)

    # Generation pipeline
    generation_started = Signal(str)
    generation_finished = Signal(str)

    # Claude streaming
    claude_token = Signal(str)
    claude_message = Signal(str)

    # Error and status
    error_occurred = Signal(str)
    status_message = Signal(str)

    # Singleton
    _instance: EventBus | None = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> EventBus:
        """Return the singleton EventBus instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.deleteLater()
            cls._instance = None
