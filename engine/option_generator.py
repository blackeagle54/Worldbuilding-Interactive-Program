"""
engine/option_generator.py -- Divergent-Convergent Option Generation Pipeline

The MOST IMPORTANT system in the Worldbuilding Interactive Program.  At each
decision point it assembles all context needed for Claude to generate 2-4
unique, fully fleshed out, standalone options for the user to choose from.

This module does NOT call an LLM.  It prepares a structured "generation
context" document containing everything Claude needs to produce the actual
creative content:

    - The step's reference material (condensed)
    - All relevant existing canon entities
    - Source tradition assignments per option (from fair_representation)
    - Random concept injections from the concept bank
    - Anti-repetition constraints (themes to avoid)
    - Template fields that need to be filled
    - Guided questions for this step

Think of it as: the option_generator prepares the brief, Claude writes the
creative content.

Pipeline overview:

    PHASE 1 -- DIVERGENT (gather widely)
        Load step guidance, existing canon, option history, random concepts,
        and per-option source assignments.  Produce a generation brief that
        asks for 6-8 raw idea sketches.

    PHASE 2 -- CONVERGENT (filter and select)
        Provide anti-repetition constraints (themes already used), canon
        contradiction avoidance rules, and diversity scoring criteria so
        Claude can winnow down to the best 2-4 ideas.

    PHASE 3 -- FLESH OUT (make each option standalone)
        Specify the output schema so Claude produces title, description,
        canon_connections, future_implications, inspirations, and
        template_data for each selected option.

Usage:
    from engine.option_generator import OptionGenerator

    og = OptionGenerator("C:/Worldbuilding-Interactive-Program")
    context = og.generate_options(step_number=7, num_options=3)
    # ... Claude uses `context` to produce the creative options ...

    og.record_choice(step_number=7, chosen_option_id="opt-a",
                     rationale="I liked the storm court idea")

Dependencies: Python standard library only (json, pathlib, random, datetime, re).
"""

import json
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from engine.utils import safe_read_json as _safe_read_json
from engine.utils import safe_write_json as _safe_write_json


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: str) -> list[dict]:
    """Read a JSONL file and return a list of parsed dicts.

    Silently skips blank or malformed lines.  Returns an empty list if the
    file does not exist.
    """
    entries: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except (FileNotFoundError, OSError):
        pass
    return entries


def _append_jsonl(path: str, record: dict) -> None:
    """Append a single JSON record as a new line to a JSONL file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Option ID generation
# ---------------------------------------------------------------------------

_OPTION_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _option_id(index: int) -> str:
    """Return a short option identifier like ``'opt-a'``, ``'opt-b'``, etc."""
    letter = _OPTION_LETTERS[index % len(_OPTION_LETTERS)]
    return f"opt-{letter}"


# ---------------------------------------------------------------------------
# OptionGenerator
# ---------------------------------------------------------------------------

class OptionGenerator:
    """Divergent-convergent option generation pipeline.

    Assembles all context that Claude needs to generate 2-4 unique,
    fully fleshed out worldbuilding options for a given progression step.

    Parameters
    ----------
    project_root : str
        Absolute path to the Worldbuilding Interactive Program root
        directory, e.g. ``"C:/Worldbuilding-Interactive-Program"``.
    """

    # Number of raw idea sketches to request in the divergent phase.
    RAW_IDEA_COUNT = 8

    # Maximum number of recent history entries to consider for
    # anti-repetition.
    HISTORY_LOOKBACK = 20

    # Number of random concepts to inject per generation cycle.
    CONCEPT_INJECTION_COUNT = 2

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()

        # Paths
        self._state_path = self.root / "user-world" / "state.json"
        self._history_path = self.root / "generation" / "option-history.jsonl"
        self._concept_bank_path = self.root / "generation" / "concept-bank.json"

        # --- Load dependent systems (graceful degradation) ----------------

        # Data Manager
        self._data_manager = None
        try:
            from engine.data_manager import DataManager
            self._data_manager = DataManager(str(self.root))
        except Exception:
            pass

        # Graph Builder
        self._graph = None
        try:
            from engine.graph_builder import WorldGraph
            self._graph = WorldGraph(str(self.root))
            self._graph.build_graph()
        except Exception:
            pass

        # Chunk Puller
        self._chunk_puller = None
        try:
            from engine.chunk_puller import ChunkPuller
            self._chunk_puller = ChunkPuller(str(self.root))
        except Exception:
            pass

        # Fair Representation
        self._fair_rep = None
        try:
            from engine.fair_representation import FairRepresentationManager
            self._fair_rep = FairRepresentationManager(str(self._state_path))
        except Exception:
            pass

        # Bookkeeper (optional -- used in record_choice)
        self._bookkeeper = None
        try:
            from engine.bookkeeper import BookkeepingManager
            bookkeeping_root = self.root / "bookkeeping"
            if bookkeeping_root.exists():
                self._bookkeeper = BookkeepingManager(str(bookkeeping_root))
        except Exception:
            pass

        # --- Load static data ---------------------------------------------

        self._concept_bank: dict = self._load_concept_bank()
        self._all_concepts: list[str] = self._flatten_concepts()

    # ------------------------------------------------------------------
    # Concept bank loading
    # ------------------------------------------------------------------

    def _load_concept_bank(self) -> dict:
        """Load the concept bank JSON file."""
        data = _safe_read_json(str(self._concept_bank_path), default={})
        return data.get("concepts", {})

    def _flatten_concepts(self) -> list[str]:
        """Return a flat list of every concept across all categories."""
        flat: list[str] = []
        for _category, words in self._concept_bank.items():
            if isinstance(words, list):
                flat.extend(words)
        return flat

    def _pick_random_concepts(self, count: int = 2) -> list[dict]:
        """Select *count* random concepts from the bank.

        Returns a list of dicts with ``concept`` and ``category`` keys.
        """
        if not self._all_concepts:
            return []

        picks: list[dict] = []
        used_concepts: set[str] = set()
        attempts = 0
        max_attempts = count * 10

        while len(picks) < count and attempts < max_attempts:
            attempts += 1
            concept = random.choice(self._all_concepts)
            if concept in used_concepts:
                continue
            used_concepts.add(concept)

            # Find which category it belongs to
            category = "unknown"
            for cat, words in self._concept_bank.items():
                if isinstance(words, list) and concept in words:
                    category = cat
                    break

            picks.append({"concept": concept, "category": category})

        return picks

    # ------------------------------------------------------------------
    # State and history loading
    # ------------------------------------------------------------------

    def _load_state(self) -> dict:
        """Load user-world/state.json."""
        return _safe_read_json(str(self._state_path), default={
            "current_step": 1,
            "current_phase": "foundation",
            "completed_steps": [],
            "in_progress_steps": [],
            "entity_index": {},
        })

    def get_option_history(self, last_n: int = 20) -> list[dict]:
        """Return the last *last_n* entries from option-history.jsonl.

        Parameters
        ----------
        last_n : int
            Maximum number of recent entries to return (most recent last).

        Returns
        -------
        list[dict]
            History entries, each containing step, options, choice, themes,
            and timestamp.
        """
        all_entries = _read_jsonl(str(self._history_path))
        if last_n and last_n > 0:
            return all_entries[-last_n:]
        return all_entries

    def get_used_themes(self, last_n: int = 20) -> list[str]:
        """Extract themes and concepts from recent option history.

        Scans the last *last_n* history entries and collects all recorded
        themes, concept injections, and option titles.  The result is a
        deduplicated list of strings that the generation pipeline should
        avoid repeating.

        Parameters
        ----------
        last_n : int
            How many recent history entries to examine.

        Returns
        -------
        list[str]
            A deduplicated list of previously used themes and concepts.
        """
        history = self.get_option_history(last_n)
        themes: list[str] = []
        seen: set[str] = set()

        for entry in history:
            # Themes explicitly tracked
            for theme in entry.get("themes_used", []):
                t = theme.strip().lower()
                if t and t not in seen:
                    themes.append(theme.strip())
                    seen.add(t)

            # Random concepts that were injected
            for concept in entry.get("random_concepts_used", []):
                c = concept.strip().lower() if isinstance(concept, str) else ""
                if c and c not in seen:
                    themes.append(concept.strip())
                    seen.add(c)

            # Option titles (to avoid reusing similar names)
            for opt in entry.get("options_presented", []):
                title = opt.get("title", "")
                t = title.strip().lower()
                if t and t not in seen:
                    themes.append(title.strip())
                    seen.add(t)

        return themes

    # ------------------------------------------------------------------
    # Canon context gathering
    # ------------------------------------------------------------------

    def _gather_canon_entities(self, step_number: int) -> dict:
        """Gather all existing canon entities relevant to a step.

        Returns a dict with:
            - ``all_entities``: summary list of every entity
            - ``related_entities``: entities connected to this step's type
            - ``entity_count_by_type``: counts by entity type
            - ``most_connected``: the most-connected entities in the graph
        """
        result = {
            "all_entities": [],
            "related_entities": [],
            "entity_count_by_type": {},
            "most_connected": [],
        }

        # Gather from data manager
        if self._data_manager:
            try:
                all_entities = self._data_manager.list_entities()
                result["all_entities"] = all_entities

                # Count by type
                type_counts: dict[str, int] = {}
                for ent in all_entities:
                    etype = ent.get("entity_type", "unknown")
                    type_counts[etype] = type_counts.get(etype, 0) + 1
                result["entity_count_by_type"] = type_counts
            except Exception:
                pass

        # Gather from graph
        if self._graph:
            try:
                # Entities created at this step
                step_entities = self._graph.get_entities_for_step(step_number)
                # Most connected entities (world's key nodes)
                most_connected = self._graph.get_most_connected(top_n=10)
                result["most_connected"] = most_connected

                # For related entities, get neighbors of step entities
                related_ids: set[str] = set()
                for eid in step_entities:
                    neighbors = self._graph.get_neighbors(eid, depth=2)
                    related_ids.update(neighbors)

                # Also include entities from adjacent steps (step-1, step+1)
                for adj_step in [step_number - 1, step_number + 1]:
                    if adj_step >= 1:
                        adj_entities = self._graph.get_entities_for_step(adj_step)
                        related_ids.update(adj_entities)

                # Load details for related entities
                related_details: list[dict] = []
                for rid in sorted(related_ids):
                    if rid in self._graph.graph:
                        node_data = self._graph.graph.nodes[rid]
                        related_details.append({
                            "id": rid,
                            "name": node_data.get("name", rid),
                            "entity_type": node_data.get("entity_type", ""),
                            "status": node_data.get("status", "draft"),
                        })
                result["related_entities"] = related_details
            except Exception:
                pass

        # Fallback: if no graph, try state.json directly
        if not result["all_entities"]:
            state = self._load_state()
            entity_index = state.get("entity_index", {})
            for eid, meta in entity_index.items():
                entry = dict(meta)
                entry["id"] = eid
                result["all_entities"].append(entry)
            type_counts = {}
            for ent in result["all_entities"]:
                etype = ent.get("entity_type", "unknown")
                type_counts[etype] = type_counts.get(etype, 0) + 1
            result["entity_count_by_type"] = type_counts

        return result

    def _gather_canon_claims(self) -> list[str]:
        """Collect all canon claims from existing entities.

        Returns a list of claim strings that new options must not contradict.
        """
        claims: list[str] = []

        if not self._data_manager:
            return claims

        try:
            all_entities = self._data_manager.list_entities()
            for ent_summary in all_entities:
                eid = ent_summary.get("id", "")
                if not eid:
                    continue
                try:
                    entity = self._data_manager.get_entity(eid)
                    for claim_entry in entity.get("canon_claims", []):
                        claim_text = claim_entry.get("claim", "") if isinstance(claim_entry, dict) else str(claim_entry)
                        if claim_text:
                            claims.append(claim_text)
                except Exception:
                    continue
        except Exception:
            pass

        return claims

    # ------------------------------------------------------------------
    # Step guidance gathering
    # ------------------------------------------------------------------

    def _gather_step_guidance(self, step_number: int) -> dict:
        """Gather the step's reference material from the chunk puller.

        Returns a dict with condensed guidance, guided questions, template
        info, and dependency status.
        """
        guidance = {
            "condensed_text": "",
            "guided_questions": [],
            "template_info": {},
            "book_quotes": [],
            "references_summary": "",
            "step_info": {
                "number": step_number,
                "title": f"Step {step_number}",
                "phase": 1,
                "phase_name": "",
            },
        }

        if not self._chunk_puller:
            return guidance

        try:
            # Get condensed guidance (compact version for context injection)
            guidance["condensed_text"] = self._chunk_puller.pull_condensed(step_number)

            # Get full guidance for richer context
            full = self._chunk_puller.pull_guidance(step_number)

            guidance["step_info"] = full.get("step", guidance["step_info"])

            # Book quotes
            layer1 = full.get("layer1_book", {})
            quotes = layer1.get("quotes", [])
            guidance["book_quotes"] = [
                {
                    "text": q.get("text", "")[:500],  # truncate for context
                    "context": q.get("context", ""),
                }
                for q in quotes[:5]
            ]

            # Template/actionable info
            layer3 = full.get("layer3_actionable", {})
            guidance["template_info"] = {
                "template_id": layer3.get("template_id"),
                "entity_type": layer3.get("entity_type", ""),
                "is_multi_instance": layer3.get("is_multi_instance", False),
                "required_fields": layer3.get("required_fields", []),
                "recommended_fields": layer3.get("recommended_fields", []),
                "optional_fields": layer3.get("optional_fields", []),
                "cross_references": layer3.get("cross_references", []),
                "minimum_count": layer3.get("minimum_count", 0),
                "existing_count": layer3.get("existing_count", 0),
                "existing_entities": layer3.get("existing_entities", []),
            }

            guidance["guided_questions"] = layer3.get("guided_questions", [])

            # References summary: build a compact summary of what databases
            # had relevant material
            layer2 = full.get("layer2_references", {})
            ref_parts: list[str] = []
            for featured in layer2.get("featured_mythologies", []):
                db_name = featured.get("database_name", "")
                section = featured.get("section", "")
                if db_name:
                    ref_parts.append(f"{db_name}: {section}")
            for featured in layer2.get("featured_authors", []):
                db_name = featured.get("database_name", "")
                section = featured.get("section", "")
                if db_name:
                    ref_parts.append(f"{db_name}: {section}")
            if ref_parts:
                guidance["references_summary"] = "; ".join(ref_parts)

        except Exception:
            pass

        return guidance

    # ------------------------------------------------------------------
    # Source assignment
    # ------------------------------------------------------------------

    def _assign_sources(self, num_options: int) -> list[dict]:
        """Assign unique source-database combinations per option.

        Uses the fair representation system to ensure each option draws
        from different mythological and authorial traditions.

        Returns a list of dicts, one per option, each containing
        ``primary_mythology``, ``primary_author``, and ``secondary``.
        """
        if self._fair_rep:
            try:
                assignments = self._fair_rep.select_option_sources(num_options)
                self._fair_rep.save_state()
                return assignments
            except Exception:
                pass

        # Fallback: simple random assignment from known database lists
        mythologies = [
            "greek", "roman", "norse", "celtic", "chinese",
            "japanese", "native-american", "mesopotamian", "hindu", "biblical",
        ]
        authors = [
            "tolkien", "martin", "rothfuss", "berg", "lovecraft", "jordan",
        ]

        random.shuffle(mythologies)
        random.shuffle(authors)

        assignments: list[dict] = []
        for i in range(num_options):
            assignments.append({
                "primary_mythology": mythologies[i % len(mythologies)],
                "primary_author": authors[i % len(authors)],
                "secondary": [
                    mythologies[(i + 1) % len(mythologies)],
                    authors[(i + 1) % len(authors)],
                ],
            })
        return assignments

    # ------------------------------------------------------------------
    # Template fields extraction
    # ------------------------------------------------------------------

    def _extract_template_fields(self, step_number: int) -> dict:
        """Extract the template field names and types for this step.

        Returns a dict mapping field names to their descriptions and types,
        suitable for pre-filling in option template_data.
        """
        fields: dict[str, dict] = {}

        if not self._chunk_puller:
            return fields

        try:
            layer3 = self._chunk_puller.pull_template_info(step_number)
            for field_desc in layer3.get("required_fields", []):
                # field_desc format: "field_name: Description text"
                parts = field_desc.split(":", 1)
                name = parts[0].strip()
                desc = parts[1].strip() if len(parts) > 1 else name
                fields[name] = {"description": desc, "required": True}

            for field_desc in layer3.get("recommended_fields", []):
                parts = field_desc.split(":", 1)
                name = parts[0].strip()
                desc = parts[1].strip() if len(parts) > 1 else name
                fields[name] = {"description": desc, "required": False}

            for field_desc in layer3.get("optional_fields", []):
                parts = field_desc.split(":", 1)
                name = parts[0].strip()
                desc = parts[1].strip() if len(parts) > 1 else name
                fields[name] = {"description": desc, "required": False}
        except Exception:
            pass

        return fields

    # ==================================================================
    # MAIN PUBLIC METHOD
    # ==================================================================

    def generate_options(
        self,
        step_number: int,
        num_options: int = 3,
        context: dict | None = None,
    ) -> dict:
        """Produce the full generation context for Claude to create options.

        This is the main method.  It assembles everything needed for
        Phases 1-3 of the divergent-convergent pipeline and returns a
        structured document.  Claude reads this document and produces
        the actual creative options.

        Parameters
        ----------
        step_number : int
            The current progression step (1-52).
        num_options : int
            How many final options to request (2-4).  The divergent phase
            will request 6-8 raw sketches regardless, then converge.
        context : dict, optional
            Additional caller-supplied context (e.g. user preferences,
            specific requests).  Merged into the output under
            ``"additional_context"``.

        Returns
        -------
        dict
            A structured generation context document.  See the return
            statement below for the full schema.
        """
        # Clamp num_options to the valid range
        num_options = max(2, min(num_options, 4))

        # --- Gather all inputs -------------------------------------------

        step_guidance = self._gather_step_guidance(step_number)
        canon_entities = self._gather_canon_entities(step_number)
        canon_claims = self._gather_canon_claims()
        used_themes = self.get_used_themes(self.HISTORY_LOOKBACK)
        random_concepts = self._pick_random_concepts(self.CONCEPT_INJECTION_COUNT)
        source_assignments = self._assign_sources(num_options)
        template_fields = self._extract_template_fields(step_number)
        option_history = self.get_option_history(last_n=5)

        # --- Build the structured generation context ----------------------

        step_info = step_guidance.get("step_info", {})
        step_title = step_info.get("title", f"Step {step_number}")
        step_phase = step_info.get("phase", 1)
        step_phase_name = step_info.get("phase_name", "")

        generation_context = {
            # ----- Step metadata -----
            "step": {
                "number": step_number,
                "title": step_title,
                "phase": step_phase,
                "phase_name": step_phase_name,
            },

            # ----- PHASE 1: DIVERGENT (Generate widely) -----
            "divergent_phase": {
                "instructions": (
                    f"Generate {self.RAW_IDEA_COUNT} raw idea sketches (2-3 sentences each) "
                    f"for Step {step_number}: {step_title}. Each sketch should capture a "
                    f"unique creative direction. Each should be inspired by different "
                    f"combinations of the assigned mythological and authorial traditions. "
                    f"Incorporate the injected random concepts where they spark interesting "
                    f"connections. Account for ALL existing canon entities listed below."
                ),
                "raw_idea_count": self.RAW_IDEA_COUNT,

                # Reference material (condensed)
                "step_guidance": {
                    "condensed_text": step_guidance.get("condensed_text", ""),
                    "book_quotes": step_guidance.get("book_quotes", []),
                    "references_summary": step_guidance.get("references_summary", ""),
                    "guided_questions": step_guidance.get("guided_questions", []),
                },

                # Existing canon (must be respected)
                "existing_canon": {
                    "entity_count_by_type": canon_entities.get("entity_count_by_type", {}),
                    "all_entities": [
                        {
                            "id": e.get("id", ""),
                            "name": e.get("name", ""),
                            "entity_type": e.get("entity_type", ""),
                            "status": e.get("status", "draft"),
                        }
                        for e in canon_entities.get("all_entities", [])
                    ],
                    "related_entities": canon_entities.get("related_entities", []),
                    "most_connected": canon_entities.get("most_connected", []),
                    "canon_claims": canon_claims[:100],  # cap to avoid context bloat
                    "total_canon_claims": len(canon_claims),
                },

                # Source tradition assignments (one per final option)
                "source_assignments": source_assignments,

                # Random concept injection
                "random_concepts": random_concepts,
                "concept_injection_instruction": (
                    "Weave the following randomly selected concepts into your "
                    "idea sketches where they create unexpected and interesting "
                    "connections. Not every concept must appear in every sketch, "
                    "but each concept should influence at least 2-3 sketches: "
                    + ", ".join(c["concept"] for c in random_concepts)
                    if random_concepts else
                    "No random concepts were selected for this generation."
                ),
            },

            # ----- PHASE 2: CONVERGENT (Refine and select) -----
            "convergent_phase": {
                "instructions": (
                    f"From the {self.RAW_IDEA_COUNT} raw sketches, select the top "
                    f"{num_options} most diverse, high-quality ideas. Apply the "
                    f"following filters and scoring criteria."
                ),
                "target_count": num_options,

                # Anti-repetition constraints
                "anti_repetition": {
                    "themes_to_avoid": used_themes,
                    "instruction": (
                        "AVOID repeating these themes and concepts from recent "
                        "option history. Each new option should explore territory "
                        "not covered by previous generations: "
                        + ", ".join(used_themes[:30])
                        if used_themes else
                        "No previous option history exists yet. "
                        "All themes are available."
                    ),
                },

                # Canon contradiction avoidance
                "canon_consistency": {
                    "instruction": (
                        "REMOVE any idea that contradicts the existing canon "
                        "claims listed above. Every option must be compatible "
                        "with all established facts about the world."
                    ),
                    "critical_claims_count": len(canon_claims),
                },

                # Diversity scoring criteria
                "diversity_criteria": [
                    "Theme diversity: no two options should explore the same central theme",
                    "Vocabulary diversity: options should use different descriptive language",
                    "Structural diversity: options should suggest different organizational patterns",
                    "Tone diversity: options should range from light to dark, simple to complex",
                    "Cultural diversity: options should draw from different real-world traditions",
                    "Scale diversity: at least one intimate/personal option and one epic/sweeping option",
                ],
            },

            # ----- PHASE 3: FLESH OUT (Make each option standalone) -----
            "flesh_out_phase": {
                "instructions": (
                    f"For each of the {num_options} selected ideas, produce a "
                    f"complete, standalone option with all fields below. Each "
                    f"option must be detailed enough that the user can make an "
                    f"informed choice without needing additional information."
                ),

                # Output schema that Claude must fill
                "output_schema": {
                    "per_option_fields": {
                        "id": "A short identifier (opt-a, opt-b, opt-c, etc.)",
                        "title": "A creative, evocative name for this option (3-8 words)",
                        "description": (
                            "A full description of this option (3-5 paragraphs). "
                            "Vivid, specific, and self-contained. The user should "
                            "be able to visualize exactly what choosing this option "
                            "means for their world."
                        ),
                        "canon_connections": (
                            "A list of specific connections to existing canon entities. "
                            "Reference entities by name and ID. Explain how this option "
                            "relates to, extends, or interacts with what already exists."
                        ),
                        "future_implications": (
                            "A list of 3-5 implications this choice would have for "
                            "future worldbuilding steps. Be specific about which "
                            "steps and what kinds of decisions would be affected."
                        ),
                        "inspirations": {
                            "mythologies": "Which mythological traditions inspired this option and how",
                            "authors": "Which authorial traditions inspired this option and how",
                        },
                        "template_data": (
                            "Pre-filled values for the template fields based on "
                            "this option. The user can accept these or modify them."
                        ),
                    },
                    "option_ids": [_option_id(i) for i in range(num_options)],
                },

                # Template fields to pre-fill
                "template_fields": template_fields,

                # Template info from step guidance
                "template_info": step_guidance.get("template_info", {}),
            },

            # ----- Metadata -----
            "random_concepts_used": [c["concept"] for c in random_concepts],
            "source_assignments": source_assignments,
            "generation_metadata": {
                "generated_at": _now_iso(),
                "raw_ideas_requested": self.RAW_IDEA_COUNT,
                "target_option_count": num_options,
                "canon_entities_loaded": len(canon_entities.get("all_entities", [])),
                "canon_claims_loaded": len(canon_claims),
                "history_entries_checked": len(option_history),
                "themes_to_avoid_count": len(used_themes),
                "concepts_injected": len(random_concepts),
            },

            # Additional caller context
            "additional_context": context or {},
        }

        return generation_context

    # ==================================================================
    # CHOICE RECORDING
    # ==================================================================

    def record_choice(
        self,
        step_number: int,
        chosen_option_id: str,
        rationale: str = "",
        modifications: dict | None = None,
        options_presented: list[dict] | None = None,
        themes_used: list[str] | None = None,
        random_concepts_used: list[str] | None = None,
    ) -> dict:
        """Record the user's choice to option-history.jsonl.

        Also calls the bookkeeper's ``record_decision`` if available.

        Parameters
        ----------
        step_number : int
            The step this choice applies to.
        chosen_option_id : str
            The ID of the option the user chose (e.g. ``"opt-a"``).
        rationale : str
            The user's reason for choosing this option.
        modifications : dict, optional
            Any modifications the user made to the chosen option.
        options_presented : list[dict], optional
            The full list of options that were presented (for history).
            Each should have at least ``id`` and ``title``.
        themes_used : list[str], optional
            Themes/concepts that appeared in the generated options
            (tracked for anti-repetition).
        random_concepts_used : list[str], optional
            The random concepts that were injected in this generation.

        Returns
        -------
        dict
            The history record that was written.
        """
        record = {
            "timestamp": _now_iso(),
            "step_number": step_number,
            "chosen_option_id": chosen_option_id,
            "rationale": rationale,
            "modifications": modifications or {},
            "options_presented": options_presented or [],
            "themes_used": themes_used or [],
            "random_concepts_used": random_concepts_used or [],
        }

        # Append to option-history.jsonl
        _append_jsonl(str(self._history_path), record)

        # Record in bookkeeper if available
        if self._bookkeeper:
            try:
                # Build the options list in the format the bookkeeper expects
                bk_options = []
                for opt in (options_presented or []):
                    bk_options.append({
                        "name": opt.get("id", opt.get("title", "")),
                        "description": opt.get("title", ""),
                    })

                chosen_name = chosen_option_id
                # Try to find the title for the chosen option
                for opt in (options_presented or []):
                    if opt.get("id") == chosen_option_id:
                        chosen_name = opt.get("title", chosen_option_id)
                        break

                self._bookkeeper.record_decision(
                    step_id=f"step-{step_number:02d}",
                    question=f"Option selection for Step {step_number}",
                    options=bk_options,
                    chosen=chosen_name,
                    rationale=rationale,
                )
            except Exception:
                pass  # Bookkeeper failure should not block recording

        return record

    # ==================================================================
    # CONVENIENCE METHODS
    # ==================================================================

    def get_generation_summary(self, step_number: int) -> str:
        """Return a compact text summary of what will be generated.

        Useful for displaying to the user before generation begins.

        Parameters
        ----------
        step_number : int
            The progression step.

        Returns
        -------
        str
            A human-readable summary of the generation parameters.
        """
        state = self._load_state()
        canon_count = len(state.get("entity_index", {}))
        history_count = len(self.get_option_history())
        used_themes = self.get_used_themes()

        lines: list[str] = [
            f"[OPTION GENERATION CONTEXT]",
            f"Step: {step_number}",
            f"Existing canon entities: {canon_count}",
            f"Previous generation cycles: {history_count}",
            f"Themes to avoid (anti-repetition): {len(used_themes)}",
        ]

        if self._fair_rep:
            try:
                stats = self._fair_rep.get_usage_stats()
                least_used = sorted(stats.items(), key=lambda x: x[1])[:3]
                lines.append(
                    f"Least-featured databases: "
                    + ", ".join(f"{name} ({count}x)" for name, count in least_used)
                )
            except Exception:
                pass

        return "\n".join(lines)

    def reload(self) -> None:
        """Reload all dependent systems from disk.

        Call this if external changes have been made to entity files,
        state.json, or the concept bank since the OptionGenerator was
        created.
        """
        # Reload data manager state
        if self._data_manager:
            try:
                self._data_manager.reload_state()
            except Exception:
                pass

        # Rebuild graph
        if self._graph:
            try:
                self._graph.build_graph()
            except Exception:
                pass

        # Reload concept bank
        self._concept_bank = self._load_concept_bank()
        self._all_concepts = self._flatten_concepts()


# ---------------------------------------------------------------------------
# Module-level convenience factory
# ---------------------------------------------------------------------------

def create_option_generator(
    project_root: str = "C:/Worldbuilding-Interactive-Program",
) -> OptionGenerator:
    """Create and return an OptionGenerator with the default project root.

    Parameters
    ----------
    project_root : str
        Path to the project root.  Defaults to the standard location.

    Returns
    -------
    OptionGenerator
    """
    return OptionGenerator(project_root)
