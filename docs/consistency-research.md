# Canon/Lore Consistency Checking: Research & Implementation Plan

## Executive Summary

This document evaluates six approaches for automated contradiction detection and canon consistency validation in an AI-assisted worldbuilding system. The recommended architecture is a **three-layer hybrid** combining (1) schema-based structural validation, (2) rule-based cross-reference checking, and (3) LLM-based semantic contradiction detection using Claude Haiku. This layered approach catches cheap-to-detect errors first and reserves expensive LLM calls for nuanced semantic contradictions.

---

## Table of Contents

1. [Research Findings](#research-findings)
2. [Approach Evaluations](#approach-evaluations)
3. [Recommended Architecture](#recommended-architecture)
4. [Implementation Plan](#implementation-plan)
5. [Code Examples](#code-examples)
6. [Sources](#sources)

---

## Research Findings

### Key Insight: Global Consistency Is Hard

A January 2026 paper ("Foundations of Global Consistency Checking with Noisy LLM Oracles") proves that **global consistency cannot be certified from pairwise checks alone** and worst-case query complexity is exponential. However, the authors propose a practical **adaptive divide-and-conquer algorithm** that localizes Minimal Unsatisfiable Subsets (MUSes) and computes minimal repairs. The takeaway: naive "check everything against everything" does not scale, but targeted, hierarchical checking does.

### Contradictions in RAG Systems (Amazon, March 2025)

Research on contradiction detection in Retrieval Augmented Generation systems found that **context validation remains challenging even for state-of-the-art LLMs**, with larger models performing better. Chain-of-thought prompting helps but varies across tasks. This confirms that LLM-based checking is viable but imperfect -- it should be one layer, not the only layer.

### NLI Models Are Not Enough Alone

Natural Language Inference models classify premise-hypothesis pairs as entailment, contradiction, or neutral. The 2025 "Targeted Entailment and Contradiction Detection Pipeline" combines attention-based saliency with NLI classification for better results. However, NLI models struggle with:
- Implied vs. explicit entailment (requiring world knowledge)
- Numerical reasoning ("500 years" vs. "immortal")
- Multi-hop reasoning across entities

For worldbuilding, many contradictions are **structural** (referencing a non-existent entity) or **numerical** (conflicting lifespans, dates), not just semantic. NLI alone misses these.

### Vector Embeddings: Good for Retrieval, Bad for Contradiction Detection

A critical finding: **contradictory statements often have HIGH cosine similarity**, not low. "Elves live 500 years" and "Elves are immortal" are semantically very similar in embedding space. Standard embedding search finds related content effectively but cannot distinguish agreement from contradiction. Embeddings are useful as a **retrieval step** (find relevant canon to check against) but not as a **detection step**.

### Knowledge Graph Consistency Is Well-Studied

The knowledge graph community has decades of work on consistency constraints:
- **SHACL (Shapes Constraint Language)** validates RDF graphs against schemas
- **Contradiction-Detecting Dependencies (CDDs)** express class disjointness and constraint rules
- **Anti-pattern detection** generalizes individual contradictions into recurring error patterns
- **Update-based repair** preserves maximum information when fixing inconsistencies

Key insight: KG approaches distinguish between TBox inconsistency (schema-level: rules themselves conflict), ABox inconsistency (data-level: instances conflict), and combined inconsistency. A worldbuilding system has both: rules like "gods are immortal, mortals are not" (TBox) and specific entity data (ABox).

### Existing Worldbuilding Tools

Current tools (World Anvil, LegendKeeper, Nucanon, Artificer DM) offer:
- **Wiki-style linking** between entities (manual cross-referencing)
- **AI content generation** that is "aware of world lore" (context injection)
- **Lorebooks** that inject relevant context into AI prompts

None of them implement **automated contradiction detection** as described in the requirements. Nucanon advertises "tools for checking canon consistency" but details are sparse. This represents a genuine gap in existing tooling.

### Claude Code Hooks: The Integration Mechanism

Claude Code hooks provide deterministic automation at specific lifecycle points:

- **PostToolUse hooks** fire after Claude edits/writes files -- perfect for validation
- Hooks can return exit code 2 with `"decision": "block"` to reject changes
- Configuration lives in `.claude/settings.json` (project-specific)
- Hooks receive tool context including file paths and can run arbitrary scripts

This is the **ideal integration point** for consistency checking: every time Claude adds or modifies a canon entry, a PostToolUse hook triggers validation.

---

## Approach Evaluations

### 1. LLM-Based Checking (Claude Haiku)

**How it works:** When new content is added, retrieve relevant existing canon and send both to Claude Haiku with a prompt like "Identify any contradictions between the new entry and existing canon."

**Effectiveness:** HIGH for semantic/narrative contradictions. An LLM can catch nuanced issues like "You said the Dark Age lasted 200 years and started in year 3000, but this timeline entry places events from the Dark Age in year 3400." It handles natural language reasoning that rule-based systems cannot.

**False positive rate:** MODERATE. LLMs sometimes flag non-contradictions as contradictions, especially with ambiguous or context-dependent statements. Mitigation: use structured output with confidence scores and require HIGH confidence to flag.

**Scalability:** MODERATE concern. With N entities, naive all-pairs checking is O(N^2). However, using embedding-based retrieval to find only RELEVANT canon (top-k similar entries) before LLM checking reduces this to O(N * k) where k is small and fixed.

**Implementation complexity:** LOW-MEDIUM. Requires API calls and prompt engineering but no custom ML models.

**Cost:**
- Claude Haiku 4.5: $1/MTok input, $5/MTok output
- Batch API: 50% discount ($0.50/$2.50 per MTok)
- Prompt caching: reads at $0.10/MTok (10x cheaper) with 5-min TTL
- **Estimated per-check cost:** ~2000 tokens input (new entry + retrieved canon), ~500 tokens output = ~$0.005 per check at standard rates, ~$0.0025 with batch
- At 500 entities, adding one new entity: retrieve top-10 relevant = 1 embedding call + 1 Haiku call = **under $0.01**
- Running full audit of 500 entities: ~500 checks = **~$2.50 standard, ~$1.25 batch**

**Claude Code setup:** YES, fully automatable. Claude Code can write the checking script and configure the PostToolUse hook.

**Verdict: ESSENTIAL -- use as the semantic layer. Not sufficient alone.**

---

### 2. Knowledge Graph Constraints

**How it works:** Model canon as a graph (entities = nodes, relationships = edges) with constraint rules. Example constraints: "If entity type is 'mortal species', lifespan must be finite", "Every referenced entity must exist as a node", "No two gods can hold the same domain unless explicitly marked as contested."

**Effectiveness:** HIGH for structural and relational contradictions. Excellent at enforcing ontological rules consistently. Cannot catch narrative contradictions that require language understanding.

**False positive rate:** VERY LOW. Constraint violations are deterministic -- either a constraint is violated or it is not.

**Scalability:** EXCELLENT. Graph databases (Neo4j, or even in-memory with NetworkX) handle millions of nodes. Constraint checking is typically O(1) to O(degree) per addition.

**Implementation complexity:** HIGH. Requires:
- Designing an ontology (entity types, relationship types, valid patterns)
- Implementing or choosing a graph storage format
- Writing constraint rules
- Keeping the graph in sync with the canon files

**Cost:** Zero marginal cost (local computation only).

**Claude Code setup:** Partially automatable. Claude Code can write the constraint checker but the ontology design requires human input on worldbuilding rules.

**Verdict: VALUABLE for mature systems, but overkill for initial implementation. Build toward this incrementally.**

---

### 3. Schema-Based Validation (JSON Schema)

**How it works:** Define JSON schemas for each entity type (god, species, settlement, etc.) with required fields, valid enums, and cross-reference fields. Validate every entry against its schema on save.

**Effectiveness:** HIGH for structural integrity. Catches: missing required fields, invalid types, malformed references. Cannot catch semantic contradictions.

**False positive rate:** ZERO. Schema validation is deterministic.

**Scalability:** EXCELLENT. JSON Schema validation is O(n) in document size, essentially instant.

**Implementation complexity:** LOW. Python's `jsonschema` library handles validation. Schemas are straightforward to write.

**Limitation:** Standard JSON Schema cannot validate cross-references (e.g., "this god field references an entity that must exist in the pantheon file"). This requires custom validation logic on top of schema validation.

**Cost:** Zero (local computation).

**Claude Code setup:** YES, fully automatable. Claude Code can generate schemas from existing entity patterns.

**Verdict: ESSENTIAL as the first validation layer. Implement immediately.**

---

### 4. Embedding/Vector Similarity (Retrieval Layer)

**How it works:** Embed all canon text chunks. When new content is added, find the top-k most similar existing entries. Feed those to the LLM contradiction checker.

**Effectiveness as detection:** LOW. As noted in research, contradictory statements often have HIGH similarity scores. "Elves live 500 years" and "Elves are immortal" would score very high similarity.

**Effectiveness as retrieval:** HIGH. Finding semantically related content is exactly what embeddings excel at. This is the critical step that makes LLM-based checking scalable.

**False positive rate:** N/A (used for retrieval, not detection).

**Scalability:** EXCELLENT. Vector databases handle millions of embeddings with sub-millisecond queries.

**Implementation complexity:** LOW-MEDIUM. Local embedding models (e.g., `sentence-transformers`) avoid API costs. ChromaDB or FAISS provide simple local vector storage.

**Cost:** Near zero with local models. Or ~$0.02/MTok with Anthropic's Voyage embeddings.

**Claude Code setup:** YES, automatable with Python dependencies.

**Verdict: IMPORTANT as a retrieval layer for the LLM checker. Do NOT use for detection itself.**

---

### 5. Rule-Based Validation Scripts

**How it works:** Python scripts that check specific known patterns:
- Referenced entities must exist
- Numerical values must not conflict (lifespan, dates, distances)
- Exclusive categories must not overlap (a being cannot be both mortal and immortal)
- Timeline events must be chronologically consistent

**Effectiveness:** HIGH for known patterns. Catches exactly what you code it to catch. Misses anything you did not anticipate.

**False positive rate:** VERY LOW (deterministic).

**Scalability:** EXCELLENT. Custom scripts run in milliseconds.

**Implementation complexity:** LOW per rule, but grows with the number of rules. Each new worldbuilding pattern needs a new rule.

**Cost:** Zero (local computation).

**Claude Code setup:** YES, fully automatable. Claude Code can write validation scripts and add new rules as the world grows.

**Verdict: ESSENTIAL as the cross-reference layer. Implement alongside schema validation.**

---

### 6. Hybrid Approach (Recommended)

**How it works:** Layer all approaches in order of cost and determinism:

```
Layer 1: Schema Validation (instant, free, catches structural errors)
    |
    v
Layer 2: Rule-Based Cross-Reference Checks (instant, free, catches reference errors)
    |
    v
Layer 3: Embedding Retrieval + LLM Contradiction Check (seconds, costs ~$0.01, catches semantic errors)
```

**Effectiveness:** HIGHEST. Each layer catches what the others miss.

**False positive rate:** LOW. Deterministic layers have zero false positives. LLM layer's false positives can be managed with confidence thresholds and human review.

**Scalability:** GOOD. Layers 1-2 are O(1). Layer 3 is O(k) where k = number of retrieved relevant entries (fixed, e.g., 10-20).

**Implementation complexity:** MEDIUM overall. Each layer is individually simple.

**Cost:** Dominated by Layer 3 (~$0.01 per addition).

**Verdict: THIS IS THE RECOMMENDED APPROACH.**

---

## Recommended Architecture

### System Design

```
canon/
  entities/
    gods/
      god_001_solara.json
      god_002_morthai.json
    species/
      species_001_elves.json
      species_002_dwarves.json
    settlements/
      settlement_001_ironhold.json
    events/
      event_001_the_sundering.json
  _schema/
    god.schema.json
    species.schema.json
    settlement.schema.json
    event.schema.json
  _index/
    entity_registry.json       # All entity IDs, names, types
    cross_references.json      # All inter-entity references
    embeddings.npz             # Cached embeddings for all entries
  _rules/
    validate_references.py     # Cross-reference existence checks
    validate_numerics.py       # Numerical consistency checks
    validate_timeline.py       # Chronological consistency
    validate_categories.py     # Category exclusivity checks
  _hooks/
    consistency_check.py       # Main PostToolUse hook orchestrator
    llm_contradiction_check.py # Haiku-based semantic checking
```

### Entity JSON Structure (Example: God)

```json
{
  "$schema": "../_schema/god.schema.json",
  "id": "god_001",
  "name": "Solara",
  "aliases": ["The Radiant", "Sunmother"],
  "domain": ["sun", "light", "truth"],
  "status": "active",
  "alignment": "benevolent",
  "relationships": [
    {
      "target_id": "god_002",
      "type": "rival",
      "description": "Eternal opposition between light and shadow"
    }
  ],
  "associated_species": ["species_001"],
  "associated_settlements": ["settlement_001"],
  "lore_summary": "Solara is the goddess of sun and truth, worshipped primarily by the elves of Ironhold. She granted the elves their extended 500-year lifespan as a blessing.",
  "canon_claims": [
    {
      "claim": "Solara granted elves a 500-year lifespan",
      "references": ["species_001"]
    },
    {
      "claim": "Solara and Morthai are eternal rivals",
      "references": ["god_002"]
    }
  ],
  "meta": {
    "created": "2026-01-15",
    "last_modified": "2026-01-30",
    "canon_status": "confirmed"
  }
}
```

The `canon_claims` field is critical -- it extracts discrete, checkable assertions from the narrative lore. These claims are what get embedded and compared.

### PostToolUse Hook Configuration

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write:**/canon/entities/**|Edit:**/canon/entities/**",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/canon/_hooks/consistency_check.py\" \"$TOOL_FILE_PATH\""
          }
        ]
      }
    ]
  }
}
```

---

## Implementation Plan

### Phase 1: Foundation (Build First)

**Goal:** Catch structural and reference errors with zero API cost.

1. **Define JSON schemas** for each entity type (god, species, settlement, event, artifact, etc.)
2. **Create entity registry** -- a master index mapping every entity ID to its name, type, and file path
3. **Write cross-reference validator** -- verify every referenced entity ID exists in the registry
4. **Write schema validator** -- validate every entity file against its schema on save
5. **Configure PostToolUse hook** to run validators after any canon file edit

**Catches:**
- Missing required fields
- Invalid field types
- References to non-existent entities
- Malformed data

**Estimated effort:** 1-2 days. Claude Code can generate all of this from a description.

### Phase 2: Rule-Based Checks (Build Second)

**Goal:** Catch known contradiction patterns deterministically.

1. **Numerical consistency** -- extract all numerical claims and cross-check:
   - Lifespans (species lifespan vs. character ages vs. lore references)
   - Dates and timelines (event ordering, duration consistency)
   - Distances and geography (travel times vs. stated distances)
2. **Category exclusivity** -- enforce mutual exclusion rules:
   - A species cannot be both mortal and immortal
   - A god cannot be both active and deceased (unless explicitly "resurrected")
   - A settlement cannot be in two regions simultaneously
3. **Relationship symmetry** -- if A is B's rival, B should reference A
4. **Domain uniqueness** -- configurable rules for unique vs. shared attributes

**Catches:**
- "Elves live 500 years" in species file vs. "Elves are immortal" in god file
- Events placed outside their era's date range
- One-directional relationships that should be bidirectional

**Estimated effort:** 2-3 days. Rules are added incrementally as the world grows.

### Phase 3: Semantic Checking (Build Third)

**Goal:** Catch narrative and semantic contradictions that rules cannot express.

1. **Embed all canon_claims** using a local embedding model (sentence-transformers) or Voyage
2. **On new entry:** embed its claims, retrieve top-k most similar existing claims
3. **Send to Claude Haiku** with structured prompt:

```
You are a canon consistency checker for a fictional world.

NEW ENTRY:
{new_entity_json}

POTENTIALLY RELATED EXISTING CANON:
{retrieved_similar_claims_with_source_entities}

Task: Identify any contradictions between the new entry and existing canon.
For each contradiction found, respond with:
- contradiction: (description)
- severity: (critical / warning / info)
- new_claim: (the claim from the new entry)
- existing_claim: (the claim from existing canon)
- source_entity: (which existing entity conflicts)

If no contradictions are found, respond with an empty list.
Respond in JSON format.
```

4. **Filter by confidence** -- only flag contradictions rated "critical" or "warning"
5. **Report results** to the user via hook output

**Catches:**
- Narrative contradictions across distant entries
- Implicit contradictions (logical consequences that conflict)
- Tone/theme inconsistencies (optional, lower severity)

**Estimated effort:** 2-3 days. Requires API key configuration.

### Phase 4: Full Audit Mode (Build Later)

**Goal:** Periodically scan the entire canon for accumulated contradictions.

1. **All-pairs semantic check** using batch API (50% discount)
2. **Contradiction report** with grouped findings
3. **Suggested repairs** preserving maximum canon (per MUS/hitting-set research)
4. **Canon health score** -- percentage of entries with no flagged issues

**Estimated effort:** 1-2 days on top of Phase 3.

---

## Code Examples

### Schema Validation (Phase 1)

```python
# canon/_hooks/validate_schema.py
import json
import sys
from pathlib import Path
from jsonschema import validate, ValidationError

def validate_entity(file_path: str) -> list[str]:
    """Validate an entity file against its schema. Returns list of errors."""
    errors = []
    path = Path(file_path)

    try:
        with open(path) as f:
            entity = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    # Determine entity type from directory
    entity_type = path.parent.name  # e.g., "gods", "species"
    schema_dir = path.parent.parent / "_schema"

    # Map directory name to schema file (plural -> singular)
    type_map = {
        "gods": "god",
        "species": "species",
        "settlements": "settlement",
        "events": "event",
        "artifacts": "artifact",
        "characters": "character",
        "regions": "region",
    }

    schema_name = type_map.get(entity_type, entity_type)
    schema_path = schema_dir / f"{schema_name}.schema.json"

    if not schema_path.exists():
        return [f"No schema found at {schema_path}"]

    with open(schema_path) as f:
        schema = json.load(f)

    try:
        validate(instance=entity, schema=schema)
    except ValidationError as e:
        errors.append(f"Schema violation: {e.message} (at {e.json_path})")

    return errors


if __name__ == "__main__":
    file_path = sys.argv[1]
    errors = validate_entity(file_path)
    if errors:
        for e in errors:
            print(f"SCHEMA ERROR: {e}", file=sys.stderr)
        sys.exit(2)  # Exit code 2 = block in Claude Code hooks
    print("Schema validation passed.")
```

### Cross-Reference Validation (Phase 1-2)

```python
# canon/_hooks/validate_references.py
import json
import sys
from pathlib import Path

def load_entity_registry(canon_dir: Path) -> dict:
    """Load or rebuild the entity registry."""
    registry_path = canon_dir / "_index" / "entity_registry.json"

    if registry_path.exists():
        with open(registry_path) as f:
            return json.load(f)

    # Rebuild from entity files
    registry = {}
    entities_dir = canon_dir / "entities"
    for entity_file in entities_dir.rglob("*.json"):
        with open(entity_file) as f:
            entity = json.load(f)
        if "id" in entity:
            registry[entity["id"]] = {
                "name": entity.get("name", "Unknown"),
                "type": entity_file.parent.name,
                "file": str(entity_file),
            }

    # Save for next time
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)

    return registry


def validate_references(file_path: str) -> list[str]:
    """Check that all entity references in a file point to existing entities."""
    errors = []
    path = Path(file_path)
    canon_dir = path.parent.parent.parent  # entities/type/file -> canon/

    with open(path) as f:
        entity = json.load(f)

    registry = load_entity_registry(canon_dir)

    # Check relationship targets
    for rel in entity.get("relationships", []):
        target_id = rel.get("target_id")
        if target_id and target_id not in registry:
            errors.append(
                f"Reference error: relationship targets '{target_id}' "
                f"which does not exist in the canon registry"
            )

    # Check associated entities (species, settlements, etc.)
    reference_fields = [
        "associated_species", "associated_settlements", "associated_gods",
        "associated_events", "associated_artifacts", "homeland",
        "patron_god", "creator", "ruler", "location",
    ]

    for field in reference_fields:
        value = entity.get(field)
        if value is None:
            continue

        # Handle both single references and lists
        refs = value if isinstance(value, list) else [value]
        for ref_id in refs:
            if isinstance(ref_id, str) and ref_id not in registry:
                errors.append(
                    f"Reference error: '{field}' references '{ref_id}' "
                    f"which does not exist in the canon registry"
                )

    # Check canon_claims references
    for claim in entity.get("canon_claims", []):
        for ref_id in claim.get("references", []):
            if ref_id not in registry:
                errors.append(
                    f"Reference error: canon claim references '{ref_id}' "
                    f"which does not exist in the canon registry"
                )

    return errors


if __name__ == "__main__":
    file_path = sys.argv[1]
    errors = validate_references(file_path)
    if errors:
        for e in errors:
            print(f"REFERENCE ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    print("Reference validation passed.")
```

### Numerical Consistency Check (Phase 2)

```python
# canon/_hooks/validate_numerics.py
import json
import sys
from pathlib import Path

def extract_numeric_claims(entity: dict) -> list[dict]:
    """Extract claims involving numbers from an entity."""
    claims = []

    # Direct numeric fields
    if "lifespan" in entity:
        claims.append({
            "subject": entity.get("id"),
            "property": "lifespan",
            "value": entity["lifespan"],
            "source_field": "lifespan",
        })

    if "mortality" in entity:
        claims.append({
            "subject": entity.get("id"),
            "property": "mortality",
            "value": entity["mortality"],  # "mortal" or "immortal"
            "source_field": "mortality",
        })

    if "founded_year" in entity:
        claims.append({
            "subject": entity.get("id"),
            "property": "founded_year",
            "value": entity["founded_year"],
            "source_field": "founded_year",
        })

    if "population" in entity:
        claims.append({
            "subject": entity.get("id"),
            "property": "population",
            "value": entity["population"],
            "source_field": "population",
        })

    return claims


def check_numeric_consistency(file_path: str) -> list[str]:
    """Cross-check numeric claims against all other entities."""
    errors = []
    path = Path(file_path)
    canon_dir = path.parent.parent.parent
    entities_dir = canon_dir / "entities"

    with open(path) as f:
        new_entity = json.load(f)

    new_claims = extract_numeric_claims(new_entity)

    # Load all other entities and their claims
    for entity_file in entities_dir.rglob("*.json"):
        if entity_file.resolve() == path.resolve():
            continue

        with open(entity_file) as f:
            existing = json.load(f)

        existing_claims = extract_numeric_claims(existing)

        # Check for conflicts on the same subject+property
        for nc in new_claims:
            for ec in existing_claims:
                if nc["subject"] == ec["subject"] and nc["property"] == ec["property"]:
                    if nc["value"] != ec["value"]:
                        errors.append(
                            f"Numeric conflict: {nc['subject']}.{nc['property']} = "
                            f"{nc['value']} in {path.name} but = {ec['value']} "
                            f"in {entity_file.name}"
                        )

        # Special cross-check: mortality vs lifespan
        for nc in new_claims:
            for ec in existing_claims:
                # If new says species is immortal but existing gives finite lifespan
                if (nc["property"] == "mortality" and nc["value"] == "immortal" and
                    ec["subject"] == nc["subject"] and ec["property"] == "lifespan" and
                    isinstance(ec["value"], (int, float))):
                    errors.append(
                        f"Contradiction: {nc['subject']} is marked 'immortal' in "
                        f"{path.name} but has finite lifespan {ec['value']} in "
                        f"{entity_file.name}"
                    )
                # Reverse direction
                if (ec["property"] == "mortality" and ec["value"] == "immortal" and
                    nc["subject"] == ec["subject"] and nc["property"] == "lifespan" and
                    isinstance(nc["value"], (int, float))):
                    errors.append(
                        f"Contradiction: {ec['subject']} is marked 'immortal' in "
                        f"{entity_file.name} but new entry gives finite lifespan "
                        f"{nc['value']} in {path.name}"
                    )

    return errors


if __name__ == "__main__":
    file_path = sys.argv[1]
    errors = check_numeric_consistency(file_path)
    if errors:
        for e in errors:
            print(f"NUMERIC CONFLICT: {e}", file=sys.stderr)
        sys.exit(2)
    print("Numeric consistency check passed.")
```

### LLM Semantic Contradiction Check (Phase 3)

```python
# canon/_hooks/llm_contradiction_check.py
import json
import sys
import os
from pathlib import Path

# Optional: Use sentence-transformers for local embeddings
# from sentence_transformers import SentenceTransformer
# import numpy as np

def get_all_canon_claims(canon_dir: Path, exclude_file: Path) -> list[dict]:
    """Gather all canon claims from all entities except the one being checked."""
    claims = []
    entities_dir = canon_dir / "entities"

    for entity_file in entities_dir.rglob("*.json"):
        if entity_file.resolve() == exclude_file.resolve():
            continue
        with open(entity_file) as f:
            entity = json.load(f)

        entity_name = entity.get("name", entity.get("id", "Unknown"))
        entity_type = entity_file.parent.name

        # Collect explicit canon claims
        for claim in entity.get("canon_claims", []):
            claims.append({
                "claim": claim["claim"],
                "source_entity": entity_name,
                "source_type": entity_type,
                "source_file": str(entity_file),
            })

        # Also include lore_summary as a claim source
        if "lore_summary" in entity:
            claims.append({
                "claim": entity["lore_summary"],
                "source_entity": entity_name,
                "source_type": entity_type,
                "source_file": str(entity_file),
            })

    return claims


def find_relevant_claims(new_entity: dict, all_claims: list[dict], top_k: int = 15) -> list[dict]:
    """Find claims most relevant to the new entity.

    Simple keyword-overlap approach for Phase 3a.
    Replace with embedding similarity for Phase 3b.
    """
    new_text = json.dumps(new_entity, indent=2).lower()
    new_name = new_entity.get("name", "").lower()
    new_id = new_entity.get("id", "").lower()

    scored = []
    for claim in all_claims:
        claim_text = claim["claim"].lower()
        score = 0

        # Boost: claim mentions the new entity by name or ID
        if new_name and new_name in claim_text:
            score += 10
        if new_id and new_id in claim_text:
            score += 10

        # Boost: new entity mentions the claim's source entity
        if claim["source_entity"].lower() in new_text:
            score += 8

        # Keyword overlap
        claim_words = set(claim_text.split())
        new_words = set(new_text.split())
        overlap = len(claim_words & new_words)
        score += overlap

        scored.append((score, claim))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [claim for _, claim in scored[:top_k]]


def check_with_llm(new_entity: dict, relevant_claims: list[dict]) -> list[dict]:
    """Send new entity + relevant claims to Claude Haiku for contradiction check."""
    try:
        import anthropic
    except ImportError:
        print("WARNING: anthropic package not installed. Skipping LLM check.", file=sys.stderr)
        return []

    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    claims_text = "\n".join(
        f"- [{c['source_type']}/{c['source_entity']}]: {c['claim']}"
        for c in relevant_claims
    )

    new_entity_text = json.dumps(new_entity, indent=2)

    prompt = f"""You are a canon consistency checker for a fictional worldbuilding project.
Your job is to identify CONTRADICTIONS between new content and existing established canon.

IMPORTANT RULES:
- Only flag genuine contradictions, not mere additions or elaborations.
- A new detail that adds to existing canon without conflicting is NOT a contradiction.
- Be precise: quote the specific conflicting claims.
- Rate severity: "critical" (direct factual conflict), "warning" (likely conflict, some ambiguity), "info" (potential tension, worth noting).

NEW ENTRY BEING ADDED:
{new_entity_text}

EXISTING CANON CLAIMS (established as true):
{claims_text}

Respond with a JSON array of contradictions found. Each item should have:
- "contradiction": description of the conflict
- "severity": "critical" | "warning" | "info"
- "new_claim": the specific claim from the new entry
- "existing_claim": the specific claim from existing canon
- "source_entity": which existing entity it conflicts with

If no contradictions are found, respond with an empty array: []

Respond ONLY with the JSON array, no other text."""

    response = client.messages.create(
        model="claude-haiku-4-5-20250901",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        result = json.loads(response.content[0].text)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, IndexError):
        return []


def main(file_path: str):
    path = Path(file_path)
    canon_dir = path.parent.parent.parent

    with open(path) as f:
        new_entity = json.load(f)

    # Gather and rank relevant claims
    all_claims = get_all_canon_claims(canon_dir, path)
    relevant = find_relevant_claims(new_entity, all_claims, top_k=15)

    if not relevant:
        print("No existing canon to check against.")
        return

    # Check with LLM
    contradictions = check_with_llm(new_entity, relevant)

    # Filter by severity
    critical = [c for c in contradictions if c.get("severity") == "critical"]
    warnings = [c for c in contradictions if c.get("severity") == "warning"]
    info = [c for c in contradictions if c.get("severity") == "info"]

    if critical:
        print("\n=== CRITICAL CONTRADICTIONS FOUND ===", file=sys.stderr)
        for c in critical:
            print(f"\n  CONFLICT: {c['contradiction']}", file=sys.stderr)
            print(f"  New claim: {c['new_claim']}", file=sys.stderr)
            print(f"  Existing: {c['existing_claim']} (from {c['source_entity']})", file=sys.stderr)
        sys.exit(2)  # Block the edit

    if warnings:
        print("\n=== WARNINGS (not blocking) ===")
        for c in warnings:
            print(f"\n  WARNING: {c['contradiction']}")
            print(f"  New claim: {c['new_claim']}")
            print(f"  Existing: {c['existing_claim']} (from {c['source_entity']})")

    if info:
        print("\n=== INFO ===")
        for c in info:
            print(f"  Note: {c['contradiction']}")

    if not critical and not warnings and not info:
        print("LLM consistency check passed. No contradictions detected.")


if __name__ == "__main__":
    main(sys.argv[1])
```

### Main Hook Orchestrator (All Phases)

```python
# canon/_hooks/consistency_check.py
"""
Main PostToolUse hook for canon consistency checking.
Runs all validation layers in order of cost.
Exit code 2 = block (contradiction found)
Exit code 0 = pass
"""
import sys
import subprocess
from pathlib import Path

def run_check(script: str, file_path: str) -> tuple[int, str, str]:
    """Run a validation script and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, script, file_path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr

def main():
    if len(sys.argv) < 2:
        print("Usage: consistency_check.py <entity_file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    hooks_dir = Path(__file__).parent

    # Ensure the file is a JSON entity file
    if not file_path.endswith(".json"):
        sys.exit(0)  # Not an entity file, skip

    all_stdout = []
    all_stderr = []

    # Layer 1: Schema validation (free, instant)
    schema_script = hooks_dir / "validate_schema.py"
    if schema_script.exists():
        code, stdout, stderr = run_check(str(schema_script), file_path)
        all_stdout.append(stdout)
        if code != 0:
            print(f"BLOCKED by schema validation:\n{stderr}", file=sys.stderr)
            sys.exit(2)

    # Layer 2: Reference validation (free, instant)
    ref_script = hooks_dir / "validate_references.py"
    if ref_script.exists():
        code, stdout, stderr = run_check(str(ref_script), file_path)
        all_stdout.append(stdout)
        if code != 0:
            print(f"BLOCKED by reference validation:\n{stderr}", file=sys.stderr)
            sys.exit(2)

    # Layer 2b: Numeric consistency (free, fast)
    num_script = hooks_dir / "validate_numerics.py"
    if num_script.exists():
        code, stdout, stderr = run_check(str(num_script), file_path)
        all_stdout.append(stdout)
        if code != 0:
            print(f"BLOCKED by numeric consistency:\n{stderr}", file=sys.stderr)
            sys.exit(2)

    # Layer 3: LLM semantic check (costs ~$0.01, takes a few seconds)
    llm_script = hooks_dir / "llm_contradiction_check.py"
    if llm_script.exists():
        code, stdout, stderr = run_check(str(llm_script), file_path)
        all_stdout.append(stdout)
        if code != 0:
            print(f"BLOCKED by LLM contradiction check:\n{stderr}", file=sys.stderr)
            sys.exit(2)

    # All checks passed
    print("\n".join(all_stdout))
    print("All consistency checks passed.")

if __name__ == "__main__":
    main()
```

---

## Cost Projections

| World Size | Adding 1 Entity | Full Audit (Batch) | Monthly (10 additions) |
|-----------|-----------------|-------------------|----------------------|
| 50 entities | ~$0.005 | ~$0.25 | ~$0.05 |
| 200 entities | ~$0.008 | ~$1.00 | ~$0.08 |
| 500 entities | ~$0.01 | ~$2.50 | ~$0.10 |
| 1000 entities | ~$0.015 | ~$5.00 | ~$0.15 |

Layers 1-2 (schema + rules) are always free. Only Layer 3 (LLM) has API cost.

---

## Key Design Decisions

### Why `canon_claims` Is Critical

The most important design choice is requiring every entity to have a `canon_claims` array of discrete, checkable assertions. This serves three purposes:

1. **Forces clarity** -- the worldbuilder must articulate what is actually being established as canon
2. **Enables targeted checking** -- claims can be individually compared rather than comparing entire lore blocks
3. **Creates an audit trail** -- you can trace exactly which claims conflict and where they came from

Without this, the system would be comparing long narrative text blobs, which is both more expensive (more tokens) and less precise (harder to pinpoint the conflict).

### Why Keyword Retrieval Before Embeddings

The Phase 3 code uses simple keyword overlap for finding relevant claims. This is intentional:

1. **Zero dependencies** -- no embedding model needed
2. **Fast to implement** -- works immediately
3. **Surprisingly effective** -- for worldbuilding, the entities that might conflict usually share names, places, or specific terms
4. **Easy to upgrade** -- swap in embedding similarity later without changing the rest of the pipeline

When the world grows past ~200 entities, switch to embedding-based retrieval for better recall.

### Why Block Only on Critical, Not Warnings

The hook exits with code 2 (blocking) only for critical contradictions. Warnings and info are displayed but do not block. This prevents:

1. **False positive frustration** -- LLMs sometimes flag non-issues
2. **Creative paralysis** -- some tensions between entries are intentional (unreliable narrators, mythological contradictions)
3. **Workflow interruption** -- the user can review warnings at their own pace

The user can change this threshold as confidence in the system grows.

---

## Sources

### Academic Research
- [Foundations of Global Consistency Checking with Noisy LLM Oracles (Jan 2026)](https://arxiv.org/html/2601.13600)
- [Contradiction Detection in RAG Systems (Amazon, Mar 2025)](https://arxiv.org/abs/2504.00180)
- [Fact-Checking with Large Language Models (2026 Preprint)](https://www.arxiv.org/pdf/2601.02574)
- [Self-contradictory Hallucinations of LLMs](https://openreview.net/forum?id=EmQSOi1X2f)
- [Targeted Entailment and Contradiction Detection Pipeline (Aug 2025)](https://arxiv.org/abs/2508.17127)
- [Dealing with Inconsistency for Reasoning over Knowledge Graphs: A Survey](https://arxiv.org/html/2502.19023v1)
- [Detecting and Fixing Inconsistencies in Large Knowledge Graphs (2025)](https://journals.sagepub.com/doi/10.1177/30504554251353512)
- [Analysing Large Inconsistent Knowledge Graphs using Anti-Patterns](https://openreview.net/forum?id=hQPNik67InK)
- [Identification of Entailment and Contradiction Relations: A Neurosymbolic Approach](https://arxiv.org/html/2405.01259v1)

### Knowledge Graph Consistency
- [How to Ensure Data Consistency in a Knowledge Graph (Milvus)](https://milvus.io/ai-quick-reference/how-do-you-ensure-data-consistency-in-a-knowledge-graph)
- [Repairing Inconsistencies in Enterprise Knowledge Graphs (Oxford Semantic)](https://www.oxfordsemantic.tech/blog/repairing-inconsistencies-in-data-processing-for-enterprise-knowledge-graphs)
- [Correcting Inconsistencies in KGs with Correlated Knowledge](https://www.sciencedirect.com/science/article/abs/pii/S2214579624000261)

### Claude Code Hooks
- [Hooks Reference - Claude Code Docs](https://code.claude.com/docs/en/hooks)
- [Claude Code Hooks: A Practical Guide (DataCamp)](https://www.datacamp.com/tutorial/claude-code-hooks)
- [Claude Code Hooks Mastery (GitHub)](https://github.com/disler/claude-code-hooks-mastery)
- [Claude Code Hooks for Automated Quality Checks](https://www.letanure.dev/blog/2025-08-06--claude-code-part-8-hooks-automated-quality-checks)
- [Claude Code Hook Development Skill (Official)](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/hook-development/SKILL.md)

### Worldbuilding Tools
- [LegendKeeper](https://www.legendkeeper.com/)
- [Nucanon](https://messari.io/project/nucanon/profile)
- [Artificer DM](https://artificerdm.com/the-game-masters-ultimate-guide-to-the-best-worldbuilding-tools/)
- [Deep Realms](https://www.revoyant.com/blog/deep-realms-the-best-ai-world-building-tool)
- [Sudowrite Worldbuilding](https://sudowrite.com/blog/what-is-the-best-ai-for-worldbuilding-we-tested-the-top-tools/)

### NLI & Embeddings
- [NLI Overview (Emergent Mind)](https://www.emergentmind.com/topics/natural-language-inference-nli)
- [Sentence Transformers NLI Training](https://sbert.net/examples/sentence_transformer/training/nli/README.html)
- [Stanford NLI Corpus](https://nlp.stanford.edu/projects/snli/)
- [Contextual Retrieval (Anthropic)](https://www.anthropic.com/news/contextual-retrieval)

### Pricing
- [Claude API Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Claude Haiku 4.5 Deep Dive (Caylent)](https://caylent.com/blog/claude-haiku-4-5-deep-dive-cost-capabilities-and-the-multi-agent-opportunity)

### JSON Schema
- [JSON Schema Validation Specification](https://json-schema.org/draft/2020-12/json-schema-validation)
- [Python jsonschema Library](https://python-jsonschema.readthedocs.io/en/latest/validate/)
- [Cross-Language Validation Schema (GitHub)](https://github.com/stephan-double-u/cross-language-validation-schema)
