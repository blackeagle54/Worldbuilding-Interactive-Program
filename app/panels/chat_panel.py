"""
app/panels/chat_panel.py -- Chat & Streaming panel.

Displays the conversation with Claude, including styled message bubbles,
basic markdown rendering, streaming token display, and a typing indicator.

Sprint 3: Mock streaming (simulated). Sprint 4: Real Claude integration.
"""

from __future__ import annotations

import html
import logging
import re

from PySide6.QtCore import Qt, QTimer
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
    """Minimal markdown-to-HTML conversion for chat messages.

    Handles: **bold**, *italic*, `inline code`, ```code blocks```,
    and newline preservation.
    """
    # Escape HTML
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
        self._streaming = False
        self._stream_buffer = ""
        self._setup_ui()
        self._connect_signals()

        # Add welcome message
        self._append_system_message(
            "Welcome to Worldbuilding Interactive Program. "
            "Claude will assist you through the 52-step process."
        )

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

        layout.addLayout(input_row)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._input.returnPressed.connect(self._on_send)
        self._send_btn.clicked.connect(self._on_send)

        # EventBus streaming signals
        self._bus.claude_token.connect(self._on_claude_token)
        self._bus.claude_message.connect(self._on_claude_message)

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

        # Scroll to bottom
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

    # ------------------------------------------------------------------
    # Streaming support
    # ------------------------------------------------------------------

    def _start_streaming(self) -> None:
        """Begin a streaming response from Claude."""
        self._streaming = True
        self._stream_buffer = ""
        self._typing_label.setText("Claude is typing...")
        self._typing_label.setVisible(True)
        self._input.setEnabled(False)
        self._send_btn.setEnabled(False)

    def _on_claude_token(self, token: str) -> None:
        """Handle a single streaming token."""
        if not self._streaming:
            self._start_streaming()
        self._stream_buffer += token

    def _on_claude_message(self, message: str) -> None:
        """Handle a complete Claude message (end of streaming or direct)."""
        self._streaming = False
        self._typing_label.setVisible(False)
        self._input.setEnabled(True)
        self._send_btn.setEnabled(True)

        # Use stream buffer if we were streaming, otherwise use the message
        text = self._stream_buffer if self._stream_buffer else message
        self._stream_buffer = ""

        if text.strip():
            self._append_claude_message(text)

        self._input.setFocus()

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

        # Sprint 3: Mock response (Sprint 4 will use real Claude)
        self._mock_response(text)

    def _mock_response(self, user_text: str) -> None:
        """Generate a simulated Claude response for testing the UI.

        This will be replaced by real Claude integration in Sprint 4.
        """
        self._start_streaming()

        response = (
            f"I received your message about **{user_text[:50]}**. "
            "In Sprint 4, I'll be connected to the real Claude API "
            "and can help you with worldbuilding decisions.\n\n"
            "For now, the chat UI is set up with:\n"
            "- Message bubbles with `markdown` support\n"
            "- Streaming token display\n"
            "- **Bold** and *italic* formatting\n"
            "- ```code blocks```"
        )

        # Simulate streaming by emitting tokens with delays
        tokens = list(response)
        self._mock_tokens = tokens
        self._mock_index = 0
        self._mock_timer = QTimer(self)
        self._mock_timer.setInterval(15)  # 15ms per token
        self._mock_timer.timeout.connect(self._emit_mock_token)
        self._mock_timer.start()

    def _emit_mock_token(self) -> None:
        """Emit the next mock token."""
        if self._mock_index < len(self._mock_tokens):
            token = self._mock_tokens[self._mock_index]
            self._bus.claude_token.emit(token)
            self._mock_index += 1
        else:
            self._mock_timer.stop()
            self._bus.claude_message.emit(self._stream_buffer)
