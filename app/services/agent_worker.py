"""
app/services/agent_worker.py -- QThread worker for Claude conversations.

Runs ClaudeClient.send_message() in a background thread and emits Qt
signals for each streaming event.  The ChatPanel connects to these signals
to update the UI on the main thread.

Usage::

    worker = AgentWorker(claude_client)
    worker.token_received.connect(on_token)
    worker.tool_called.connect(on_tool)
    worker.finished_signal.connect(on_done)
    worker.error_occurred.connect(on_error)
    worker.send("Tell me about my pantheon", system_prompt, history)
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from app.services.claude_client import ClaudeClient, EventType, StreamEvent

logger = logging.getLogger(__name__)


class AgentWorker(QThread):
    """Background thread for Claude API calls.

    Signals
    -------
    token_received(str)
        Emitted for each text token in the stream.
    tool_called(str, str)
        Emitted when Claude calls a tool: (tool_name, tool_input_json).
    tool_result_received(str, str)
        Emitted when a tool result is ready: (tool_name, result_preview).
    finished_signal(str)
        Emitted when the full response is complete. Payload is the
        accumulated response text.
    error_occurred(str)
        Emitted on error. Payload is the error message.
    """

    token_received = Signal(str)
    tool_called = Signal(str, str)
    tool_result_received = Signal(str, str)
    finished_signal = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, client: ClaudeClient, parent=None):
        super().__init__(parent)
        self._client = client
        self._user_message = ""
        self._system_prompt = ""
        self._history: list[dict] = []

    def send(
        self,
        user_message: str,
        system_prompt: str = "",
        conversation_history: list[dict] | None = None,
    ) -> None:
        """Queue a message and start the worker thread.

        If already running, does nothing (caller should wait or cancel).
        """
        if self.isRunning():
            logger.warning("AgentWorker already running, ignoring send()")
            return

        self._user_message = user_message
        self._system_prompt = system_prompt
        self._history = list(conversation_history or [])
        self.start()

    def cancel(self) -> None:
        """Request cancellation of the current request."""
        self._client.cancel()

    def run(self) -> None:
        """Thread entry point -- streams events from ClaudeClient."""
        try:
            for event in self._client.send_message(
                self._user_message,
                self._system_prompt,
                self._history,
            ):
                self._handle_event(event)
        except Exception as e:
            logger.exception("AgentWorker run() failed")
            self.error_occurred.emit(str(e))

    def _handle_event(self, event: StreamEvent) -> None:
        """Dispatch a stream event to the appropriate signal."""
        if event.type == EventType.TOKEN:
            self.token_received.emit(event.data)

        elif event.type == EventType.TOOL_CALL:
            import json
            input_json = json.dumps(event.tool_input, indent=2, default=str)
            self.tool_called.emit(event.tool_name, input_json)

        elif event.type == EventType.TOOL_RESULT:
            self.tool_result_received.emit(event.tool_name, event.data)

        elif event.type == EventType.MESSAGE_COMPLETE:
            self.finished_signal.emit(event.data)

        elif event.type == EventType.ERROR:
            self.error_occurred.emit(event.data)
