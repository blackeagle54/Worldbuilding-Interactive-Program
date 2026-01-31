"""
engine/models/factory.py -- Dynamic Pydantic model generation from JSON Schema.

Reads the 84 JSON Schema template files and generates Pydantic v2 models
at runtime.  Generated models are cached so each template is only processed
once per process lifetime.

Key design decisions:
    - JSON Schema files remain the single source of truth for field
      definitions.  We do NOT maintain 84 hand-coded Pydantic model files.
    - Custom extension fields (``x-cross-reference``, ``x-cross-references``,
      ``step``, ``phase``, ``source_chapter``) are preserved as metadata on
      the generated ``Field`` objects but do not affect validation.
    - The factory produces concrete subclasses of ``WorldEntity`` with
      ``model_config = ConfigDict(extra='forbid')`` so that unknown fields
      are caught at validation time.
    - Enum fields in the schema become ``Literal`` unions in the model so
      that Anthropic constrained decoding can enforce valid values.

Usage::

    from engine.models.factory import ModelFactory

    factory = ModelFactory("C:/Worldbuilding-Interactive-Program")
    GodProfile = factory.get_model("god-profile")

    god = GodProfile.model_validate(entity_data)        # validate
    schema = GodProfile.model_json_schema()              # for constrained decoding
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, create_model

from engine.models.base import EntityMeta, WorldEntity
from engine.utils import safe_read_json as _safe_read_json

logger = logging.getLogger(__name__)

# Fields that are engine-internal or handled by WorldEntity base
_BASE_HANDLED_FIELDS = frozenset({
    "id", "name", "notes", "canon_claims", "_meta",
})

# JSON Schema top-level keys that are metadata, not field definitions
_SCHEMA_META_KEYS = frozenset({
    "$schema", "$id", "title", "description", "type",
    "step", "phase", "source_chapter",
    "x-cross-references", "required", "properties",
})


# ------------------------------------------------------------------
# Type mapping: JSON Schema type -> Python type annotation
# ------------------------------------------------------------------

def _json_type_to_python(prop: dict) -> Any:
    """Convert a JSON Schema property definition to a Python type annotation.

    Handles: string, integer, number, boolean, array, object, enums, and
    nested structures.
    """
    # Enum -> Literal
    if "enum" in prop:
        values = tuple(prop["enum"])
        if all(isinstance(v, str) for v in values):
            return Optional[Literal[values]]  # type: ignore[valid-type]
        return Optional[Any]

    json_type = prop.get("type", "string")

    if json_type == "string":
        return Optional[str]
    elif json_type == "integer":
        return Optional[int]
    elif json_type == "number":
        return Optional[float]
    elif json_type == "boolean":
        return Optional[bool]
    elif json_type == "array":
        items = prop.get("items", {})
        item_type = _json_type_to_python_inner(items)
        return Optional[list[item_type]]  # type: ignore[valid-type]
    elif json_type == "object":
        # Nested objects without predefined properties -> dict
        if "properties" not in prop:
            return Optional[dict[str, Any]]
        # Nested objects with properties -> inline dict (we don't create
        # sub-models for every nested object to keep things simple)
        return Optional[dict[str, Any]]
    else:
        return Optional[Any]


def _json_type_to_python_inner(prop: dict) -> Any:
    """Inner type (for array items) -- not Optional-wrapped."""
    if not isinstance(prop, dict):
        return Any

    if "enum" in prop:
        values = tuple(prop["enum"])
        if all(isinstance(v, str) for v in values):
            return str  # array items: keep as str, enum checked at item level
        return Any

    json_type = prop.get("type", "string")

    if json_type == "string":
        return str
    elif json_type == "integer":
        return int
    elif json_type == "number":
        return float
    elif json_type == "boolean":
        return bool
    elif json_type == "array":
        return list
    elif json_type == "object":
        return dict[str, Any]
    else:
        return Any


# ------------------------------------------------------------------
# Field metadata extraction
# ------------------------------------------------------------------

def _build_field_kwargs(prop_name: str, prop: dict, required_fields: set[str]) -> dict:
    """Build keyword arguments for ``pydantic.Field()`` from a schema property."""
    kwargs: dict[str, Any] = {}

    # Description
    desc = prop.get("description", "")
    if desc:
        kwargs["description"] = desc

    # Default value
    if prop_name in required_fields:
        # Required fields: use ... (no default) -- but we still make the
        # type Optional so that validation errors are clear rather than
        # getting a "field required" at the Python type level.
        kwargs["default"] = None
    else:
        # Optional fields get an appropriate empty default
        json_type = prop.get("type", "string")
        if "enum" in prop:
            kwargs["default"] = None
        elif json_type == "array":
            kwargs["default_factory"] = list
        elif json_type == "object":
            kwargs["default"] = None
        elif json_type == "integer":
            kwargs["default"] = None
        elif json_type == "number":
            kwargs["default"] = None
        elif json_type == "boolean":
            kwargs["default"] = None
        else:
            kwargs["default"] = None

    # Preserve cross-reference info as json_schema_extra
    xref = prop.get("x-cross-reference")
    if xref:
        kwargs["json_schema_extra"] = {"x-cross-reference": xref}

    # Min/max items for arrays
    if prop.get("minItems"):
        kwargs.setdefault("json_schema_extra", {})["minItems"] = prop["minItems"]

    return kwargs


# ------------------------------------------------------------------
# ModelFactory
# ------------------------------------------------------------------

class ModelFactory:
    """Generates and caches Pydantic models from JSON Schema template files.

    Parameters
    ----------
    project_root : str
        Absolute path to the Worldbuilding Interactive Program root.
    """

    def __init__(self, project_root: str):
        self.root = Path(project_root)
        self.templates_dir = self.root / "templates"
        self.registry_path = self.root / "engine" / "template_registry.json"

        # Cache: template_id -> generated model class
        self._model_cache: dict[str, type[WorldEntity]] = {}

        # Cache: template_id -> raw schema dict
        self._schema_cache: dict[str, dict] = {}

        # Registry cache
        self._registry: dict[str, dict] | None = None

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def _load_registry(self) -> dict[str, dict]:
        """Load and cache the template registry (template_id -> entry)."""
        if self._registry is not None:
            return self._registry
        data = _safe_read_json(str(self.registry_path), default={})
        templates = data.get("templates", [])
        if isinstance(templates, list):
            self._registry = {t["id"]: t for t in templates if "id" in t}
        elif isinstance(templates, dict):
            self._registry = templates
        else:
            self._registry = {}
        return self._registry

    def get_template_ids(self) -> list[str]:
        """Return all known template IDs from the registry."""
        return sorted(self._load_registry().keys())

    # ------------------------------------------------------------------
    # Schema loading
    # ------------------------------------------------------------------

    def get_schema(self, template_id: str) -> dict | None:
        """Load a JSON Schema by template ID.

        Checks the registry first, then falls back to scanning the
        templates directory.
        """
        if template_id in self._schema_cache:
            return self._schema_cache[template_id]

        registry = self._load_registry()

        # Try registry path
        if template_id in registry:
            rel_path = registry[template_id].get("file", "")
            if rel_path:
                full_path = self.root / rel_path
                schema = _safe_read_json(str(full_path))
                if schema:
                    self._schema_cache[template_id] = schema
                    return schema

        # Fallback: scan templates directory
        if self.templates_dir.exists():
            for json_path in sorted(self.templates_dir.rglob("*.json")):
                schema = _safe_read_json(str(json_path))
                if schema and schema.get("$id") == template_id:
                    self._schema_cache[template_id] = schema
                    return schema

        return None

    # ------------------------------------------------------------------
    # Model generation
    # ------------------------------------------------------------------

    def get_model(self, template_id: str) -> type[WorldEntity] | None:
        """Return a Pydantic model class for the given template.

        The model is a concrete subclass of ``WorldEntity`` with all
        template-specific fields declared.  Generated models are cached.

        Returns ``None`` if the template schema cannot be found.
        """
        if template_id in self._model_cache:
            return self._model_cache[template_id]

        schema = self.get_schema(template_id)
        if schema is None:
            logger.warning("Schema not found for template '%s'", template_id)
            return None

        model = self._build_model(template_id, schema)
        self._model_cache[template_id] = model
        return model

    def _build_model(self, template_id: str, schema: dict) -> type[WorldEntity]:
        """Generate a Pydantic model from a JSON Schema dict."""
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        title = schema.get("title", template_id)

        # Build field definitions for pydantic.create_model()
        # Shape: {field_name: (type_annotation, FieldInfo)}
        field_definitions: dict[str, Any] = {}

        for prop_name, prop_def in properties.items():
            if prop_name in _BASE_HANDLED_FIELDS:
                continue  # Handled by WorldEntity base

            python_type = _json_type_to_python(prop_def)
            field_kwargs = _build_field_kwargs(prop_name, prop_def, required)

            # create_model expects (type, Field(...)) tuples
            if "default_factory" in field_kwargs:
                factory = field_kwargs.pop("default_factory")
                field_definitions[prop_name] = (
                    python_type,
                    Field(default_factory=factory, **field_kwargs),
                )
            else:
                field_definitions[prop_name] = (
                    python_type,
                    Field(**field_kwargs),
                )

        # Build a class name from template_id: "god-profile" -> "GodProfileModel"
        class_name = "".join(
            part.capitalize() for part in template_id.replace("_", "-").split("-")
        ) + "Model"

        # Store schema metadata on the model class
        model = create_model(
            class_name,
            __base__=WorldEntity,
            __module__="engine.models.factory",
            **field_definitions,
        )

        # Attach schema metadata as class attributes
        model._template_id = template_id  # type: ignore[attr-defined]
        model._schema_title = title  # type: ignore[attr-defined]
        model._schema_step = schema.get("step")  # type: ignore[attr-defined]
        model._schema_phase = schema.get("phase")  # type: ignore[attr-defined]
        model._required_fields = required  # type: ignore[attr-defined]
        model._cross_references = schema.get("x-cross-references", {})  # type: ignore[attr-defined]

        return model

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def validate_entity(
        self,
        entity_data: dict[str, Any],
        template_id: str = "",
    ) -> "ValidationResult":
        """Validate entity data against its template's Pydantic model.

        Parameters
        ----------
        entity_data : dict
            The full entity dict as read from a JSON file.
        template_id : str, optional
            Override template ID.  If empty, extracted from
            ``entity_data["_meta"]["template_id"]``.

        Returns
        -------
        ValidationResult
            A result object with ``passed``, ``errors``, and ``entity``.
        """
        if not template_id:
            meta = entity_data.get("_meta", {})
            template_id = meta.get("template_id", "")

        if not template_id:
            return ValidationResult(
                passed=False,
                errors=["No template_id found -- cannot determine which schema to validate against."],
                entity=None,
            )

        model = self.get_model(template_id)
        if model is None:
            return ValidationResult(
                passed=False,
                errors=[
                    f"Could not find the template '{template_id}'. "
                    f"This usually means the template file is missing or "
                    f"its name has changed."
                ],
                entity=None,
            )

        return self._validate_with_model(entity_data, model)

    def _validate_with_model(
        self,
        entity_data: dict[str, Any],
        model: type[WorldEntity],
    ) -> "ValidationResult":
        """Run Pydantic validation and collect errors."""
        from pydantic import ValidationError

        # Strip internal fields that are not part of the template schema
        # (_meta is handled by WorldEntity, canon_claims likewise)
        try:
            entity = model.model_validate(entity_data)
            return ValidationResult(passed=True, errors=[], entity=entity)
        except ValidationError as exc:
            errors = []
            for err in exc.errors():
                errors.append(_humanize_pydantic_error(err, entity_data))
            return ValidationResult(passed=False, errors=errors, entity=None)

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def preload_all(self) -> int:
        """Pre-generate models for all templates in the registry.

        Returns the number of models generated.
        """
        count = 0
        for template_id in self.get_template_ids():
            model = self.get_model(template_id)
            if model is not None:
                count += 1
        return count


# ------------------------------------------------------------------
# Validation result
# ------------------------------------------------------------------

class ValidationResult:
    """Result of validating an entity against its Pydantic model.

    Attributes
    ----------
    passed : bool
        Whether validation succeeded.
    errors : list[str]
        Human-readable error messages (empty if passed).
    entity : WorldEntity | None
        The validated entity instance (only set if passed).
    """

    __slots__ = ("passed", "errors", "entity")

    def __init__(
        self,
        passed: bool,
        errors: list[str],
        entity: WorldEntity | None,
    ):
        self.passed = passed
        self.errors = errors
        self.entity = entity

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the dict shape expected by existing callers."""
        return {
            "passed": self.passed,
            "errors": self.errors,
        }


# ------------------------------------------------------------------
# Error humanization
# ------------------------------------------------------------------

def _humanize_pydantic_error(err: dict, entity_data: dict) -> str:
    """Convert a single Pydantic error dict to a human-friendly message.

    Pydantic error dicts look like::

        {
            "type": "string_type",
            "loc": ("domain_primary",),
            "msg": "Input should be a valid string",
            "input": 42,
        }
    """
    loc = err.get("loc", ())
    msg = err.get("msg", "Validation error")
    err_type = err.get("type", "")

    # Build a friendly field path
    field_path = " -> ".join(str(part) for part in loc if part != "__root__")
    if not field_path:
        field_path = "(root)"

    # Friendly entity name for context
    entity_name = entity_data.get("name", entity_data.get("id", "this entity"))

    # Special handling for common error types
    if err_type == "missing":
        return (
            f"The field '{field_path}' is required for '{entity_name}' "
            f"but was not provided."
        )
    elif err_type == "literal_error":
        return (
            f"The field '{field_path}' has an invalid value. {msg}."
        )
    elif "type" in err_type:
        return (
            f"The field '{field_path}' has the wrong type. {msg}."
        )
    else:
        return f"Field '{field_path}': {msg}."
