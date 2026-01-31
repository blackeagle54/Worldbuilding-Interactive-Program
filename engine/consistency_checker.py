"""
engine/consistency_checker.py -- Three-Layer Consistency Validation

Validates every entity write against three layers of checks:

    Layer 1 (Schema):   JSON Schema validation -- instant, free.
    Layer 2 (Rules):    Rule-based cross-reference and logical checks -- instant, free.
    Layer 3 (Semantic): Prepares context for LLM semantic contradiction detection.
                        Does NOT call an LLM directly; it builds a structured
                        comparison document that a Claude Code sub-agent can use.

Design decisions (from docs/decisions.md):
    - Layer 3 uses Claude Code sub-agents, NOT external API calls.
    - No API keys needed, no external infrastructure.
    - The consistency_checker prepares the context; Claude does the analysis.
    - Layers 1 and 2 are free and instant (pure Python).

Usage:
    from engine.consistency_checker import ConsistencyChecker

    cc = ConsistencyChecker("C:/Worldbuilding-Interactive-Program")
    result = cc.check_entity(entity_id_or_data, template_id="god-profile")
    # result["passed"]         -> True/False
    # result["human_message"]  -> Friendly summary for a non-technical user
"""

import json
import os
import re
import time
from collections import Counter
from pathlib import Path

from engine.models.factory import ModelFactory as _ModelFactory
from engine.utils import safe_read_json as _safe_read_json
from engine.utils import extract_referenced_ids as _extract_referenced_ids_util


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens for keyword matching.

    Strips punctuation and common stop words to focus on content words
    that carry semantic meaning for worldbuilding entities.
    """
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "has", "have", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "can", "could", "of", "in", "to", "for",
        "with", "on", "at", "from", "by", "about", "as", "into", "through",
        "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
        "neither", "each", "every", "all", "any", "few", "more", "most",
        "other", "some", "such", "no", "only", "own", "same", "than", "too",
        "very", "just", "because", "if", "when", "while", "that", "this",
        "it", "its", "he", "she", "they", "them", "his", "her", "their",
        "which", "who", "whom", "what", "where", "how", "also", "then",
    }
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in stop_words and len(t) > 1]


def _keyword_similarity(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Compute Jaccard similarity between two token lists.

    Returns a float between 0.0 (no overlap) and 1.0 (identical).
    """
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


# ---------------------------------------------------------------------------
# ConsistencyChecker
# ---------------------------------------------------------------------------

class ConsistencyChecker:
    """Three-layer consistency validation for worldbuilding entities.

    Parameters
    ----------
    project_root : str
        Absolute path to the Worldbuilding Interactive Program root directory,
        e.g. ``"C:/Worldbuilding-Interactive-Program"``.
    """

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.entities_dir = self.root / "user-world" / "entities"
        self.state_path = self.root / "user-world" / "state.json"
        self.templates_dir = self.root / "templates"
        self.registry_path = self.root / "engine" / "template_registry.json"

        # Load template registry for quick template lookups
        self._registry: dict = self._load_registry()
        # Cache of loaded template schemas keyed by template $id
        self._schema_cache: dict[str, dict] = {}
        # Cache of all existing entities (loaded lazily, auto-expires after 30s)
        self._entity_cache: dict[str, dict] | None = None
        self._entity_cache_time: float = 0.0
        self._entity_cache_ttl: float = 30.0  # seconds
        # Lazy-loaded Pydantic model factory
        self._model_factory: _ModelFactory | None = None

    def _get_model_factory(self) -> _ModelFactory:
        """Return the shared Pydantic ModelFactory (lazy-loaded)."""
        if self._model_factory is None:
            self._model_factory = _ModelFactory(str(self.root))
        return self._model_factory

    # ------------------------------------------------------------------
    # Internal loaders
    # ------------------------------------------------------------------

    def _load_registry(self) -> dict:
        """Load template_registry.json. Returns a dict keyed by template id."""
        data = _safe_read_json(str(self.registry_path), default={})
        templates = data.get("templates", {})
        if isinstance(templates, list):
            return {t["id"]: t for t in templates if "id" in t}
        if isinstance(templates, dict):
            return templates
        return {}

    def _get_template_schema(self, template_id: str) -> dict | None:
        """Load a template JSON schema by its ``$id``.

        Returns ``None`` if the template cannot be found.
        """
        if template_id in self._schema_cache:
            return self._schema_cache[template_id]

        # Strategy 1: look up file path in registry
        if template_id in self._registry:
            rel_path = self._registry[template_id].get("file", "")
            if rel_path:
                full_path = self.root / rel_path
                schema = _safe_read_json(str(full_path))
                if schema:
                    self._schema_cache[template_id] = schema
                    return schema

        # Strategy 2: scan all template files for matching $id
        if self.templates_dir.exists():
            for json_path in sorted(self.templates_dir.rglob("*.json")):
                schema = _safe_read_json(str(json_path))
                if schema and schema.get("$id") == template_id:
                    self._schema_cache[template_id] = schema
                    return schema

        return None

    def _load_state(self) -> dict:
        """Load user-world/state.json."""
        return _safe_read_json(str(self.state_path), default={})

    def _load_all_entities(self) -> dict[str, dict]:
        """Load every entity JSON file under user-world/entities/.

        Returns a dict keyed by entity ID. Results are cached after
        the first call; call ``_invalidate_entity_cache()`` to force
        a reload.  Cache auto-expires after ``_entity_cache_ttl`` seconds
        to prevent stale reads during long-running sessions.
        """
        # Auto-expire stale cache
        if (
            self._entity_cache is not None
            and (time.monotonic() - self._entity_cache_time) > self._entity_cache_ttl
        ):
            self._entity_cache = None

        if self._entity_cache is not None:
            return self._entity_cache

        entities: dict[str, dict] = {}
        if not self.entities_dir.exists():
            self._entity_cache = entities
            return entities

        for json_path in self.entities_dir.rglob("*.json"):
            data = _safe_read_json(str(json_path))
            if not data:
                continue
            meta = data.get("_meta", {})
            entity_id = meta.get("id") or data.get("id")
            if entity_id:
                entities[entity_id] = data

        self._entity_cache = entities
        self._entity_cache_time = time.monotonic()
        return entities

    def invalidate_cache(self) -> None:
        """Force the entity cache to reload on next access.

        Call this after creating, updating, or deleting entities
        if you need the consistency checker to see the latest data.
        """
        self._entity_cache = None

    # Keep the old private name for internal callers
    _invalidate_entity_cache = invalidate_cache

    def _get_all_canon_claims(self) -> list[dict]:
        """Collect all canon_claims from every existing entity.

        Returns a flat list of dicts, each with keys:
        ``entity_id``, ``entity_name``, ``claim``, ``references``.
        """
        all_claims: list[dict] = []
        entities = self._load_all_entities()
        for entity_id, entity_data in entities.items():
            entity_name = entity_data.get("name", entity_id)
            for claim_obj in entity_data.get("canon_claims", []):
                if isinstance(claim_obj, dict):
                    all_claims.append({
                        "entity_id": entity_id,
                        "entity_name": entity_name,
                        "claim": claim_obj.get("claim", ""),
                        "references": claim_obj.get("references", []),
                    })
                elif isinstance(claim_obj, str):
                    all_claims.append({
                        "entity_id": entity_id,
                        "entity_name": entity_name,
                        "claim": claim_obj,
                        "references": [],
                    })
        return all_claims

    # ------------------------------------------------------------------
    # Schema cleaning (reuses DataManager's approach)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Cross-reference extraction from schema
    # ------------------------------------------------------------------

    def _extract_referenced_ids(self, entity: dict, schema: dict) -> list[tuple[str, str]]:
        """Walk an entity and its schema to find all cross-referenced entity IDs.

        Delegates to the consolidated ``engine.utils.extract_referenced_ids``.
        Returns a list of ``(referenced_entity_id, field_name)`` tuples.
        """
        return _extract_referenced_ids_util(entity, schema)

    # ------------------------------------------------------------------
    # Layer 1: Schema Validation
    # ------------------------------------------------------------------

    def check_schema(self, entity_data: dict, template_id: str) -> dict:
        """Layer 1: Validate entity data against its Pydantic model.

        This is instant and free. It checks:
        - Required fields are present
        - Field types are correct
        - Enum values are valid
        - Array minimum lengths are met

        Parameters
        ----------
        entity_data : dict
            The entity's field values.  May include ``_meta``, ``id``,
            etc. -- they are handled transparently.
        template_id : str
            The ``$id`` of the template schema to validate against.

        Returns
        -------
        dict
            ``{"passed": bool, "errors": [human-readable strings]}``
        """
        factory = self._get_model_factory()
        result = factory.validate_entity(entity_data, template_id)
        return result.to_dict()

    # ------------------------------------------------------------------
    # Layer 2: Rule-Based Cross-Reference Checks
    # ------------------------------------------------------------------

    def check_rules(self, entity_data: dict, entity_id: str | None = None) -> dict:
        """Layer 2: Rule-based cross-reference and logical consistency checks.

        This is instant and free (pure Python). It checks:
        - All referenced entity IDs actually exist
        - Relationships are bidirectional where required
        - Numerical values are consistent (dates, lifespans, populations)
        - Category exclusions are respected (mortal vs immortal, etc.)

        Parameters
        ----------
        entity_data : dict
            The full entity document (may include ``_meta`` and ``canon_claims``).
        entity_id : str, optional
            The entity's ID. If ``None``, extracted from ``entity_data``.

        Returns
        -------
        dict
            ``{"passed": bool, "errors": [human-readable strings]}``
        """
        errors: list[str] = []
        entity_name = entity_data.get("name", "this entity")

        if entity_id is None:
            entity_id = entity_data.get("_meta", {}).get("id") or entity_data.get("id", "")

        # Determine template schema for cross-reference extraction
        template_id = entity_data.get("_meta", {}).get("template_id", "")
        schema = self._get_template_schema(template_id) if template_id else None

        # Load all existing entities for reference checks
        existing = self._load_all_entities()

        # ---- Check 1: Referenced entity IDs must exist ----
        if schema:
            refs = self._extract_referenced_ids(entity_data, schema)
            for ref_id, field_name in refs:
                if ref_id and ref_id not in existing:
                    # Allow self-references during creation (the entity might
                    # not be saved yet).
                    if ref_id == entity_id:
                        continue
                    clean_field = field_name.replace("_", " ").replace(".", " > ")
                    errors.append(
                        f"'{entity_name}' references '{ref_id}' in the "
                        f"'{clean_field}' field, but that entity does not exist yet. "
                        f"You can either create '{ref_id}' first, or remove this "
                        f"reference for now and add it later."
                    )

        # ---- Check 2: Bidirectional relationships ----
        errors.extend(self._check_bidirectional_relationships(
            entity_data, entity_id, entity_name, existing
        ))

        # ---- Check 3: Numerical / logical consistency ----
        errors.extend(self._check_numerical_consistency(entity_data, entity_name))

        # ---- Check 4: Category exclusions ----
        errors.extend(self._check_category_exclusions(entity_data, entity_name))

        return {"passed": len(errors) == 0, "errors": errors}

    def _check_bidirectional_relationships(
        self,
        entity_data: dict,
        entity_id: str,
        entity_name: str,
        existing: dict[str, dict],
    ) -> list[str]:
        """Check that relationships that should be bidirectional actually are.

        For example, if God A lists God B as a "spouse", then God B should
        also list God A as a "spouse". Similarly for "sibling", "twin",
        "ally", "rival", and "enemy" relationships.
        """
        errors: list[str] = []
        bidirectional_types = {"spouse", "sibling", "twin", "ally", "rival", "enemy"}

        relationships = entity_data.get("relationships", [])
        if not isinstance(relationships, list):
            return errors

        for rel in relationships:
            if not isinstance(rel, dict):
                continue

            target_id = rel.get("target_id", "")
            rel_type = rel.get("relationship_type", "")

            if not target_id or rel_type not in bidirectional_types:
                continue

            # Check if the target entity exists and has the reciprocal relationship
            target_entity = existing.get(target_id)
            if target_entity is None:
                # Target does not exist -- already caught by Check 1
                continue

            target_name = target_entity.get("name", target_id)
            target_relationships = target_entity.get("relationships", [])
            if not isinstance(target_relationships, list):
                target_relationships = []

            has_reciprocal = False
            for t_rel in target_relationships:
                if not isinstance(t_rel, dict):
                    continue
                t_target = t_rel.get("target_id", "")
                t_type = t_rel.get("relationship_type", "")
                if t_target == entity_id and t_type == rel_type:
                    has_reciprocal = True
                    break

            if not has_reciprocal:
                errors.append(
                    f"'{entity_name}' lists '{target_name}' as a {rel_type}, "
                    f"but '{target_name}' does not list '{entity_name}' as a "
                    f"{rel_type} in return. {rel_type.capitalize()} relationships "
                    f"should go both ways. You may want to update '{target_name}' "
                    f"to add this relationship."
                )

        return errors

    def _check_numerical_consistency(
        self, entity_data: dict, entity_name: str
    ) -> list[str]:
        """Check that numerical values are logically consistent.

        Examples of checks:
        - A founding date should not be in the future relative to other
          established dates.
        - Population values should be non-negative.
        - Lifespans and ages should be non-negative.
        - A settlement's population should not exceed its sovereign power's
          total population.
        """
        errors: list[str] = []

        # Population must be non-negative
        population = entity_data.get("population")
        if population is not None:
            if isinstance(population, (int, float)) and population < 0:
                errors.append(
                    f"'{entity_name}' has a negative population ({population}). "
                    f"Population should be zero or a positive number."
                )

        # Age / lifespan must be non-negative
        for field in ("age", "lifespan", "average_lifespan", "max_lifespan"):
            value = entity_data.get(field)
            if value is not None and isinstance(value, (int, float)) and value < 0:
                clean_field = field.replace("_", " ")
                errors.append(
                    f"'{entity_name}' has a negative {clean_field} ({value}). "
                    f"This should be zero or a positive number."
                )

        # Founding year should not be after dissolution year
        founded = entity_data.get("founded") or entity_data.get("founding_year")
        dissolved = entity_data.get("dissolved") or entity_data.get("dissolution_year")
        if (
            founded is not None
            and dissolved is not None
            and isinstance(founded, (int, float))
            and isinstance(dissolved, (int, float))
            and founded > dissolved
        ):
            errors.append(
                f"'{entity_name}' was founded in year {founded} but dissolved "
                f"in year {dissolved}. The founding date cannot be after the "
                f"dissolution date."
            )

        # Settlement population vs. species breakdown total
        species_breakdown = entity_data.get("species_breakdown")
        if (
            population is not None
            and isinstance(population, (int, float))
            and isinstance(species_breakdown, list)
            and species_breakdown
        ):
            breakdown_total = 0
            for entry in species_breakdown:
                if isinstance(entry, dict):
                    pct = entry.get("percentage", 0)
                    if isinstance(pct, (int, float)):
                        breakdown_total += pct
            if breakdown_total > 0 and abs(breakdown_total - 100) > 5:
                errors.append(
                    f"'{entity_name}' has species breakdown percentages that "
                    f"add up to {breakdown_total}%, which is not close to 100%. "
                    f"Please adjust the percentages so they sum to approximately 100%."
                )

        return errors

    def _check_category_exclusions(
        self, entity_data: dict, entity_name: str
    ) -> list[str]:
        """Check that mutually exclusive categories are respected.

        Examples:
        - A god with god_type "god" and lifespan "mortal" is contradictory.
        - A species marked as "immortal" should not have an average lifespan
          in years (unless it is conditional immortality).
        - An entity cannot simultaneously be both "good" and "evil" alignment.
        """
        errors: list[str] = []

        god_type = entity_data.get("god_type", "")
        lifespan = entity_data.get("lifespan", "")

        # God / half_god with mortal lifespan
        if god_type == "god" and isinstance(lifespan, str):
            lifespan_lower = lifespan.lower()
            if "mortal" in lifespan_lower and "immortal" not in lifespan_lower:
                errors.append(
                    f"'{entity_name}' is listed as a full god but has a mortal "
                    f"lifespan ('{lifespan}'). Full gods are typically immortal "
                    f"or conditionally immortal. If this god can die, consider "
                    f"using 'conditionally immortal' or changing the god type "
                    f"to 'demigod' or 'half_god'."
                )

        # Alignment contradiction: same entity cannot be good AND evil
        alignment = entity_data.get("alignment", "")
        alignment_nuance = entity_data.get("alignment_nuance", "")
        if alignment == "good" and isinstance(alignment_nuance, str):
            nuance_lower = alignment_nuance.lower()
            if "evil" in nuance_lower and "not evil" not in nuance_lower:
                errors.append(
                    f"'{entity_name}' has an alignment of 'good' but the "
                    f"alignment nuance mentions 'evil'. If this is intentional "
                    f"(a complex moral character), consider changing the "
                    f"alignment to 'complex' instead."
                )
        elif alignment == "evil" and isinstance(alignment_nuance, str):
            nuance_lower = alignment_nuance.lower()
            if "good" in nuance_lower and "not good" not in nuance_lower:
                errors.append(
                    f"'{entity_name}' has an alignment of 'evil' but the "
                    f"alignment nuance mentions 'good'. If this is intentional "
                    f"(a complex moral character), consider changing the "
                    f"alignment to 'complex' instead."
                )

        # Species: immortal with a numeric average lifespan
        species_lifespan = entity_data.get("average_lifespan")
        mortality = entity_data.get("mortality", "")
        if (
            isinstance(mortality, str)
            and "immortal" in mortality.lower()
            and "conditional" not in mortality.lower()
            and isinstance(species_lifespan, (int, float))
            and species_lifespan > 0
        ):
            errors.append(
                f"'{entity_name}' is marked as immortal but has an average "
                f"lifespan of {species_lifespan}. Immortal species do not "
                f"have a numeric lifespan. If they can die under certain "
                f"conditions, consider marking them as 'conditionally immortal' "
                f"instead."
            )

        return errors

    # ------------------------------------------------------------------
    # Layer 3: Semantic Check (Context Preparation)
    # ------------------------------------------------------------------

    def check_semantic(self, entity_data: dict, entity_id: str | None = None) -> dict:
        """Layer 3: Prepare context for LLM semantic contradiction detection.

        This does NOT call an LLM directly. It builds a structured comparison
        document that a Claude Code sub-agent can use to detect contradictions
        between the new entity's claims and existing canon.

        Process:
        1. Extract the entity's canon_claims.
        2. Find the top 10-15 most similar existing claims (keyword matching).
        3. Identify obvious keyword-level conflicts.
        4. Build a pre-formatted LLM prompt for Claude sub-agent if needed.

        Parameters
        ----------
        entity_data : dict
            The full entity document (including ``canon_claims``).
        entity_id : str, optional
            The entity's ID. Used to exclude self-matches.

        Returns
        -------
        dict
            A structured comparison document::

                {
                    "passed": True/False,
                    "warnings": [...],
                    "conflicts": [...],
                    "new_claims": [...],
                    "similar_existing_claims": [...],
                    "potential_conflicts": [...],
                    "needs_llm_review": True/False,
                    "llm_prompt": "..." or None
                }
        """
        if entity_id is None:
            entity_id = entity_data.get("_meta", {}).get("id") or entity_data.get("id", "")

        entity_name = entity_data.get("name", "this entity")

        # Step 1: Extract this entity's canon claims
        new_claims = entity_data.get("canon_claims", [])
        if not new_claims:
            return {
                "passed": True,
                "warnings": [],
                "conflicts": [],
                "new_claims": [],
                "similar_existing_claims": [],
                "potential_conflicts": [],
                "needs_llm_review": False,
                "llm_prompt": None,
            }

        # Normalize claims to list of strings
        new_claim_texts = []
        for claim in new_claims:
            if isinstance(claim, dict):
                new_claim_texts.append(claim.get("claim", ""))
            elif isinstance(claim, str):
                new_claim_texts.append(claim)

        # Step 2: Find similar existing claims
        similar = self.find_similar_claims(new_claims, entity_id=entity_id, top_n=15)

        # Step 3: Detect obvious keyword-level conflicts
        potential_conflicts = self._detect_keyword_conflicts(
            new_claim_texts, similar, entity_name
        )

        # Step 4: Determine if LLM review is needed
        needs_llm = len(similar) > 0 and (
            len(potential_conflicts) > 0
            or len(similar) >= 5  # Many similar claims warrant deeper review
        )

        # Build warnings from potential conflicts
        warnings = [c["description"] for c in potential_conflicts]

        # Step 5: Build LLM prompt if needed
        llm_prompt = None
        if needs_llm:
            llm_prompt = self._build_llm_prompt(
                entity_name, new_claim_texts, similar, potential_conflicts
            )

        return {
            "passed": len(potential_conflicts) == 0,
            "warnings": warnings,
            "conflicts": potential_conflicts,
            "new_claims": new_claim_texts,
            "similar_existing_claims": similar,
            "potential_conflicts": potential_conflicts,
            "needs_llm_review": needs_llm,
            "llm_prompt": llm_prompt,
        }

    def find_similar_claims(
        self,
        claims: list,
        entity_id: str | None = None,
        top_n: int = 15,
    ) -> list[dict]:
        """Keyword-based similarity search across all existing canon_claims.

        For each new claim, tokenizes it and compares against all existing
        claims using Jaccard similarity. Returns the *top_n* most similar
        existing claims across all new claims.

        Parameters
        ----------
        claims : list
            The new entity's canon_claims (list of dicts or strings).
        entity_id : str, optional
            If provided, excludes claims from this entity (to avoid
            self-matching when updating an existing entity).
        top_n : int
            How many similar claims to return (default 15).

        Returns
        -------
        list[dict]
            Each dict has: ``entity_id``, ``entity_name``, ``claim``,
            ``similarity_score``, ``matching_keywords``.
        """
        # Normalize new claims to strings
        new_claim_texts = []
        for claim in claims:
            if isinstance(claim, dict):
                new_claim_texts.append(claim.get("claim", ""))
            elif isinstance(claim, str):
                new_claim_texts.append(claim)

        if not new_claim_texts:
            return []

        # Tokenize all new claims
        new_tokens_per_claim = [_tokenize(text) for text in new_claim_texts]
        # Also build a combined token set for broad matching
        all_new_tokens = set()
        for tokens in new_tokens_per_claim:
            all_new_tokens.update(tokens)

        # Collect all existing claims
        all_existing = self._get_all_canon_claims()

        # Score each existing claim
        scored: list[tuple[float, dict, list[str]]] = []
        for existing in all_existing:
            # Skip claims from the same entity
            if entity_id and existing["entity_id"] == entity_id:
                continue

            existing_text = existing["claim"]
            if not existing_text:
                continue

            existing_tokens = _tokenize(existing_text)
            if not existing_tokens:
                continue

            # Find the best similarity against any individual new claim
            best_score = 0.0
            best_matching = []
            for new_tokens in new_tokens_per_claim:
                score = _keyword_similarity(new_tokens, existing_tokens)
                if score > best_score:
                    best_score = score
                    best_matching = sorted(set(new_tokens) & set(existing_tokens))

            # Also check against the combined token set (catches partial overlaps)
            combined_score = _keyword_similarity(list(all_new_tokens), existing_tokens)
            if combined_score > best_score:
                best_score = combined_score
                best_matching = sorted(all_new_tokens & set(existing_tokens))

            if best_score > 0.05:  # Minimum threshold to be considered "similar"
                scored.append((best_score, existing, best_matching))

        # Sort by score descending and take top_n
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, existing, matching in scored[:top_n]:
            results.append({
                "entity_id": existing["entity_id"],
                "entity_name": existing["entity_name"],
                "claim": existing["claim"],
                "similarity_score": round(score, 3),
                "matching_keywords": matching,
            })

        return results

    def _detect_keyword_conflicts(
        self,
        new_claim_texts: list[str],
        similar_claims: list[dict],
        entity_name: str,
    ) -> list[dict]:
        """Detect obvious keyword-level conflicts between new and existing claims.

        Looks for patterns like:
        - Same domain/role assigned to different entities
        - Contradictory relationship statements
        - "Only" / "sole" / "unique" claims that conflict with existing entities

        Returns a list of conflict dicts, each with:
        ``description``, ``new_claim``, ``existing_claim``, ``existing_entity``.
        """
        conflicts: list[dict] = []

        # Extract key attributes from new claims
        for new_text in new_claim_texts:
            new_lower = new_text.lower()

            for existing in similar_claims:
                existing_text = existing["claim"]
                existing_lower = existing_text.lower()
                existing_entity = existing["entity_name"]

                # Skip if same entity name (self-reference)
                if existing_entity.lower() == entity_name.lower():
                    continue

                # Pattern 1: Same unique role/domain
                # e.g., "X's primary domain is storms" vs "Y's primary domain is storms"
                if "primary domain" in new_lower and "primary domain" in existing_lower:
                    new_domain = self._extract_after(new_lower, "primary domain is")
                    existing_domain = self._extract_after(existing_lower, "primary domain is")
                    if (
                        new_domain
                        and existing_domain
                        and new_domain.strip(": ") == existing_domain.strip(": ")
                    ):
                        domain_name = new_domain.strip(": ").strip()
                        conflicts.append({
                            "description": (
                                f"'{entity_name}' has '{domain_name}' as their "
                                f"primary domain, but '{existing_entity}' already "
                                f"has the same primary domain. Two entities sharing "
                                f"the exact same primary domain may cause confusion. "
                                f"Consider giving one of them a different primary "
                                f"domain, or making this a shared domain with a "
                                f"rivalry or hierarchy between them."
                            ),
                            "new_claim": new_text,
                            "existing_claim": existing_text,
                            "existing_entity": existing_entity,
                            "conflict_type": "duplicate_domain",
                        })

                # Pattern 2: "Only" / "sole" / "unique" claims
                uniqueness_words = ["only", "sole", "unique", "single", "one true"]
                for word in uniqueness_words:
                    if word in new_lower and existing["similarity_score"] > 0.3:
                        # Check if the existing claim covers similar territory
                        new_tokens_set = set(_tokenize(new_text))
                        existing_tokens_set = set(_tokenize(existing_text))
                        overlap = new_tokens_set & existing_tokens_set
                        # Strong overlap with a uniqueness claim is suspicious
                        if len(overlap) >= 3:
                            conflicts.append({
                                "description": (
                                    f"'{entity_name}' makes a claim involving "
                                    f"'{word}' that may conflict with an existing "
                                    f"claim about '{existing_entity}'. "
                                    f"Overlapping keywords: {', '.join(sorted(overlap))}. "
                                    f"Please verify these claims are compatible."
                                ),
                                "new_claim": new_text,
                                "existing_claim": existing_text,
                                "existing_entity": existing_entity,
                                "conflict_type": "uniqueness_conflict",
                            })
                            break  # Only flag once per uniqueness word

                # Pattern 3: Contradictory spouse/parent/creator relationships
                rel_types = ["spouse", "parent", "child", "creator", "created by"]
                for rel in rel_types:
                    if rel in new_lower and rel in existing_lower:
                        # Check if they make contradictory claims about the
                        # same relationship target
                        if existing["similarity_score"] > 0.25:
                            new_tokens_set = set(_tokenize(new_text))
                            existing_tokens_set = set(_tokenize(existing_text))
                            overlap = new_tokens_set & existing_tokens_set
                            if len(overlap) >= 3 and entity_name.lower() not in existing_lower:
                                conflicts.append({
                                    "description": (
                                        f"'{entity_name}' and '{existing_entity}' "
                                        f"both make claims about '{rel}' relationships "
                                        f"that may conflict. Please verify that these "
                                        f"relationship claims are consistent with each other."
                                    ),
                                    "new_claim": new_text,
                                    "existing_claim": existing_text,
                                    "existing_entity": existing_entity,
                                    "conflict_type": "relationship_conflict",
                                })
                                break  # Only flag once per relationship type

        # Deduplicate conflicts (same existing entity + same conflict type)
        seen: set[str] = set()
        deduped: list[dict] = []
        for c in conflicts:
            key = f"{c['existing_entity']}|{c['conflict_type']}|{c.get('new_claim', '')}"
            if key not in seen:
                seen.add(key)
                deduped.append(c)

        return deduped

    @staticmethod
    def _extract_after(text: str, marker: str) -> str:
        """Extract the text that follows *marker* in *text*.

        Returns an empty string if the marker is not found.
        """
        idx = text.find(marker)
        if idx == -1:
            return ""
        return text[idx + len(marker):].strip().split(".")[0].strip()

    def _build_llm_prompt(
        self,
        entity_name: str,
        new_claims: list[str],
        similar_claims: list[dict],
        potential_conflicts: list[dict],
    ) -> str:
        """Build a pre-formatted prompt for a Claude Code sub-agent.

        The sub-agent will use this prompt to perform deep semantic
        contradiction detection. This method does NOT call the LLM;
        it just prepares the prompt string.

        Parameters
        ----------
        entity_name : str
            Name of the entity being checked.
        new_claims : list[str]
            The entity's new canon claims.
        similar_claims : list[dict]
            Similar existing claims found by keyword search.
        potential_conflicts : list[dict]
            Keyword-level conflicts already detected.

        Returns
        -------
        str
            A complete prompt string ready for a Claude sub-agent.
        """
        lines = [
            "You are a worldbuilding consistency checker. Your job is to detect ",
            "contradictions between NEW claims about an entity and EXISTING canon ",
            "claims in the user's worldbuilding project.",
            "",
            "Analyze carefully and report any contradictions, logical impossibilities, ",
            "or inconsistencies. Be precise -- only flag real problems, not creative ",
            "choices that are simply unusual.",
            "",
            f"=== NEW ENTITY: {entity_name} ===",
            "",
            "NEW CLAIMS:",
        ]

        for i, claim in enumerate(new_claims, 1):
            lines.append(f"  {i}. {claim}")

        lines.append("")
        lines.append("EXISTING CANON CLAIMS (most similar):")
        for i, sim in enumerate(similar_claims, 1):
            score_pct = int(sim["similarity_score"] * 100)
            lines.append(
                f"  {i}. [{sim['entity_name']}] {sim['claim']} "
                f"(similarity: {score_pct}%)"
            )

        if potential_conflicts:
            lines.append("")
            lines.append("ALREADY-DETECTED KEYWORD CONFLICTS:")
            for i, conflict in enumerate(potential_conflicts, 1):
                lines.append(f"  {i}. {conflict['description']}")

        lines.append("")
        lines.append("YOUR TASK:")
        lines.append("1. Review each new claim against the existing claims.")
        lines.append("2. Identify any CONTRADICTIONS (facts that cannot both be true).")
        lines.append("3. Identify any WARNINGS (facts that are unusual but not impossible).")
        lines.append("4. For each issue, explain what the conflict is and suggest options")
        lines.append("   to resolve it.")
        lines.append("")
        lines.append("Respond with a JSON object:")
        lines.append('{')
        lines.append('  "contradictions": [')
        lines.append('    {"description": "...", "severity": "critical|warning", ')
        lines.append('     "new_claim": "...", "existing_claim": "...", ')
        lines.append('     "suggestions": ["option 1", "option 2"]}')
        lines.append('  ],')
        lines.append('  "passed": true/false')
        lines.append('}')

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Main entry point: check_entity
    # ------------------------------------------------------------------

    def check_entity(
        self,
        entity_id_or_data: str | dict,
        template_id: str | None = None,
    ) -> dict:
        """Run all three validation layers on an entity.

        Layers are run in sequence. If Layer 1 fails, Layers 2 and 3 are
        skipped. If Layer 2 fails, Layer 3 is skipped.

        Parameters
        ----------
        entity_id_or_data : str or dict
            Either an entity ID (string) to load from disk, or a full entity
            data dict (for validating data before it is saved).
        template_id : str, optional
            The template ``$id`` to validate against. Required if
            *entity_id_or_data* is a dict and does not contain ``_meta``.

        Returns
        -------
        dict
            A comprehensive result dict::

                {
                    "passed": True/False,
                    "layer1_schema": {"passed": bool, "errors": [...]},
                    "layer2_rules": {"passed": bool, "errors": [...]},
                    "layer3_semantic": {
                        "passed": bool,
                        "warnings": [...],
                        "conflicts": [...],
                        ...
                    },
                    "human_message": "A friendly summary of any issues"
                }
        """
        # Invalidate the entity cache so cross-reference checks see the
        # latest data (fixes stale-cache bug where newly created entities
        # were invisible to the checker).
        self._invalidate_entity_cache()

        # Resolve entity data
        entity_data: dict
        entity_id: str | None = None

        if isinstance(entity_id_or_data, str):
            # Load from disk
            entity_id = entity_id_or_data
            entity_data = self._load_entity_by_id(entity_id)
            if entity_data is None:
                return self._build_result(
                    layer1={"passed": False, "errors": [
                        f"Could not find the entity '{entity_id}'. It may have "
                        f"been deleted or the ID may be incorrect."
                    ]},
                    layer2=None,
                    layer3=None,
                    entity_name=entity_id,
                )
        else:
            entity_data = entity_id_or_data
            entity_id = (
                entity_data.get("_meta", {}).get("id")
                or entity_data.get("id")
            )

        entity_name = entity_data.get("name", entity_id or "this entity")

        # Determine template_id
        if template_id is None:
            template_id = entity_data.get("_meta", {}).get("template_id", "")

        if not template_id:
            return self._build_result(
                layer1={"passed": False, "errors": [
                    f"Cannot determine which template '{entity_name}' belongs to. "
                    f"Please specify a template_id so the data can be validated."
                ]},
                layer2=None,
                layer3=None,
                entity_name=entity_name,
            )

        # ----- Layer 1: Schema Validation -----
        layer1 = self.check_schema(entity_data, template_id)
        if not layer1["passed"]:
            return self._build_result(
                layer1=layer1,
                layer2=None,
                layer3=None,
                entity_name=entity_name,
            )

        # ----- Layer 2: Rule-Based Checks -----
        layer2 = self.check_rules(entity_data, entity_id=entity_id)
        if not layer2["passed"]:
            return self._build_result(
                layer1=layer1,
                layer2=layer2,
                layer3=None,
                entity_name=entity_name,
            )

        # ----- Layer 3: Semantic Check -----
        layer3 = self.check_semantic(entity_data, entity_id=entity_id)

        return self._build_result(
            layer1=layer1,
            layer2=layer2,
            layer3=layer3,
            entity_name=entity_name,
        )

    def _load_entity_by_id(self, entity_id: str) -> dict | None:
        """Load a single entity by ID from the entity files."""
        entities = self._load_all_entities()
        return entities.get(entity_id)

    def _build_result(
        self,
        layer1: dict,
        layer2: dict | None,
        layer3: dict | None,
        entity_name: str,
    ) -> dict:
        """Assemble the final check result from individual layer results."""
        # Default layer results for skipped layers
        skipped_layer2 = {
            "passed": None,
            "errors": ["Skipped (Layer 1 did not pass)"],
        }
        skipped_layer3 = {
            "passed": None,
            "warnings": [],
            "conflicts": [],
            "new_claims": [],
            "similar_existing_claims": [],
            "potential_conflicts": [],
            "needs_llm_review": False,
            "llm_prompt": None,
        }

        if layer2 is None:
            layer2 = skipped_layer2
            if layer1["passed"]:
                layer2["errors"] = ["Skipped (not reached)"]

        if layer3 is None:
            layer3 = skipped_layer3
            if layer2.get("passed") is False:
                # Layer 2 failed, so layer 3 was skipped
                pass
            elif not layer1["passed"]:
                # Layer 1 failed
                pass

        # Overall pass/fail
        overall_passed = (
            layer1["passed"]
            and (layer2.get("passed") is True)
            and (layer3.get("passed", True) is True or layer3.get("passed") is None)
        )

        result = {
            "passed": overall_passed,
            "layer1_schema": layer1,
            "layer2_rules": layer2,
            "layer3_semantic": layer3,
            "human_message": "",
        }

        # Generate human-readable message
        result["human_message"] = self.format_human_message(result, entity_name)

        return result

    # ------------------------------------------------------------------
    # Human-friendly message formatting
    # ------------------------------------------------------------------

    def format_human_message(
        self,
        check_result: dict,
        entity_name: str | None = None,
    ) -> str:
        """Convert technical check results into a friendly message.

        Written for a non-technical user. No Python tracebacks, no JSON
        jargon. Explains what happened, why it matters, and what the
        user can do about it.

        Parameters
        ----------
        check_result : dict
            The result from ``check_entity()``.
        entity_name : str, optional
            The entity's display name (for the message header).

        Returns
        -------
        str
            A human-readable summary of the check results.

        Example output::

            Something went wrong while saving the god 'Thorin Stormkeeper.'

            ISSUE: Thorin is listed as the god of storms, but you already
            have a god of storms -- Kael Thunderborn (created in your last session).

            OPTIONS:
            1. Give Thorin a different primary domain
            2. Make storms a SHARED domain with a rivalry between them
            3. Rename one of them and merge their profiles

            Your data is safe. Nothing was changed.
        """
        if entity_name is None:
            entity_name = "this entity"

        if check_result.get("passed", False):
            return self._format_passed_message(check_result, entity_name)
        else:
            return self._format_failed_message(check_result, entity_name)

    def _format_passed_message(self, check_result: dict, entity_name: str) -> str:
        """Format the message when all checks pass."""
        lines = [f"'{entity_name}' passed all consistency checks."]

        # Include any warnings from Layer 3
        layer3 = check_result.get("layer3_semantic", {})
        warnings = layer3.get("warnings", [])
        if warnings:
            lines.append("")
            lines.append("NOTES (not blocking, just worth reviewing):")
            for i, warning in enumerate(warnings, 1):
                lines.append(f"  {i}. {warning}")

        if layer3.get("needs_llm_review", False):
            lines.append("")
            lines.append(
                "A deeper semantic review is recommended to double-check "
                "for subtle contradictions with existing lore."
            )

        return "\n".join(lines)

    def _format_failed_message(self, check_result: dict, entity_name: str) -> str:
        """Format the message when one or more checks fail."""
        lines = [f"Something went wrong while saving '{entity_name}'."]
        lines.append("")

        # Layer 1 failures
        layer1 = check_result.get("layer1_schema", {})
        if not layer1.get("passed", True):
            layer1_errors = layer1.get("errors", [])
            if len(layer1_errors) == 1:
                lines.append(f"ISSUE: {layer1_errors[0]}")
            else:
                lines.append("ISSUES FOUND:")
                for i, err in enumerate(layer1_errors, 1):
                    lines.append(f"  {i}. {err}")
            lines.append("")
            lines.append(
                "This is a data structure issue -- the information provided "
                "does not match what the template expects. Please review the "
                "fields listed above and try again."
            )
            lines.append("")
            lines.append("Your data is safe. Nothing was changed.")
            return "\n".join(lines)

        # Layer 2 failures
        layer2 = check_result.get("layer2_rules", {})
        if not layer2.get("passed", True):
            layer2_errors = layer2.get("errors", [])
            if len(layer2_errors) == 1:
                lines.append(f"ISSUE: {layer2_errors[0]}")
            else:
                lines.append("ISSUES FOUND:")
                for i, err in enumerate(layer2_errors, 1):
                    lines.append(f"  {i}. {err}")
            lines.append("")
            lines.append("OPTIONS:")
            lines.append("  1. Fix the issues listed above and try again")
            lines.append("  2. Create missing entities first, then come back to this one")
            lines.append("  3. Remove the problematic references for now and add them later")
            lines.append("")
            lines.append("Your data is safe. Nothing was changed.")
            return "\n".join(lines)

        # Layer 3 failures (semantic conflicts)
        layer3 = check_result.get("layer3_semantic", {})
        if not layer3.get("passed", True):
            conflicts = layer3.get("conflicts", []) or layer3.get("potential_conflicts", [])
            if conflicts:
                lines.append("POTENTIAL CONFLICTS WITH EXISTING LORE:")
                lines.append("")
                for i, conflict in enumerate(conflicts, 1):
                    desc = conflict.get("description", str(conflict))
                    lines.append(f"  {i}. {desc}")
                lines.append("")
                lines.append("OPTIONS:")
                lines.append("  1. Modify the new entity to avoid the conflict")
                lines.append("  2. Update the existing entity to accommodate both")
                lines.append("  3. Make this an intentional contradiction (worldbuilding choice)")
                lines.append("  4. Proceed anyway if you believe these are compatible")
                lines.append("")
                lines.append("Your data is safe. Nothing was changed.")
            else:
                lines.append("A potential consistency issue was detected.")
                lines.append("Please review the entity and try again.")
                lines.append("")
                lines.append("Your data is safe. Nothing was changed.")
            return "\n".join(lines)

        # Generic fallback (should not normally reach here)
        lines.append("An unexpected issue was found during validation.")
        lines.append("Please try again or ask for help.")
        lines.append("")
        lines.append("Your data is safe. Nothing was changed.")
        return "\n".join(lines)
