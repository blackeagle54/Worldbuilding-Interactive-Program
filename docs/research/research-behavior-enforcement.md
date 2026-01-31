# Research: Enforcing Correct LLM Behavior in Structured Desktop Workflows

**Date:** 2026-01-30
**Context:** Worldbuilding tool with 52-step progression, PySide6 desktop app, Claude via Agent SDK
**Problem:** How do we ensure Claude follows a strict workflow, generates valid structured output, respects existing canon, and never skips validation -- in a desktop app where CLI hooks are no longer the enforcement mechanism?

---

## Table of Contents

1. [System Prompt Engineering for Structured Workflows](#1-system-prompt-engineering-for-structured-workflows)
2. [Tool-Use as Guardrails](#2-tool-use-as-guardrails)
3. [UI-Level Enforcement](#3-ui-level-enforcement)
4. [Validation Pipeline](#4-validation-pipeline)
5. [Context Window Management](#5-context-window-management)
6. [Drift Detection and Correction](#6-drift-detection-and-correction)
7. [Hybrid Architecture Patterns](#7-hybrid-architecture-patterns)
8. [The Architecture Spectrum: App Drives vs Claude Drives](#8-the-architecture-spectrum-app-drives-vs-claude-drives)
9. [Recommended Architecture for This Project](#9-recommended-architecture-for-this-project)
10. [Sources](#10-sources)

---

## 1. System Prompt Engineering for Structured Workflows

### What the Research Shows

Anthropic's Claude 4.x prompt engineering best practices emphasize that Claude responds best to **explicit, bounded, verifiable instructions**. A system prompt should read like "a short contract" with: a role, a goal, constraints, fallback behavior, and output format. This is directly applicable to our 52-step workflow.

### Techniques That Work

**Role Definition with Explicit Boundaries:**
```
You are a worldbuilding assistant operating within a structured 52-step
creation workflow. You are currently on Step {step_number}: {step_name}.

Your ONLY job right now is to generate {task_type} for this step.
You must NOT:
- Reference steps you haven't reached yet
- Create entities not defined in the current step's schema
- Skip validation or suggest the user skip ahead
- Generate content outside the current step's scope
```

**Output Format Specification (Constrained Decoding):**
As of November 2025, Anthropic supports **structured outputs via constrained decoding**. This compiles a JSON schema into a grammar and restricts token generation at inference time. The model literally cannot produce tokens that violate the schema. This is the single most powerful enforcement mechanism available.

```python
from anthropic import Anthropic

client = Anthropic()

# Using constrained decoding -- Claude CANNOT produce invalid JSON
response = client.messages.create(
    model="claude-sonnet-4-5-20250514",
    max_tokens=4096,
    system="You are a worldbuilding assistant. Generate options for the current step.",
    messages=[{"role": "user", "content": step_context}],
    headers={"anthropic-beta": "structured-outputs-2025-11-13"},
    output_config={
        "format": {
            "type": "json_schema",
            "json_schema": {
                "name": "worldbuilding_options",
                "schema": current_step_schema  # One of our 85 JSON schemas
            }
        }
    }
)
```

**Chain-of-Thought Steering:**
```
Before generating options, reason through the following:
1. What entities already exist that are relevant to this step?
2. What constraints does the current schema impose?
3. What previous decisions must be respected?
4. Generate 2-4 options that are distinct, valid, and internally consistent.

Present your reasoning in <thinking> tags, then output the structured result.
```

**Explicit Constraint Injection:**
Anthropic recommends explaining WHY constraints exist, not just WHAT they are. Claude 4.x models follow instructions more reliably when given motivation:

```
You MUST respect all existing canon entities listed below. These represent
decisions the user has already made and are immutable. Contradicting them
would break the world's internal consistency, which is the core value of
this tool.
```

### What Does NOT Work

- **Vague instructions:** "Be consistent" is not enforceable. "Do not contradict any entity in the EXISTING_CANON section" is.
- **Relying solely on the system prompt for format:** Without constrained decoding, Claude will occasionally produce prose instead of JSON, especially in long conversations. System prompts degrade over time (instruction amnesia).
- **Overly long system prompts:** Anthropic's research shows that bloated prompts reduce compliance. Keep the system prompt focused; inject step-specific context via messages, not the system prompt.
- **Negative-only instructions:** "Don't hallucinate" is less effective than "Only reference entities listed in the EXISTING_CANON section below."

### Key Insight

System prompts are necessary but not sufficient. They set the behavioral baseline, but enforcement must come from **structural constraints** (constrained decoding, tool gating, validation pipelines). Think of the system prompt as the first layer of a defense-in-depth strategy.

---

## 2. Tool-Use as Guardrails

### The Core Principle

If Claude can only act through validated tools, it cannot drift. Instead of asking Claude to "generate a faction" and hoping it produces valid JSON, you register a `create_faction` tool with a strict input schema. Claude must call the tool with valid parameters, and your application validates those parameters before executing.

### How Tool-Use Constrains Behavior

With **strict tool use** (`"strict": true` on the tool's `input_schema`), Anthropic guarantees that Claude's tool call parameters will match the schema exactly. Combined with structured outputs, this creates a two-layer enforcement:

1. **Constrained decoding** ensures Claude produces valid JSON structure
2. **Tool schema validation** ensures the content matches your entity definitions

### Tool Registration Pattern for Worldbuilding

```python
tools = [
    {
        "name": "generate_options",
        "description": "Generate 2-4 options for the current worldbuilding step. "
                       "Each option must conform to the step's entity schema and "
                       "must not contradict existing canon.",
        "input_schema": {
            "type": "object",
            "strict": True,
            "properties": {
                "step_id": {
                    "type": "integer",
                    "description": "Current step number (1-52)"
                },
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "entity_data": {
                                "type": "object",
                                "description": "Must conform to the step's JSON schema"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "Why this option fits the existing world"
                            }
                        },
                        "required": ["title", "description", "entity_data", "reasoning"]
                    },
                    "minItems": 2,
                    "maxItems": 4
                }
            },
            "required": ["step_id", "options"]
        }
    },
    {
        "name": "validate_entity",
        "description": "Check an entity against existing canon before committing. "
                       "Returns validation results.",
        "input_schema": {
            "type": "object",
            "strict": True,
            "properties": {
                "entity_type": {"type": "string"},
                "entity_data": {"type": "object"},
                "step_id": {"type": "integer"}
            },
            "required": ["entity_type", "entity_data", "step_id"]
        }
    },
    {
        "name": "get_canon_context",
        "description": "Retrieve existing canon entities relevant to the current step. "
                       "Use this BEFORE generating options to ensure consistency.",
        "input_schema": {
            "type": "object",
            "strict": True,
            "properties": {
                "step_id": {"type": "integer"},
                "entity_types": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["step_id"]
        }
    },
    {
        "name": "advance_step",
        "description": "Request to move to the next step. Will only succeed if "
                       "the current step's completion criteria are met.",
        "input_schema": {
            "type": "object",
            "strict": True,
            "properties": {
                "current_step": {"type": "integer"},
                "completion_summary": {"type": "string"}
            },
            "required": ["current_step", "completion_summary"]
        }
    }
]
```

### Agent SDK Tool Registration

The Claude Agent SDK supports tool registration with permission scoping. Key capabilities:

- **Allowed tools configuration:** You can restrict which tools Claude has access to, enforcing least-privilege. For worldbuilding, Claude gets `generate_options`, `get_canon_context`, and `validate_entity` -- but NOT direct file write or arbitrary code execution.
- **PreToolUse hooks:** These validate tool calls before execution. Even if Claude calls `advance_step`, the hook can reject it if completion criteria are not met.
- **Tool response handling:** You intercept tool results before they go back to Claude, allowing you to inject additional context or correct errors.

### Critical Design Decision: No Free-Form Output

In the tool-constrained model, Claude never produces "raw text" that gets displayed directly. Every piece of content flows through a tool call:

```
User clicks "Generate Options"
  -> App sends step context to Claude
  -> Claude MUST call generate_options() tool
  -> App validates tool call parameters against step schema
  -> App validates against canon via consistency checker
  -> Only validated options reach the UI
```

If Claude tries to respond with prose instead of a tool call, the application can detect this (no tool_use block in the response) and either retry or display an error.

---

## 3. UI-Level Enforcement

### The Desktop App as the Primary Guardrail

In a CLI workflow, hooks enforce behavior automatically. In a desktop app, the **UI itself becomes the enforcement layer**. This is actually a stronger enforcement model because the UI can impose constraints that are impossible to circumvent, regardless of what Claude produces.

### Step Navigation Control

```
+--------------------------------------------------+
|  STEP NAVIGATOR (controlled by app, not Claude)   |
|                                                    |
|  [1] World Seed        [COMPLETE]                 |
|  [2] Cosmology         [COMPLETE]                 |
|  [3] Geography         [IN PROGRESS] <-- current  |
|  [4] Climate           [LOCKED]                   |
|  [5] Natural Resources [LOCKED]                   |
|  ...                                              |
+--------------------------------------------------+
```

The app controls step progression:
- Steps are locked until prerequisites are complete
- The "Advance" button only enables when `check_completion` hook passes
- Claude cannot unlock steps -- only the app's completion checker can
- If Claude's output references a future step, the app ignores it

### Button-Triggered Generation

Instead of Claude deciding when to generate, generation is triggered by explicit user actions:

```
+--------------------------------------------------+
|  STEP 3: GEOGRAPHY                                |
|                                                    |
|  Context: [summary of existing world shown here]  |
|                                                    |
|  [Generate Options]  <-- user clicks this          |
|                                                    |
|  Option A: Pangaea-style continent                |
|    [Select] [Modify] [Regenerate]                 |
|  Option B: Island archipelago                     |
|    [Select] [Modify] [Regenerate]                 |
|  Option C: Multiple continents                    |
|    [Select] [Modify] [Regenerate]                 |
|                                                    |
|  [Confirm Selection]  [Back to Options]           |
+--------------------------------------------------+
```

This pattern means:
1. The user initiates every Claude interaction
2. Claude responds within a bounded context (this step, this schema)
3. The user explicitly confirms before anything is committed
4. Each Claude call is short and focused (not a long conversation)

### Schema-Validated Forms

When Claude generates an entity, it flows through a form that validates against the JSON schema BEFORE saving:

```python
class EntityForm(QWidget):
    """Form that validates entity data against step schema before save."""

    def __init__(self, step_schema: dict, existing_canon: dict):
        super().__init__()
        self.schema = step_schema
        self.canon = existing_canon
        self.validator = ConsistencyChecker(existing_canon)

    def populate_from_claude(self, claude_entity_data: dict):
        """Fill form fields from Claude's output. User can edit."""
        # Schema validation first
        errors = validate_against_schema(claude_entity_data, self.schema)
        if errors:
            self.show_validation_errors(errors)
            return

        # Populate editable fields
        for field_name, value in claude_entity_data.items():
            self.set_field(field_name, value)

    def on_save(self):
        """Validate everything before committing to canon."""
        entity_data = self.collect_field_values()

        # Layer 1: JSON schema validation
        schema_errors = validate_against_schema(entity_data, self.schema)
        if schema_errors:
            self.show_validation_errors(schema_errors)
            return

        # Layer 2: Canon consistency check
        canon_errors = self.validator.check_consistency(entity_data)
        if canon_errors:
            self.show_consistency_warnings(canon_errors)
            return

        # Layer 3: Completeness check
        if not self.validator.check_completeness(entity_data, self.schema):
            self.show_incomplete_warning()
            return

        # All checks pass -> commit to bookkeeping
        self.commit_to_canon(entity_data)
```

### Who Drives the Workflow?

In the UI-enforcement model, the answer is clear: **the app drives, Claude fills**. The app:
- Controls which step is active
- Decides when to call Claude
- Validates Claude's output before displaying it
- Gates step advancement on completion criteria
- Maintains the authoritative state (canon database)

Claude's role is reduced to:
- Generating creative content within strict schemas
- Producing 2-4 options when asked
- Explaining/elaborating when the user requests it

This is the most robust model for non-technical users.

---

## 4. Validation Pipeline

### Architecture: Middleware Between Claude and the UI

Every piece of Claude output passes through a validation pipeline before reaching the user's world state. This is the "trust but verify" layer.

```
Claude Output
    |
    v
+-------------------+
| FORMAT VALIDATION  |  Does the output match expected structure?
| (JSON Schema)      |  Is it valid JSON? Does it match the step schema?
+-------------------+
    |
    v
+-------------------+
| RULE-BASED CHECKS  |  Does it contradict existing canon?
| (Cross-reference)  |  Are all referenced entities valid?
+-------------------+
    |
    v
+-------------------+
| SEMANTIC CHECKS    |  Does it make narrative sense?
| (Optional LLM)     |  Is it tonally consistent?
+-------------------+
    |
    v
+-------------------+
| COMPLETENESS CHECK |  Are all required fields populated?
| (Schema required)  |  Does it meet step completion criteria?
+-------------------+
    |
    v
UI Display / Canon Commit
```

### Layer 1: JSON Schema Validation

This is deterministic and fast. Using our 85 JSON schema templates:

```python
import jsonschema

class SchemaValidator:
    def __init__(self, schema_registry: dict):
        self.schemas = schema_registry  # step_id -> JSON schema

    def validate(self, step_id: int, entity_data: dict) -> list[str]:
        schema = self.schemas[step_id]
        validator = jsonschema.Draft7Validator(schema)
        errors = []
        for error in validator.iter_errors(entity_data):
            errors.append(f"{error.path}: {error.message}")
        return errors
```

With Anthropic's constrained decoding (`output_config` with `json_schema`), schema violations should be rare. But defense-in-depth means we validate anyway -- constrained decoding has edge cases (safety refusals, edge-case schemas).

### Layer 2: Rule-Based Cross-Reference Checks

These enforce canon consistency using our existing consistency checker:

```python
class CanonConsistencyChecker:
    def __init__(self, canon_db):
        self.canon = canon_db

    def check(self, new_entity: dict, step_id: int) -> list[str]:
        errors = []

        # Check: referenced entities must exist
        for ref in self.extract_entity_references(new_entity):
            if not self.canon.entity_exists(ref):
                errors.append(f"References non-existent entity: {ref}")

        # Check: no contradictions with established facts
        contradictions = self.find_contradictions(new_entity)
        errors.extend(contradictions)

        # Check: temporal consistency (events in order)
        if "timeline" in new_entity:
            temporal_errors = self.check_temporal_consistency(new_entity)
            errors.extend(temporal_errors)

        # Check: geographic consistency (locations make sense)
        if "location" in new_entity:
            geo_errors = self.check_geographic_consistency(new_entity)
            errors.extend(geo_errors)

        return errors
```

### Layer 3: Semantic Checks (Optional LLM-Based)

For checks that are hard to express as rules (narrative coherence, tonal consistency), use a separate, lightweight Claude call:

```python
class SemanticValidator:
    """Uses a separate Claude call to check narrative consistency."""

    async def check(self, new_entity: dict, relevant_canon: list[dict]) -> dict:
        prompt = f"""
        You are a consistency checker for a worldbuilding project.

        EXISTING CANON (authoritative):
        {json.dumps(relevant_canon, indent=2)}

        NEW ENTITY (to validate):
        {json.dumps(new_entity, indent=2)}

        Check for:
        1. Narrative contradictions with existing canon
        2. Tonal inconsistencies (e.g., grimdark entity in a lighthearted world)
        3. Logical impossibilities
        4. Missing connections (entity references things that should exist but don't)

        Return your assessment as JSON.
        """

        response = await self.client.messages.create(
            model="claude-sonnet-4-5-20250514",  # Use cheaper model for validation
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "validation_result",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "is_consistent": {"type": "boolean"},
                                "issues": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "severity": {
                                    "type": "string",
                                    "enum": ["none", "warning", "error"]
                                }
                            },
                            "required": ["is_consistent", "issues", "severity"]
                        }
                    }
                }
            }
        )
        return json.loads(response.content[0].text)
```

### Implementation as Middleware

```python
class ValidationPipeline:
    """Middleware between Claude output and UI/canon."""

    def __init__(self, schema_validator, canon_checker, semantic_validator):
        self.schema_val = schema_validator
        self.canon_check = canon_checker
        self.semantic_val = semantic_validator

    async def validate(self, claude_output: dict, step_id: int) -> ValidationResult:
        result = ValidationResult()

        # Stage 1: Schema (fast, deterministic)
        schema_errors = self.schema_val.validate(step_id, claude_output)
        if schema_errors:
            result.add_errors("schema", schema_errors)
            return result  # Fail fast -- schema errors mean malformed data

        # Stage 2: Canon consistency (fast, deterministic)
        canon_errors = self.canon_check.check(claude_output, step_id)
        if canon_errors:
            result.add_errors("canon", canon_errors)
            # Don't fail fast -- user might want to see these as warnings

        # Stage 3: Semantic (slow, LLM-based, optional)
        if not result.has_blocking_errors():
            semantic_result = await self.semantic_val.check(
                claude_output,
                self.canon_check.get_relevant_canon(step_id)
            )
            if not semantic_result["is_consistent"]:
                result.add_warnings("semantic", semantic_result["issues"])

        return result
```

---

## 5. Context Window Management

### The Challenge

In a 52-step worldbuilding session, the canon grows continuously. By step 30, you might have 50-100+ entities. The full context could easily exceed 200K tokens. Claude needs to know:
- The current step and its requirements
- All relevant existing canon (not necessarily ALL canon)
- The schema for the current step
- Previous decisions in this session

### Strategy: Selective Context Injection

Do NOT dump the entire canon into every Claude call. Instead, inject only what's relevant:

```python
class ContextBuilder:
    """Builds minimal, relevant context for each Claude call."""

    def __init__(self, canon_db, step_registry, fts_search):
        self.canon = canon_db
        self.steps = step_registry
        self.search = fts_search  # SQLite FTS5

    def build_context(self, step_id: int, user_query: str = "") -> str:
        sections = []

        # 1. Current step definition (always included)
        step_def = self.steps.get_step(step_id)
        sections.append(f"## Current Step\n{step_def.to_prompt()}")

        # 2. Step schema (always included)
        schema = self.steps.get_schema(step_id)
        sections.append(f"## Required Schema\n```json\n{json.dumps(schema, indent=2)}\n```")

        # 3. Direct dependencies (entities this step builds on)
        deps = self.steps.get_dependencies(step_id)
        dep_entities = self.canon.get_entities_by_type(deps)
        sections.append(f"## Existing Canon (Direct Dependencies)\n{self.format_entities(dep_entities)}")

        # 4. FTS5 search for user-query-relevant entities
        if user_query:
            relevant = self.search.search(user_query, limit=10)
            sections.append(f"## Related Canon\n{self.format_entities(relevant)}")

        # 5. World summary (compact, always included)
        summary = self.canon.get_world_summary()
        sections.append(f"## World Summary\n{summary}")

        # 6. Recent decisions in this session
        recent = self.canon.get_recent_decisions(limit=5)
        sections.append(f"## Recent Decisions\n{self.format_decisions(recent)}")

        return "\n\n---\n\n".join(sections)
```

### RAG with SQLite FTS5

Our existing SQLite FTS5 search is ideal for retrieval-augmented generation in this context:

```python
class CanonRAG:
    """Retrieval-Augmented Generation using SQLite FTS5."""

    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        # Assumes FTS5 table already exists

    def search(self, query: str, entity_types: list = None, limit: int = 10) -> list:
        """Search canon entities by relevance to query."""
        sql = """
            SELECT entity_id, entity_type, name, data,
                   rank as relevance_score
            FROM canon_fts
            WHERE canon_fts MATCH ?
        """
        params = [query]

        if entity_types:
            placeholders = ",".join("?" * len(entity_types))
            sql += f" AND entity_type IN ({placeholders})"
            params.extend(entity_types)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        return self.conn.execute(sql, params).fetchall()

    def get_step_relevant_entities(self, step_id: int) -> list:
        """Get entities relevant to a specific step based on step metadata."""
        step_meta = self.get_step_metadata(step_id)
        related_types = step_meta.get("related_entity_types", [])
        keywords = step_meta.get("context_keywords", [])

        results = []
        for keyword in keywords:
            results.extend(self.search(keyword, related_types, limit=5))

        # Deduplicate and rank
        seen = set()
        unique = []
        for r in results:
            if r[0] not in seen:
                seen.add(r[0])
                unique.append(r)

        return unique[:20]  # Cap at 20 most relevant entities
```

### Prompt Caching for Cost Reduction

Anthropic's prompt caching can dramatically reduce costs for repeated interactions within a step:

```python
class CachedContextManager:
    """Uses Anthropic prompt caching for stable context sections."""

    def build_messages(self, step_context: str, user_message: str) -> list:
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": step_context,  # Stable within a step
                        "cache_control": {"type": "ephemeral"}  # Cache this
                    },
                    {
                        "type": "text",
                        "text": user_message  # Changes each interaction
                    }
                ]
            }
        ]
```

The step context (schema, dependencies, canon summary) stays cached for 5 minutes (refreshed on each use). Only the user's specific request changes between calls. This can reduce input token costs by up to 90% for multiple interactions within the same step.

### Context Budget Allocation

For a 200K token context window, budget allocation should look like:

| Component | Token Budget | Notes |
|-----------|-------------|-------|
| System prompt | ~2,000 | Role, constraints, current step |
| Step schema | ~500-1,000 | JSON schema for current step |
| Direct dependencies | ~10,000-30,000 | Entities this step builds on |
| FTS5 search results | ~5,000-10,000 | Query-relevant canon |
| World summary | ~2,000-5,000 | Compact summary of all decisions |
| Recent decisions | ~1,000-2,000 | Last 5 decisions in session |
| User message | ~500-1,000 | Current request |
| **Reserved for output** | **~4,000-8,000** | Claude's response |
| **Total used** | **~25,000-60,000** | Well within 200K limit |

This leaves substantial headroom. Even in late-game steps with 100+ canon entities, selective injection keeps context manageable.

### World Summary as Living Document

Maintain a compact world summary that gets updated after each step completion:

```python
class WorldSummarizer:
    """Maintains a running compact summary of the world state."""

    async def update_summary(self, current_summary: str, new_entity: dict) -> str:
        """Update world summary after a new entity is committed."""
        response = await self.client.messages.create(
            model="claude-sonnet-4-5-20250514",
            max_tokens=2048,
            system="You maintain a compact summary of a worldbuilding project. "
                   "Update the summary to incorporate the new entity. Keep it "
                   "under 1000 words. Focus on facts, connections, and themes.",
            messages=[{
                "role": "user",
                "content": f"Current summary:\n{current_summary}\n\n"
                           f"New entity added:\n{json.dumps(new_entity, indent=2)}\n\n"
                           f"Update the summary."
            }]
        )
        return response.content[0].text
```

---

## 6. Drift Detection and Correction

### Types of Drift in Worldbuilding Context

1. **Format drift:** Claude returns prose when JSON is expected
2. **Topic drift:** Asked about geography, Claude talks about magic systems
3. **Instruction amnesia:** Claude forgets constraints over long conversations
4. **Canon drift:** Claude invents entities that don't exist in the canon
5. **Scope drift:** Claude generates content for future steps

### Detection Mechanisms

**Format Drift Detection:**
```python
def detect_format_drift(response) -> bool:
    """Check if Claude returned a tool call vs. free-form text."""
    has_tool_use = any(
        block.type == "tool_use" for block in response.content
    )
    if not has_tool_use:
        # Claude responded with prose instead of calling a tool
        return True
    return False
```

**Topic Drift Detection:**
```python
def detect_topic_drift(response_text: str, step_id: int, step_meta: dict) -> bool:
    """Check if Claude's response is about the right topic."""
    expected_topics = step_meta["expected_topics"]  # e.g., ["geography", "terrain", "landmass"]
    forbidden_topics = step_meta["future_step_topics"]  # Topics from later steps

    # Simple keyword check (fast)
    response_lower = response_text.lower()
    for forbidden in forbidden_topics:
        if forbidden in response_lower:
            return True  # Drift detected

    # More sophisticated: use embeddings or a classifier
    return False
```

**Canon Drift Detection:**
```python
def detect_canon_drift(entity_data: dict, canon_db) -> list[str]:
    """Find references to entities that don't exist."""
    drift_issues = []

    # Extract all entity references from the generated content
    references = extract_entity_references(entity_data)

    for ref in references:
        if not canon_db.entity_exists(ref):
            drift_issues.append(
                f"References '{ref}' which does not exist in canon. "
                f"This may be a hallucinated entity."
            )

    return drift_issues
```

### Correction Strategies

**Strategy 1: Re-injection of System Prompt Context**

For long conversations, periodically re-inject the system prompt constraints as a user message:

```python
def build_reminder_message(step_id: int, step_meta: dict) -> str:
    return f"""
    REMINDER: You are on Step {step_id}: {step_meta['name']}.

    Current constraints:
    - Only generate {step_meta['entity_type']} entities
    - Must conform to schema: {step_meta['schema_name']}
    - Must reference only existing canon entities
    - Generate exactly 2-4 options

    Use the generate_options tool to respond.
    """
```

**Strategy 2: Short, Stateless Conversations**

The most effective anti-drift technique: **don't have long conversations**. Each Claude interaction should be a single request-response:

```
User clicks "Generate Options"
  -> App builds fresh context (system prompt + step context + relevant canon)
  -> Single Claude API call
  -> Validate response
  -> Display to user
  -> Conversation ends

User clicks "Regenerate" or "Modify"
  -> App builds fresh context again (with any updates)
  -> New, independent Claude API call
  -> No accumulated conversation history to drift from
```

This is the strongest drift prevention mechanism. Claude cannot accumulate confusion over turns if there are no turns.

**Strategy 3: Automatic Retry with Escalation**

```python
class DriftCorrectedGenerator:
    """Retries with stronger constraints when drift is detected."""

    MAX_RETRIES = 3

    async def generate(self, step_context: str, step_id: int) -> dict:
        for attempt in range(self.MAX_RETRIES):
            response = await self.call_claude(step_context, step_id, attempt)

            # Check for drift
            if detect_format_drift(response):
                step_context = self.add_format_reminder(step_context)
                continue

            parsed = self.parse_tool_call(response)

            canon_issues = detect_canon_drift(parsed, self.canon_db)
            if canon_issues:
                step_context = self.add_canon_reminder(step_context, canon_issues)
                continue

            # Passed all checks
            return parsed

        raise DriftError(
            "Claude failed to produce valid output after "
            f"{self.MAX_RETRIES} attempts"
        )

    def add_format_reminder(self, context: str) -> str:
        return context + "\n\nIMPORTANT: You MUST use the generate_options tool. "
                         "Do not respond with prose."

    def add_canon_reminder(self, context: str, issues: list) -> str:
        return context + f"\n\nPREVIOUS ATTEMPT HAD ERRORS:\n" + \
               "\n".join(f"- {issue}" for issue in issues) + \
               "\n\nPlease regenerate, fixing these issues."
```

---

## 7. Hybrid Architecture Patterns

### Pattern 1: Cursor / Claude Code -- Tool-Scoped Agents

Cursor and Claude Code constrain LLM behavior through:

- **Tool scoping:** Claude Code subagents each get a curated set of tool permissions and an isolated context window. The "Explore" subagent can read files but not write them. The "Plan" subagent can reason but not execute.
- **PreToolUse hooks:** Validate operations before they execute. This is directly analogous to our `validate_writes` hook.
- **Deterministic security guardrails:** Codacy's integration with Claude Code shows real-time guardrails for shell commands, file access, and MCP tool governance.
- **System prompt layering:** Claude Code uses 110+ prompt strings that are conditionally assembled based on environment and task. This is similar to our step-specific context injection.

**Lesson for us:** Use subagent-style isolation. The "option generator" agent gets read-only access to canon and can only output via the `generate_options` tool. The "validator" agent gets read access and outputs only validation results. Neither can modify canon directly.

### Pattern 2: LangGraph -- State Machine Agents

LangGraph models agent workflows as state machines:

- **Nodes** represent agents or processing steps
- **Edges** define transitions with conditions
- **Shared state** is typed and schema-validated
- **Conditional routing** based on agent outputs

This maps directly to our 52-step workflow:

```
[Step N: Generate] -> [Validate] -> [User Review] -> [Commit] -> [Step N+1: Generate]
                         |                |
                         v                v
                    [Retry with          [Modify
                     corrections]         and re-validate]
```

**Lesson for us:** Model our workflow as a state machine in the app. Each step has states: `LOCKED -> ACTIVE -> GENERATING -> REVIEWING -> VALIDATING -> COMPLETE`. Transitions are controlled by the app, not Claude.

### Pattern 3: Novelcrafter / Sudowrite -- Story Bibles as Guardrails

Creative writing tools use "story bibles" or "codexes" as structured knowledge bases that constrain AI generation:

- **Novelcrafter** maintains character sheets, worldbuilding databases, and structured story elements. The AI generates content tied to these structured elements.
- **Sudowrite's Story Bible** lets users create entries for characters, locations, items, and lore that the AI references during generation.
- **Deep Realms** builds characters with layers (names, roles, backstories, relationships) tied to events and locations.

**Lesson for us:** Our canon database is exactly this pattern. The key insight from these tools is that the structured knowledge base is **user-editable and authoritative**. The AI is a subordinate that references it, never the other way around.

### Pattern 4: Guardrails AI / NeMo Guardrails -- Validation Frameworks

- **Guardrails AI** uses Pydantic schemas and "RAIL" specs to validate LLM outputs, with automatic retry on validation failure.
- **NVIDIA NeMo Guardrails** uses "Colang" (a modeling language) to define conversational rails -- specific ways of controlling output like topic boundaries and dialog paths.

**Lesson for us:** Implement a validation framework with automatic retry. When Claude's output fails validation, retry with the error message included in context. Cap retries at 3 to avoid infinite loops.

### Pattern 5: ChatGPT Structured Outputs

OpenAI's structured outputs use a similar constrained decoding approach. Their documentation emphasizes:
- Defining schemas upfront
- Using `strict: true` on function parameters
- Handling refusals gracefully (model may refuse for safety, breaking schema)

**Lesson for us:** Always handle the refusal edge case. Even with constrained decoding, Claude may produce a safety refusal instead of schema-valid JSON. Our validation pipeline must detect this and provide a clear user-facing message.

---

## 8. The Architecture Spectrum: App Drives vs Claude Drives

### Option A: App Drives Everything

**How it works:** The app controls all workflow logic. Claude is called for specific, bounded sub-tasks: "Given this context, generate 4 options for a mountain range." Claude never sees the big picture of the 52-step workflow.

```
App State Machine
    |
    |--> Step 3 Active
    |      |
    |      |--> User clicks "Generate"
    |      |      |
    |      |      |--> App builds context for step 3
    |      |      |--> App calls Claude: "Generate 4 geography options"
    |      |      |--> App validates Claude's response
    |      |      |--> App displays options to user
    |      |
    |      |--> User selects option
    |      |      |
    |      |      |--> App validates against canon
    |      |      |--> App commits to canon DB
    |      |      |--> App checks completion criteria
    |      |
    |      |--> Completion criteria met -> unlock Step 4
```

**Pros:**
- Maximum control and predictability
- Claude cannot skip steps, drift, or go off-script
- Each Claude call is short, focused, stateless -- minimal drift risk
- Easiest to debug (app logic is deterministic)
- Best for non-technical users (they interact with the UI, not with Claude)
- Validation is guaranteed (app controls the pipeline)

**Cons:**
- Claude cannot offer creative suggestions about workflow (e.g., "you should define your magic system before your religion")
- Less dynamic -- the experience feels more like a form wizard than a conversation
- More app code to maintain (all workflow logic is in Python, not delegated to Claude)
- Claude's responses may feel less contextually rich because it doesn't see the big picture

### Option B: Claude Drives, App Validates

**How it works:** Claude is an autonomous agent that drives the workflow. It decides what step to work on, generates content, and proposes advances. The app provides tools and validates every action.

```
Claude Agent Loop
    |
    |--> Claude reads current state via tools
    |--> Claude decides: "We should work on geography next"
    |--> Claude calls generate_options(step=3, ...)
    |      |
    |      |--> App validates tool call
    |      |--> Returns options to Claude
    |
    |--> Claude presents options to user
    |--> User selects
    |--> Claude calls commit_entity(...)
    |      |
    |      |--> App validates against canon
    |      |--> App checks schema
    |      |--> Commits or rejects
    |
    |--> Claude calls advance_step(...)
    |      |
    |      |--> App checks completion criteria
    |      |--> Advances or rejects
```

**Pros:**
- More conversational and dynamic
- Claude can offer creative workflow suggestions
- Feels like working with an intelligent collaborator
- Less app code for workflow logic (Claude handles sequencing)

**Cons:**
- High drift risk -- Claude may try to skip steps, hallucinate entities, or lose context
- Harder to debug (Claude's decision-making is non-deterministic)
- Requires extensive tool-level validation (every tool call must be gated)
- Context window pressure increases (Claude needs to maintain conversation state)
- Non-technical users may find it unpredictable
- Claude could "forget" the workflow rules in a long session (instruction amnesia)

### Option C: Hybrid -- App Drives High-Level, Claude Drives Creative Content

**How it works:** The app controls the workflow (step progression, validation, gating). Within each step, Claude has creative freedom to generate content, but only through structured tools and validated outputs.

```
App Controls:                    Claude Controls:
- Step progression               - Creative content generation
- Validation pipeline             - Option diversity and richness
- Canon database                 - Narrative coherence suggestions
- UI state                       - Elaboration and detail
- Completion criteria            - Explaining connections to canon
- Schema enforcement             - Answering user questions about the world
```

**Pros:**
- Best of both worlds: predictable workflow, creative content
- App handles what it's good at (state management, validation, UI)
- Claude handles what it's good at (creative generation, narrative reasoning)
- Each Claude call is scoped to a specific creative task within a validated framework
- Non-technical users get a guided experience with rich AI content
- Drift is contained within individual step interactions

**Cons:**
- More complex to implement than pure Option A
- Need clear boundaries between app and Claude responsibilities
- Some edge cases where the boundary is unclear

### Recommendation: Option C (Hybrid) with Option A Safety Net

**Use Option C as the primary architecture**, but with Option A as the fallback:

1. The app always controls step progression, validation, and canon
2. Within each step, Claude generates creative content via structured tools
3. If Claude fails validation 3 times, fall back to Option A mode: present the user with a simpler form-based interface and use Claude only for individual field suggestions
4. The user always has a "manual entry" option that bypasses Claude entirely

This gives non-technical users a guided, AI-enhanced experience while maintaining absolute control over data integrity.

---

## 9. Recommended Architecture for This Project

### Defense-in-Depth: Seven Layers of Enforcement

```
Layer 1: SYSTEM PROMPT
  - Role definition, step context, explicit constraints
  - Re-injected fresh on every Claude call (stateless conversations)

Layer 2: CONSTRAINED DECODING
  - output_config with json_schema matching the step's template
  - Claude literally cannot produce schema-invalid JSON

Layer 3: STRICT TOOL USE
  - Claude must call generate_options() -- cannot free-form respond
  - Tool input_schema enforces parameter types and constraints

Layer 4: APPLICATION VALIDATION
  - JSON schema validation (our 85 templates)
  - Canon cross-reference checks
  - Completeness verification

Layer 5: UI GATING
  - Step navigator locks future steps
  - User must explicitly confirm selections
  - Entity forms validate before save

Layer 6: DRIFT DETECTION
  - Format drift: no tool call in response
  - Canon drift: references to non-existent entities
  - Automatic retry with escalating constraints

Layer 7: BOOKKEEPING
  - Every decision logged with provenance
  - Audit trail for debugging
  - Session state recoverable after crash
```

### Data Flow Diagram

```
User Action (click "Generate Options")
    |
    v
Context Builder
    |- Loads step schema (from 85 templates)
    |- Queries canon DB for dependencies
    |- Runs FTS5 search for relevant entities
    |- Builds world summary
    |- Assembles system prompt
    |
    v
Claude API Call (single request-response, stateless)
    |- System prompt: role + constraints + step context
    |- output_config: step-specific JSON schema (constrained decoding)
    |- Tools: generate_options (strict: true)
    |- Prompt caching: step context cached for 5min
    |
    v
Response Handler
    |- Check: is there a tool_use block? (format drift detection)
    |- Extract tool call parameters
    |
    v
Validation Pipeline
    |- Schema validation (jsonschema)
    |- Canon consistency check
    |- Semantic check (optional, async)
    |
    v
[PASS]                          [FAIL]
  |                               |
  v                               v
UI Display                     Retry Handler
  |- Show 2-4 options            |- Add error context
  |- User reviews/selects        |- Re-call Claude (max 3)
  |- User can edit               |- If 3 fails: manual entry
  |
  v
User Confirms Selection
  |
  v
Canon Commit
  |- Write to SQLite
  |- Update FTS5 index
  |- Update world summary
  |- Log to bookkeeping
  |- Check completion criteria
  |
  v
Step Advancement Check
  |- All required entities created?
  |- All validation rules pass?
  |
  v
[COMPLETE]                      [INCOMPLETE]
  |                               |
  v                               v
Unlock Next Step              Stay on current step
```

### Key Implementation Principles

1. **Stateless Claude calls:** Every interaction is a fresh request-response. No multi-turn conversations with Claude. This eliminates instruction amnesia and drift accumulation.

2. **App is the source of truth:** The canon database, step state, and validation rules live in the app. Claude is a content generator, not a state manager.

3. **Constrained decoding + tool use + validation = triple enforcement:** Schema validity is guaranteed at the token level, enforced at the tool level, and verified at the application level.

4. **Selective context injection via RAG:** Use FTS5 to inject only relevant canon, keeping context focused and within budget.

5. **Prompt caching for cost efficiency:** Cache stable context (step definition, schema, canon summary) across multiple interactions within a step.

6. **Graceful degradation:** If Claude fails, the user can always fall back to manual entry. The app never blocks on Claude.

---

## 10. Sources

### Anthropic Documentation
- [Structured Outputs - Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Context Windows](https://platform.claude.com/docs/en/build-with-claude/context-windows)
- [Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Prompt Engineering Overview](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)
- [Claude 4.x Prompting Best Practices](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
- [How to Implement Tool Use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use)
- [Increase Output Consistency](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/increase-consistency)
- [Get Structured Output from Agents](https://platform.claude.com/docs/en/agent-sdk/structured-outputs)

### Anthropic Engineering Blog
- [Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
- [Building Agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Context Management on the Claude Developer Platform](https://www.anthropic.com/news/context-management)
- [Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)

### LangChain / LangGraph
- [Workflows and Agents - LangGraph Docs](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [How to Force Tool-Calling Agent to Structure Output](https://langchain-ai.github.io/langgraph/how-tos/react-agent-structured-output/)
- [LangGraph State Machines](https://dev.to/jamesli/langgraph-state-machines-managing-complex-agent-task-flows-in-production-36f4)

### Guardrails Frameworks
- [Guardrails AI](https://github.com/guardrails-ai/guardrails)
- [NVIDIA NeMo Guardrails](https://github.com/NVIDIA-NeMo/Guardrails)
- [LLM Guardrails Best Practices - Datadog](https://www.datadoghq.com/blog/llm-guardrails-best-practices/)
- [LLM Guardrails Guide - Orq.ai](https://orq.ai/blog/llm-guardrails)

### Worldbuilding Tools
- [Patchview: LLM-Powered Worldbuilding](https://arxiv.org/html/2408.04112v1)
- [Creating Worlds with LLMs - Ian Bicking](https://ianbicking.org/blog/2025/06/creating-worlds-with-llms)
- [Worldbuilding Tools and Narrative AI in 2025](https://openforge.io/a-founders-guide-to-worldbuilding-tools-how-narrative-ai-is-shaping-app-ux-in-2025/)

### Drift Detection & Correction
- [Drift Detection in Large Language Models](https://medium.com/@tsiciliani/drift-detection-in-large-language-models-a-practical-guide-3f54d783792c)
- [DRIFT: Dynamic Rule-Based Defense with Injection Isolation](https://openreview.net/forum?id=oY1Xnt83oJ)
- [Catching LLM Task Drift with Activations](https://arxiv.org/html/2406.00799v1)
- [Understanding Model Drift and Data Drift in LLMs](https://orq.ai/blog/model-vs-data-drift)

### Context Engineering
- [Claude's Context Engineering Secrets](https://01.me/en/2025/12/context-engineering-from-claude/)
- [How Claude Code Got Better by Protecting More Context](https://hyperdev.matsuoka.com/p/how-claude-code-got-better-by-protecting)
- [Claude Prompt Engineering Best Practices 2026](https://promptbuilder.cc/blog/claude-prompt-engineering-best-practices-2026)

### Claude Code Architecture
- [Claude Code System Prompts Repository](https://github.com/Piebald-AI/claude-code-system-prompts)
- [Claude Code Guardrails](https://github.com/rulebricks/claude-code-guardrails)
- [Equipping Claude Code with Deterministic Security Guardrails](https://blog.codacy.com/equipping-claude-code-with-deterministic-security-guardrails)
- [Red-Teaming Coding Agents](https://arxiv.org/html/2509.05755)
