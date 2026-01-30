# Orchestration Research: Keeping Claude Code On-Task for Complex Projects

**Research Date:** January 30, 2026
**Focus:** Practical systems for managing a worldbuilding project with 52 progression steps, 84 templates, and 16 reference databases with heavy cross-referencing.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Project Orchestration Systems](#1-project-orchestration-systems-for-claude-code)
3. [Hook-Based Task Enforcement](#2-hook-based-task-enforcement)
4. [Context Injection Strategies](#3-context-injection-strategies)
5. [Multi-Agent Orchestration](#4-multi-agent-orchestration)
6. [Knowledge Graph Integration](#5-knowledge-graph-integration)
7. [The Memory Bank Pattern](#6-the-memory-bank-pattern)
8. [Competing IDE Approaches](#7-competing-ide-approaches-cursor-windsurf-etc)
9. [Custom System Prompt Injection](#8-custom-system-prompt-injection-via-hooks)
10. [Recommended Architecture for This Project](#recommended-architecture-for-this-project)
11. [Sources](#sources)

---

## Executive Summary

The Claude Code ecosystem has matured significantly through late 2025 and into 2026. For a massive worldbuilding project with deep cross-references, the most practical approach combines several layers:

- **CLAUDE.md hierarchy** for static project rules and structure (built-in, zero setup)
- **Hooks** for dynamic context injection and task enforcement (built-in since mid-2025)
- **MCP Memory Server** for persistent state across sessions (lightweight setup)
- **Knowledge Graph MCP** for entity/relationship tracking (moderate setup)
- **Task Tool / SubagentStop** for delegating and quality-gating sub-tasks (built-in)

Multi-agent orchestration frameworks like Claude-Flow exist but are overkill unless you need 10+ agents working on different codebases simultaneously. For a single complex project, the built-in tools plus 1-2 MCP servers will get you further with less complexity.

---

## 1. Project Orchestration Systems for Claude Code

### What Exists

**A. Claude Code's Built-in Task Tool**
Claude Code can natively spawn sub-agents (separate Claude instances) that work independently on delegated tasks and return results. This is the simplest orchestration -- no external framework needed.

- Sub-agents get their own context window (no pollution from the parent)
- Can run in parallel or sequence
- Parent agent receives results and continues
- SubagentStop hooks can enforce quality gates before accepting results

**B. Claude-Flow (Third-Party Framework)**
The most mature external orchestration platform. Key capabilities:
- 54+ specialized agents across 8 categories
- 6 swarm coordination topologies (mesh, pipeline, competitive, supervisor, etc.)
- SQLite-based persistent memory across sessions
- 3-tier model routing (saves ~75% on API costs by routing simple tasks to cheaper models)
- MCP protocol integration so it works inside Claude Code sessions

Installation:
```bash
npm install -g claude-flow@alpha
claude-flow init
export ANTHROPIC_API_KEY="your-key"
claude-flow orchestrate "your task" --agents 3 --parallel
```

**Verdict for this project:** Claude-Flow is designed for software engineering teams running microservices. For a single worldbuilding project, it adds more complexity than value. The built-in Task Tool plus hooks is the right starting point. If you later need specialized agents (e.g., one for lore consistency, one for template generation, one for cross-reference validation), revisit Claude-Flow.

**C. Oh My Claude Code (OMC)**
32 specialized agents and 40 skills with a "zero learning curve" setup (similar to oh-my-zsh). More approachable than Claude-Flow but still primarily aimed at software development workflows.

**D. Task Orchestration MCP Skill**
An MCP server that provides task management with dependency tracking, status progression, and cascading completion events. This is closer to what you need -- it can model your 52 progression steps as a task graph with dependencies.

### What Claude Code Can Set Up Itself
- CLAUDE.md files and the entire `.claude/` directory structure
- Hook configurations in `.claude/settings.json`
- Custom slash commands for common workflows

### What Needs Manual Intervention
- Installing Node.js/npm if not present
- Running `npm install -g` for external packages
- Setting API keys as environment variables
- Installing and configuring MCP servers (Claude can generate the config, but you run the install commands)

---

## 2. Hook-Based Task Enforcement

Hooks are the most powerful practical tool for keeping Claude on-task. They are shell commands that fire at specific lifecycle events and provide **deterministic** control -- unlike prompt instructions which Claude can "forget," hooks are guaranteed to execute.

### Available Hook Events

| Event | When It Fires | Use For |
|-------|--------------|---------|
| `SessionStart` | Session begins | Load project state, current step, recent changes |
| `UserPromptSubmit` | Before Claude processes your prompt | Inject context, enforce rules, append reminders |
| `PreToolUse` | Before Claude executes a tool | Block dangerous operations, validate file paths |
| `PostToolUse` | After a tool executes | Log changes, update state, trigger validation |
| `Stop` | When Claude tries to finish | Verify task completion before allowing stop |
| `SubagentStop` | When a sub-agent tries to finish | Quality-gate sub-agent output |
| `PreCompact` | Before context compaction | Save important state before memory is compressed |
| `SessionEnd` | Session ends | Persist state, generate summary |

### Practical Enforcement Patterns

**Pattern 1: The Step Enforcer**
Inject the current progression step and its requirements on every prompt:

```json
// .claude/settings.json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "command": "python inject-step-context.py",
        "description": "Injects current worldbuilding step context"
      }
    ]
  }
}
```

The script reads your current step from a state file and outputs the relevant requirements, constraints, and cross-references as plain text to stdout. Claude receives this alongside every prompt.

**Pattern 2: The Completion Gate**
Prevent Claude from stopping until a checklist is verified:

```json
{
  "hooks": {
    "Stop": [
      {
        "command": "python check-completion.py",
        "description": "Verify all task requirements met before stopping"
      }
    ]
  }
}
```

If the script exits with code 2, Claude is blocked from stopping and receives the error message explaining what remains incomplete.

**Pattern 3: The Cross-Reference Validator**
After any file write, check for cross-reference consistency:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "command": "python validate-crossrefs.py",
        "description": "Check cross-reference integrity after file changes"
      }
    ]
  }
}
```

**Pattern 4: Input Modification (v2.0.10+)**
PreToolUse hooks can now modify tool inputs before execution. Instead of blocking and forcing retries, hooks can transparently correct parameters:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "command": "python enforce-template-format.py",
        "description": "Ensure file writes follow template conventions"
      }
    ]
  }
}
```

### Key Insight
"Prompts are great for suggestions; hooks are guarantees." For a project where consistency across 84 templates matters, hooks provide the deterministic enforcement that prompt-based instructions cannot.

### Known Issues
- A bug was reported (Dec 2025, GitHub issue #14281) where `additionalContext` from hooks can be injected multiple times. Monitor this if using JSON-structured context injection.
- SubagentStop hooks can cause infinite loops if the acceptance criteria are too strict or ambiguous. Always include a maximum retry count or escape condition.

---

## 3. Context Injection Strategies

### The Core Problem
Your project has ~152 interconnected elements (52 steps + 84 templates + 16 databases). Claude's 200K token context window is large but not infinite. You cannot dump everything in at once. The solution is **strategic, just-in-time context loading**.

### Strategy A: Hierarchical CLAUDE.md (Zero Setup, Immediate Use)

Claude Code's built-in memory system loads CLAUDE.md files automatically at session start:

```
~/.claude/CLAUDE.md                          # Global preferences
C:\Worldbuilding-Interactive-Program\CLAUDE.md      # Project overview + architecture
C:\Worldbuilding-Interactive-Program\.claude\rules\  # Modular rule files
    consistency-rules.md
    template-standards.md
    cross-reference-guide.md
    progression-sequence.md
```

CLAUDE.md files support `@path/to/import` syntax for pulling in additional files. This lets you keep the root CLAUDE.md lean (~150 lines of critical rules) while importing detailed specs on demand.

**Best practice:** Keep core memory files under 500 lines total. They consume context window on every session start.

### Strategy B: Hook-Based Dynamic Context (Recommended for This Project)

Use `UserPromptSubmit` hooks to inject only the context relevant to the current task:

```python
#!/usr/bin/env python3
# inject-context.py -- called on every user prompt
import sys, json, os

# Read the user's prompt from stdin
input_data = json.loads(sys.stdin.read())
prompt = input_data.get("prompt", "").lower()

# Load current project state
state = json.load(open("project-state.json"))
current_step = state["current_step"]

# Always inject: current step info
step_info = load_step(current_step)
print(f"[PROJECT STATE] Current step: {current_step}/52")
print(f"[STEP REQUIREMENTS] {step_info['requirements']}")

# Conditionally inject based on keywords in prompt
if any(word in prompt for word in ["template", "format", "structure"]):
    print(f"[RELEVANT TEMPLATES] {get_related_templates(current_step)}")

if any(word in prompt for word in ["reference", "database", "lookup"]):
    print(f"[RELEVANT DATABASES] {get_related_databases(current_step)}")

# Inject cross-references for any mentioned entities
entities = extract_entity_mentions(prompt, state["entity_index"])
for entity in entities:
    print(f"[CROSS-REF: {entity}] {get_cross_references(entity)}")
```

This approach gives Claude exactly what it needs without flooding the context window.

### Strategy C: Two-Tier Memory Architecture

The most sophisticated proven pattern uses two layers:

- **Tier 1: CLAUDE.md** (~150 lines) -- auto-generated compact briefing loaded on every session start. Contains project overview, current state, critical constraints.
- **Tier 2: Full State Store** (`.memory/state.json` or SQLite) -- complete memory with every fact, decision, and observation. Accessed mid-conversation through MCP tools (keyword search, tag queries, natural language questions).

This is implemented by the `memory-mcp` project, which uses Claude Code hooks to:
1. Observe the session from the outside
2. Process observations in the background
3. Inject context at the right time

Setup:
```bash
claude mcp add memory-keeper npx mcp-memory-keeper
```
Data persists in `~/mcp-data/memory-keeper/` across sessions.

### Strategy D: Subagent-Based Context Exploration

For complex queries that touch many parts of the project, use Claude's built-in Task tool to spawn sub-agents that gather specific context before the main agent proceeds:

> "Before working on Step 23, use subagents to:
> 1. Summarize all templates that reference elements created in Steps 20-22
> 2. List all database entries that will be affected
> 3. Identify any cross-reference conflicts"

This keeps the main agent's context clean while still accessing deep project knowledge.

### Strategy E: Compaction-Aware Checkpointing

Long sessions inevitably require compaction (context summarization). Use the `PreCompact` hook to save critical state before it gets compressed:

```json
{
  "hooks": {
    "PreCompact": [
      {
        "command": "python save-checkpoint.py",
        "description": "Save critical project state before context compaction"
      }
    ]
  }
}
```

Monitor with `/cost` -- when over 50K tokens, expect compaction. Before changing major topics, use `/clear` to start fresh with a clean context load.

---

## 4. Multi-Agent Orchestration

### Anthropic's Own Research Pattern

Anthropic's internal multi-agent research system uses an **orchestrator-worker pattern**:
- Lead agent (Claude Opus) analyzes the task and develops strategy
- Spawns specialized sub-agents (Claude Sonnet) to explore different aspects in parallel
- Lead agent synthesizes results

This pattern outperformed single-agent Claude Opus by **90.2%** on Anthropic's internal research eval. The key insight: isolated context windows prevent "context rot" where unrelated information degrades performance.

### Built-in TeammateTool / Task System

Claude Code includes native support for multi-agent patterns:

- **Swarm**: One orchestrator, multiple interchangeable workers. Leader creates tasks, workers self-assign from queue, leader monitors.
- **Pipeline**: Agent A -> Agent B -> Agent C, sequential with handoffs.
- **Competitive**: Multiple agents attempt same task, leader picks best result.
- **Supervisor**: Worker does task, watcher monitors, watcher can trigger rollback.

For your worldbuilding project, the **Pipeline** pattern maps naturally to progression steps, while the **Supervisor** pattern is ideal for cross-reference validation.

### Practical Multi-Agent Setup (No External Framework)

You can orchestrate multiple Claude instances using only built-in features:

1. **Manager Agent**: Has CLAUDE.md with the full progression map and cross-reference index. Delegates individual steps to worker agents via the Task tool.

2. **Worker Agents**: Each receives a focused brief -- one step's requirements, relevant templates, and the specific databases needed. Works in isolation, returns results.

3. **Validator Agent**: Spawned via SubagentStop hook. Checks the worker's output against cross-reference rules before the manager accepts it.

This is available today with zero external dependencies.

### External Frameworks (If Needed Later)

- **Claude-Flow**: Most mature. `npm install -g claude-flow@alpha`. Best for 10+ agents across multiple codebases. SQLite persistence, 6 topologies, MCP integration.
- **CLI Agent Orchestrator (CAO)**: AWS open-source. Supervisor coordinates worker agents with project context.
- **Claude Code Agentrooms**: Open-source, uses @mentions to route tasks to specialized agents.

---

## 5. Knowledge Graph Integration

This is the most directly relevant technology for your project's 16 reference databases and heavy cross-referencing.

### Option A: Official Knowledge Graph Memory Server (Recommended Starting Point)

Anthropic's own MCP server for persistent memory via knowledge graph.

**Data Model:**
- **Entities**: Primary nodes with unique name and type (e.g., "Arcane Academy" / location, "Fire Magic" / magic_system)
- **Observations**: Atomic facts about entities (e.g., "Founded in the Third Era", "Requires attunement to flame crystals")
- **Relations**: Directed connections (e.g., "Arcane Academy" --TEACHES--> "Fire Magic")

**Setup:**
```bash
claude mcp add knowledge-graph npx @anthropic/mcp-knowledge-graph
```

**Available Tools:**
- `create_entities` -- batch create entities with types
- `create_relations` -- create directed relationships between entities
- `add_observations` -- attach facts to entities
- `search_nodes` -- search across names, types, and observations
- `read_graph` -- read the entire knowledge graph
- `open_nodes` -- retrieve specific entities by name

**For Your Project:**
You could model each of your 16 databases as entity types, with relations capturing cross-references. When Claude mentions an entity, a hook can automatically query the knowledge graph and inject relevant connections.

### Option B: Neo4j-Based Knowledge Graph (For Scale)

If the official server feels limited (it stores in a local JSONL file), a Neo4j-based approach provides:
- True graph database performance for complex queries
- Visual exploration of relationships
- Cypher query language for sophisticated cross-reference searches
- Relationship types like MODIFIES, MENTIONS, IMPLEMENTS, DECIDES

Setup requires running Neo4j (Docker is easiest):
```bash
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 neo4j
claude mcp add neo4j-memory npx @neo4j/mcp-server
```

**For Your Project:** Neo4j is the better choice if your 16 databases have complex multi-hop relationships (e.g., "What magic systems are taught at institutions founded during eras when this political faction was in power?"). The JSONL-based official server handles simple lookups well but struggles with graph traversals.

### Option C: Arc Memory Temporal Knowledge Graph

Tracks entities with temporal context and provenance -- useful if your worldbuilding has historical eras where relationships change over time. Relationships include temporal metadata showing when they were valid.

### Practical Integration Pattern

Combine a knowledge graph MCP with a `UserPromptSubmit` hook:

```python
# When the user mentions entities, auto-query the knowledge graph
# and inject the relevant context
entities = extract_entities_from_prompt(user_prompt)
for entity in entities:
    relations = query_knowledge_graph(entity)
    print(f"[KNOWLEDGE GRAPH] {entity}: {relations}")
```

This makes Claude automatically aware of cross-references without you manually specifying them.

---

## 6. The Memory Bank Pattern

### Origin and Evolution

The Memory Bank pattern originated in the Cline ecosystem and has been adapted for Claude Code. The core insight: instead of losing project context between sessions, maintain structured memory banks that persist and evolve with your project.

### Implementation 1: hudrazine/claude-code-memory-bank

Adapted from Cline's Memory Bank methodology for Claude Code.

**Core Files:**
```
.memory-bank/
    projectbrief.md          # Foundation document
    productContext.md         # Why the project exists, problems it solves
    systemPatterns.md         # Architecture and design patterns
    techContext.md            # Technical decisions and constraints
    activeContext.md          # Current work focus, recent changes
    progress.md              # What works, what doesn't, what's next
```

**How It Works:**
1. At session start, Claude reads the memory bank files
2. During work, Claude updates `activeContext.md` and `progress.md`
3. At session end (or on command), Claude updates all relevant memory files
4. Next session starts with full project awareness

**For Your Project:** You would adapt this structure:
```
.memory-bank/
    worldbrief.md             # Project overview
    progression-state.md      # Current step (X/52), completed steps, blockers
    template-registry.md      # 84 templates with status and cross-refs
    database-index.md         # 16 databases with summaries and links
    active-work.md            # What's being worked on right now
    decisions-log.md          # Worldbuilding decisions and rationale
    cross-reference-map.md    # Key entity relationships
```

### Implementation 2: russbeye/claude-memory-bank

More sophisticated -- includes specialized agents for code searching, memory synchronization, and context analysis. Transforms Claude from a stateless assistant into a persistent development partner.

### Implementation 3: memory-mcp (Automated Approach)

Uses Claude Code hooks to automatically capture what matters during sessions:
- `Stop` hook: after every Claude response, silently extract and store important context
- `PreCompact` hook: before context compression, save critical state
- `SessionEnd` hook: generate session summary

This is the most hands-off approach -- memory management happens automatically rather than requiring explicit "update memory" commands.

### Effectiveness Assessment

Based on community reports:
- **Strengths**: Dramatic improvement in session-to-session continuity. Projects that previously required 15 minutes of re-orientation now pick up in seconds.
- **Limitations**: Memory files consume context window space. For a project with 152 elements, you cannot store everything in memory bank files -- you need selective loading (see Strategy B in Context Injection above).
- **Best practice**: Keep memory bank files lean. Use them as an index/summary layer, with detailed content loaded on demand via MCP tools or hook-based injection.

---

## 7. Competing IDE Approaches (Cursor, Windsurf, etc.)

### Cursor
- **Approach**: Manual context curation via @ symbols to reference specific files/folders
- **Effective context**: ~10K-50K tokens in practice
- **Strength**: Precision -- you control exactly what the AI sees
- **Weakness**: Manual overhead scales poorly with project complexity
- **Borrowable idea**: The @ symbol reference system is elegant. Claude Code's `@path/to/import` in CLAUDE.md files serves a similar purpose.

### Windsurf
- **Approach**: Automatic RAG-based context selection via "Cascade" technology
- **Effective context**: ~200K tokens with automatic selection
- **Strength**: No manual curation needed; handles large codebases automatically
- **Key innovation**: **Codemaps** -- AI-annotated visual maps of code structure with line-level linking
- **Key innovation**: **SWE-grep** -- specialized models for context retrieval that are 10x faster than frontier models while maintaining accuracy
- **Borrowable idea**: Automatic context selection based on what's being discussed. This is exactly what a `UserPromptSubmit` hook can do for Claude Code -- analyze the prompt, determine relevant files/databases, inject them.

### What We Can Borrow for Claude Code

1. **Auto-indexing**: Build a project index (entity names -> file locations, cross-references) that a hook can query on every prompt. Windsurf does this automatically; we build it once and maintain it.

2. **Relevance scoring**: When injecting context, rank elements by relevance to the current prompt. Don't inject everything -- inject the top 5-10 most relevant items. Windsurf's RAG does this; we can approximate it with keyword matching or embedding similarity.

3. **Visual maps**: Windsurf's Codemaps concept could be adapted -- maintain a visual/textual map of your worldbuilding project structure that Claude can reference to understand how elements connect.

4. **Progressive disclosure**: Start with high-level context, drill into details only when needed. This is Claude Code's "just-in-time" philosophy -- maintain lightweight identifiers (file paths, entity names) and load full content only when referenced.

---

## 8. Custom System Prompt Injection via Hooks

### Can Hooks Inject System-Level Instructions?

Yes. The `UserPromptSubmit` hook injects content that Claude treats as authoritative context alongside the user's prompt. While it is technically "user-level" rather than "system-level" in the API sense, the practical effect is the same -- Claude follows these instructions consistently.

### Dynamic System Prompt Based on Project State

```python
#!/usr/bin/env python3
# dynamic-system-prompt.py
import json, sys

state = json.load(open("C:/Worldbuilding-Interactive-Program/project-state.json"))
step = state["current_step"]
phase = state["current_phase"]

# Output rules that change based on project state
print(f"""
[SYSTEM CONTEXT - WORLDBUILDING PROJECT]
Current Phase: {phase}
Current Step: {step}/52
Completed Steps: {', '.join(str(s) for s in state['completed_steps'])}

ACTIVE RULES FOR THIS PHASE:
""")

# Phase-specific rules
if phase == "foundation":
    print("- Do NOT reference elements from later phases")
    print("- All new entities must be added to the foundation database")
    print("- Template format: use foundation-template-v2")
elif phase == "expansion":
    print("- Cross-reference ALL new elements against foundation entries")
    print("- Flag any contradictions with existing lore")
    print("- Template format: use expansion-template-v1")
elif phase == "refinement":
    print("- No new entities without explicit approval")
    print("- Focus on consistency and gap-filling")
    print("- Run cross-reference validation after every change")

# Always inject cross-reference reminders
print(f"\nENTITIES MODIFIED THIS SESSION: {state.get('session_entities', [])}")
print(f"PENDING CROSS-REFERENCES: {state.get('pending_xrefs', [])}")
```

### Configuration

```json
// .claude/settings.json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/dynamic-system-prompt.py",
        "description": "Inject phase-aware project rules"
      }
    ],
    "SessionStart": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/load-session.py",
        "description": "Load project state and recent history at session start"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "command": "python C:/Worldbuilding-Interactive-Program/validate-and-update.py",
        "description": "Validate cross-refs and update state after file changes"
      }
    ],
    "Stop": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/check-completion.py",
        "description": "Verify step requirements before allowing session to end"
      }
    ],
    "PreCompact": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/save-checkpoint.py",
        "description": "Checkpoint critical state before context compaction"
      }
    ]
  }
}
```

---

## Recommended Architecture for This Project

Based on all research, here is the practical, layered architecture for managing your worldbuilding project:

### Layer 1: Static Foundation (CLAUDE.md + Rules)
**Setup time:** 30 minutes | **Complexity:** Zero | **Claude can set this up:** Yes

```
C:\Worldbuilding-Interactive-Program\
    CLAUDE.md                           # ~100 lines: project overview, core rules
    .claude\
        settings.json                   # Hook configurations
        settings.local.json             # Personal preferences (gitignored)
        rules\
            consistency-rules.md        # Cross-reference consistency rules
            template-standards.md       # Template format requirements
            progression-sequence.md     # Step ordering and dependencies
```

### Layer 2: Dynamic Context Injection (Hooks)
**Setup time:** 2-3 hours | **Complexity:** Low-Medium | **Claude can set this up:** Mostly (writes the scripts; you configure settings.json)

- `SessionStart`: Load current step, recent changes, session summary
- `UserPromptSubmit`: Analyze prompt keywords, inject relevant templates/databases/cross-refs
- `PostToolUse`: Validate cross-references after file changes, update state
- `Stop`: Verify step checklist before allowing completion
- `PreCompact`: Checkpoint state before context compression

### Layer 3: Persistent Memory (MCP Server)
**Setup time:** 1 hour | **Complexity:** Low | **Manual setup required:** Running npm install

Pick ONE:
- **MCP Memory Keeper** (simplest): `claude mcp add memory-keeper npx mcp-memory-keeper`
  - SQLite with WAL mode, knowledge graph extraction, semantic search
  - Data in `~/mcp-data/memory-keeper/`

- **SaveContext** (most features for session management): Provides 52 MCP tools for context management including session lifecycle, checkpoints, and plan management.

### Layer 4: Knowledge Graph (MCP Server)
**Setup time:** 1-2 hours | **Complexity:** Medium | **Manual setup required:** Running npm install

For 16 databases with cross-references, this is essential:
- **Start with**: Official Knowledge Graph Memory Server (`npx @anthropic/mcp-knowledge-graph`)
- **Scale to**: Neo4j-based server if you need complex multi-hop queries

Model your worldbuilding entities, observations, and relations. Use hooks to auto-query on entity mentions.

### Layer 5: Quality Gates (SubagentStop + Stop Hooks)
**Setup time:** 1-2 hours | **Complexity:** Medium | **Claude can set this up:** Yes (writes the validation scripts)

- Stop hooks verify checklist completion
- SubagentStop hooks validate worker output against cross-reference rules
- Prompt-based evaluation hooks use an LLM to judge quality (not just script-based checks)

### What to Skip (For Now)

- **Claude-Flow / OMC**: Overkill for a single project. Revisit if you need 5+ specialized agents.
- **Neo4j**: Start with the JSONL-based knowledge graph. Upgrade to Neo4j only if query complexity demands it.
- **Full multi-agent swarms**: Start with the built-in Task tool for delegation. The manager/worker pattern works with zero external dependencies.

### Implementation Order

1. **Week 1**: Set up CLAUDE.md hierarchy and basic hooks (SessionStart, UserPromptSubmit)
2. **Week 2**: Add MCP Memory Keeper for persistent state across sessions
3. **Week 3**: Add Knowledge Graph MCP, begin populating entities/relations from your 16 databases
4. **Week 4**: Add quality gate hooks (Stop, SubagentStop, PostToolUse validation)
5. **Ongoing**: Refine context injection scripts as you learn which information Claude needs most often

---

## Key Takeaways

1. **Hooks are the foundation.** They provide deterministic enforcement that prompt instructions cannot match. Every rule you care about should be a hook, not just a CLAUDE.md line.

2. **Context engineering beats context dumping.** Load only what is relevant to the current task. Use keyword matching, entity extraction, or step-based filtering to inject the right 5-10% of your project, not all of it.

3. **Two-tier memory works.** Compact summary (CLAUDE.md) for every-session awareness, plus deep store (MCP/knowledge graph) for on-demand retrieval. This is the proven pattern across multiple community implementations.

4. **Sub-agents prevent context rot.** Anthropic's own research shows 90%+ improvement when using orchestrator-worker patterns. For your project, delegate individual steps to sub-agents with focused briefs rather than having one long session try to hold everything.

5. **Start simple, add complexity only when needed.** CLAUDE.md + hooks + one MCP server covers 90% of use cases. Add more infrastructure only when you hit specific limitations.

---

## Sources

### Official Anthropic Documentation
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Memory Management](https://code.claude.com/docs/en/memory)
- [Create Custom Subagents](https://code.claude.com/docs/en/sub-agents)
- [How to Configure Hooks (Anthropic Blog)](https://claude.com/blog/how-to-configure-hooks)
- [How Anthropic Built Their Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Claude Code Best Practices for Agentic Coding](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Advanced Tool Use (Anthropic Engineering)](https://www.anthropic.com/engineering/advanced-tool-use)

### Frameworks and Tools
- [Claude-Flow (GitHub)](https://github.com/ruvnet/claude-flow) -- Multi-agent orchestration platform
- [Claude-Flow Installation Guide](https://github.com/ruvnet/claude-flow/wiki/Installation-Guide)
- [Claude Code Hooks Mastery (GitHub)](https://github.com/disler/claude-code-hooks-mastery)
- [BMAD Context Injection (GitHub)](https://github.com/darraghh1/bmad-context-injection)
- [Continuous-Claude-v3 (GitHub)](https://github.com/parcadei/Continuous-Claude-v3)
- [Awesome Claude Code (GitHub)](https://github.com/hesreallyhim/awesome-claude-code)
- [wshobson/agents (GitHub)](https://github.com/wshobson/agents)
- [Claude Code Agentrooms](https://claudecode.run)

### Memory and Persistence
- [claude-memory-bank by russbeye (GitHub)](https://github.com/russbeye/claude-memory-bank)
- [claude-code-memory-bank by hudrazine (GitHub)](https://github.com/hudrazine/claude-code-memory-bank)
- [MCP Memory Keeper (GitHub)](https://github.com/mkreyman/mcp-memory-keeper)
- [MCP Memory Service by doobidoo (GitHub)](https://github.com/doobidoo/mcp-memory-service)
- [SaveContext by Greenfield Labs (GitHub)](https://github.com/greenfieldlabs-inc/savecontext)
- [Claude-Mem Hooks Architecture](https://docs.claude-mem.ai/hooks-architecture)
- [Architecture of Persistent Memory for Claude Code (DEV)](https://dev.to/suede/the-architecture-of-persistent-memory-for-claude-code-17d)
- [Fixing Concurrent Session Problem with SQLite WAL (DEV)](https://dev.to/daichikudo/fixing-claude-codes-concurrent-session-problem-implementing-memory-mcp-with-sqlite-wal-mode-o7k)

### Knowledge Graphs
- [MCP Knowledge Graph (GitHub)](https://github.com/shaneholloman/mcp-knowledge-graph)
- [Knowledge Graph Memory Server (Anthropic)](https://www.pulsemcp.com/servers/modelcontextprotocol-knowledge-graph-memory)
- [Building Knowledge Graphs with Claude and Neo4j (Neo4j Blog)](https://neo4j.com/blog/developer/knowledge-graphs-claude-neo4j-mcp/)
- [Arc Memory Temporal Knowledge Graph](https://playbooks.com/mcp/arc-memory-temporal-knowledge-graph)

### Context Engineering
- [4 Context Engineering Secrets for Claude Code](https://kane.mx/posts/2025/context-engineering-secrets-claude-code/)
- [Context Engineering for Claude Code (Substack)](https://thomaslandgraf.substack.com/p/context-engineering-for-claude-code)
- [Context Engineering Intro (GitHub)](https://github.com/coleam00/context-engineering-intro)
- [Context and Memory Management in Claude Code](https://angelo-lima.fr/en/claude-code-context-memory-management/)
- [Claude Code Context Optimization -- 54% Token Reduction (GitHub Gist)](https://gist.github.com/johnlindquist/849b813e76039a908d962b2f0923dc9a)

### Multi-Agent Patterns
- [Claude Code Swarm Orchestration Skill (GitHub Gist)](https://gist.github.com/kieranklaassen/4f2aba89594a4aea4ad64d753984b2ea)
- [Multi-Agent Orchestration: 10+ Claude Instances in Parallel (DEV)](https://dev.to/bredmond1019/multi-agent-orchestration-running-10-claude-instances-in-parallel-part-3-29da)
- [The Task Tool: Claude Code's Agent Orchestration System (DEV)](https://dev.to/bhaidar/the-task-tool-claude-codes-agent-orchestration-system-4bf2)
- [The 3 Amigo Agents Pattern (Medium)](https://medium.com/@george.vetticaden/the-3-amigo-agents-the-claude-code-development-pattern-i-discovered-while-implementing-anthropics-67b392ab4e3f)
- [Oh My Claude Code Review (Medium)](https://medium.com/@joe.njenga/i-tested-oh-my-claude-code-the-only-agents-swarm-orchestration-you-need-7338ad92c00f)
- [Claude Code Frameworks & Sub-Agents Engineering Guide (Dec 2025)](https://www.medianeth.dev/blog/claude-code-frameworks-subagents-2025)
- [AWS CLI Agent Orchestrator](https://aws.amazon.com/blogs/opensource/introducing-cli-agent-orchestrator-transforming-developer-cli-tools-into-a-multi-agent-powerhouse/)
- [Task Orchestration MCP Skill](https://mcpmarket.com/tools/skills/task-orchestration-2)

### IDE Comparisons
- [Best AI Code Editor: Cursor vs Windsurf vs Replit (2026)](https://research.aimultiple.com/ai-code-editor/)
- [Claude Code vs Cursor Deep Comparison (Qodo)](https://www.qodo.ai/blog/claude-code-vs-cursor/)
- [Windsurf vs Cursor (Builder.io)](https://www.builder.io/blog/windsurf-vs-cursor)
- [Cursor vs Windsurf vs Claude Code (2025)](https://amirteymoori.com/cursor-vs-windsurf-vs-claude-code-which-ai-coding-tool-should-you-choose-in-2025/)

### Hooks Deep Dives
- [Claude Code Hook Control Flow (Steve Kinney)](https://stevekinney.com/courses/ai-development/claude-code-hook-control-flow)
- [Claude Code Hooks Practical Guide (DataCamp)](https://www.datacamp.com/tutorial/claude-code-hooks)
- [Configure Claude Code Hooks (Gend.co)](https://www.gend.co/blog/configure-claude-code-hooks-automation)
- [End-of-Turn Quality Gates (Dev Genius)](https://blog.devgenius.io/claude-code-use-hooks-to-enforce-end-of-turn-quality-gates-5bed84e89a0d)
- [ClaudeLog Hooks Guide](https://claudelog.com/mechanics/hooks/)
- [Claude Code Best Practices: Memory Management (Medium)](https://medium.com/@codecentrevibe/claude-code-best-practices-memory-management-7bc291a87215)
