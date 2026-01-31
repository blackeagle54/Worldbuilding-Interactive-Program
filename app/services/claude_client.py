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
            yield from self._send_subprocess(user_message, system_prompt, conversation_history)
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
                    model="claude-opus-4-0-20250514",
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

    @staticmethod
    def _serialize_history(history: list[dict], max_messages: int = 20) -> str:
        """Serialize recent conversation history into a text block.

        The claude CLI does not natively accept multi-turn message arrays,
        so we flatten the last *max_messages* turns into a readable
        transcript that is prepended to the user message.
        """
        if not history:
            return ""

        recent = history[-max_messages:]
        lines: list[str] = []
        for msg in recent:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            # Content may be a list of content blocks (tool results, etc.)
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        parts.append(block.get("text", block.get("content", str(block))))
                    else:
                        parts.append(str(block))
                content = "\n".join(parts)
            lines.append(f"[{role}]: {content}")

        return "\n".join(lines)

    def _build_subprocess_prompt(
        self,
        user_message: str,
        system_prompt: str,
        history: list[dict] | None,
    ) -> tuple[str, str]:
        """Build the enriched system prompt and user message for subprocess.

        For the subprocess backend we pre-load ALL available context into
        the system prompt so that Claude can answer without needing tool
        calls.  We also serialize conversation history into the user
        message so Claude has multi-turn awareness.

        Returns (enriched_system_prompt, enriched_user_message).
        """
        # --- Enrich the system prompt with tool-equivalent context ---
        extra_sections: list[str] = []
        loaded_sections: list[str] = []  # Track what loaded for diagnostics

        # Pre-fetch step guidance (equivalent to get_step_guidance tool)
        try:
            if self._engine:
                guidance = self._engine.with_lock(
                    "chunk_puller", lambda c: c.pull_guidance(self._current_step)
                )
                if isinstance(guidance, dict):
                    # Step title
                    step_info = guidance.get("step", {})
                    title = step_info.get("title", f"Step {self._current_step}")

                    # Layer 1: condensed book guidance
                    layer1_text = guidance.get("layer1_book", "")
                    if isinstance(layer1_text, dict):
                        # layer1_book is a dict with quotes and teaching_summary
                        teaching = layer1_text.get("teaching_summary", "")
                        quotes = layer1_text.get("quotes", [])
                        layer1_parts = []
                        if teaching:
                            layer1_parts.append(teaching)
                        for q in quotes[:3]:
                            qt = q.get("text", "")
                            if len(qt) > 300:
                                qt = qt[:300] + "..."
                            layer1_parts.append(f'  - "{qt}"')
                        layer1_text = "\n".join(layer1_parts)

                    extra_sections.append(
                        f"DETAILED STEP GUIDANCE (Step {self._current_step}: {title}):\n{layer1_text}"
                    )

                    # Layer 2: reference content from databases
                    layer2 = guidance.get("layer2_references", {})
                    if isinstance(layer2, dict):
                        ref_parts = []
                        for ref in layer2.get("featured_mythologies", []):
                            content = ref.get("content", "")
                            if content:
                                db_name = ref.get("database_name", ref.get("database", ""))
                                section = ref.get("section", "")
                                if len(content) > 1000:
                                    content = content[:1000] + "..."
                                ref_parts.append(f"  [{db_name} -- {section}]\n  {content}")
                        for ref in layer2.get("featured_authors", []):
                            content = ref.get("content", "")
                            if content:
                                db_name = ref.get("database_name", ref.get("database", ""))
                                section = ref.get("section", "")
                                if len(content) > 1000:
                                    content = content[:1000] + "..."
                                ref_parts.append(f"  [{db_name} -- {section}]\n  {content}")
                        if ref_parts:
                            extra_sections.append(
                                "REFERENCE DATABASE CONTENT:\n" + "\n\n".join(ref_parts)
                            )

                    # Layer 3: actionable guidance
                    layer3 = guidance.get("layer3_actionable", {})
                    if isinstance(layer3, dict):
                        layer3_parts = []
                        questions = layer3.get("guided_questions", [])
                        if questions:
                            q_text = "\n".join(f"  - {q}" for q in questions[:8])
                            layer3_parts.append(f"GUIDED QUESTIONS:\n{q_text}")
                        req_fields = layer3.get("required_fields", [])
                        if req_fields:
                            layer3_parts.append(
                                f"REQUIRED FIELDS: {', '.join(req_fields[:10])}"
                            )
                        tmpl_id = layer3.get("template_id")
                        if tmpl_id:
                            tmpl_display = tmpl_id if isinstance(tmpl_id, str) else ", ".join(tmpl_id)
                            layer3_parts.append(f"TEMPLATE: {tmpl_display}")
                        if layer3_parts:
                            extra_sections.append("\n".join(layer3_parts))
        except Exception:
            logger.debug("subprocess: could not pre-fetch step guidance", exc_info=True)
        else:
            if isinstance(guidance, dict):
                loaded_sections.append(f"step_guidance(step={self._current_step})")
                _l2 = guidance.get("layer2_references", {})
                if isinstance(_l2, dict) and (_l2.get("featured_mythologies") or _l2.get("featured_authors")):
                    loaded_sections.append("references(loaded)")

        # Pre-fetch canon context (equivalent to get_canon_context tool)
        try:
            if self._engine:
                entities = self._engine.with_lock(
                    "data_manager", lambda d: d.list_entities()
                )
                if entities:
                    lines = []
                    for ent in entities[:60]:
                        name = ent.get("name", ent.get("id", "?"))
                        etype = ent.get("entity_type", "unknown")
                        status = ent.get("status", "draft")
                        lines.append(f"  - {name} ({etype}, {status})")
                    extra_sections.append(
                        f"ALL CANON ENTITIES ({len(entities)} total):\n"
                        + "\n".join(lines)
                    )
                    if len(entities) > 60:
                        extra_sections[-1] += f"\n  ... and {len(entities) - 60} more"
        except Exception:
            logger.debug("subprocess: could not pre-fetch entities", exc_info=True)
        else:
            if entities:
                loaded_sections.append(f"entities({len(entities)})")

        # Pre-fetch graph stats (equivalent to query_knowledge_graph stats)
        try:
            if self._engine:
                stats = self._engine.with_lock("world_graph", lambda g: g.get_stats())
                if stats:
                    extra_sections.append(
                        f"KNOWLEDGE GRAPH STATS: "
                        f"{stats.get('node_count', 0)} nodes, "
                        f"{stats.get('edge_count', 0)} edges, "
                        f"{stats.get('orphan_count', 0)} orphans"
                    )
        except Exception:
            logger.debug("subprocess: could not pre-fetch graph stats", exc_info=True)
        else:
            if stats:
                loaded_sections.append("graph_stats")

        # Pre-fetch recent decisions (equivalent to bookkeeper context)
        try:
            if self._engine:
                session_data = self._engine.with_lock(
                    "bookkeeper", lambda b: b.get_current_session()
                )
                if session_data and isinstance(session_data, dict):
                    events = session_data.get("events", [])
                    recent = events[-8:] if events else []
                    if recent:
                        lines = []
                        for evt in recent:
                            desc = evt.get("description", evt.get("type", "event"))
                            lines.append(f"  - {desc}")
                        extra_sections.append(
                            "RECENT SESSION DECISIONS:\n" + "\n".join(lines)
                        )
        except Exception:
            logger.debug("subprocess: could not pre-fetch decisions", exc_info=True)
        else:
            if recent:
                loaded_sections.append(f"decisions({len(recent)})")

        # Pre-fetch featured sources
        try:
            if self._engine:
                featured = self._engine.with_lock(
                    "fair_representation", lambda f: f.select_featured(self._current_step)
                )
                if featured:
                    myths = featured.get("featured_mythologies", [])
                    authors = featured.get("featured_authors", [])
                    if myths or authors:
                        parts = []
                        if myths:
                            parts.append(f"  Mythologies: {', '.join(myths)}")
                        if authors:
                            parts.append(f"  Authors: {', '.join(authors)}")
                        extra_sections.append(
                            "FEATURED REFERENCE SOURCES:\n" + "\n".join(parts)
                        )
        except Exception:
            logger.debug("subprocess: could not pre-fetch featured sources", exc_info=True)
        else:
            if myths or authors:
                loaded_sections.append(f"featured({len(myths)}myth+{len(authors)}auth)")

        # Compose enriched system prompt
        enriched_system = system_prompt
        if extra_sections:
            enriched_system += (
                "\n\n--- PRE-LOADED CONTEXT (use this data instead of requesting tools) ---\n"
                + "\n\n".join(extra_sections)
            )

        logger.info(
            "Subprocess prompt built: %d extra sections [%s], "
            "system_prompt=%d chars, enriched=%d chars, user_msg=%d chars",
            len(extra_sections),
            ", ".join(loaded_sections) if loaded_sections else "NONE",
            len(system_prompt), len(enriched_system), len(user_message),
        )

        # --- Serialize conversation history into the user message ---
        history_text = self._serialize_history(history or [])
        if history_text:
            enriched_user = (
                f"CONVERSATION SO FAR:\n{history_text}\n\n"
                f"---\n\n"
                f"USER'S CURRENT MESSAGE:\n{user_message}"
            )
        else:
            enriched_user = user_message

        return enriched_system, enriched_user

    def _send_subprocess(
        self,
        user_message: str,
        system_prompt: str,
        history: list[dict] | None = None,
    ) -> Generator[StreamEvent, None, None]:
        """Send via claude CLI subprocess with streaming JSON output.

        The subprocess backend enriches the system prompt with pre-loaded
        context (entities, graph stats, step guidance, recent decisions)
        so Claude can respond knowledgeably without tool calls.  It also
        serializes conversation history into the user message for
        multi-turn awareness.
        """
        try:
            # Build enriched prompt and message for subprocess
            enriched_system, enriched_user = self._build_subprocess_prompt(
                user_message, system_prompt, history
            )

            cmd = [
                "claude",
                "-p", enriched_user,
                "--output-format", "stream-json",
                "--verbose",
                "--model", "claude-opus-4-0-20250514",
            ]
            logger.debug("Subprocess cmd: %s", cmd)

            if enriched_system:
                cmd.extend(["--system-prompt", enriched_system])

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
                        logger.debug("Non-JSON line from CLI: %s", line[:100])
                        continue

                    event_type = event.get("type", "")
                    logger.debug("CLI event: type=%s", event_type)

                    # Claude CLI stream-json format uses these event types:
                    #   "system"    -- init info (session_id, model, tools)
                    #   "assistant" -- full message with content blocks
                    #   "result"    -- final summary with result text
                    #   "content_block_delta" -- only in raw API streaming

                    if event_type == "assistant":
                        # Full message -- extract text from content blocks
                        message = event.get("message", {})
                        for block in message.get("content", []):
                            if block.get("type") == "text":
                                text = block.get("text", "")
                                if text:
                                    accumulated_text += text
                                    yield StreamEvent(type=EventType.TOKEN, data=text)
                            elif block.get("type") == "tool_use":
                                yield StreamEvent(
                                    type=EventType.TOOL_CALL,
                                    data=block.get("name", "unknown"),
                                    tool_name=block.get("name", ""),
                                    tool_input=block.get("input", {}),
                                )

                    elif event_type == "result":
                        # Final result -- emit completion
                        result_text = event.get("result", accumulated_text)
                        if not message_complete_emitted:
                            message_complete_emitted = True
                            yield StreamEvent(
                                type=EventType.MESSAGE_COMPLETE,
                                data=result_text or accumulated_text,
                            )

                    elif event_type == "content_block_delta":
                        # Raw API streaming format (if CLI ever uses it)
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
