# Claude Code Persistent Memory: State of the Art (January 2026)

This document summarizes every known approach for giving Claude Code persistent memory across sessions and surviving context compaction. It is written for a non-technical user; where possible, it notes what Claude Code itself can set up for you if you simply ask it.

---

## Table of Contents

1. [The Core Problem](#the-core-problem)
2. [Built-in Memory: CLAUDE.md Files](#built-in-memory-claudemd-files)
3. [The /init and /memory Commands](#the-init-and-memory-commands)
4. [The .claude/rules/ Directory](#the-clauderules-directory)
5. [What Happens During Context Compaction](#what-happens-during-context-compaction)
6. [MCP Memory Servers](#mcp-memory-servers)
7. [Hook-Based Automatic Memory Systems](#hook-based-automatic-memory-systems)
8. [File-Based Memory Strategies (Manual)](#file-based-memory-strategies-manual)
9. [Community "Unlimited Memory" Projects](#community-unlimited-memory-projects)
10. [Recommended Setup for This Project](#recommended-setup-for-this-project)
11. [Sources](#sources)

---

## The Core Problem

Claude Code starts every session with zero memory. It does not remember previous sessions, previous work, or anything you discussed before. Every new session is like talking to a brand-new colleague who has never seen your project.

Additionally, within a single session, if the conversation gets too long, Claude Code performs "context compaction" -- it summarizes older parts of the conversation to free up space. This can lose important details from earlier in the session.

The entire memory ecosystem exists to solve these two problems:
- **Between-session amnesia**: Claude forgets everything when you close and reopen it.
- **Within-session compaction**: Claude loses details from earlier in a long conversation.

---

## Built-in Memory: CLAUDE.md Files

This is Claude Code's official, built-in memory system. It is simple, file-based, and requires no external tools.

### How It Works

Claude Code automatically reads files named `CLAUDE.md` at the start of every session. Whatever is written in those files becomes part of Claude's initial knowledge. Think of it as a briefing document that Claude reads before you start talking.

### The Memory Hierarchy (All Loaded Automatically)

Claude Code checks for memory files at four levels. All levels combine -- they do not replace each other:

| Level | File Location | Purpose | Shared? |
|-------|--------------|---------|---------|
| **Global** | `~/.claude/CLAUDE.md` | Your personal preferences across ALL projects | Private to you |
| **Project** | `./CLAUDE.md` (project root) | Team-shared project knowledge | Committed to git, shared with team |
| **Project (alt location)** | `./.claude/CLAUDE.md` | Same as above, alternative path | Committed to git, shared with team |
| **Local/Private** | `./CLAUDE.local.md` | Your personal project preferences | Auto-added to .gitignore, private |

Claude also reads CLAUDE.md files in subdirectories, but only when it accesses files in those directories (on-demand loading to save space).

### What to Put in CLAUDE.md

Be specific. Good examples:
- "Use 2-space indentation in all JavaScript files"
- "Run tests with `npm test` before committing"
- "The database schema is in `docs/schema.md`"
- "Never modify files in the `legacy/` folder without asking first"

Bad examples (too vague to be useful):
- "Write clean code"
- "Follow best practices"

### File Imports

CLAUDE.md files can pull in other files using the `@path/to/file` syntax. For example, putting `@docs/architecture.md` inside your CLAUDE.md will make Claude read that file too. Imports can be nested up to 5 levels deep.

### What Claude Code Can Do For You

You can ask Claude Code: **"Create a CLAUDE.md file for this project that documents the key architecture decisions and file structure."** Claude will analyze your project and write one. You can also use the `/init` command (see below).

---

## The /init and /memory Commands

### /init -- Bootstrap Your Memory

Type `/init` inside Claude Code to have it automatically analyze your project and generate a starter `CLAUDE.md` file. It will:
- Scan your project files and directory structure
- Detect your tech stack (languages, frameworks, build tools)
- Document build commands, test instructions, key directories
- Note coding conventions it detected

**Important**: Always review what `/init` generates. It captures obvious patterns but may miss nuances. Think of it as a first draft that you refine.

You can run `/init` on existing projects too -- Claude will review the current CLAUDE.md and suggest improvements.

### /memory -- View and Edit Memory

Type `/memory` during a session to:
- See which memory files are currently loaded
- Open any memory file in your system editor for editing

### Quick Memory Addition with #

During any session, prefix a line with `#` to instantly add it to memory. For example, typing:
```
# The API keys are stored in .env.local, never commit them
```
Claude will save this to the appropriate memory file.

---

## The .claude/rules/ Directory

For larger projects, a single CLAUDE.md file can get unwieldy. The `.claude/rules/` directory lets you split instructions into focused files.

### Structure

```
your-project/
  .claude/
    CLAUDE.md              (main instructions)
    rules/
      code-style.md        (formatting rules)
      testing.md           (how to run/write tests)
      architecture.md      (project structure notes)
      security.md          (security requirements)
```

All `.md` files in `.claude/rules/` are automatically loaded at session start, just like CLAUDE.md.

### Scoping Rules to Specific Files

You can make rules apply only when Claude is working with certain files by adding a header:

```yaml
---
paths:
  - "src/api/**/*.ts"
---
# API Rules
- All endpoints must validate input
- Use standard error format
```

Rules without a `paths` header apply to everything.

### What Claude Code Can Do For You

You can ask Claude: **"Set up a .claude/rules directory for this project with separate rule files for [your topics]."** Claude will create the directory and files.

---

## What Happens During Context Compaction

### When It Triggers

Context compaction triggers automatically when your conversation fills approximately 95% of the context window (when only about 25% remains). You can also trigger it manually by typing `/compact`.

### What Happens

1. Claude analyzes the conversation to identify key information
2. It creates a concise summary of previous interactions, decisions, and code changes
3. Older messages are replaced with this summary
4. Tool outputs (file contents, search results) are cleared first, then conversation is summarized

### What Gets Lost

This is the critical pain point that many users report:

- **Instructions from early in the conversation** can be lost or summarized away
- **Nuances and specific details** may be flattened into vague summaries
- **Claude Skills and procedures** that were being followed may be forgotten
- **The summary quality varies** -- sometimes it misses crucial context

### What Survives

- Your CLAUDE.md files (they are re-read, not part of the conversation)
- The most recent code changes and requests
- Key decisions (usually, but not always in full detail)

### How to Protect Against Compaction Loss

1. **Put persistent instructions in CLAUDE.md**, not in conversation messages
2. **Compact manually at logical breakpoints** (type `/compact` after finishing a feature) rather than waiting for auto-compact
3. **Use `/compact` with a focus**: typing `/compact focus on the API changes` tells Claude what to prioritize in the summary
4. **Start fresh sessions** for new tasks rather than continuing very long sessions
5. **Write important decisions to files** (like a `decisions.md`) so they persist in the project, not just in conversation

---

## MCP Memory Servers

MCP (Model Context Protocol) servers are plugins that give Claude additional tools. Several are designed specifically for persistent memory.

### Option 1: Official Anthropic Memory Server (Simplest)

The official memory server from Anthropic. It stores a knowledge graph (entities and their relationships) as plain JSON.

**Setup** (ask Claude Code to run this for you):
```
claude mcp add memory -- npx -y @modelcontextprotocol/server-memory
```

**What it does**: Gives Claude tools to store and retrieve entities, facts, and relationships. Data is stored locally in a JSON file. Human-readable and editable.

### Option 2: MCP Memory Keeper (Checkpoint/Restore)

Designed specifically for Claude Code's context loss problem. Uses SQLite for storage.

**Setup**:
```
claude mcp add memory-keeper -- npx -y mcp-memory-keeper
```

**How to use it**: When your conversation gets long, tell Claude "save a checkpoint." When starting a new session, tell Claude "restore from the last checkpoint." It also enables sharing knowledge between multiple Claude sessions.

### Option 3: MCP Memory Service (Feature-Rich)

More advanced, with features like memory consolidation, decay scoring, and semantic search.

**Setup**: Requires Python. More complex installation -- see the [GitHub repository](https://github.com/doobidoo/mcp-memory-service).

### Option 4: Claude Memory MCP (Lightweight, Local)

All data stored locally in `~/.memory-mcp/memory.db`. Supports full-text search.

**Setup**:
See [GitHub](https://github.com/WhenMoon-afk/claude-memory-mcp) for installation instructions.

### What Claude Code Can Do For You

You can ask Claude Code: **"Set up the official Anthropic MCP memory server for me so you have persistent memory across sessions."** Claude can run the installation command and configure it.

---

## Hook-Based Automatic Memory Systems

Claude Code supports "hooks" -- scripts that run automatically at certain moments. The most powerful memory systems use hooks to capture knowledge without you doing anything.

### How Hooks Work

Hooks can fire at these moments:
- **Stop**: After every Claude response
- **PreCompact**: Right before context compaction happens (critical for saving context)
- **SessionEnd**: When you close the session

### Option 1: memory-mcp (Recommended Automatic Approach)

This system silently captures important information during your sessions and writes it to CLAUDE.md for future sessions. Completely automatic.

**How it works**:
1. During your session, hooks silently extract decisions, patterns, and learnings from the conversation
2. It uses Claude Haiku (a small, cheap model) to identify what is worth remembering
3. Extracted memories are saved to a `.memory/state.json` file
4. A generator creates an optimized CLAUDE.md from the memory store, ranked by importance
5. Next session, Claude reads the updated CLAUDE.md and knows everything

**Cost**: About $0.05-0.10 per full day of development. No vector database or infrastructure needed.

**Memory budget**: It allocates fixed line counts per section (25 lines for architecture, 25 for decisions, etc.) and ranks memories by confidence and access frequency. Low-confidence memories are excluded from CLAUDE.md but kept in the full store.

### Option 2: Claude Cortex

A "brain-like" memory system with features inspired by how human memory works.

**Features**:
- PreCompact hook automatically extracts important content before compaction
- After compaction, Claude automatically restores context
- Memories have "temporal decay" (old irrelevant things fade naturally)
- Short-term memories consolidate into long-term memories
- Semantic linking creates a knowledge graph

**Setup** (added to `~/.claude/settings.json`):
Hooks run `npx -y claude-cortex hook pre-compact` and `npx -y claude-cortex hook session-start`.

See [GitHub](https://github.com/mkdelta221/claude-cortex) for full setup.

### What Claude Code Can Do For You

You can ask Claude: **"Set up memory hooks so that important context is automatically saved before compaction and at the end of each session."** Claude can configure the hooks in your settings file.

---

## File-Based Memory Strategies (Manual)

These approaches require no plugins or MCP servers. They rely on writing important information to files in your project that Claude can re-read.

### Strategy 1: Decision Log

Create a `docs/decisions.md` file (or `decisions/` directory) where you document every important decision. Reference it from your CLAUDE.md using `@docs/decisions.md`.

### Strategy 2: Progress Tracking

Maintain a `docs/progress.md` with checkboxes for current tasks:
```markdown
## Current Sprint
- [x] Set up database schema
- [ ] Build API endpoints
- [ ] Write tests for user auth
```

### Strategy 3: The docs/ Folder Pattern

Put detailed documentation in a `docs/` folder. Only reference it from CLAUDE.md using `@docs/filename.md`. This way, Claude does not load everything into memory upfront (saving tokens) but can access it when needed.

### Strategy 4: Architecture Documentation

Maintain a `docs/architecture.md` that describes your project structure, key patterns, and how components connect. This is one of the highest-value files for Claude to have access to.

### What Claude Code Can Do For You

You can ask Claude: **"Create a docs/ folder with architecture.md, decisions.md, and progress.md files, and reference them from CLAUDE.md."** Claude will create the structure and populate it based on your project.

---

## Community "Unlimited Memory" Projects

### Claude-Mem (by thedotmack)

A Claude Code plugin that automatically captures everything Claude does during sessions, compresses it with AI, and injects relevant context back into future sessions. Described on Twitter/X as providing "infinite memory to Claude Code."

See [GitHub](https://github.com/thedotmack/claude-mem).

### Grov (Persistent Memory Proxy)

Runs a local proxy that intercepts Claude Code's API calls. It captures reasoning from each session, stores it in SQLite, and auto-injects relevant context into future sessions. Reported dramatic speedups: tasks that took 10-11 minutes dropped to 1-2 minutes because Claude already knew the codebase patterns.

### Claude Cognitive

Working memory with "attention-based file injection." Files get attention scores: HOT (above 0.8) means full file is injected, WARM (0.25-0.8) means only headers are injected. Files decay when not mentioned and activate on keywords.

See [GitHub](https://github.com/GMaN1911/claude-cognitive).

### Memory Bank Systems (Cline-inspired)

Several projects adapt the "Memory Bank" concept from Cline (another AI coding tool) to Claude Code. These maintain structured project context across sessions. Notable implementations:
- [hudrazine/claude-code-memory-bank](https://github.com/hudrazine/claude-code-memory-bank)
- [centminmod/my-claude-code-setup](https://github.com/centminmod/my-claude-code-setup)
- [russbeye/claude-memory-bank](https://github.com/russbeye/claude-memory-bank)

---

## Recommended Setup for This Project

Here is a practical, layered approach from simplest to most advanced. Start with Layer 1 and add more as needed.

### Layer 1: CLAUDE.md (Do This First -- Zero Setup Required)

**Ask Claude Code to do this for you by saying:**

> "Run /init to generate a CLAUDE.md for this project. Then review it with me so I can refine it."

Or more specifically:

> "Create a CLAUDE.md file for this project. Include: the project purpose (an interactive worldbuilding program), the key files and their roles, any coding conventions, and how to run the project. Keep it under 100 lines."

This alone will give Claude memory of your project structure and conventions across every future session.

### Layer 2: Decision and Progress Files (Easy, No Tools Required)

**Ask Claude Code:**

> "Create a docs/ folder with decisions.md and progress.md. Add @docs/decisions.md and @docs/progress.md references to CLAUDE.md. From now on, whenever we make an important decision, record it in decisions.md."

This gives Claude access to your project history without cluttering the main CLAUDE.md.

### Layer 3: MCP Memory Server (Moderate, One Command)

**Ask Claude Code:**

> "Set up the official Anthropic MCP memory server so you have persistent memory across our sessions."

Claude will run: `claude mcp add memory -- npx -y @modelcontextprotocol/server-memory`

This gives Claude structured memory tools (store facts, query knowledge) that persist in a local file.

### Layer 4: Automatic Memory Hooks (Advanced, Hands-Off)

**Ask Claude Code:**

> "Set up automatic memory hooks using claude-cortex (or memory-mcp) so that important context is saved before compaction and at session end, and restored at session start."

This is the most powerful option but also the most complex. It makes memory completely automatic -- you never have to tell Claude to remember things.

### Day-to-Day Tips

1. **At the start of each session**, Claude automatically reads your CLAUDE.md. If something seems off, type `/memory` to check what is loaded.
2. **Before ending a session**, tell Claude: "Update the progress file and CLAUDE.md with what we accomplished today."
3. **If a session gets very long**, type `/compact` yourself at a natural break point rather than waiting for auto-compact.
4. **For critical instructions**, always put them in CLAUDE.md rather than just saying them in conversation. Conversation messages can be lost to compaction; CLAUDE.md cannot.
5. **Use the # shortcut** to quickly add things to memory mid-session: `# Always use TypeScript strict mode in this project`

---

## Sources

### Official Documentation
- [Manage Claude's Memory - Claude Code Docs](https://code.claude.com/docs/en/memory)
- [How Claude Code Works - Claude Code Docs](https://code.claude.com/docs/en/how-claude-code-works)
- [Hooks Reference - Claude Code Docs](https://code.claude.com/docs/en/hooks)
- [Claude Code Best Practices - Anthropic Engineering](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Using CLAUDE.md Files - Claude Blog](https://claude.com/blog/using-claude-md-files)

### Architecture and Deep Dives
- [The Architecture of Persistent Memory for Claude Code - DEV Community](https://dev.to/suede/the-architecture-of-persistent-memory-for-claude-code-17d)
- [How Claude's Memory Actually Works (And Why CLAUDE.md Matters) - Rajiv Pant](https://rajiv.com/blog/2025/12/12/how-claude-memory-actually-works-and-why-claude-md-matters/)
- [Claude Memory: A Deep Dive - Skywork AI](https://skywork.ai/blog/claude-memory-a-deep-dive-into-anthropics-persistent-context-solution/)
- [The Complete Guide to CLAUDE.md - Builder.io](https://www.builder.io/blog/claude-md-guide)

### Context Compaction
- [How Claude Code Got Better by Protecting More Context](https://hyperdev.matsuoka.com/p/how-claude-code-got-better-by-protecting)
- [Claude Code Context Recovery: Stop Losing Progress - Medium](https://medium.com/coding-nexus/claude-code-context-recovery-stop-losing-progress-when-context-compacts-772830ee7863)
- [What to Do When Claude Code Starts Compacting - Du'An Lightfoot](https://www.duanlightfoot.com/posts/what-to-do-when-claude-code-starts-compacting/)
- [Claude Code Compaction - Steve Kinney](https://stevekinney.com/courses/ai-development/claude-code-compaction)
- [Auto-Compact FAQ - ClaudeLog](https://claudelog.com/faqs/what-is-claude-code-auto-compact/)

### MCP Memory Servers
- [Adding Memory to Claude Code with MCP - Medium](https://medium.com/@brentwpeterson/adding-memory-to-claude-code-with-mcp-d515072aea8e)
- [MCP Memory Keeper - GitHub](https://github.com/mkreyman/mcp-memory-keeper)
- [MCP Memory Service - GitHub](https://github.com/doobidoo/mcp-memory-service)
- [Claude Memory MCP - GitHub](https://github.com/WhenMoon-afk/claude-memory-mcp)

### Hook-Based Memory Systems
- [Claude Cortex - GitHub](https://github.com/mkdelta221/claude-cortex)
- [everything-claude-code Hooks - GitHub](https://github.com/affaan-m/everything-claude-code/tree/main/hooks/memory-persistence)
- [I Built a Brain for Claude Code - DEV Community](https://dev.to/mkdelta221/i-built-a-brain-for-claude-code-because-it-keeps-forgetting-everything-ef9)

### Community Projects and Discussions
- [Claude-Mem - GitHub](https://github.com/thedotmack/claude-mem)
- [Claude Cognitive - GitHub](https://github.com/GMaN1911/claude-cognitive)
- [claude-code-memory-bank - GitHub](https://github.com/hudrazine/claude-code-memory-bank)
- [centminmod/my-claude-code-setup - GitHub](https://github.com/centminmod/my-claude-code-setup)
- [Fixing Claude Code's Amnesia - Jesse Vincent](https://blog.fsck.com/2025/10/23/episodic-memory/)
- [Show HN: Stop Claude Code from Forgetting Everything](https://news.ycombinator.com/item?id=46426624)
- [Show HN: Persistent Memory for Claude Code Sessions](https://news.ycombinator.com/item?id=46126066)
- [Claude Memory - Hacker News Discussion](https://news.ycombinator.com/item?id=45684134)

### Guides and Best Practices
- [Project Memory (CLAUDE.md) - Claude Code for Product Managers](https://ccforpms.com/fundamentals/project-memory)
- [Claude Code Best Practices: Memory Management - Code Centre](https://cuong.io/blog/2025/06/15-claude-code-best-practices-memory-management)
- [Writing a Good CLAUDE.md - HumanLayer](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [Creating the Perfect CLAUDE.md - Dometrain](https://dometrain.com/blog/creating-the-perfect-claudemd-for-claude-code/)
- [Rules Directory Mechanics - Claude Fast](https://claudefa.st/blog/guide/mechanics/rules-directory)
- [Modular Rules in Claude Code](https://claude-blog.setec.rs/blog/claude-code-rules-directory)
- [The .claude Folder: A 10-Minute Setup - Medium](https://medium.com/@manojkumar.vadivel/the-claude-folder-a-10-minute-setup-that-makes-ai-code-smarter-93da465ef39e)

### GitHub Issues (Feature Requests and Bug Reports)
- [Feature Request: Persistent Memory Between Sessions - #14227](https://github.com/anthropics/claude-code/issues/14227)
- [BUG: Memory Loss After Auto-compact - #1534](https://github.com/anthropics/claude-code/issues/1534)
- [BUG: Skills Context Lost After Auto-compaction - #13919](https://github.com/anthropics/claude-code/issues/13919)
- [FEATURE: Pre-compaction Hook - #15923](https://github.com/anthropics/claude-code/issues/15923)
- [FEATURE: PreCompact and PostCompact Hooks - #17237](https://github.com/anthropics/claude-code/issues/17237)
