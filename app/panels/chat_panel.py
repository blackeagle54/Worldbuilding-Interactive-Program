"""
app/panels/chat_panel.py -- Chat & Streaming panel.

Displays the conversation with Claude, including styled message bubbles,
basic markdown rendering, streaming token display, tool call indicators,
and a stop button for cancellation.

Modern chat-focused UI with centered messages, multi-line input,
and Enter-to-send / Shift+Enter-for-newline behavior.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QTextCursor, QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.event_bus import EventBus

logger = logging.getLogger(__name__)

MAX_HISTORY = 50
MAX_DISPLAY_MESSAGES = 200  # Trim HTML display to prevent memory bloat

# CSS for message bubbles inside the QTextEdit
_CHAT_CSS = """
body {
    font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
    font-size: 14px;
    color: #d0d0e0;
    margin: 0;
    padding: 8px;
    line-height: 1.5;
}
.msg-container {
    max-width: 800px;
    margin: 0 auto;
    padding: 0 8px;
}
.msg {
    margin: 6px 0;
    padding: 12px 16px;
    border-radius: 12px;
    line-height: 1.5;
}
.user-msg {
    background-color: #2a4a5e;
    margin-left: 15%;
    text-align: left;
}
.claude-msg {
    background-color: #262630;
    margin-right: 15%;
}
.system-msg {
    background-color: transparent;
    color: #6a6a8a;
    font-style: italic;
    text-align: center;
    font-size: 12px;
    padding: 8px 16px;
}
.tool-msg {
    background-color: #1a2a1a;
    color: #7c7;
    font-size: 12px;
    margin-right: 15%;
    border-left: 3px solid #4a4;
    padding: 8px 12px;
}
.sender {
    font-weight: bold;
    font-size: 11px;
    color: #7a7a9a;
    margin-bottom: 4px;
}
code {
    background-color: #1a1a2e;
    padding: 2px 5px;
    border-radius: 4px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
}
pre {
    background-color: #1a1a2e;
    padding: 10px 12px;
    border-radius: 8px;
    overflow-x: auto;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
}
strong { color: #e0e0f0; }
em { color: #b0b0c8; }
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


class ChatInputEdit(QPlainTextEdit):
    """Multi-line text input that sends on Enter and inserts newline on Shift+Enter.

    Grows from 2 to 6 visible lines based on content.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._min_lines = 2
        self._max_lines = 6
        self._send_callback = None
        self.setPlaceholderText("Message Claude...")
        self.setTabChangesFocus(True)

        # Calculate line height for dynamic sizing
        fm = self.fontMetrics()
        self._line_height = fm.lineSpacing()

        self._update_height()
        self.document().contentsChanged.connect(self._update_height)

    def set_send_callback(self, callback) -> None:
        """Set the callback for when Enter is pressed to send."""
        self._send_callback = callback

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Enter to send, Shift+Enter for newline."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter inserts a newline
                super().keyPressEvent(event)
            else:
                # Enter sends the message
                if self._send_callback:
                    self._send_callback()
                event.accept()
            return
        super().keyPressEvent(event)

    def _update_height(self) -> None:
        """Dynamically adjust height based on content lines."""
        doc = self.document()
        line_count = max(self._min_lines, min(doc.blockCount(), self._max_lines))
        # Account for document margins and widget margins
        doc_margin = doc.documentMargin()
        content_height = int(line_count * self._line_height + 2 * doc_margin + 4)
        self.setFixedHeight(content_height)


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
        self._display_msg_count = 0
        self._pre_send_hook = None  # Callable to invoke before each send
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

    def set_pre_send_hook(self, hook) -> None:
        """Set a callback to invoke before each message send.

        This allows the MainWindow to refresh the system prompt (with
        latest entity counts, graph stats, etc.) right before every
        message is dispatched to the worker.

        Parameters
        ----------
        hook : callable
            A zero-argument callable.  It is invoked synchronously on
            the main thread before the AgentWorker.send() call.
        """
        self._pre_send_hook = hook

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Message display area -- takes up all available space
        self._display = QTextEdit()
        self._display.setReadOnly(True)
        self._display.setObjectName("chatDisplay")
        self._display.setStyleSheet("""
            QTextEdit#chatDisplay {
                background-color: #0f0f1a;
                border: none;
                border-radius: 0;
            }
        """)
        self._display.document().setDefaultStyleSheet(_CHAT_CSS)
        self._display.setHtml("<body></body>")
        layout.addWidget(self._display, 1)

        # Typing indicator
        self._typing_label = QLabel("")
        self._typing_label.setStyleSheet(
            "color: #6a6a8a; font-style: italic; font-size: 11px; "
            "padding: 4px 16px; background: transparent;"
        )
        self._typing_label.setVisible(False)
        layout.addWidget(self._typing_label)

        # Input area container
        input_container = QWidget()
        input_container.setObjectName("chatInputContainer")
        input_container.setStyleSheet("""
            QWidget#chatInputContainer {
                background-color: #16213e;
                border-top: 1px solid #2a2a4a;
            }
        """)
        input_outer = QVBoxLayout(input_container)
        input_outer.setContentsMargins(12, 8, 12, 8)
        input_outer.setSpacing(4)

        # Input row with text area and send button
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._input = ChatInputEdit()
        self._input.set_send_callback(self._on_send)
        self._input.setObjectName("chatInput")
        self._input.setStyleSheet("""
            QPlainTextEdit#chatInput {
                background-color: #0f0f1a;
                color: #d0d0e0;
                border: 1px solid #2a2a4a;
                border-radius: 12px;
                padding: 8px 12px;
                font-size: 14px;
                font-family: 'Segoe UI', sans-serif;
            }
            QPlainTextEdit#chatInput:focus {
                border-color: #3a5a7e;
            }
        """)
        input_row.addWidget(self._input, 1)

        # Button column (send + stop stacked)
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)

        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("chatSendBtn")
        self._send_btn.setFixedSize(60, 34)
        self._send_btn.setStyleSheet("""
            QPushButton#chatSendBtn {
                background-color: #2a4a5e;
                color: #d0d0e0;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#chatSendBtn:hover {
                background-color: #3a5a7e;
            }
        """)
        btn_col.addWidget(self._send_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("chatStopBtn")
        self._stop_btn.setFixedSize(60, 34)
        self._stop_btn.setStyleSheet("""
            QPushButton#chatStopBtn {
                background-color: #6B2020;
                color: #e0b0b0;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#chatStopBtn:hover {
                background-color: #8B3030;
            }
        """)
        self._stop_btn.setVisible(False)
        btn_col.addWidget(self._stop_btn)

        btn_col.addStretch()
        input_row.addLayout(btn_col)

        input_outer.addLayout(input_row)

        # Backend indicator -- small, subtle, in corner of input area
        self._backend_label = QLabel("")
        self._backend_label.setStyleSheet(
            "color: #4a4a6a; font-size: 10px; background: transparent; padding: 0 4px;"
        )
        input_outer.addWidget(self._backend_label, 0, Qt.AlignmentFlag.AlignRight)

        layout.addWidget(input_container)

    def set_backend_label(self, text: str) -> None:
        """Show which Claude backend is active."""
        self._backend_label.setText(text)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
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
        # Trim old messages if display has grown too large
        self._display_msg_count += 1
        if self._display_msg_count > MAX_DISPLAY_MESSAGES:
            self._trim_display()

        html_text = _md_to_html(text)
        bubble = (
            f'<div class="msg-container">'
            f'<div class="msg {css_class}">'
            f'<div class="sender">{html.escape(sender)}</div>'
            f"{html_text}</div></div>"
        )

        cursor = self._display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._display.setTextCursor(cursor)
        self._display.insertHtml(bubble)
        self._display.insertPlainText("\n")

        scrollbar = self._display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _trim_display(self) -> None:
        """Remove the oldest messages from the display to stay within budget."""
        doc = self._display.document()
        # Remove roughly the first quarter of content
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        # Move to 25% of document length
        total_chars = doc.characterCount()
        trim_chars = total_chars // 4
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.KeepAnchor,
            trim_chars,
        )
        cursor.removeSelectedText()
        self._display_msg_count = int(self._display_msg_count * 0.75)

    def _append_user_message(self, text: str) -> None:
        self._append_message("You", text, "user-msg")

    def _append_claude_message(self, text: str) -> None:
        self._append_message("Claude", text, "claude-msg")

    def _append_system_message(self, text: str) -> None:
        html_text = html.escape(text)
        bubble = (
            f'<div class="msg-container">'
            f'<div class="msg system-msg">{html_text}</div>'
            f'</div>'
        )

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
        bubble = (
            f'<div class="msg-container">'
            f'<div class="msg tool-msg">{html_text}</div>'
            f'</div>'
        )

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
        text = self._input.toPlainText().strip()
        if not text:
            return

        self._input.clear()
        self._append_user_message(text)

        # Track in conversation history
        self._conversation_history.append({"role": "user", "content": text})
        self._conversation_history = self._conversation_history[-MAX_HISTORY:]

        # Send via AgentWorker if available
        if self._worker is not None:
            # Refresh system prompt with latest world state before sending
            if self._pre_send_hook is not None:
                try:
                    self._pre_send_hook()
                except Exception:
                    logger.debug("pre_send_hook failed", exc_info=True)

            logger.info("Sending message to AgentWorker: %s", text[:50])
            self._start_streaming()
            self._worker.send(
                text,
                system_prompt=self._system_prompt,
                conversation_history=self._conversation_history[:-1],
            )
        else:
            logger.warning("No worker available -- cannot send message")
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
