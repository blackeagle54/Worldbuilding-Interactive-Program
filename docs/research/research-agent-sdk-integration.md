# Research Report: Claude Agent SDK Integration with PySide6

**Date:** 2026-01-30
**Purpose:** Evaluate how to integrate the Claude Agent SDK (`claude-agent-sdk`) into a PySide6 desktop worldbuilding tool where Claude acts as a streaming creative assistant.
**Key constraint:** No API keys. The user authenticates via Claude Code CLI subscription login. Responses stream token-by-token.

---

## Table of Contents

1. [Claude Agent SDK Basics](#1-claude-agent-sdk-basics)
2. [Streaming Integration with Qt](#2-streaming-integration-with-qt)
3. [Session Management](#3-session-management)
4. [Tool Use / Function Calling](#4-tool-use--function-calling)
5. [Error Handling](#5-error-handling)
6. [Alternative Approach: Subprocess](#6-alternative-approach-subprocess)
7. [Context Injection](#7-context-injection)
8. [Recommendations](#8-recommendations)
9. [Sources](#9-sources)

---

## 1. Claude Agent SDK Basics

### What It Is

The **Claude Agent SDK** (`claude-agent-sdk`) is Anthropic's official Python SDK for building agents powered by Claude Code. It was formerly called `claude-code-sdk` (now deprecated). The SDK wraps the Claude Code CLI, spawning it as a subprocess and communicating via stdin/stdout JSONL messages. Your Python code never calls the Anthropic API directly; it delegates to the CLI.

**Current version:** 0.1.26 (released 2026-01-30).

### Installation

```bash
pip install claude-agent-sdk
```

**Requirements:**
- Python 3.10+
- Node.js (the Claude Code CLI is automatically bundled with the pip package -- no separate `npm install -g @anthropic-ai/claude-code` required as of recent versions)

### Authentication (No API Key)

This is a critical point for our use case. The Claude Code CLI authenticates via **subscription-based login** (Claude Pro/Team/Max), not via API key. Users run `claude /login` once in their terminal, authenticating through the browser. The Agent SDK inherits this authentication.

There is a documented inconsistency: the SDK quickstart mentions setting `ANTHROPIC_API_KEY`, but the underlying CLI uses subscription auth when the user has logged in via `claude /login`. For our desktop app, we rely on the user having already authenticated with Claude Code CLI. **No API key is needed.**

If the user has both a subscription login and an API key set, the CLI prefers the API key. For our case, we should ensure `ANTHROPIC_API_KEY` is NOT set in the environment we pass to the SDK, so it falls through to subscription auth.

### Core API: Two Modes

#### Mode 1: `query()` -- Simple, Stateless

```python
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock

options = ClaudeAgentOptions(
    system_prompt="You are a worldbuilding assistant.",
    max_turns=1
)

async for message in query(prompt="Describe a desert kingdom", options=options):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text)
```

Each `query()` call starts fresh. No session memory. No custom tools.

#### Mode 2: `ClaudeSDKClient` -- Full-Featured, Stateful

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock

options = ClaudeAgentOptions(
    system_prompt="You are a worldbuilding creative assistant.",
    permission_mode="bypassPermissions"
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("Describe three potential factions for a desert kingdom")

    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
```

`ClaudeSDKClient` supports:
- Bidirectional multi-turn conversations
- Custom tools via in-process MCP servers
- Hooks for pre/post tool execution
- Session resume/fork
- Streaming events (token-by-token)

### Token-by-Token Streaming

To receive partial text as it generates (not just complete messages), enable `include_partial_messages`:

```python
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import StreamEvent

options = ClaudeAgentOptions(include_partial_messages=True)

async for message in query(prompt="Write a creation myth", options=options):
    if isinstance(message, StreamEvent):
        event = message.event
        event_type = event.get("type")

        if event_type == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                text_chunk = delta.get("text", "")
                print(text_chunk, end="", flush=True)
        elif event_type == "message_stop":
            print("\n[Complete]")
```

The `StreamEvent` contains raw Anthropic API stream events. The key event types:
- `content_block_start` -- a new content block begins
- `content_block_delta` with `delta.type == "text_delta"` -- a text token
- `content_block_stop` -- block finished
- `message_stop` -- entire message finished

This is the mechanism we need for the streaming chat panel.

### ClaudeAgentOptions Reference

Key fields for our use case:

```python
ClaudeAgentOptions(
    system_prompt="...",                    # Custom system prompt (string or preset)
    allowed_tools=["Read", "Grep", ...],   # Tools that bypass permission prompts
    mcp_servers={...},                      # Custom tool servers
    permission_mode="bypassPermissions",   # Or "acceptEdits"
    resume="session-id-here",              # Resume a previous session
    max_turns=10,                          # Limit agent loop iterations
    model="claude-sonnet-4-5",             # Model selection
    cwd="/path/to/project",               # Working directory
    env={"KEY": "VALUE"},                  # Environment variables
    include_partial_messages=True,         # Enable StreamEvent for token streaming
    hooks={...},                           # Pre/post tool hooks
)
```

---

## 2. Streaming Integration with Qt

### The Core Challenge

The Claude Agent SDK is **async-first** (built on `anyio`/`asyncio`). PySide6/Qt has its **own event loop** (`QApplication.exec()`). These two loops conflict: you cannot simply `asyncio.run()` inside a Qt application because Qt's event loop is already running.

We need a bridge that lets async SDK calls execute while Qt remains responsive.

### Approach A: `qasync` -- Asyncio-Qt Event Loop Bridge

**Install:** `pip install qasync`

`qasync` replaces the asyncio event loop with one based on Qt's event loop, so both run in the same thread.

```python
import asyncio
import qasync
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit, QPushButton, QVBoxLayout, QWidget
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import StreamEvent


class ChatPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.send_btn = QPushButton("Generate")
        self.send_btn.clicked.connect(lambda: asyncio.ensure_future(self.on_generate()))

        layout = QVBoxLayout()
        layout.addWidget(self.text_edit)
        layout.addWidget(self.send_btn)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    async def on_generate(self):
        self.send_btn.setEnabled(False)
        self.text_edit.clear()

        options = ClaudeAgentOptions(
            system_prompt="You are a worldbuilding assistant.",
            include_partial_messages=True
        )

        async for message in query(prompt="Describe a desert kingdom", options=options):
            if isinstance(message, StreamEvent):
                event = message.event
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        # Append token directly -- we are on the main thread
                        cursor = self.text_edit.textCursor()
                        cursor.movePosition(cursor.MoveOperation.End)
                        cursor.insertText(delta.get("text", ""))
                        self.text_edit.setTextCursor(cursor)

        self.send_btn.setEnabled(True)


def main():
    app = QApplication([])
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = ChatPanel()
    window.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
```

**Pros:**
- Single-threaded: no thread-safety issues when updating Qt widgets
- `async/await` works naturally inside slot handlers
- Mature library, supports PySide6

**Cons:**
- Adds a dependency (`qasync`)
- If the async coroutine blocks (CPU-bound work), Qt becomes unresponsive
- Some edge cases with cleanup on shutdown
- Slightly non-standard Qt application setup

### Approach B: QThread + Signal/Slot Bridge

Run the Agent SDK in a background `QThread`, emit Qt signals per token, connect signals to the main thread for UI updates.

```python
import asyncio
from PySide6.QtCore import QThread, Signal, QObject
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit, QPushButton, QVBoxLayout, QWidget
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import StreamEvent


class AgentWorker(QThread):
    token_received = Signal(str)
    finished_signal = Signal()
    error_occurred = Signal(str)

    def __init__(self, prompt: str, system_prompt: str):
        super().__init__()
        self.prompt = prompt
        self.system_prompt = system_prompt

    def run(self):
        """Runs in background thread with its own asyncio event loop."""
        try:
            asyncio.run(self._stream())
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.finished_signal.emit()

    async def _stream(self):
        options = ClaudeAgentOptions(
            system_prompt=self.system_prompt,
            include_partial_messages=True
        )
        async for message in query(prompt=self.prompt, options=options):
            if isinstance(message, StreamEvent):
                event = message.event
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        self.token_received.emit(delta.get("text", ""))


class ChatPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.send_btn = QPushButton("Generate")
        self.send_btn.clicked.connect(self.on_generate)
        self.worker = None

        layout = QVBoxLayout()
        layout.addWidget(self.text_edit)
        layout.addWidget(self.send_btn)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def on_generate(self):
        self.send_btn.setEnabled(False)
        self.text_edit.clear()

        self.worker = AgentWorker(
            prompt="Describe a desert kingdom",
            system_prompt="You are a worldbuilding assistant."
        )
        self.worker.token_received.connect(self._append_token)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _append_token(self, text: str):
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.text_edit.setTextCursor(cursor)

    def _on_finished(self):
        self.send_btn.setEnabled(True)

    def _on_error(self, error_msg: str):
        self.text_edit.append(f"\n[Error: {error_msg}]")
        self.send_btn.setEnabled(True)


if __name__ == "__main__":
    app = QApplication([])
    window = ChatPanel()
    window.show()
    app.exec()
```

**Pros:**
- Standard Qt pattern -- no extra async dependencies
- Clean separation of concerns (UI thread vs. worker thread)
- Standard `QApplication.exec()` startup
- Easy to cancel (terminate the thread or set a flag)

**Cons:**
- Each query spawns a new thread (or reuse via a pool)
- Cannot share `ClaudeSDKClient` across threads easily (session state)
- Slightly more boilerplate

### Approach C: PySide6.QtAsyncio (Official Qt Module)

PySide6 ships with `PySide6.QtAsyncio`, an official asyncio-Qt bridge.

```python
import asyncio
import PySide6.QtAsyncio as QtAsyncio
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit

# ... same async code as Approach A ...

def main():
    app = QApplication([])
    window = ChatPanel()
    window.show()
    QtAsyncio.run()  # Replaces app.exec()
```

**Pros:**
- Official Qt solution, no third-party dependency
- Same single-threaded model as qasync

**Cons:**
- Relatively new; less community testing than qasync
- May have rough edges on Windows

### Approach D: asyncio.Queue as Bridge

A hybrid: run asyncio in a daemon thread, use `asyncio.Queue` (or `queue.Queue`) to pass tokens to the main Qt thread via a `QTimer` poll.

```python
import asyncio
import threading
import queue
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import StreamEvent


class ChatPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.setCentralWidget(self.text_edit)

        self.token_queue = queue.Queue()

        # Poll the queue every 16ms (~60fps)
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._drain_queue)
        self.poll_timer.start(16)

    def start_query(self, prompt: str):
        thread = threading.Thread(
            target=self._run_async_query, args=(prompt,), daemon=True
        )
        thread.start()

    def _run_async_query(self, prompt: str):
        asyncio.run(self._stream(prompt))

    async def _stream(self, prompt: str):
        options = ClaudeAgentOptions(
            system_prompt="You are a worldbuilding assistant.",
            include_partial_messages=True
        )
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, StreamEvent):
                event = message.event
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        self.token_queue.put(delta.get("text", ""))
        self.token_queue.put(None)  # Sentinel: stream complete

    def _drain_queue(self):
        while not self.token_queue.empty():
            token = self.token_queue.get_nowait()
            if token is None:
                return  # Stream complete
            cursor = self.text_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.insertText(token)
            self.text_edit.setTextCursor(cursor)
```

**Pros:**
- No extra dependencies
- Works with standard Qt event loop
- Decoupled: async code knows nothing about Qt

**Cons:**
- Polling introduces slight latency (up to 16ms at 60fps -- imperceptible for text)
- Manual queue management
- Sentinel values for completion signaling

### Recommendation for This Project

**Use Approach B (QThread + Signals)** as the primary strategy. It is the most idiomatic Qt pattern, requires no extra dependencies beyond PySide6 and `claude-agent-sdk`, handles errors cleanly via signals, and keeps standard `app.exec()` startup. If multi-turn `ClaudeSDKClient` sessions become necessary (and they will for session resume), use Approach A (qasync) or C (QtAsyncio) to keep the client alive across turns.

---

## 3. Session Management

### How Sessions Work in the SDK

The Agent SDK creates a session when you first query, and returns a `session_id` in the init system message:

```python
async with ClaudeSDKClient(options=options) as client:
    await client.query("Hello")
    async for message in client.receive_response():
        if hasattr(message, 'session_id'):
            saved_session_id = message.session_id
            break
```

Sessions are persisted to disk at `~/.claude/projects/` by default.

### Resuming Sessions

To continue a conversation:

```python
options = ClaudeAgentOptions(
    resume="the-session-id-from-before",
    system_prompt="You are a worldbuilding assistant."
)
async for message in query(prompt="Continue with the faction details", options=options):
    ...
```

Or with `ClaudeSDKClient`:

```python
options = ClaudeAgentOptions(resume=session_id)
async with ClaudeSDKClient(options=options) as client:
    await client.query("What were those factions again?")
    async for message in client.receive_response():
        ...
```

### Forking Sessions

Create a branch from an existing session without modifying the original:

```python
options = ClaudeAgentOptions(
    resume=session_id,
    fork_session=True  # Creates a new session ID from the resumed state
)
```

This is useful for "what-if" explorations in worldbuilding (e.g., "What if this faction had a different origin?").

### Mapping to Our Hook System

Our existing hooks (`session_start.py`, `end_session.py`) can integrate as follows:

```python
# session_start.py -- called when user begins a worldbuilding step
async def start_claude_session(step_context: dict) -> str:
    """Start a new Claude session with step context. Returns session_id."""
    system_prompt = build_system_prompt(step_context)

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        include_partial_messages=True,
        max_turns=5
    )

    async with ClaudeSDKClient(options=options) as client:
        session_id = None
        await client.query(build_initial_prompt(step_context))
        async for message in client.receive_response():
            if hasattr(message, 'session_id') and session_id is None:
                session_id = message.session_id
            # ... process response ...

    return session_id


# end_session.py -- called when user finishes a step
async def end_claude_session(session_id: str):
    """Clean up or save session state."""
    # Sessions persist on disk automatically.
    # Optionally save session_id to our project metadata
    # for later resume.
    save_session_mapping(current_step=..., session_id=session_id)
```

### Passing Context to Claude

Context for each step (current entity data, guidance, template instructions) is passed via:

1. **System prompt** -- sets Claude's role and behavioral guidelines
2. **Initial user message** -- includes the specific entity data and step context
3. **Resume** -- for continuing multi-step workflows

Example context structure:

```python
def build_initial_prompt(step_context: dict) -> str:
    return f"""
    Current Step: {step_context['step_name']}
    Entity Type: {step_context['entity_type']}
    Entity Data So Far: {json.dumps(step_context['entity_data'], indent=2)}

    Relevant World Context:
    {step_context['world_context']}

    Task: {step_context['task_description']}

    Please provide 3 options for the user to choose from, each with a brief rationale.
    """
```

---

## 4. Tool Use / Function Calling

### In-Process MCP Tools

The Agent SDK supports custom tools via **in-process MCP servers**. These run in your Python process -- no separate subprocess or server needed. This is how we expose our engine modules to Claude.

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.tools import tool, create_sdk_mcp_server

# Define a tool for creating entities
@tool(
    name="create_entity",
    description="Create a new worldbuilding entity (character, location, faction, etc.)",
    input_schema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["character", "location", "faction", "event", "item"]
            },
            "name": {"type": "string"},
            "attributes": {"type": "object"}
        },
        "required": ["entity_type", "name"]
    }
)
async def create_entity(entity_type: str, name: str, attributes: dict = None):
    """Called by Claude when it wants to create an entity."""
    # Call into our actual engine
    from engine.entity_manager import EntityManager
    em = EntityManager()
    entity = em.create(entity_type, name, attributes or {})
    return {"status": "created", "entity_id": entity.id, "name": name}


@tool(
    name="check_consistency",
    description="Run a consistency check on the world state, checking for contradictions.",
    input_schema={
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["full", "entity", "relationship"]
            },
            "entity_id": {"type": "string"}
        },
        "required": ["scope"]
    }
)
async def check_consistency(scope: str, entity_id: str = None):
    from engine.consistency import ConsistencyChecker
    checker = ConsistencyChecker()
    results = checker.check(scope=scope, entity_id=entity_id)
    return {"issues": results.issues, "warnings": results.warnings}


@tool(
    name="query_knowledge_graph",
    description="Query the worldbuilding knowledge graph for entities and relationships.",
    input_schema={
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["entity", "relationships", "neighbors", "path"]
            },
            "entity_name": {"type": "string"},
            "relationship_type": {"type": "string"}
        },
        "required": ["query_type"]
    }
)
async def query_knowledge_graph(query_type: str, entity_name: str = None,
                                 relationship_type: str = None):
    from engine.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph()
    results = kg.query(query_type, entity_name, relationship_type)
    return {"results": results}


# Bundle tools into an MCP server
worldbuilding_server = create_sdk_mcp_server(
    tools=[create_entity, check_consistency, query_knowledge_graph]
)

# Use with ClaudeSDKClient
options = ClaudeAgentOptions(
    system_prompt="You are a worldbuilding assistant with access to the project's entity database and knowledge graph.",
    mcp_servers={
        "worldbuilding": {
            "type": "sdk",
            "name": "worldbuilding",
            "server": worldbuilding_server
        }
    },
    allowed_tools=[
        "mcp__worldbuilding__create_entity",
        "mcp__worldbuilding__check_consistency",
        "mcp__worldbuilding__query_knowledge_graph"
    ],
    include_partial_messages=True
)
```

### Tool Naming Convention

Tools registered via MCP servers follow the pattern: `mcp__<server_name>__<tool_name>`.

For example:
- `mcp__worldbuilding__create_entity`
- `mcp__worldbuilding__check_consistency`
- `mcp__worldbuilding__query_knowledge_graph`

These names are used in `allowed_tools` to auto-approve them (skip permission prompts).

### How Tool Calls Flow

1. Claude decides to use a tool based on the conversation
2. The SDK receives a `ToolUseBlock` in the stream
3. For in-process MCP tools, the SDK calls your Python function directly
4. The result is sent back to Claude as a `ToolResultBlock`
5. Claude incorporates the result into its response

In the streaming output, you will see:
- `ToolUseBlock` with `name` and `input` (Claude's tool call)
- `ToolResultBlock` with the function's return value

### Processing Tool Use in the Stream

```python
from claude_agent_sdk.types import AssistantMessage, ToolUseBlock, ToolResultBlock, TextBlock

async for message in client.receive_response():
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                display_text(block.text)
            elif isinstance(block, ToolUseBlock):
                display_tool_call(block.name, block.input)
            elif isinstance(block, ToolResultBlock):
                display_tool_result(block.content)
```

---

## 5. Error Handling

### Exception Hierarchy

All SDK exceptions inherit from `ClaudeSDKError`:

```
ClaudeSDKError (base)
  +-- CLINotFoundError       # Claude Code CLI not found
  +-- ProcessError           # CLI process failed (has exit_code, stderr)
  +-- CLIJSONDecodeError     # CLI output couldn't be parsed
  +-- MessageParseError      # A message failed to parse
```

### Scenario 1: Claude Code CLI Not Installed

```python
from claude_agent_sdk.exceptions import CLINotFoundError, ClaudeSDKError

try:
    async for message in query(prompt="Hello", options=options):
        pass
except CLINotFoundError:
    # Show user-friendly message in the UI
    show_dialog(
        "Claude Code CLI not found. Please install it first:\n"
        "  npm install -g @anthropic-ai/claude-code\n"
        "Then run: claude /login"
    )
```

**Note:** Recent SDK versions bundle the CLI, so this error may only occur if Node.js is missing. Test this on your target platforms.

### Scenario 2: Subscription Expired or Not Authenticated

```python
try:
    async for message in query(prompt="Hello", options=options):
        pass
except ProcessError as e:
    if "API key not found" in e.stderr or "authentication" in e.stderr.lower():
        show_dialog(
            "Claude authentication required.\n"
            "Please run 'claude /login' in your terminal."
        )
    elif "rate_limit" in e.stderr:
        show_dialog("Rate limit reached. Please wait and try again.")
    else:
        show_dialog(f"Claude error: {e.stderr}")
```

### Scenario 3: Connection Drop Mid-Stream

```python
async def safe_stream(prompt: str, options: ClaudeAgentOptions):
    """Stream with automatic retry on transient failures."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async for message in query(prompt=prompt, options=options):
                yield message
            return  # Success
        except ClaudeSDKError as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise  # Final attempt failed
```

### Scenario 4: Windows-Specific Hang

There is a **known issue** on Windows where `ClaudeSDKClient` can hang during initialization due to subprocess stdin/stdout buffering issues. The SDK spawns the CLI via `anyio.open_process()`, and on Windows the process may never send the expected init response.

**Mitigations:**
- Add a timeout to the connection: wrap the `async with ClaudeSDKClient(...)` in `asyncio.wait_for()`
- Fall back to the subprocess approach (Section 6) if the SDK hangs
- Test on WSL as a comparison -- the issue does not occur there

```python
async def connect_with_timeout(options, timeout=30):
    """Connect to Claude SDK with a timeout."""
    try:
        client = ClaudeSDKClient(options=options)
        await asyncio.wait_for(client.connect(), timeout=timeout)
        return client
    except asyncio.TimeoutError:
        raise RuntimeError(
            "Claude SDK connection timed out. "
            "This may be a Windows-specific issue. "
            "Try running in WSL or use the subprocess fallback."
        )
```

### Graceful Degradation Pattern

```python
class ClaudeIntegration:
    """Manages Claude integration with graceful fallback."""

    async def initialize(self):
        """Try SDK first, fall back to subprocess."""
        try:
            self.mode = "sdk"
            self.client = await self._init_sdk()
        except CLINotFoundError:
            self.mode = "unavailable"
            self.status_message = "Claude not available (CLI not found)"
        except Exception:
            try:
                self.mode = "subprocess"
                await self._verify_cli_available()
            except FileNotFoundError:
                self.mode = "unavailable"
                self.status_message = "Claude not available"

    async def query(self, prompt: str):
        if self.mode == "sdk":
            return self._query_sdk(prompt)
        elif self.mode == "subprocess":
            return self._query_subprocess(prompt)
        else:
            yield "[Claude is not available. Working in offline mode.]"
```

---

## 6. Alternative Approach: Subprocess

### Direct CLI Invocation

If the Agent SDK has issues (especially the Windows hang), we can invoke the `claude` CLI directly as a subprocess with streaming JSON output.

```python
import asyncio
import json
from asyncio.subprocess import PIPE


async def query_claude_subprocess(
    prompt: str,
    system_prompt: str = None,
    session_id: str = None
) -> asyncio.AsyncIterator[dict]:
    """Query Claude Code CLI directly via subprocess."""

    cmd = ["claude", "-p", "--output-format", "stream-json"]

    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    if session_id:
        cmd.extend(["--resume", session_id])

    cmd.append(prompt)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=PIPE,
        stderr=PIPE
    )

    async for line in process.stdout:
        line = line.decode("utf-8").strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            yield event
        except json.JSONDecodeError:
            continue

    await process.wait()
    if process.returncode != 0:
        stderr = await process.stderr.read()
        raise RuntimeError(f"Claude CLI exited with code {process.returncode}: {stderr.decode()}")
```

### Streaming JSON Events from CLI

When using `--output-format stream-json`, the CLI emits newline-delimited JSON. Each line is an event:

```json
{"type": "system", "subtype": "init", "session_id": "abc123"}
{"type": "assistant", "content": [{"type": "text", "text": "Here are three options..."}]}
{"type": "result", "cost": {"input_tokens": 150, "output_tokens": 320}}
```

### Qt Integration with Subprocess

```python
from PySide6.QtCore import QThread, Signal
import subprocess
import json


class SubprocessWorker(QThread):
    token_received = Signal(str)
    finished_signal = Signal()
    error_occurred = Signal(str)
    session_started = Signal(str)  # Emits session_id

    def __init__(self, prompt: str, system_prompt: str = None, session_id: str = None):
        super().__init__()
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.session_id = session_id

    def run(self):
        try:
            cmd = ["claude", "-p", "--output-format", "stream-json"]

            if self.system_prompt:
                cmd.extend(["--append-system-prompt", self.system_prompt])

            if self.session_id:
                cmd.extend(["--resume", self.session_id])

            cmd.append(self.prompt)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line-buffered
            )

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    event_type = event.get("type")

                    if event_type == "system" and event.get("subtype") == "init":
                        self.session_started.emit(event.get("session_id", ""))

                    elif event_type == "assistant":
                        content = event.get("content", [])
                        for block in content:
                            if block.get("type") == "text":
                                self.token_received.emit(block.get("text", ""))

                except json.JSONDecodeError:
                    continue

            process.wait()
            if process.returncode != 0:
                stderr = process.stderr.read()
                self.error_occurred.emit(f"CLI error: {stderr}")

        except FileNotFoundError:
            self.error_occurred.emit(
                "Claude CLI not found. Please install it and run 'claude /login'."
            )
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.finished_signal.emit()
```

### SDK vs. Subprocess Comparison

| Aspect | Agent SDK | Subprocess |
|---|---|---|
| **Token streaming** | Native via `StreamEvent` | Via `--output-format stream-json` |
| **Custom tools (MCP)** | Full support, in-process | Not available (CLI-only tools) |
| **Session management** | `resume`, `fork_session` | `--resume` flag |
| **System prompt** | `system_prompt` option | `--append-system-prompt` flag |
| **Multi-turn in session** | `ClaudeSDKClient` persistent connection | New process per query (resume for continuity) |
| **Error handling** | Typed exceptions | Exit codes + stderr parsing |
| **Windows stability** | Known hang issues | More reliable (standard subprocess) |
| **Dependencies** | `claude-agent-sdk` + Node.js | Just `claude` CLI on PATH |
| **Performance** | Better (persistent process) | Startup cost per query |
| **Hooks** | Python-native hooks | Not available |

**Recommendation:** Start with the Agent SDK. Use the subprocess approach as a tested fallback, especially for Windows users who encounter the known hanging issue.

---

## 7. Context Injection

### The Three-Layer Guidance Model

Our worldbuilding tool uses three layers of context:
1. **Book quotes** -- authoritative source material
2. **Reference material** -- supplementary worldbuilding references
3. **Template instructions** -- step-specific procedural guidance

### Strategy 1: System Prompt (Recommended for Layer 3)

Template instructions belong in the system prompt because they define Claude's behavior for the current step.

```python
system_prompt = """You are a worldbuilding assistant for a fantasy world creation tool.

CURRENT STEP: Faction Creation
INSTRUCTIONS:
- Present exactly 3 options for each decision point
- Each option should include: name, brief description, and how it connects to existing world elements
- Flag any consistency issues with existing entities
- Use the query_knowledge_graph tool to check for related entities before suggesting new ones

TONE: Creative but grounded. Avoid cliches. Draw from the source material provided.
"""

options = ClaudeAgentOptions(
    system_prompt=system_prompt,
    include_partial_messages=True
)
```

### Strategy 2: Append to Claude Code Preset (Hybrid)

If you want Claude Code's built-in capabilities (file reading, code execution) plus your worldbuilding context:

```python
options = ClaudeAgentOptions(
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
        "append": """
        You are also acting as a worldbuilding assistant.
        When the user asks about their world, use the worldbuilding MCP tools.
        Follow the three-option pattern for all creative decisions.
        """
    }
)
```

### Strategy 3: User Message Prefilling (Recommended for Layers 1 and 2)

Book quotes and reference material change per entity/step and belong in the user message, not the system prompt.

```python
def build_context_message(step_context: dict) -> str:
    sections = []

    # Layer 1: Book quotes
    if step_context.get("book_quotes"):
        sections.append("=== SOURCE MATERIAL ===")
        for quote in step_context["book_quotes"]:
            sections.append(f'"{quote["text"]}" -- {quote["source"]}, p.{quote["page"]}')

    # Layer 2: Reference material
    if step_context.get("references"):
        sections.append("\n=== REFERENCE MATERIAL ===")
        for ref in step_context["references"]:
            sections.append(f"[{ref['title']}]: {ref['content']}")

    # Current entity state
    if step_context.get("entity_data"):
        sections.append("\n=== CURRENT ENTITY STATE ===")
        sections.append(json.dumps(step_context["entity_data"], indent=2))

    # The actual request
    sections.append(f"\n=== TASK ===")
    sections.append(step_context["task_prompt"])

    return "\n".join(sections)


# Usage
prompt = build_context_message({
    "book_quotes": [
        {"text": "The desert clans swore no oath they could not keep...",
         "source": "Chronicles of Ash", "page": 47}
    ],
    "references": [
        {"title": "Desert Cultures", "content": "Nomadic desert societies often..."}
    ],
    "entity_data": {"name": "Sand Covenant", "type": "faction", "territory": "Eastern Wastes"},
    "task_prompt": "Generate 3 possible founding myths for the Sand Covenant faction."
})
```

### Strategy 4: Tool Results as Context

Use the knowledge graph tool to dynamically inject context. Claude calls the tool, gets relevant world data, and incorporates it into its response.

```python
@tool(
    name="get_step_guidance",
    description="Retrieve the guidance material for the current worldbuilding step.",
    input_schema={
        "type": "object",
        "properties": {
            "step_name": {"type": "string"},
            "entity_type": {"type": "string"}
        },
        "required": ["step_name"]
    }
)
async def get_step_guidance(step_name: str, entity_type: str = None):
    """Returns the three-layer context for the requested step."""
    guidance = load_guidance(step_name, entity_type)
    return {
        "book_quotes": guidance.book_quotes,
        "reference_material": guidance.references,
        "template_instructions": guidance.instructions,
        "related_entities": guidance.related_entities
    }
```

This approach lets Claude request context on-demand rather than front-loading everything. It keeps token usage efficient for large worlds.

### Context Size Considerations

Claude has a large context window, but including the entire knowledge graph wastes tokens and money (if on API) or rate limits (if on subscription). Strategies:

- **Selective inclusion:** Only include entities related to the current step
- **Summarization:** For large worlds, summarize distant entities rather than including full details
- **Tool-based retrieval:** Let Claude query for specific entities as needed
- **Session resume:** Previous context is preserved in the session, no need to re-inject

### Recommended Context Architecture

```
System Prompt (persistent per step):
  - Role definition
  - Step-specific behavioral instructions (Layer 3)
  - Output format requirements

User Message (per query):
  - Book quotes relevant to this entity/step (Layer 1)
  - Reference material excerpts (Layer 2)
  - Current entity state (from our data model)
  - The specific task/question

Tools (on-demand):
  - Knowledge graph queries for related entities
  - Consistency checks
  - Step guidance retrieval
```

---

## 8. Recommendations

### Immediate Implementation Plan

1. **Install:** `pip install claude-agent-sdk` alongside PySide6
2. **Start with `query()` + QThread** (Approach B from Section 2) for the simplest working integration
3. **Enable `include_partial_messages=True`** for token-by-token streaming to the chat panel
4. **Use custom system prompt** for step-specific instructions
5. **Build the context injection** using the user-message approach (Strategy 3)
6. **Implement the subprocess fallback** (Section 6) as a safety net

### Phase 2 Enhancements

7. **Migrate to `ClaudeSDKClient`** for multi-turn sessions within a step
8. **Add custom MCP tools** for entity creation, consistency checking, knowledge graph queries
9. **Implement session persistence** -- save session IDs per entity/step for resume
10. **Add session forking** for "what-if" explorations

### Key Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Windows subprocess hang | Medium-High | Subprocess fallback (Section 6) |
| SDK API changes (pre-1.0) | Medium | Pin version, wrap in adapter layer |
| Subscription auth issues | Low | Clear error messages, check on startup |
| Token streaming latency | Low | Queue-based approach handles this well |
| Custom tools complexity | Medium | Start without tools, add incrementally |

### Architecture Sketch

```
+---------------------------+
|  PySide6 UI (Main Thread) |
|  +---------------------+  |
|  |   Chat Panel        |  |
|  |   (QTextEdit)       |  |   <-- token_received signal updates text
|  +---------------------+  |
|  +---------------------+  |
|  |   Step Controls     |  |
|  +---------------------+  |
+-------------|-------------+
              | Signal/Slot
+-------------|-------------+
|  AgentWorker (QThread)    |
|  +---------------------+  |
|  | asyncio event loop  |  |
|  | claude_agent_sdk    |  |   <-- async for message in query(...)
|  +---------------------+  |
+-------------|-------------+
              | stdin/stdout JSONL
+-------------|-------------+
|  Claude Code CLI          |
|  (bundled subprocess)     |   <-- Talks to Anthropic API
+---------------------------+
              | HTTPS
+---------------------------+
|  Anthropic API            |
|  (Claude model)           |
+---------------------------+
```

---

## 9. Sources

### Official Documentation
- [Claude Agent SDK -- PyPI](https://pypi.org/project/claude-agent-sdk/)
- [Claude Agent SDK -- GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- [Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Agent SDK Python Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Agent SDK Quickstart](https://platform.claude.com/docs/en/agent-sdk/quickstart)
- [Streaming Output](https://platform.claude.com/docs/en/agent-sdk/streaming-output)
- [Streaming vs. Single Mode](https://platform.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)
- [Session Management](https://platform.claude.com/docs/en/agent-sdk/sessions)
- [Modifying System Prompts](https://platform.claude.com/docs/en/agent-sdk/modifying-system-prompts)
- [Connect to External Tools with MCP](https://platform.claude.com/docs/en/agent-sdk/mcp)
- [Configure Permissions](https://platform.claude.com/docs/en/agent-sdk/permissions)
- [Run Claude Code Programmatically (Headless)](https://code.claude.com/docs/en/headless)

### Tutorials and Articles
- [Getting Started with the Claude Agent SDK -- KDnuggets](https://www.kdnuggets.com/getting-started-with-the-claude-agent-sdk)
- [Claude Agent SDK Tutorial -- DataCamp](https://www.datacamp.com/tutorial/how-to-use-claude-agent-sdk)
- [Getting Started with Anthropic Claude Agent SDK -- Medium](https://medium.com/@aiablog/getting-started-with-anthropic-claude-agent-sdk-python-826a2216381d)
- [Building Agents with the Claude Agent SDK -- Anthropic Engineering](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [The Complete Guide to Building Agents with the Claude Agent SDK -- Nader Dabit](https://nader.substack.com/p/the-complete-guide-to-building-agents)
- [Inside the Claude Agent SDK: From stdin/stdout to Production](https://buildwithaws.substack.com/p/inside-the-claude-agent-sdk-from)
- [Claude Agent SDK Python Learning Guide](https://redreamality.com/blog/claude-agent-sdk-python-/)

### Qt/Asyncio Integration
- [qasync -- PyPI](https://pypi.org/project/qasync/)
- [qasync -- GitHub](https://github.com/CabbageDevelopment/qasync)
- [PySide6.QtAsyncio -- Official Qt Docs](https://doc.qt.io/qtforpython-6/PySide6/QtAsyncio/index.html)
- [qtinter -- GitHub](https://github.com/fancidev/qtinter)

### Known Issues
- [ClaudeSDKClient hangs on Windows -- Issue #208](https://github.com/anthropics/claude-agent-sdk-python/issues/208)
- [Documentation inconsistency: SDK requires API key but CLI uses subscription -- Issue #5891](https://github.com/anthropics/claude-code/issues/5891)
- [SSE MCP server disconnection crashes session -- Issue #18557](https://github.com/anthropics/claude-code/issues/18557)
- [Streaming support in TextBlock -- Issue #164](https://github.com/anthropics/claude-agent-sdk-python/issues/164)

### Error Handling
- [Error Handling Documentation -- Tessl Registry](https://tessl.io/registry/tessl/pypi-claude-agent-sdk/0.1.1/files/docs/error-handling.md)
- [Anthropic API Errors](https://docs.claude.com/en/api/errors)

---

*This report was compiled on 2026-01-30. The Claude Agent SDK is pre-1.0 (v0.1.26) and APIs may change. All code examples should be validated against the current SDK version before production use.*
