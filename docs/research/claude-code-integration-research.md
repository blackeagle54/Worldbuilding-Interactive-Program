# Claude Code Integration Research for NiceGUI Web Application

**Date:** 2026-01-30
**Objective:** Determine the best approach to use Claude Code as a backend for a NiceGUI web application with real-time streaming, hook support, session management, and dashboard integration.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Approach 1: Claude Code CLI Subprocess](#approach-1-claude-code-cli-subprocess)
3. [Approach 2: Claude Agent SDK (Python)](#approach-2-claude-agent-sdk-python)
4. [Approach 3: Anthropic API Direct](#approach-3-anthropic-api-direct)
5. [Approach 4: Claude Code MCP Server](#approach-4-claude-code-mcp-server)
6. [NiceGUI Streaming Capabilities](#nicegui-streaming-capabilities)
7. [Comparison Matrix](#comparison-matrix)
8. [Recommended Architecture](#recommended-architecture)
9. [Implementation Guide](#implementation-guide)
10. [Sources](#sources)

---

## Executive Summary

**Recommended Approach: Approach 2 -- Claude Agent SDK (Python)**

The Claude Agent SDK (`claude-agent-sdk` on PyPI) is the clear winner. It provides a native Python async API with full streaming support, multi-turn conversation management via `ClaudeSDKClient`, hook support (PreToolUse, PostToolUse, UserPromptSubmit, Stop), custom tools via in-process MCP servers, and permission control. It wraps the Claude Code CLI subprocess transparently, so you get all Claude Code capabilities without managing the process yourself.

---

## Approach 1: Claude Code CLI Subprocess

### How It Works

Run the `claude` CLI as a subprocess from Python, communicating via stdin/stdout with JSON-lines protocol.

### Key CLI Flags

| Flag | Purpose |
|------|---------|
| `-p` / `--print` | Non-interactive (headless) mode |
| `--output-format text` | Plain text output (default) |
| `--output-format json` | Structured JSON with result, session ID, metadata |
| `--output-format stream-json` | Newline-delimited JSON for real-time streaming |
| `--input-format stream-json` | Accept streaming JSON input on stdin |
| `--include-partial-messages` | Emit token-level streaming events |
| `--verbose` | Detailed output for debugging |
| `--continue` | Continue most recent conversation |
| `--resume <session_id>` | Resume a specific conversation by ID |
| `--allowedTools` | Auto-approve specific tools |
| `--append-system-prompt` | Add custom instructions |
| `--json-schema` | Enforce structured output schema |

### Streaming Example (Bash)

```bash
# Stream tokens as they are generated
claude -p "Explain recursion" \
  --output-format stream-json \
  --verbose \
  --include-partial-messages

# Filter for just text deltas
claude -p "Write a poem" \
  --output-format stream-json \
  --verbose \
  --include-partial-messages | \
  jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'
```

### Session Continuity

```bash
# First request -- capture session ID
session_id=$(claude -p "Start a review" --output-format json | jq -r '.session_id')

# Resume that specific session
claude -p "Continue that review" --resume "$session_id"

# Or just continue the most recent conversation
claude -p "Show me our progress" --continue
```

### Multi-Turn Interactive Mode (stdin streaming)

For persistent sessions, the CLI supports:
```
--input-format stream-json --output-format stream-json --include-partial-messages --verbose
```
This keeps stdin open for multiple messages, with JSON-lines communication in both directions.

### Python Subprocess Implementation

```python
import asyncio
import json

async def claude_stream(prompt: str, session_id: str = None):
    """Stream Claude Code CLI output via subprocess."""
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json",
           "--verbose", "--include-partial-messages"]
    if session_id:
        cmd.extend(["--resume", session_id])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    async for line in proc.stdout:
        line = line.decode().strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            # Check for text deltas
            if (event.get("type") == "stream_event" and
                event.get("event", {}).get("delta", {}).get("type") == "text_delta"):
                yield event["event"]["delta"]["text"]
            # Check for result message (contains session_id)
            if event.get("type") == "result":
                yield {"session_id": event.get("session_id"),
                       "result": event.get("result")}
        except json.JSONDecodeError:
            continue

    await proc.wait()
```

### Feasibility Assessment

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Technically feasible | YES | Well-documented, production-ready |
| Real-time streaming | YES | `--output-format stream-json --include-partial-messages` |
| Conversation history | YES | `--continue` / `--resume <id>` |
| Hooks still work | YES | Hooks are part of the CLI itself |
| Dependencies | Node.js + Claude Code CLI installed | `npm install -g @anthropic-ai/claude-code` |
| Integration complexity | MEDIUM | Must manage subprocess lifecycle, parse JSON-lines |
| Windows support | YES | Claude Code CLI runs on Windows |

---

## Approach 2: Claude Agent SDK (Python)

### Overview

The **Claude Agent SDK** (formerly Claude Code SDK) is the official Python package for programmatic access to Claude Code. It wraps the CLI subprocess internally and provides a clean async Python API.

- **Package:** `pip install claude-agent-sdk`
- **Requires:** Python 3.10+, Node.js 18+, Claude Code CLI
- **GitHub:** [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)

### Two Main Interfaces

#### 1. `query()` -- One-Shot Queries

Creates a new session for each call. Best for independent tasks.

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

async for message in query(
    prompt="What does auth.py do?",
    options=ClaudeAgentOptions(
        system_prompt="You are a helpful assistant",
        allowed_tools=["Read", "Grep"],
        cwd="/path/to/project"
    )
):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text)
```

#### 2. `ClaudeSDKClient` -- Multi-Turn Conversations (RECOMMENDED)

Maintains a persistent session with conversation memory, hooks, custom tools, and interrupts.

```python
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions,
    AssistantMessage, TextBlock, StreamEvent
)
import asyncio

async def chat_session():
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Bash", "Edit"],
        permission_mode="acceptEdits",
        cwd="/path/to/project",
        include_partial_messages=True,  # Enable token-level streaming
        setting_sources=["project"],    # Load CLAUDE.md
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": "You are assisting with a worldbuilding project."
        }
    )

    async with ClaudeSDKClient(options) as client:
        # First message
        await client.query("Describe the current state of the world")

        async for message in client.receive_response():
            if isinstance(message, StreamEvent):
                # Real-time token streaming
                delta = message.event.get("delta", {})
                if delta.get("type") == "text_delta":
                    print(delta["text"], end="", flush=True)
            elif isinstance(message, AssistantMessage):
                # Complete message
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"\n[Complete]: {block.text}")

        # Follow-up -- Claude remembers context
        await client.query("What factions exist?")
        async for message in client.receive_response():
            # Process response...
            pass

asyncio.run(chat_session())
```

### Feature Comparison: `query()` vs `ClaudeSDKClient`

| Feature | `query()` | `ClaudeSDKClient` |
|---------|-----------|-------------------|
| Session | New each time | Persistent |
| Conversation memory | No | Yes |
| Streaming input | Yes | Yes |
| Interrupts | No | Yes |
| Hooks | No | Yes |
| Custom tools (MCP) | No | Yes |
| Multi-turn | No | Yes |
| Use case | One-off tasks | Chat interfaces |

### Hooks Support (Python SDK)

The SDK supports hooks as Python async functions (not shell commands like the CLI config):

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, HookContext
from typing import Any

async def inject_worldbuilding_context(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext
) -> dict[str, Any]:
    """Inject project context before every user prompt."""
    # Read current world state and inject as context
    return {
        'hookSpecificOutput': {
            'hookEventName': 'UserPromptSubmit',
            'additionalContext': 'Current era: Age of Fracture. Active factions: 5.'
        }
    }

async def log_tool_usage(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext
) -> dict[str, Any]:
    """Log all tool usage for the dashboard."""
    tool_name = input_data.get('tool_name', 'unknown')
    print(f"[HOOK] Tool used: {tool_name}")
    return {}

async def block_dangerous_ops(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext
) -> dict[str, Any]:
    """Block destructive file operations."""
    tool_input = input_data.get('tool_input', {})
    if 'rm -rf' in str(tool_input):
        return {
            'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': 'deny',
                'permissionDecisionReason': 'Destructive operation blocked'
            }
        }
    return {}

options = ClaudeAgentOptions(
    hooks={
        'UserPromptSubmit': [
            HookMatcher(hooks=[inject_worldbuilding_context])
        ],
        'PreToolUse': [
            HookMatcher(matcher='Bash', hooks=[block_dangerous_ops]),
            HookMatcher(hooks=[log_tool_usage])
        ],
        'PostToolUse': [
            HookMatcher(hooks=[log_tool_usage])
        ]
    }
)
```

**Supported hook events in Python SDK:** PreToolUse, PostToolUse, UserPromptSubmit, Stop, SubagentStop, PreCompact. (Note: SessionStart, SessionEnd, and Notification are NOT supported in the Python SDK.)

### Custom Tools via In-Process MCP Server

Define Python functions as tools that Claude can call:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeAgentOptions

@tool("get_world_state", "Get current worldbuilding state", {"aspect": str})
async def get_world_state(args):
    aspect = args["aspect"]
    # Read from your project state files
    import json
    with open("C:/Worldbuilding-Interactive-Program/data/world_state.json") as f:
        state = json.load(f)
    return {
        "content": [{"type": "text", "text": json.dumps(state.get(aspect, {}))}]
    }

@tool("update_entity", "Update a worldbuilding entity", {
    "entity_type": str, "name": str, "data": str
})
async def update_entity(args):
    # Write to your entity files
    return {"content": [{"type": "text", "text": f"Updated {args['name']}"}]}

worldbuilding_server = create_sdk_mcp_server(
    name="worldbuilding",
    tools=[get_world_state, update_entity]
)

options = ClaudeAgentOptions(
    mcp_servers={"wb": worldbuilding_server},
    allowed_tools=[
        "mcp__wb__get_world_state",
        "mcp__wb__update_entity",
        "Read", "Write", "Edit"
    ]
)
```

### Session Management

```python
# Resume a previous session
options = ClaudeAgentOptions(
    resume="previous-session-id",  # Resume specific session
    # OR
    continue_conversation=True,     # Continue most recent
)

# Fork a session (branch off)
options = ClaudeAgentOptions(
    resume="session-id",
    fork_session=True  # Creates new branch from that point
)
```

### Feasibility Assessment

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Technically feasible | YES | Official SDK, production-ready |
| Real-time streaming | YES | `include_partial_messages=True` yields `StreamEvent` objects |
| Conversation history | YES | `ClaudeSDKClient` maintains session; `resume`/`continue_conversation` options |
| Hooks still work | YES | Python async functions, full PreToolUse/PostToolUse/UserPromptSubmit support |
| Dependencies | `pip install claude-agent-sdk` + Node.js + Claude Code CLI |
| Integration complexity | LOW | Native Python async, fits perfectly with NiceGUI's async model |
| Windows support | YES | Python package, cross-platform |

---

## Approach 3: Anthropic API Direct

### Overview

Use the `anthropic` Python SDK to call the Claude API directly, bypassing Claude Code entirely.

```python
import anthropic

client = anthropic.Anthropic(api_key="sk-ant-...")

# Streaming
with client.messages.stream(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system="You are a worldbuilding assistant...",
    messages=[{"role": "user", "content": "Describe the factions"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### Feasibility Assessment

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Technically feasible | YES | Well-documented, mature SDK |
| Real-time streaming | YES | Native streaming support |
| Conversation history | MANUAL | You must manage message history yourself |
| Hooks still work | NO | No hook system -- must replicate all behavior manually |
| Dependencies | `pip install anthropic` + API key |
| Integration complexity | HIGH | Must replicate all Claude Code features: tool execution, file access, hook behavior, context injection, system prompt, CLAUDE.md loading |
| Windows support | YES | Pure Python |
| Cost model | API TOKENS | Pay per token (no subscription), can get expensive |

### Why NOT Recommended

- **No hooks:** You would need to reimplement all hook logic (PreToolUse validation, PostToolUse processing, context injection).
- **No tools:** Claude Code's file read/write/edit/bash/grep/glob tools would all need to be reimplemented as API tool definitions.
- **No CLAUDE.md:** Automatic project context loading would need to be manually coded.
- **No session persistence:** Claude Code's automatic session saving to `~/.claude/history.jsonl` would not exist.
- **Cost:** API tokens cost money per use. Claude Code subscription provides unlimited usage within limits.
- **Essentially rebuilding Claude Code:** You would be rebuilding most of what Claude Code already does.

---

## Approach 4: Claude Code MCP Server

### Overview

MCP (Model Context Protocol) is an open standard for connecting AI systems to tools and data. There are two possible configurations:

**Option A: Web app exposes MCP server, Claude Code connects as client**
- Claude Code already supports connecting to MCP servers
- Your NiceGUI app would run an MCP server exposing worldbuilding tools
- Claude Code calls these tools during its normal operation
- Problem: This gives Claude Code access to your app's tools, but does NOT let your web app send messages to Claude Code

**Option B: Claude Code exposed as an MCP server**
- The community project [claude-code-mcp](https://github.com/auchenberg/claude-code-mcp) wraps Claude Code as an MCP server
- Another AI agent or application could call Claude Code through MCP
- Problem: Adds unnecessary indirection; your web app would need to be an MCP client

### Feasibility Assessment

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Technically feasible | PARTIAL | MCP is for tool integration, not chat interfaces |
| Real-time streaming | LIMITED | MCP is request/response, not designed for chat streaming |
| Conversation history | NO | MCP is stateless per-request |
| Hooks still work | PARTIAL | Only if Claude Code is the one running (Option A) |
| Dependencies | MCP server implementation + Claude Code configuration |
| Integration complexity | HIGH | Wrong abstraction for a chat interface |
| Windows support | YES | MCP servers run cross-platform |

### Why NOT Recommended for This Use Case

MCP is designed for **tool integration** (give AI access to databases, APIs, etc.), not for building **chat interfaces** on top of an AI agent. It adds unnecessary complexity. However, MCP is excellent for the **reverse direction**: giving Claude Code access to your worldbuilding data via custom MCP tools. This is already supported natively in the Agent SDK via `create_sdk_mcp_server()`.

---

## NiceGUI Streaming Capabilities

### Chat Component

NiceGUI provides `ui.chat_message` for building chat interfaces:

```python
from nicegui import ui

# Basic chat message
ui.chat_message('Hello!', name='User', sent=True)
ui.chat_message('Hi there!', name='Claude', avatar='https://...')
```

### Streaming Pattern (Recommended)

The proven pattern for streaming LLM responses in NiceGUI:

```python
from nicegui import ui
import asyncio

async def send_message(user_input: str):
    # Add user message
    with chat_container:
        ui.chat_message(user_input, name='User', sent=True)

    # Create bot message container
    with chat_container:
        bot_msg = ui.chat_message(name='Claude', sent=False, text_html=True)
        with bot_msg:
            content = ui.html('')
        spinner = ui.spinner('dots')

    # Stream response
    response_text = ''
    async for chunk in get_claude_response(user_input):
        response_text += chunk
        content.set_content(response_text)

    spinner.delete()
```

### Key NiceGUI Patterns

1. **Use `async` functions** -- NiceGUI runs on asyncio, perfect for async streaming
2. **Use `ui.chat_message` with `text_html=True`** -- Allows HTML/Markdown rendering
3. **Use `ui.html().set_content()`** -- Update message content in real-time without flickering
4. **Use `ui.spinner`** -- Show loading indicator while waiting
5. **Use `ui.timer`** -- Alternative: poll for updates at fixed intervals (e.g., 0.1s)
6. **Both NiceGUI and the Agent SDK use asyncio** -- They share the same event loop naturally

---

## Comparison Matrix

| Criterion | CLI Subprocess | Agent SDK (Python) | Anthropic API | MCP Server |
|-----------|---------------|-------------------|---------------|------------|
| **Feasibility** | High | High | High | Medium |
| **Streaming** | Yes (JSON-lines) | Yes (native async) | Yes (native) | Limited |
| **Conversation Memory** | Yes (--continue/--resume) | Yes (ClaudeSDKClient) | Manual | No |
| **Hooks** | Yes (shell commands) | Yes (Python functions) | No | Partial |
| **Custom Tools** | Via config | Via @tool decorator | Via API tools | Yes |
| **Integration Effort** | Medium | Low | High | High |
| **Python-native** | No (subprocess) | Yes | Yes | No |
| **Async-compatible** | Via asyncio.subprocess | Native async | Native async | Varies |
| **Windows** | Yes | Yes | Yes | Yes |
| **Cost Model** | Subscription | Subscription | Per-token API | Subscription |
| **CLAUDE.md Loading** | Automatic | Via setting_sources | Manual | Automatic |
| **Permission Control** | --allowedTools | can_use_tool callback | Manual | Via Claude Code |
| **NiceGUI Fit** | Good | Excellent | Good | Poor |

---

## Recommended Architecture

### Architecture: NiceGUI + Claude Agent SDK

```
+----------------------------------------------------------+
|                    NiceGUI Web Application                 |
|  (Python, runs on localhost:8080)                         |
|                                                           |
|  +------------------+  +-----------------------------+    |
|  |   Chat Panel     |  |   Dashboard Panel           |    |
|  |                  |  |                             |    |
|  |  [User Input]    |  |  - Entity Browser          |    |
|  |  [Chat History]  |  |  - Knowledge Graph (vis)   |    |
|  |  [Stream Display]|  |  - Progression Tracker     |    |
|  |                  |  |  - World State Dashboard   |    |
|  +--------+---------+  +-------------+--------------+    |
|           |                          |                    |
+-----------+--------------------------+--------------------+
            |                          |
            v                          v
+------------------------+   +------------------------+
|  Claude Integration    |   |  State File Reader     |
|  Layer (async)         |   |  (watchdog/polling)    |
|                        |   |                        |
|  ClaudeSDKClient       |   |  Reads JSON/YAML from  |
|  - query()             |   |  project data files    |
|  - receive_response()  |   |  and updates dashboard |
|  - hooks               |   |                        |
|  - custom MCP tools    |   +------------------------+
+----------+-------------+
           |
           v
+------------------------+
|  Claude Code CLI       |
|  (subprocess, managed  |
|   by Agent SDK)        |
|                        |
|  - Full tool access    |
|  - CLAUDE.md context   |
|  - Session persistence |
|  - File operations     |
+------------------------+
```

### Why This Architecture

1. **ClaudeSDKClient** is designed exactly for this: interactive chat applications with persistent sessions
2. **Python hooks** let you inject worldbuilding context, validate operations, and log tool usage -- all as Python async functions, no shell scripts needed
3. **Custom MCP tools** let Claude access your worldbuilding data (entities, factions, world state) natively
4. **NiceGUI and the SDK both use asyncio** -- they share the event loop, making streaming integration seamless
5. **Dashboard** reads project state files independently, showing real-time data alongside the chat

---

## Implementation Guide

### Project Structure

```
C:\Worldbuilding-Interactive-Program\
  app\
    main.py              # NiceGUI app entry point
    claude_client.py     # Claude Agent SDK integration
    chat_panel.py        # Chat UI component
    dashboard.py         # Dashboard UI components
    hooks.py             # Custom hook functions
    tools.py             # Custom MCP tool definitions
    state_reader.py      # Project state file reader
  data\
    world_state.json     # World state data
    entities\            # Entity files
    knowledge_graph\     # Graph data
  .claude\
    settings.json        # Claude Code project settings
  CLAUDE.md              # Project instructions for Claude
```

### Core Integration Layer: `claude_client.py`

```python
"""
Claude Agent SDK integration layer for NiceGUI web application.
Manages ClaudeSDKClient lifecycle, streaming, and session state.
"""

import asyncio
from typing import AsyncIterator, Optional, Callable
from dataclasses import dataclass, field

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    StreamEvent,
    ResultMessage,
    HookMatcher,
)


@dataclass
class StreamChunk:
    """A chunk of streamed response data."""
    type: str  # "text", "tool_start", "tool_result", "done"
    content: str = ""
    metadata: dict = field(default_factory=dict)


class ClaudeChat:
    """
    Manages a Claude Code conversation session via the Agent SDK.
    Designed to integrate with NiceGUI's async event loop.
    """

    def __init__(
        self,
        project_dir: str = "C:/Worldbuilding-Interactive-Program",
        hooks: dict = None,
        mcp_servers: dict = None,
        on_tool_use: Optional[Callable] = None,
    ):
        self.project_dir = project_dir
        self.client: Optional[ClaudeSDKClient] = None
        self.session_id: Optional[str] = None
        self.is_connected = False
        self.on_tool_use = on_tool_use
        self._hooks = hooks or {}
        self._mcp_servers = mcp_servers or {}

    def _build_options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            cwd=self.project_dir,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
            permission_mode="acceptEdits",
            include_partial_messages=True,  # Enable token-level streaming
            setting_sources=["project"],     # Load CLAUDE.md and .claude/settings.json
            system_prompt={
                "type": "preset",
                "preset": "claude_code",
                "append": (
                    "You are the Worldbuilding Engine. You help develop and manage "
                    "a rich, interconnected fictional world. When making changes, "
                    "always update the relevant state files in the data/ directory."
                )
            },
            hooks=self._hooks,
            mcp_servers=self._mcp_servers,
        )

    async def connect(self):
        """Initialize the Claude SDK client and connect."""
        options = self._build_options()
        self.client = ClaudeSDKClient(options)
        await self.client.connect()
        self.is_connected = True

    async def disconnect(self):
        """Disconnect the client."""
        if self.client:
            await self.client.disconnect()
            self.is_connected = False

    async def send_message(self, message: str) -> AsyncIterator[StreamChunk]:
        """
        Send a message and yield streaming response chunks.
        Each chunk contains either streamed text or tool usage info.

        Usage with NiceGUI:
            async for chunk in claude_chat.send_message("Tell me about factions"):
                if chunk.type == "text":
                    content_element.set_content(accumulated_text)
        """
        if not self.is_connected:
            await self.connect()

        await self.client.query(message)

        async for msg in self.client.receive_response():
            # Token-level streaming events
            if isinstance(msg, StreamEvent):
                delta = msg.event.get("delta", {})
                if delta.get("type") == "text_delta":
                    yield StreamChunk(type="text", content=delta["text"])

            # Complete assistant messages (with tool use info)
            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        yield StreamChunk(
                            type="tool_start",
                            content=f"Using tool: {block.name}",
                            metadata={"tool": block.name, "input": block.input}
                        )
                        if self.on_tool_use:
                            await self.on_tool_use(block.name, block.input)
                    elif isinstance(block, ToolResultBlock):
                        yield StreamChunk(
                            type="tool_result",
                            content=str(block.content)[:200],
                            metadata={"tool_use_id": block.tool_use_id}
                        )

            # Final result
            elif isinstance(msg, ResultMessage):
                self.session_id = msg.session_id
                yield StreamChunk(
                    type="done",
                    metadata={
                        "session_id": msg.session_id,
                        "cost_usd": msg.total_cost_usd,
                        "duration_ms": msg.duration_ms,
                        "turns": msg.num_turns,
                    }
                )

    async def interrupt(self):
        """Interrupt the current operation."""
        if self.client:
            await self.client.interrupt()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()
```

### Custom Hooks: `hooks.py`

```python
"""
Hook definitions for the worldbuilding Claude integration.
These run as Python async functions within the Agent SDK.
"""

import json
import os
from typing import Any
from claude_agent_sdk import HookMatcher, HookContext

PROJECT_DIR = "C:/Worldbuilding-Interactive-Program"


async def inject_world_context(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext
) -> dict[str, Any]:
    """
    UserPromptSubmit hook: Inject current world state summary
    before every user prompt so Claude always has context.
    """
    state_file = os.path.join(PROJECT_DIR, "data", "world_state.json")
    try:
        with open(state_file, "r") as f:
            state = json.load(f)
        summary = json.dumps({
            "current_era": state.get("current_era"),
            "active_factions": len(state.get("factions", [])),
            "recent_events": state.get("recent_events", [])[:3],
        }, indent=2)
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"[World State Summary]\n{summary}"
            }
        }
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


async def validate_file_writes(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext
) -> dict[str, Any]:
    """
    PreToolUse hook: Ensure file writes stay within the project directory.
    """
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Normalize path
    norm_path = os.path.normpath(file_path)
    norm_project = os.path.normpath(PROJECT_DIR)

    if file_path and not norm_path.startswith(norm_project):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"File operations must stay within {PROJECT_DIR}. "
                    f"Attempted path: {file_path}"
                )
            }
        }
    return {}


async def log_tool_activity(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext
) -> dict[str, Any]:
    """
    PostToolUse hook: Log tool activity for the dashboard.
    """
    tool_name = input_data.get("tool_name", "unknown")
    log_file = os.path.join(PROJECT_DIR, "data", "tool_activity_log.jsonl")

    import datetime
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "tool": tool_name,
        "input_summary": str(input_data.get("tool_input", {}))[:200],
    }

    try:
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

    return {}


def build_hooks() -> dict:
    """Build the hooks configuration dict for ClaudeAgentOptions."""
    return {
        "UserPromptSubmit": [
            HookMatcher(hooks=[inject_world_context])
        ],
        "PreToolUse": [
            HookMatcher(matcher="Write|Edit", hooks=[validate_file_writes]),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[log_tool_activity])
        ],
    }
```

### Custom MCP Tools: `tools.py`

```python
"""
Custom MCP tools that give Claude access to worldbuilding data.
These run as in-process MCP servers within the Python application.
"""

import json
import os
from typing import Any
from claude_agent_sdk import tool, create_sdk_mcp_server

PROJECT_DIR = "C:/Worldbuilding-Interactive-Program"


@tool("get_entities", "List or search worldbuilding entities", {
    "entity_type": str,  # e.g., "faction", "character", "location"
    "filter": str,       # Optional search filter
})
async def get_entities(args: dict[str, Any]) -> dict[str, Any]:
    entity_type = args["entity_type"]
    filter_text = args.get("filter", "").lower()

    entities_dir = os.path.join(PROJECT_DIR, "data", "entities", entity_type)
    results = []

    if os.path.isdir(entities_dir):
        for fname in os.listdir(entities_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(entities_dir, fname)
                with open(fpath, "r") as f:
                    entity = json.load(f)
                if not filter_text or filter_text in json.dumps(entity).lower():
                    results.append(entity)

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(results, indent=2)
        }]
    }


@tool("get_world_state", "Get current worldbuilding state", {"aspect": str})
async def get_world_state(args: dict[str, Any]) -> dict[str, Any]:
    aspect = args["aspect"]
    state_file = os.path.join(PROJECT_DIR, "data", "world_state.json")

    try:
        with open(state_file, "r") as f:
            state = json.load(f)
        result = state.get(aspect, f"No data found for aspect: {aspect}")
    except FileNotFoundError:
        result = "World state file not found"

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
        }]
    }


@tool("get_knowledge_graph", "Get knowledge graph connections for an entity", {
    "entity_name": str
})
async def get_knowledge_graph(args: dict[str, Any]) -> dict[str, Any]:
    graph_file = os.path.join(PROJECT_DIR, "data", "knowledge_graph", "graph.json")

    try:
        with open(graph_file, "r") as f:
            graph = json.load(f)
        entity = args["entity_name"].lower()
        connections = [
            edge for edge in graph.get("edges", [])
            if entity in edge.get("source", "").lower()
            or entity in edge.get("target", "").lower()
        ]
        return {
            "content": [{
                "type": "text",
                "text": json.dumps(connections, indent=2)
            }]
        }
    except FileNotFoundError:
        return {
            "content": [{"type": "text", "text": "Knowledge graph not found"}]
        }


def build_mcp_servers() -> dict:
    """Build MCP server configuration for ClaudeAgentOptions."""
    wb_server = create_sdk_mcp_server(
        name="worldbuilding",
        version="1.0.0",
        tools=[get_entities, get_world_state, get_knowledge_graph]
    )
    return {"wb": wb_server}
```

### NiceGUI Chat Panel: `chat_panel.py`

```python
"""
NiceGUI chat panel component with real-time streaming from Claude Agent SDK.
"""

from nicegui import ui
import asyncio
from typing import Optional
from .claude_client import ClaudeChat, StreamChunk


class ChatPanel:
    """Chat interface component for NiceGUI."""

    def __init__(self, claude_chat: ClaudeChat):
        self.claude = claude_chat
        self.chat_container = None
        self.input_field = None
        self.is_processing = False

    def build(self):
        """Build the chat UI."""
        with ui.column().classes('w-full h-full'):
            # Chat message area (scrollable)
            self.chat_container = ui.column().classes(
                'w-full flex-grow overflow-y-auto p-4 gap-2'
            )

            # Input area
            with ui.row().classes('w-full p-2 items-center'):
                self.input_field = ui.input(
                    placeholder='Type your message...'
                ).classes('flex-grow').on(
                    'keydown.enter', self._on_send
                )
                ui.button('Send', on_click=self._on_send).props('color=primary')
                ui.button('Stop', on_click=self._on_stop).props(
                    'color=negative outline'
                )

    async def _on_send(self):
        """Handle sending a message."""
        if self.is_processing or not self.input_field.value.strip():
            return

        user_text = self.input_field.value.strip()
        self.input_field.value = ''
        self.is_processing = True

        # Add user message to chat
        with self.chat_container:
            ui.chat_message(
                user_text,
                name='You',
                sent=True,
            )

        # Create bot message container for streaming
        with self.chat_container:
            bot_msg = ui.chat_message(
                name='Claude',
                sent=False,
                text_html=True,
            )
            with bot_msg:
                content_el = ui.html('')
                tool_status = ui.html('')
            spinner = ui.spinner('dots', size='sm')

        # Stream response from Claude
        accumulated_text = ''
        try:
            async for chunk in self.claude.send_message(user_text):
                if chunk.type == 'text':
                    accumulated_text += chunk.content
                    # Convert markdown to HTML (basic)
                    content_el.set_content(
                        f'<pre style="white-space:pre-wrap;font-family:inherit">'
                        f'{accumulated_text}</pre>'
                    )
                elif chunk.type == 'tool_start':
                    tool_status.set_content(
                        f'<div style="color:#888;font-size:0.85em;margin-top:4px">'
                        f'&#9881; {chunk.content}</div>'
                    )
                elif chunk.type == 'tool_result':
                    tool_status.set_content('')  # Clear tool status
                elif chunk.type == 'done':
                    meta = chunk.metadata
                    cost = meta.get('cost_usd')
                    duration = meta.get('duration_ms', 0) / 1000
                    # Optionally show metadata
                    if cost is not None:
                        tool_status.set_content(
                            f'<div style="color:#aaa;font-size:0.75em">'
                            f'Cost: ${cost:.4f} | Time: {duration:.1f}s</div>'
                        )
        except Exception as e:
            content_el.set_content(
                f'<div style="color:red">Error: {str(e)}</div>'
            )
        finally:
            spinner.delete()
            self.is_processing = False

    async def _on_stop(self):
        """Handle stop/interrupt."""
        if self.is_processing:
            await self.claude.interrupt()
            self.is_processing = False
```

### NiceGUI Dashboard: `dashboard.py`

```python
"""
Dashboard components that read project state files independently.
"""

import json
import os
from nicegui import ui

PROJECT_DIR = "C:/Worldbuilding-Interactive-Program"


class WorldDashboard:
    """Dashboard panel showing project state, entities, and progression."""

    def __init__(self):
        self.refresh_interval = 5.0  # seconds

    def build(self):
        """Build dashboard UI."""
        with ui.column().classes('w-full h-full p-4 gap-4'):
            ui.label('World Dashboard').classes('text-xl font-bold')

            with ui.tabs() as tabs:
                tab_state = ui.tab('World State')
                tab_entities = ui.tab('Entities')
                tab_graph = ui.tab('Knowledge Graph')
                tab_progress = ui.tab('Progression')

            with ui.tab_panels(tabs).classes('w-full flex-grow'):
                with ui.tab_panel(tab_state):
                    self._build_world_state_panel()
                with ui.tab_panel(tab_entities):
                    self._build_entity_browser()
                with ui.tab_panel(tab_graph):
                    self._build_knowledge_graph()
                with ui.tab_panel(tab_progress):
                    self._build_progression_tracker()

        # Auto-refresh timer
        ui.timer(self.refresh_interval, self._refresh_all)

    @ui.refreshable
    def _build_world_state_panel(self):
        state_file = os.path.join(PROJECT_DIR, "data", "world_state.json")
        try:
            with open(state_file) as f:
                state = json.load(f)
            ui.json_editor({'content': {'json': state}}).classes('w-full')
        except (FileNotFoundError, json.JSONDecodeError):
            ui.label('No world state file found.').classes('text-gray-500')

    @ui.refreshable
    def _build_entity_browser(self):
        entities_dir = os.path.join(PROJECT_DIR, "data", "entities")
        if not os.path.isdir(entities_dir):
            ui.label('No entities directory found.').classes('text-gray-500')
            return

        for entity_type in sorted(os.listdir(entities_dir)):
            type_dir = os.path.join(entities_dir, entity_type)
            if os.path.isdir(type_dir):
                with ui.expansion(entity_type.title(), icon='folder'):
                    for fname in sorted(os.listdir(type_dir)):
                        if fname.endswith('.json'):
                            fpath = os.path.join(type_dir, fname)
                            try:
                                with open(fpath) as f:
                                    entity = json.load(f)
                                name = entity.get('name', fname.replace('.json', ''))
                                with ui.expansion(name):
                                    ui.json_editor({
                                        'content': {'json': entity}
                                    }).classes('w-full')
                            except (json.JSONDecodeError, Exception):
                                ui.label(f'Error reading {fname}')

    @ui.refreshable
    def _build_knowledge_graph(self):
        graph_file = os.path.join(PROJECT_DIR, "data", "knowledge_graph", "graph.json")
        try:
            with open(graph_file) as f:
                graph = json.load(f)

            # Use Plotly or ECharts for graph visualization
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])

            # Simple table view (replace with proper graph viz)
            with ui.column().classes('w-full'):
                ui.label(f'{len(nodes)} nodes, {len(edges)} edges')
                columns = [
                    {'name': 'source', 'label': 'Source', 'field': 'source'},
                    {'name': 'relation', 'label': 'Relation', 'field': 'relation'},
                    {'name': 'target', 'label': 'Target', 'field': 'target'},
                ]
                ui.table(columns=columns, rows=edges[:50]).classes('w-full')
        except (FileNotFoundError, json.JSONDecodeError):
            ui.label('No knowledge graph found.').classes('text-gray-500')

    @ui.refreshable
    def _build_progression_tracker(self):
        progress_file = os.path.join(PROJECT_DIR, "data", "progression.json")
        try:
            with open(progress_file) as f:
                progress = json.load(f)

            for phase in progress.get("phases", []):
                name = phase.get("name", "Unknown")
                pct = phase.get("completion", 0)
                with ui.row().classes('w-full items-center'):
                    ui.label(name).classes('w-40')
                    ui.linear_progress(value=pct / 100).classes('flex-grow')
                    ui.label(f'{pct}%').classes('w-12 text-right')
        except (FileNotFoundError, json.JSONDecodeError):
            ui.label('No progression data found.').classes('text-gray-500')

    def _refresh_all(self):
        """Refresh all dashboard panels."""
        self._build_world_state_panel.refresh()
        self._build_entity_browser.refresh()
        self._build_knowledge_graph.refresh()
        self._build_progression_tracker.refresh()
```

### Main Application: `main.py`

```python
"""
NiceGUI Web Application with Claude Code Backend.
Entry point for the Worldbuilding Interactive Program.
"""

from nicegui import ui, app
from .claude_client import ClaudeChat
from .chat_panel import ChatPanel
from .dashboard import WorldDashboard
from .hooks import build_hooks
from .tools import build_mcp_servers

# Global Claude chat instance (shared across the session)
claude_chat: ClaudeChat = None


async def startup():
    """Initialize Claude connection on app startup."""
    global claude_chat
    claude_chat = ClaudeChat(
        project_dir="C:/Worldbuilding-Interactive-Program",
        hooks=build_hooks(),
        mcp_servers=build_mcp_servers(),
    )
    await claude_chat.connect()


async def shutdown():
    """Clean up on app shutdown."""
    global claude_chat
    if claude_chat:
        await claude_chat.disconnect()


app.on_startup(startup)
app.on_shutdown(shutdown)


@ui.page('/')
def main_page():
    """Main application page with split layout."""
    ui.page_title('Worldbuilding Interactive Program')

    with ui.header().classes('bg-primary'):
        ui.label('Worldbuilding Interactive Program').classes(
            'text-xl font-bold text-white'
        )

    with ui.splitter(value=50).classes('w-full h-[calc(100vh-64px)]') as splitter:
        with splitter.before:
            # Left: Chat with Claude
            chat_panel = ChatPanel(claude_chat)
            chat_panel.build()

        with splitter.after:
            # Right: Dashboard
            dashboard = WorldDashboard()
            dashboard.build()


ui.run(
    title='Worldbuilding',
    host='127.0.0.1',
    port=8080,
    reload=False,
)
```

### Installation & Setup

```bash
# 1. Install Claude Code CLI (requires Node.js 18+)
npm install -g @anthropic-ai/claude-code

# 2. Authenticate Claude Code (one-time)
claude

# 3. Install Python dependencies
pip install claude-agent-sdk nicegui

# 4. Run the application
python -m app.main
```

### Requirements

```
# requirements.txt
nicegui>=2.0
claude-agent-sdk>=0.1.0
```

---

## Streaming Implementation Details

### How Streaming Works End-to-End

1. **User types message** in NiceGUI input field and presses Enter
2. **NiceGUI calls `_on_send()`** (async function in the asyncio event loop)
3. **`ClaudeChat.send_message()`** calls `client.query(message)`
4. **Agent SDK** sends the message to the Claude Code CLI subprocess via stdin (JSON-lines)
5. **Claude Code CLI** sends the prompt to the Anthropic API with streaming enabled
6. **Anthropic API** streams tokens back to Claude Code CLI
7. **Claude Code CLI** writes `stream-json` events to stdout
8. **Agent SDK** parses these and yields `StreamEvent` objects
9. **`ClaudeChat.send_message()`** extracts text deltas and yields `StreamChunk` objects
10. **NiceGUI chat panel** calls `content_el.set_content()` for each chunk
11. **NiceGUI's WebSocket** pushes the updated HTML to the browser in real-time

### Key Configuration for Streaming

```python
options = ClaudeAgentOptions(
    include_partial_messages=True,  # THIS IS CRITICAL for token-level streaming
)
```

Without `include_partial_messages=True`, you only get complete `AssistantMessage` objects after Claude finishes its entire response. With it enabled, you also receive `StreamEvent` objects containing individual token deltas as they arrive.

### Handling the StreamEvent

```python
if isinstance(msg, StreamEvent):
    event = msg.event
    delta = event.get("delta", {})

    if delta.get("type") == "text_delta":
        # This is a text token
        text = delta["text"]
        # Append to accumulated text and update UI

    elif delta.get("type") == "input_json_delta":
        # This is a tool input being streamed (optional to display)
        pass
```

---

## Sources

- [Run Claude Code programmatically (Headless mode)](https://code.claude.com/docs/en/headless)
- [Claude Code CLI Reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage)
- [Claude Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Claude Agent SDK Python Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Claude Agent SDK Quickstart](https://platform.claude.com/docs/en/agent-sdk/quickstart)
- [Claude Agent SDK -- Streaming Input](https://platform.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)
- [Claude Agent SDK -- Hooks](https://platform.claude.com/docs/en/agent-sdk/hooks)
- [Claude Agent SDK -- MCP Integration](https://platform.claude.com/docs/en/agent-sdk/mcp)
- [Claude Agent SDK -- Sessions](https://platform.claude.com/docs/en/agent-sdk/sessions)
- [Claude Agent SDK Python GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- [Claude Agent SDK Migration Guide](https://platform.claude.com/docs/en/agent-sdk/migration-guide)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code MCP Integration](https://code.claude.com/docs/en/mcp)
- [Claude Code Common Workflows](https://code.claude.com/docs/en/common-workflows)
- [Building Agents with Claude Agent SDK (Anthropic Engineering Blog)](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [Inside the Claude Agent SDK (AWS Substack)](https://buildwithaws.substack.com/p/inside-the-claude-agent-sdk-from)
- [Claude Code CLI Cheatsheet (Shipyard)](https://shipyard.build/blog/claude-code-cheat-sheet/)
- [NiceGUI Documentation -- Chat Message](https://nicegui.io/documentation/chat_message)
- [NiceGUI Chat with AI Example](https://github.com/zauberzeug/nicegui/blob/main/examples/chat_with_ai/main.py)
- [NiceGUI Streaming Chat Discussion #4142](https://github.com/zauberzeug/nicegui/discussions/4142)
- [NiceGUI Streaming Chatbot Discussion #2210](https://github.com/zauberzeug/nicegui/discussions/2210)
- [claude-code-mcp (Community MCP Server)](https://github.com/auchenberg/claude-code-mcp)
