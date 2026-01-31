"""
app/panels/chat_panel.py -- Chat & Streaming panel.

Displays the conversation with Claude, including styled message bubbles,
basic markdown rendering, streaming token display, tool call indicators,
and a stop button for cancellation.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.event_bus import EventBus

logger = logging.getLogger(__name__)

MAX_HISTORY = 50

# CSS for message bubbles inside the QTextEdit
_CHAT_CSS = """
body {
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    color: #ddd;
    margin: 0;
    padding: 4px;
}
.msg {
    margin: 6px 0;
    padding: 8px 12px;
    border-radius: 8px;
    max-width: 80%;
    line-height: 1.4;
}
.user-msg {
    background-color: #1a3a5c;
    margin-left: 20%;
    text-align: left;
}
.claude-msg {
    background-color: #2a2a3a;
    margin-right: 20%;
}
.system-msg {
    background-color: #333;
    color: #999;
    font-style: italic;
    text-align: center;
    font-size: 12px;
}
.tool-msg {
    background-color: #1a2a1a;
    color: #7c7;
    font-size: 11px;
    margin-right: 20%;
    border-left: 3px solid #4a4;
}
.sender {
    font-weight: bold;
    font-size: 11px;
    color: #888;
    margin-bottom: 2px;
}
code {
    background-color: #1a1a2e;
    padding: 1px 4px;
    border-radius: 3px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}
pre {
    background-color: #1a1a2e;
    padding: 8px;
    border-radius: 4px;
    overflow-x: auto;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}
strong { color: #fff; }
em { color: #bbb; }
"""


def _md_to_html(text: str) -> str:
    """Minimal markdown-to-HTML conversion for chat messages."""
    text = html.escape(text)

    # Code blocks (triple backtick)
    text = re.sub(
        r"```(\w*)\n?(.*?)```",
        r"<pre><code>\2</code></pre>",
        text,
        flags=re.DOTALL,
    )

    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

    # Italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

    # Line breaks
    text = text.replace("\n", "<br>")

    return text


class ChatPanel(QWidget):
    """Chat interface with Claude, featuring message bubbles and streaming."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bus = EventBus.instance()
        self._worker = None  # AgentWorker, set via set_worker()
        self._streaming = False
        self._stream_buffer = ""
        self._conversation_history: list[dict] = []
        self._system_prompt = ""
        self._setup_ui()
        self._connect_signals()

        # Add welcome message
        self._append_system_message(
            "Welcome to Worldbuilding Interactive Program. "
            "Claude will assist you through the 52-step process."
        )

    def set_worker(self, worker: Any) -> None:
        """Inject the AgentWorker after construction."""
        self._worker = worker
        # Connect worker signals
        worker.token_received.connect(self._on_worker_token)
        worker.tool_called.connect(self._on_worker_tool_called)
        worker.tool_result_received.connect(self._on_worker_tool_result)
        worker.finished_signal.connect(self._on_worker_finished)
        worker.error_occurred.connect(self._on_worker_error)

    def set_system_prompt(self, prompt: str) -> None:
        """Set the system prompt for future messages."""
        self._system_prompt = prompt

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Message display area
        self._display = QTextEdit()
        self._display.setReadOnly(True)
        self._display.document().setDefaultStyleSheet(_CHAT_CSS)
        self._display.setHtml("<body></body>")
        layout.addWidget(self._display, 1)

        # Typing indicator
        self._typing_label = QLabel("")
        self._typing_label.setStyleSheet("color: #888; font-style: italic; font-size: 11px;")
        self._typing_label.setVisible(False)
        layout.addWidget(self._typing_label)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a message to Claude...")
        input_row.addWidget(self._input, 1)

        self._send_btn = QPushButton("Send")
        self._send_btn.setMaximumWidth(60)
        input_row.addWidget(self._send_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setMaximumWidth(50)
        self._stop_btn.setStyleSheet("background-color: #8B0000;")
        self._stop_btn.setVisible(False)
        input_row.addWidget(self._stop_btn)

        layout.addLayout(input_row)

        # Backend indicator
        self._backend_label = QLabel("")
        self._backend_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self._backend_label)

    def set_backend_label(self, text: str) -> None:
        """Show which Claude backend is active."""
        self._backend_label.setText(text)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._input.returnPressed.connect(self._on_send)
        self._send_btn.clicked.connect(self._on_send)
        self._stop_btn.clicked.connect(self._on_stop)

        # EventBus streaming signals (for external components)
        self._bus.claude_token.connect(self._on_external_token)
        self._bus.claude_message.connect(self._on_external_message)

    # ------------------------------------------------------------------
    # Message rendering
    # ------------------------------------------------------------------

    def _append_message(self, sender: str, text: str, css_class: str) -> None:
        """Append a styled message bubble to the display."""
        html_text = _md_to_html(text)
        bubble = (
            f'<div class="msg {css_class}">'
            f'<div class="sender">{html.escape(sender)}</div>'
            f"{html_text}</div>"
        )

        cursor = self._display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._display.setTextCursor(cursor)
        self._display.insertHtml(bubble)
        self._display.insertPlainText("\n")

        scrollbar = self._display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _append_user_message(self, text: str) -> None:
        self._append_message("You", text, "user-msg")

    def _append_claude_message(self, text: str) -> None:
        self._append_message("Claude", text, "claude-msg")

    def _append_system_message(self, text: str) -> None:
        html_text = html.escape(text)
        bubble = f'<div class="msg system-msg">{html_text}</div>'

        cursor = self._display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._display.setTextCursor(cursor)
        self._display.insertHtml(bubble)
        self._display.insertPlainText("\n")

        scrollbar = self._display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _append_tool_message(self, tool_name: str, detail: str) -> None:
        """Show a tool call indicator."""
        display_name = tool_name.replace("_", " ").title()
        html_text = html.escape(f"[Tool: {display_name}] {detail[:150]}")
        bubble = f'<div class="msg tool-msg">{html_text}</div>'

        cursor = self._display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._display.setTextCursor(cursor)
        self._display.insertHtml(bubble)
        self._display.insertPlainText("\n")

        scrollbar = self._display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ------------------------------------------------------------------
    # Streaming lifecycle
    # ------------------------------------------------------------------

    def _start_streaming(self) -> None:
        """Enter streaming mode."""
        self._streaming = True
        self._stream_buffer = ""
        self._typing_label.setText("Claude is thinking...")
        self._typing_label.setVisible(True)
        self._input.setEnabled(False)
        self._send_btn.setVisible(False)
        self._stop_btn.setVisible(True)

    def _end_streaming(self) -> None:
        """Exit streaming mode."""
        self._streaming = False
        self._typing_label.setVisible(False)
        self._input.setEnabled(True)
        self._send_btn.setVisible(True)
        self._stop_btn.setVisible(False)
        self._input.setFocus()

    # ------------------------------------------------------------------
    # Worker signal handlers
    # ------------------------------------------------------------------

    def _on_worker_token(self, token: str) -> None:
        """Handle a streaming token from AgentWorker."""
        self._stream_buffer += token
        self._typing_label.setText(
            f"Claude is responding... ({len(self._stream_buffer)} chars)"
        )

    def _on_worker_tool_called(self, tool_name: str, tool_input: str) -> None:
        """Handle a tool call from AgentWorker."""
        self._append_tool_message(tool_name, tool_input)
        self._typing_label.setText(f"Running tool: {tool_name}...")

    def _on_worker_tool_result(self, tool_name: str, result: str) -> None:
        """Handle a tool result from AgentWorker."""
        self._append_tool_message(tool_name, f"Result: {result[:100]}")

    def _on_worker_finished(self, full_text: str) -> None:
        """Handle completion from AgentWorker."""
        text = self._stream_buffer if self._stream_buffer else full_text
        self._stream_buffer = ""

        if text.strip():
            self._append_claude_message(text)
            # Track in conversation history
            self._conversation_history.append(
                {"role": "assistant", "content": text}
            )

        self._end_streaming()

    def _on_worker_error(self, error_msg: str) -> None:
        """Handle an error from AgentWorker."""
        if error_msg == "Cancelled":
            self._append_system_message("Response cancelled.")
            if self._stream_buffer.strip():
                self._append_claude_message(self._stream_buffer + "\n\n[cancelled]")
        else:
            self._append_system_message(f"Error: {error_msg}")
            self._bus.error_occurred.emit(error_msg)

        self._stream_buffer = ""
        self._end_streaming()

    # ------------------------------------------------------------------
    # External token handlers (from EventBus, for non-worker sources)
    # ------------------------------------------------------------------

    def _on_external_token(self, token: str) -> None:
        if not self._streaming:
            self._start_streaming()
        self._stream_buffer += token

    def _on_external_message(self, message: str) -> None:
        text = self._stream_buffer if self._stream_buffer else message
        self._stream_buffer = ""
        if text.strip():
            self._append_claude_message(text)
        self._end_streaming()

    # ------------------------------------------------------------------
    # User input
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        """Handle user sending a message."""
        text = self._input.text().strip()
        if not text:
            return

        self._input.clear()
        self._append_user_message(text)

        # Track in conversation history
        self._conversation_history.append({"role": "user", "content": text})
        self._conversation_history = self._conversation_history[-MAX_HISTORY:]

        # Send via AgentWorker if available
        if self._worker is not None:
            self._start_streaming()
            self._worker.send(
                text,
                system_prompt=self._system_prompt,
                conversation_history=self._conversation_history[:-1],
            )
        else:
            # No worker -- show offline message
            self._append_system_message(
                "Claude is not connected. Configure the API key or "
                "Claude CLI to enable AI assistance."
            )

    def focus_input(self) -> None:
        """Set focus to the chat input field."""
        self._input.setFocus()

    def _on_stop(self) -> None:
        """Handle stop button click."""
        if self._worker is not None:
            self._worker.cancel()
