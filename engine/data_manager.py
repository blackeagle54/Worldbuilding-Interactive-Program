"""
engine/data_manager.py -- Entity CRUD Operations for the Worldbuilding Interactive Program

Handles all entity creation, reading, updating, validation, search, and
cross-reference resolution. Every other system in the program calls the
DataManager rather than reading/writing entity files directly.

Usage:
    from engine.data_manager import DataManager

    dm = DataManager("C:/Worldbuilding-Interactive-Program")
    entity_id = dm.create_entity("god-profile", {"name": "Thorin Stormkeeper", ...})
    entity = dm.get_entity(entity_id)
    errors = dm.validate_entity(entity_id)
    refs = dm.get_cross_references(entity_id)
"""

import json
import os
import re
import copy
import secrets
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

try:
    import jsonschema
except ImportError:
    raise ImportError(
        "The 'jsonschema' package is required but not installed. "
        "Install it with: pip install jsonschema"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert a human-readable name to a URL-friendly slug.

    Examples:
        "Thorin Stormkeeper"  -> "thorin-stormkeeper"
        "The Celestial Court" -> "the-celestial-court"
        "Mira's Haven"       -> "miras-haven"
    """
    # Normalize unicode characters to ASCII equivalents where possible
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    # Lowercase
    text = text.lower()
    # Replace any non-alphanumeric character with a hyphen
    text = re.sub(r"[^a-z0-9]+", "-", text)
    # Strip leading/trailing hyphens and collapse runs of hyphens
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def _generate_id(name: str) -> str:
    """Generate a unique entity ID in the format: slugified-name-XXXX.

    The 4-character hex suffix prevents collisions when two entities share
    the same name (unlikely but possible across different entity types).
    """
    slug = _slugify(name)
    if not slug:
        slug = "entity"
    suffix = secrets.token_hex(2)  # 4 hex chars
    return f"{slug}-{suffix}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _safe_read_json(path: str, default=None):
    """Read a JSON file, returning *default* if the file is missing or corrupt."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def _safe_write_json(path: str, data, *, indent: int = 2) -> None:
    """Write JSON to *path*, creating parent directories if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Canon-claims extraction
# ---------------------------------------------------------------------------

def _extract_canon_claims(entity_data: dict, template_schema: dict) -> list:
    """Extract discrete factual claims from an entity's field values.

    Each claim is a short, self-contained statement of fact that the
    consistency checker (Sprint 3) can compare against all other claims
    in the world.  Cross-references are recorded so the checker knows
    which other entities are involved.

    Returns a list of dicts: [{"claim": str, "references": [str, ...]}, ...]
    """
    claims: list[dict] = []
    name = entity_data.get("name", entity_data.get("_meta", {}).get("id", "Unknown"))
    schema_props = template_schema.get("properties", {})

    for field_key, value in entity_data.items():
        # Skip metadata, internal fields, and empty values
        if field_key.startswith("_") or field_key in ("id", "canon_claims"):
            continue
        if value is None or value == "" or value == []:
            continue

        field_schema = schema_props.get(field_key, {})
        field_desc = field_schema.get("description", field_key.replace("_", " "))

        # --- Simple string fields ---
        if isinstance(value, str) and field_key != "name":
            claim_text = f"{name}'s {field_desc.lower().rstrip('.')} is: {value}"
            # Detect if this field is a cross-reference
            refs = []
            if "x-cross-reference" in field_schema:
                refs.append(value)
            claims.append({"claim": claim_text, "references": refs})

        # --- Array of strings ---
        elif isinstance(value, list) and value and isinstance(value[0], str):
            item_schema = field_schema.get("items", {})
            is_xref = "x-cross-reference" in item_schema
            claim_text = f"{name}'s {field_desc.lower().rstrip('.')} includes: {', '.join(str(v) for v in value)}"
            refs = list(value) if is_xref else []
            claims.append({"claim": claim_text, "references": refs})

        # --- Array of objects (relationships, species_breakdown, etc.) ---
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            for idx, item in enumerate(value):
                parts = []
                refs = []
                for sub_key, sub_val in item.items():
                    if sub_val is None or sub_val == "":
                        continue
                    parts.append(f"{sub_key}: {sub_val}")
                    # Check for cross-reference in nested schema
                    item_props = field_schema.get("items", {}).get("properties", {})
                    sub_schema = item_props.get(sub_key, {})
                    if "x-cross-reference" in sub_schema and isinstance(sub_val, str):
                        refs.append(sub_val)
                if parts:
                    claim_text = f"{name} has {field_desc.lower().rstrip('.')} entry: {'; '.join(parts)}"
                    claims.append({"claim": claim_text, "references": refs})

        # --- Nested object (water_supply, leadership, old_town, etc.) ---
        elif isinstance(value, dict):
            parts = []
            for sub_key, sub_val in value.items():
                if sub_val is None or sub_val == "":
                    continue
                parts.append(f"{sub_key}: {sub_val}")
            if parts:
                claim_text = f"{name}'s {field_desc.lower().rstrip('.')} is: {'; '.join(parts)}"
                claims.append({"claim": claim_text, "references": []})

        # --- Numeric / boolean fields ---
        elif isinstance(value, (int, float, bool)):
            claim_text = f"{name}'s {field_desc.lower().rstrip('.')} is {value}"
            claims.append({"claim": claim_text, "references": []})

    return claims


# ---------------------------------------------------------------------------
# DataManager
# ---------------------------------------------------------------------------

class DataManager:
    """Central manager for all entity CRUD operations.

    Parameters
    ----------
    project_root : str
        Absolute path to the Worldbuilding Interactive Program root directory,
        e.g. ``"C:/Worldbuilding-Interactive-Program"``.
    """

    # Mapping from template $id to entity folder name under user-world/entities/
    # Built dynamically from the template registry, but we keep sensible
    # fallbacks derived from the template id itself.
    _TYPE_FOLDER_OVERRIDES: dict[str, str] = {
        # Explicitly map template ids whose folder names differ from a naive
        # slug derivation.  Add more as templates are discovered.
    }

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.entities_dir = self.root / "user-world" / "entities"
        self.state_path = self.root / "user-world" / "state.json"
        self.templates_dir = self.root / "templates"
        self.registry_path = self.root / "engine" / "template_registry.json"
        self.bookkeeping_dir = self.root / "bookkeeping"
        self.snapshots_dir = self.bookkeeping_dir / "revisions" / "snapshots"

        # Load the template registry (maps template_id -> metadata)
        self._registry: dict = self._load_registry()
        # Cache of loaded template schemas keyed by template $id
        self._schema_cache: dict[str, dict] = {}
        # Load state
        self._state: dict = self._load_state()

    # ------------------------------------------------------------------
    # Internal loaders
    # ------------------------------------------------------------------

    def _load_registry(self) -> dict:
        """Load template_registry.json.  Returns the 'templates' dict or
        an empty dict if the file is missing / empty."""
        data = _safe_read_json(str(self.registry_path), default={})
        templates = data.get("templates", {})
        # The registry might be a dict keyed by template id, or a list.
        # Normalise to a dict keyed by template $id.
        if isinstance(templates, list):
            return {t["id"]: t for t in templates if "id" in t}
        if isinstance(templates, dict):
            return templates
        return {}

    def _load_state(self) -> dict:
        """Load user-world/state.json."""
        default_state = {
            "current_step": 1,
            "current_phase": "foundation",
            "completed_steps": [],
            "in_progress_steps": [],
            "entity_index": {},
            "session_log": [],
        }
        state = _safe_read_json(str(self.state_path), default=default_state)
        # Ensure entity_index exists (older state files may lack it)
        if "entity_index" not in state:
            state["entity_index"] = {}
        return state

    def _save_state(self) -> None:
        """Persist the current state to user-world/state.json."""
        _safe_write_json(str(self.state_path), self._state)

    def _get_template_schema(self, template_id: str) -> dict:
        """Load a template JSON schema by its ``$id``.

        The schema is read from the templates/ directory tree and cached.
        Raises ``ValueError`` if the template cannot be found.
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
        for json_path in sorted(self.templates_dir.rglob("*.json")):
            schema = _safe_read_json(str(json_path))
            if schema and schema.get("$id") == template_id:
                self._schema_cache[template_id] = schema
                return schema

        raise ValueError(
            f"Could not find a template with id '{template_id}'. "
            f"Check that the template exists in the templates/ directory "
            f"and that its '$id' field matches."
        )

    def _entity_type_for_template(self, template_id: str) -> str:
        """Determine the entity type (= subfolder name) for a template.

        Checks the registry first, then falls back to a slug derivation
        of the template id.
        """
        if template_id in self._registry:
            meta = self._registry[template_id]
            # entity_folder might be "user-world/entities/gods/"
            folder = meta.get("entity_folder", "")
            if folder:
                # Extract the last meaningful path segment
                parts = [p for p in folder.replace("\\", "/").rstrip("/").split("/") if p]
                if parts:
                    return parts[-1]
            # Or there might be an explicit entity_type
            etype = meta.get("entity_type", "")
            if etype:
                return etype

        # Fallback: derive from template id  (e.g. "god-profile" -> "gods")
        # This is a best-effort heuristic.
        base = template_id.replace("-profile", "").replace("-worksheet", "")
        base = base.replace("-template", "").replace("-overview", "")
        base = base.replace("-catalog", "").replace("-detail", "")
        # Naive pluralisation
        if not base.endswith("s"):
            base += "s"
        return base

    def _entity_folder(self, entity_type: str) -> Path:
        """Return the directory where entities of *entity_type* are stored,
        creating it if necessary."""
        folder = self.entities_dir / entity_type
        os.makedirs(folder, exist_ok=True)
        return folder

    def _entity_path_from_index(self, entity_id: str) -> str | None:
        """Look up the file path of an entity in the state index."""
        entry = self._state.get("entity_index", {}).get(entity_id)
        if entry:
            return entry.get("file_path")
        return None

    def _find_entity_file(self, entity_id: str) -> str | None:
        """Find the JSON file for *entity_id*, searching the index first,
        then falling back to a filesystem scan."""
        # Try index
        path = self._entity_path_from_index(entity_id)
        if path:
            full = self.root / path if not os.path.isabs(path) else Path(path)
            if full.exists():
                return str(full)

        # Fallback: walk entities directory
        for json_path in self.entities_dir.rglob("*.json"):
            data = _safe_read_json(str(json_path))
            if data and data.get("_meta", {}).get("id") == entity_id:
                return str(json_path)

        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_entity(self, template_id: str, data: dict) -> str:
        """Create a new entity from a template.

        Parameters
        ----------
        template_id : str
            The ``$id`` of the template schema (e.g. ``"god-profile"``).
        data : dict
            The entity's field values.  Must satisfy the template's
            ``required`` fields and pass schema validation.

        Returns
        -------
        str
            The auto-generated entity ID (e.g. ``"thorin-stormkeeper-a1b2"``).

        Raises
        ------
        ValueError
            If the template cannot be found.
        jsonschema.ValidationError
            If *data* does not pass schema validation (raised as a
            ``ValueError`` with a friendly message).
        """
        # Load the template schema
        schema = self._get_template_schema(template_id)

        # Validate data against the schema
        errors = self._validate_data(data, schema)
        if errors:
            friendly = self._format_validation_errors(errors, template_id)
            raise ValueError(friendly)

        # Determine entity type and folder
        entity_type = self._entity_type_for_template(template_id)
        folder = self._entity_folder(entity_type)

        # Generate unique ID
        name = data.get("name", template_id)
        entity_id = _generate_id(name)

        # Ensure no collision (extremely unlikely but handle it)
        while self._entity_path_from_index(entity_id) is not None:
            entity_id = _generate_id(name)

        # Build relative file path (relative to project root)
        filename = f"{entity_id}.json"
        file_path_abs = folder / filename
        file_path_rel = str(file_path_abs.relative_to(self.root)).replace("\\", "/")

        # Build _meta section
        now = _now_iso()
        meta = {
            "id": entity_id,
            "template_id": template_id,
            "entity_type": entity_type,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
            "step_created": self._state.get("current_step", None),
            "file_path": file_path_rel,
        }

        # Assemble full entity document
        entity_doc = dict(data)
        entity_doc["_meta"] = meta
        entity_doc["id"] = entity_id

        # Extract canon claims
        entity_doc["canon_claims"] = _extract_canon_claims(data, schema)

        # Write entity file
        _safe_write_json(str(file_path_abs), entity_doc)

        # Update state.json entity index
        self._state.setdefault("entity_index", {})[entity_id] = {
            "template_id": template_id,
            "entity_type": entity_type,
            "name": data.get("name", entity_id),
            "status": "draft",
            "file_path": file_path_rel,
            "created_at": now,
            "updated_at": now,
        }
        self._save_state()

        return entity_id

    def update_entity(self, entity_id: str, data: dict) -> None:
        """Update an existing entity's fields.

        A snapshot of the previous version is saved to
        ``bookkeeping/revisions/snapshots/`` before the update is written.

        Parameters
        ----------
        entity_id : str
            The entity to update.
        data : dict
            A dict of fields to merge into the entity.  Fields present in
            *data* overwrite the entity's current values; fields not present
            in *data* are left unchanged.

        Raises
        ------
        FileNotFoundError
            If the entity does not exist.
        ValueError
            If the merged data fails schema validation.
        """
        file_path = self._find_entity_file(entity_id)
        if not file_path:
            raise FileNotFoundError(
                f"Could not find entity '{entity_id}'. "
                f"It may have been deleted or the ID may be incorrect."
            )

        # Load current entity
        current = _safe_read_json(file_path)
        if current is None:
            raise FileNotFoundError(
                f"The file for entity '{entity_id}' exists but could not be read. "
                f"It may be corrupted."
            )

        # Save revision snapshot
        self._save_revision_snapshot(entity_id, current)

        # Determine template schema
        template_id = current.get("_meta", {}).get("template_id", "")
        schema = self._get_template_schema(template_id)

        # Merge new data into existing entity (shallow merge of top-level keys)
        merged = dict(current)
        for key, value in data.items():
            if key not in ("_meta", "id", "canon_claims"):
                merged[key] = value

        # Validate merged data (exclude _meta / internal fields for validation)
        validation_data = {
            k: v for k, v in merged.items()
            if not k.startswith("_") and k not in ("id", "canon_claims")
        }
        errors = self._validate_data(validation_data, schema)
        if errors:
            friendly = self._format_validation_errors(errors, template_id)
            raise ValueError(friendly)

        # Update metadata
        now = _now_iso()
        merged["_meta"]["updated_at"] = now

        # Re-extract canon claims
        merged["canon_claims"] = _extract_canon_claims(validation_data, schema)

        # Write updated entity
        _safe_write_json(file_path, merged)

        # Update state index
        index_entry = self._state.get("entity_index", {}).get(entity_id, {})
        index_entry["updated_at"] = now
        if "name" in data:
            index_entry["name"] = data["name"]
        self._state.setdefault("entity_index", {})[entity_id] = index_entry
        self._save_state()

    def get_entity(self, entity_id: str) -> dict:
        """Load and return a single entity by ID.

        Parameters
        ----------
        entity_id : str
            The entity's unique identifier.

        Returns
        -------
        dict
            The full entity document including ``_meta`` and ``canon_claims``.

        Raises
        ------
        FileNotFoundError
            If the entity cannot be found.
        """
        file_path = self._find_entity_file(entity_id)
        if not file_path:
            raise FileNotFoundError(
                f"Could not find entity '{entity_id}'. "
                f"It may have been deleted or the ID may be incorrect."
            )
        data = _safe_read_json(file_path)
        if data is None:
            raise FileNotFoundError(
                f"The file for entity '{entity_id}' exists but could not be read."
            )
        return data

    def list_entities(self, entity_type: str | None = None) -> list[dict]:
        """Return all entities, optionally filtered by type.

        Parameters
        ----------
        entity_type : str, optional
            If provided, only entities of this type are returned
            (e.g. ``"gods"``, ``"settlements"``).

        Returns
        -------
        list[dict]
            A list of entity summary dicts from the state index, each
            containing: id, template_id, entity_type, name, status,
            file_path, created_at, updated_at.
        """
        index = self._state.get("entity_index", {})
        results = []
        for eid, meta in index.items():
            if entity_type and meta.get("entity_type") != entity_type:
                continue
            entry = dict(meta)
            entry["id"] = eid
            results.append(entry)
        return results

    def get_cross_references(self, entity_id: str) -> dict:
        """Find all entities that reference *entity_id* and all entities
        that *entity_id* references.

        Returns
        -------
        dict
            ``{"references": [...], "referenced_by": [...]}``.
            Each item is a dict with ``id``, ``name``, ``entity_type``,
            and ``relationship`` (the field or relationship that creates
            the link).
        """
        # Load the target entity
        try:
            target = self.get_entity(entity_id)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Cannot find cross-references for '{entity_id}' because "
                f"the entity does not exist."
            )

        references: list[dict] = []      # entities this one points to
        referenced_by: list[dict] = []    # entities that point to this one

        # --- Outbound: scan target entity for cross-reference fields ---
        target_schema = self._get_template_schema(
            target.get("_meta", {}).get("template_id", "")
        )
        outbound_ids = self._extract_referenced_ids(target, target_schema)
        for ref_id, field_name in outbound_ids:
            try:
                ref_entity = self.get_entity(ref_id)
                references.append({
                    "id": ref_id,
                    "name": ref_entity.get("name", ref_id),
                    "entity_type": ref_entity.get("_meta", {}).get("entity_type", ""),
                    "relationship": field_name,
                })
            except FileNotFoundError:
                # Referenced entity does not exist (orphan reference)
                references.append({
                    "id": ref_id,
                    "name": ref_id,
                    "entity_type": "unknown",
                    "relationship": field_name,
                })

        # --- Inbound: scan all other entities for references to entity_id ---
        index = self._state.get("entity_index", {})
        for other_id, other_meta in index.items():
            if other_id == entity_id:
                continue
            other_path = self._find_entity_file(other_id)
            if not other_path:
                continue
            other_data = _safe_read_json(other_path)
            if not other_data:
                continue
            other_template_id = other_data.get("_meta", {}).get("template_id", "")
            try:
                other_schema = self._get_template_schema(other_template_id)
            except ValueError:
                continue
            other_refs = self._extract_referenced_ids(other_data, other_schema)
            for ref_id, field_name in other_refs:
                if ref_id == entity_id:
                    referenced_by.append({
                        "id": other_id,
                        "name": other_data.get("name", other_id),
                        "entity_type": other_data.get("_meta", {}).get("entity_type", ""),
                        "relationship": field_name,
                    })

        return {"references": references, "referenced_by": referenced_by}

    def validate_entity(self, entity_id: str) -> list[str]:
        """Run schema validation on an existing entity.

        Parameters
        ----------
        entity_id : str
            The entity to validate.

        Returns
        -------
        list[str]
            A list of human-readable error messages.  Empty if valid.
        """
        try:
            entity = self.get_entity(entity_id)
        except FileNotFoundError as exc:
            return [str(exc)]

        template_id = entity.get("_meta", {}).get("template_id", "")
        try:
            schema = self._get_template_schema(template_id)
        except ValueError as exc:
            return [str(exc)]

        # Strip internal fields before validation
        validation_data = {
            k: v for k, v in entity.items()
            if not k.startswith("_") and k not in ("id", "canon_claims")
        }
        errors = self._validate_data(validation_data, schema)
        return [self._humanize_error(e) for e in errors]

    def search_entities(self, query: str) -> list[dict]:
        """Search entity names, tags, and descriptions for a keyword.

        This is a simple in-memory keyword search.  It will be upgraded to
        SQLite FTS5 in Sprint 3 for much faster results.

        Parameters
        ----------
        query : str
            The search term (case-insensitive substring match).

        Returns
        -------
        list[dict]
            Matching entity summaries (same shape as ``list_entities``).
        """
        if not query or not query.strip():
            return []

        query_lower = query.strip().lower()
        results = []
        index = self._state.get("entity_index", {})

        for eid, meta in index.items():
            # Check the index-level name first (fast path)
            name = meta.get("name", "")
            if query_lower in name.lower():
                entry = dict(meta)
                entry["id"] = eid
                results.append(entry)
                continue

            # Load the full entity to search deeper fields
            file_path = self._find_entity_file(eid)
            if not file_path:
                continue
            entity = _safe_read_json(file_path)
            if not entity:
                continue

            if self._entity_matches_query(entity, query_lower):
                entry = dict(meta)
                entry["id"] = eid
                results.append(entry)

        return results

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_data(self, data: dict, schema: dict) -> list:
        """Validate *data* against a JSON Schema.

        Returns a list of ``jsonschema.ValidationError`` instances (empty
        if the data is valid).
        """
        # Build a validation-only copy of the schema.  We remove custom
        # fields that are not part of standard JSON Schema (step, phase,
        # source_chapter, x-cross-references, x-cross-reference, $id that
        # collides with jsonschema's internal use) to prevent validation
        # noise.
        clean_schema = self._clean_schema_for_validation(schema)

        validator_cls = jsonschema.Draft202012Validator
        validator = validator_cls(clean_schema)
        return list(validator.iter_errors(data))

    @staticmethod
    def _clean_schema_for_validation(schema: dict) -> dict:
        """Return a copy of *schema* stripped of custom extension fields
        so that ``jsonschema`` does not choke on them."""
        skip_keys = {
            "$id", "step", "phase", "source_chapter",
            "x-cross-references",
        }
        clean = {}
        for key, value in schema.items():
            if key in skip_keys:
                continue
            if isinstance(value, dict):
                clean[key] = DataManager._clean_schema_deep(value)
            elif isinstance(value, list):
                clean[key] = [
                    DataManager._clean_schema_deep(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                clean[key] = value
        return clean

    @staticmethod
    def _clean_schema_deep(obj: dict) -> dict:
        """Recursively remove ``x-cross-reference`` (and similar custom
        keywords) from nested schema objects."""
        skip_keys = {"x-cross-reference", "x-cross-references"}
        result = {}
        for key, value in obj.items():
            if key in skip_keys:
                continue
            if isinstance(value, dict):
                result[key] = DataManager._clean_schema_deep(value)
            elif isinstance(value, list):
                result[key] = [
                    DataManager._clean_schema_deep(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    @staticmethod
    def _format_validation_errors(errors: list, template_id: str) -> str:
        """Format a list of validation errors into a single friendly message."""
        lines = [
            f"The data for template '{template_id}' has some issues that need fixing:\n"
        ]
        for i, err in enumerate(errors, 1):
            lines.append(f"  {i}. {DataManager._humanize_error(err)}")
        lines.append(
            "\nPlease correct these issues and try again. "
            "If you are unsure what a field expects, check the template description."
        )
        return "\n".join(lines)

    @staticmethod
    def _humanize_error(error) -> str:
        """Convert a ``jsonschema.ValidationError`` into plain English."""
        path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
        msg = error.message
        # Make common messages friendlier
        if "'required'" in str(error.validator) or error.validator == "required":
            return f"Missing required field at {path}: {msg}"
        if error.validator == "type":
            return f"Wrong data type at '{path}': {msg}"
        if error.validator == "enum":
            return f"Invalid value at '{path}': {msg}"
        if error.validator == "minItems":
            return f"Not enough items at '{path}': {msg}"
        return f"Issue at '{path}': {msg}"

    # ------------------------------------------------------------------
    # Cross-reference extraction
    # ------------------------------------------------------------------

    def _extract_referenced_ids(self, entity: dict, schema: dict) -> list[tuple[str, str]]:
        """Walk an entity and its schema to find all cross-referenced IDs.

        Returns a list of ``(referenced_entity_id, field_name)`` tuples.
        """
        refs: list[tuple[str, str]] = []
        props = schema.get("properties", {})

        for field_key, field_schema in props.items():
            value = entity.get(field_key)
            if value is None:
                continue

            # Direct cross-reference field (string)
            if "x-cross-reference" in field_schema and isinstance(value, str) and value:
                refs.append((value, field_key))

            # Array of cross-reference strings
            elif isinstance(value, list):
                item_schema = field_schema.get("items", {})
                if "x-cross-reference" in item_schema:
                    for v in value:
                        if isinstance(v, str) and v:
                            refs.append((v, field_key))
                # Array of objects with nested cross-references
                elif isinstance(item_schema, dict) and "properties" in item_schema:
                    for item in value:
                        if not isinstance(item, dict):
                            continue
                        for sub_key, sub_schema in item_schema["properties"].items():
                            if "x-cross-reference" in sub_schema:
                                sub_val = item.get(sub_key)
                                if isinstance(sub_val, str) and sub_val:
                                    refs.append((sub_val, f"{field_key}.{sub_key}"))

        return refs

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entity_matches_query(entity: dict, query_lower: str) -> bool:
        """Return True if *query_lower* appears anywhere in the entity's
        searchable text fields (name, tags, description, notes,
        canon_claims, titles)."""
        searchable_fields = [
            "name", "description", "notes", "titles", "tags",
            "reputation", "local_lore", "slogan",
            "domain_primary", "domains_secondary", "personality",
        ]
        for field in searchable_fields:
            val = entity.get(field)
            if val is None:
                continue
            if isinstance(val, str) and query_lower in val.lower():
                return True
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and query_lower in item.lower():
                        return True

        # Search canon_claims text
        for claim in entity.get("canon_claims", []):
            claim_text = claim.get("claim", "") if isinstance(claim, dict) else str(claim)
            if query_lower in claim_text.lower():
                return True

        return False

    # ------------------------------------------------------------------
    # Revision snapshots
    # ------------------------------------------------------------------

    def _save_revision_snapshot(self, entity_id: str, entity_data: dict) -> str:
        """Save a timestamped snapshot of an entity before it is modified.

        Returns the absolute path to the saved snapshot file.
        """
        os.makedirs(str(self.snapshots_dir), exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{entity_id}_{timestamp}.json"
        snapshot_path = self.snapshots_dir / filename
        _safe_write_json(str(snapshot_path), entity_data)
        return str(snapshot_path)

    # ------------------------------------------------------------------
    # Convenience / state helpers
    # ------------------------------------------------------------------

    def reload_state(self) -> None:
        """Re-read state.json from disk.  Useful after external changes."""
        self._state = self._load_state()

    def get_state(self) -> dict:
        """Return a copy of the current in-memory state."""
        return copy.deepcopy(self._state)

    def set_entity_status(self, entity_id: str, status: str) -> None:
        """Change an entity's status (e.g. from 'draft' to 'canon').

        Parameters
        ----------
        entity_id : str
            The entity to update.
        status : str
            New status value -- typically ``"draft"`` or ``"canon"``.
        """
        if status not in ("draft", "canon"):
            raise ValueError(
                f"Invalid status '{status}'. Must be 'draft' or 'canon'."
            )

        entity = self.get_entity(entity_id)
        old_status = entity.get("_meta", {}).get("status", "draft")
        entity["_meta"]["status"] = status
        entity["_meta"]["updated_at"] = _now_iso()

        file_path = self._find_entity_file(entity_id)
        _safe_write_json(file_path, entity)

        # Update state index
        index_entry = self._state.get("entity_index", {}).get(entity_id, {})
        index_entry["status"] = status
        index_entry["updated_at"] = entity["_meta"]["updated_at"]
        self._state["entity_index"][entity_id] = index_entry
        self._save_state()
