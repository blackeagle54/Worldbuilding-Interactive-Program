"""
app/services/claude_client.py -- Claude integration facade.

Provides a unified interface for communicating with Claude, with three
backends tried in order:

    1. Anthropic SDK (direct API) -- fastest, most control
    2. Subprocess (claude CLI) -- fallback if SDK auth fails
    3. Offline mode -- graceful degradation with helpful messages

The facade exposes a simple send_message() method that returns an iterator
of events (tokens, tool calls, completion).  The AgentWorker QThread
consumes this iterator and emits Qt signals.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Generator

logger = logging.getLogger(__name__)


class BackendType(Enum):
    SDK = auto()
    SUBPROCESS = auto()
    OFFLINE = auto()


class EventType(Enum):
    TOKEN = auto()
    TOOL_CALL = auto()
    TOOL_RESULT = auto()
    MESSAGE_COMPLETE = auto()
    ERROR = auto()


@dataclass
class StreamEvent:
    """A single event from the Claude response stream."""
    type: EventType
    data: str = ""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    tool_use_id: str = ""


class ClaudeClient:
    """Facade for communicating with Claude.

    Parameters
    ----------
    engine_manager : EngineManager
        For executing tool calls.
    current_step : int
        Current worldbuilding step (1-52).
    """

    # Default timeout for API requests (seconds).  The SDK stream itself
    # does not have a single timeout parameter -- this is applied via the
    # httpx timeout on the Anthropic client.  For subprocess, it is the
    # maximum wall-clock time to wait for the process.
    DEFAULT_TIMEOUT = 120  # 2 minutes

    def __init__(
        self,
        engine_manager: Any = None,
        current_step: int = 1,
        timeout: int | None = None,
    ):
        self._engine = engine_manager
        self._current_step = current_step
        self._timeout = timeout or self.DEFAULT_TIMEOUT
        self._backend: BackendType = BackendType.OFFLINE
        self._cancel = threading.Event()
        self._detect_backend()

    @property
    def backend(self) -> BackendType:
        return self._backend

    @property
    def is_online(self) -> bool:
        return self._backend != BackendType.OFFLINE

    def set_current_step(self, step: int) -> None:
        self._current_step = step

    def cancel(self) -> None:
        """Signal cancellation of the current request."""
        self._cancel.set()

    # ------------------------------------------------------------------
    # Backend detection
    # ------------------------------------------------------------------

    def _detect_backend(self) -> None:
        """Detect which backend is available."""
        # Try SDK first
        if self._try_sdk():
            self._backend = BackendType.SDK
            logger.info("Claude backend: Anthropic SDK")
            return

        # Try subprocess
        if self._try_subprocess():
            self._backend = BackendType.SUBPROCESS
            logger.info("Claude backend: subprocess (claude CLI)")
            return

        self._backend = BackendType.OFFLINE
        logger.info("Claude backend: offline mode")

    def _try_sdk(self) -> bool:
        """Check if the Anthropic SDK is available and has valid auth."""
        try:
            import anthropic
            # Check for API key
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                return False
            # Quick validation -- just check the client can be created
            anthropic.Anthropic(api_key=key)
            return True
        except Exception:
            return False

    def _try_subprocess(self) -> bool:
        """Check if the claude CLI is available."""
        try:
            path = shutil.which("claude")
            return path is not None
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Message sending
    # ------------------------------------------------------------------

    def send_message(
        self,
        user_message: str,
        system_prompt: str = "",
        conversation_history: list[dict] | None = None,
    ) -> Generator[StreamEvent, None, None]:
        """Send a message and yield streaming events.

        Parameters
        ----------
        user_message : str
            The user's message text.
        system_prompt : str
            System prompt to use.
        conversation_history : list[dict] | None
            Previous messages in Anthropic format.

        Yields
        ------
        StreamEvent
            Token, tool call, or completion events.
        """
        self._cancel.clear()

        if self._backend == BackendType.SDK:
            yield from self._send_sdk(user_message, system_prompt, conversation_history)
        elif self._backend == BackendType.SUBPROCESS:
            yield from self._send_subprocess(user_message, system_prompt)
        else:
            yield from self._send_offline(user_message)

    # ------------------------------------------------------------------
    # SDK backend
    # ------------------------------------------------------------------

    def _send_sdk(
        self,
        user_message: str,
        system_prompt: str,
        history: list[dict] | None,
    ) -> Generator[StreamEvent, None, None]:
        """Send via Anthropic SDK with streaming."""
        try:
            import anthropic
            from app.services.tools import TOOL_DEFINITIONS, execute_tool

            client = anthropic.Anthropic(
                timeout=self._timeout,
            )

            messages = list(history or [])
            messages.append({"role": "user", "content": user_message})

            # Agentic loop -- handle tool calls
            MAX_TOOL_ROUNDS = 10
            tool_round = 0
            while True:
                tool_round += 1
                if tool_round > MAX_TOOL_ROUNDS:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        data=f"Exceeded maximum tool rounds ({MAX_TOOL_ROUNDS})",
                    )
                    break

                if self._cancel.is_set():
                    yield StreamEvent(type=EventType.ERROR, data="Cancelled")
                    return

                accumulated_text = ""

                with client.messages.stream(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4096,
                    system=system_prompt,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                ) as stream:
                    for event in stream:
                        if self._cancel.is_set():
                            yield StreamEvent(type=EventType.ERROR, data="Cancelled")
                            return

                        if hasattr(event, "type"):
                            if event.type == "content_block_delta":
                                if hasattr(event.delta, "text"):
                                    accumulated_text += event.delta.text
                                    yield StreamEvent(
                                        type=EventType.TOKEN,
                                        data=event.delta.text,
                                    )

                    # Get the final message
                    response = stream.get_final_message()

                # Check for tool use in response
                tool_uses = [
                    block for block in response.content
                    if block.type == "tool_use"
                ]

                if not tool_uses:
                    # No tool calls -- done
                    yield StreamEvent(
                        type=EventType.MESSAGE_COMPLETE,
                        data=accumulated_text,
                    )
                    return

                # Handle tool calls
                # Add assistant message to history
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for tool_use in tool_uses:
                    yield StreamEvent(
                        type=EventType.TOOL_CALL,
                        tool_name=tool_use.name,
                        tool_input=dict(tool_use.input),
                        tool_use_id=tool_use.id,
                    )

                    # Execute the tool
                    result = execute_tool(
                        tool_use.name,
                        dict(tool_use.input),
                        self._engine,
                        self._current_step,
                    )

                    yield StreamEvent(
                        type=EventType.TOOL_RESULT,
                        data=result[:500],  # Truncate for display
                        tool_name=tool_use.name,
                        tool_use_id=tool_use.id,
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result,
                    })

                # Add tool results to history and loop
                messages.append({"role": "user", "content": tool_results})

        except Exception as e:
            logger.exception("SDK send failed")
            yield StreamEvent(type=EventType.ERROR, data=str(e))

    # ------------------------------------------------------------------
    # Subprocess backend
    # ------------------------------------------------------------------

    def _send_subprocess(
        self,
        user_message: str,
        system_prompt: str,
    ) -> Generator[StreamEvent, None, None]:
        """Send via claude CLI subprocess with streaming JSON output."""
        try:
            cmd = [
                "claude",
                "-p", user_message,
                "--output-format", "stream-json",
            ]

            if system_prompt:
                cmd.extend(["--system-prompt", system_prompt])

            # CREATE_NO_WINDOW prevents a console flash on Windows
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation_flags,
            )

            try:
                accumulated_text = ""
                message_complete_emitted = False

                for line in proc.stdout:
                    if self._cancel.is_set():
                        proc.terminate()
                        yield StreamEvent(type=EventType.ERROR, data="Cancelled")
                        return

                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    if event_type == "content_block_delta":
                        text = event.get("delta", {}).get("text", "")
                        if text:
                            accumulated_text += text
                            yield StreamEvent(type=EventType.TOKEN, data=text)

                    elif event_type == "message_stop":
                        if not message_complete_emitted:
                            message_complete_emitted = True
                            yield StreamEvent(
                                type=EventType.MESSAGE_COMPLETE,
                                data=accumulated_text,
                            )

                    elif event_type == "error":
                        yield StreamEvent(
                            type=EventType.ERROR,
                            data=event.get("error", {}).get("message", "Unknown error"),
                        )

                proc.wait(timeout=self._timeout)

                if proc.returncode != 0 and not accumulated_text:
                    stderr = proc.stderr.read()
                    yield StreamEvent(
                        type=EventType.ERROR,
                        data=f"claude CLI exited with code {proc.returncode}: {stderr[:200]}",
                    )
                elif accumulated_text and not self._cancel.is_set() and not message_complete_emitted:
                    # Ensure completion event if we got text but no message_stop
                    message_complete_emitted = True
                    yield StreamEvent(
                        type=EventType.MESSAGE_COMPLETE,
                        data=accumulated_text,
                    )
            finally:
                try:
                    proc.kill()
                except OSError:
                    pass
                proc.wait(timeout=5)

        except FileNotFoundError:
            yield StreamEvent(
                type=EventType.ERROR,
                data="claude CLI not found. Install Claude Code to use this feature.",
            )
        except Exception as e:
            logger.exception("Subprocess send failed")
            yield StreamEvent(type=EventType.ERROR, data=str(e))

    # ------------------------------------------------------------------
    # Offline fallback
    # ------------------------------------------------------------------

    def _send_offline(
        self, user_message: str
    ) -> Generator[StreamEvent, None, None]:
        """Generate a helpful offline response."""
        response = (
            "I'm currently in **offline mode** because no Claude API key "
            "or Claude CLI was detected.\n\n"
            "To enable AI assistance, either:\n"
            "1. Set the `ANTHROPIC_API_KEY` environment variable\n"
            "2. Install and authenticate Claude Code (`claude` CLI)\n\n"
            "In the meantime, you can still:\n"
            "- Browse and create entities manually\n"
            "- Navigate the 52-step progression\n"
            "- View the knowledge graph\n"
            "- Use all other app features\n\n"
            f"Your message was: *{user_message[:100]}*"
        )

        # Simulate streaming for consistent UX
        for char in response:
            if self._cancel.is_set():
                return
            yield StreamEvent(type=EventType.TOKEN, data=char)

        yield StreamEvent(type=EventType.MESSAGE_COMPLETE, data=response)
