"""
Shared utility functions for the Worldbuilding Interactive Program engine.

Consolidates duplicated helpers (_safe_read_json, _safe_write_json,
_clean_schema_for_validation) that were previously copy-pasted across
14+ engine modules and hook files.

All JSON writes use atomic temp-file-then-os.replace() to prevent
data corruption from crashes or concurrent access.
"""

import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON I/O (atomic writes)
# ---------------------------------------------------------------------------

def safe_read_json(path, default=None):
    """Read a JSON file, returning *default* if the file is missing or corrupt.

    Parameters
    ----------
    path : str or pathlib.Path
        Absolute path to the JSON file.
    default
        Value returned when the file cannot be read (default ``None``).

    Returns
    -------
    object
        Parsed JSON content, or *default* on failure.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def safe_write_json(path, data, *, indent=2):
    """Atomically write *data* as JSON to *path*.

    Uses a temporary file in the same directory followed by
    ``os.replace()`` so that readers never see a partially-written file.
    Parent directories are created if they do not exist.

    Parameters
    ----------
    path : str or pathlib.Path
        Absolute path to the target JSON file.
    data
        JSON-serialisable object to write.
    indent : int, optional
        JSON indentation level (default 2).
    """
    path = str(path)
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)

    # Write to a temp file in the same directory, then atomically replace.
    fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=indent, ensure_ascii=False)
        os.replace(tmp_path, path)
    except BaseException:
        # Clean up the temp file on any failure.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def safe_append_jsonl(path, record):
    """Append a single JSON record to a JSONL (JSON Lines) file.

    Uses a temporary file and rename for atomicity when the file
    does not yet exist.  For existing files, appends in place (the
    append is a single ``write`` call to minimise partial-write risk).

    Parameters
    ----------
    path : str or pathlib.Path
        Absolute path to the JSONL file.
    record
        JSON-serialisable object to append as one line.
    """
    path = str(path)
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)

    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


# ---------------------------------------------------------------------------
# Schema cleaning (strips custom extensions for jsonschema validation)
# ---------------------------------------------------------------------------

_SCHEMA_SKIP_KEYS = {
    "$id", "step", "phase", "source_chapter",
    "x-cross-references",
}

_DEEP_SKIP_KEYS = {
    "x-cross-reference", "x-cross-references",
}


def clean_schema_for_validation(schema):
    """Return a copy of *schema* stripped of custom extension fields.

    Removes top-level keys like ``$id``, ``step``, ``phase``,
    ``source_chapter``, and ``x-cross-references`` so that
    ``jsonschema`` does not choke on unrecognised keywords.
    Recursively cleans nested objects and arrays.

    Parameters
    ----------
    schema : dict
        The raw JSON Schema loaded from a template file.

    Returns
    -------
    dict
        A cleaned copy safe for ``jsonschema.validate()``.
    """
    clean = {}
    for key, value in schema.items():
        if key in _SCHEMA_SKIP_KEYS:
            continue
        if isinstance(value, dict):
            clean[key] = _clean_schema_deep(value)
        elif isinstance(value, list):
            clean[key] = [
                _clean_schema_deep(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            clean[key] = value
    return clean


# ---------------------------------------------------------------------------
# Cross-reference extraction (consolidated from data_manager, consistency_checker)
# ---------------------------------------------------------------------------

def extract_referenced_ids(entity: dict, schema: dict) -> list[tuple[str, str]]:
    """Walk an entity and its schema to find all cross-referenced entity IDs.

    Scans ``properties`` in *schema* for fields annotated with
    ``x-cross-reference`` and extracts matching values from *entity*.
    Handles direct string fields, arrays of cross-reference strings,
    and arrays of objects with nested cross-reference sub-fields.

    Parameters
    ----------
    entity : dict
        The entity data dict.
    schema : dict
        The template JSON Schema for the entity.

    Returns
    -------
    list[tuple[str, str]]
        A list of ``(referenced_entity_id, field_name)`` tuples.
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

        # Array fields
        elif isinstance(value, list):
            item_schema = field_schema.get("items", {})
            if "x-cross-reference" in item_schema:
                for v in value:
                    if isinstance(v, str) and v:
                        refs.append((v, field_key))
            elif isinstance(item_schema, dict) and "properties" in item_schema:
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    for sub_key, sub_schema in item_schema.get("properties", {}).items():
                        if "x-cross-reference" in sub_schema:
                            sub_val = item.get(sub_key)
                            if isinstance(sub_val, str) and sub_val:
                                refs.append((sub_val, f"{field_key}.{sub_key}"))

    return refs


def _clean_schema_deep(obj):
    """Recursively remove custom extension keywords from nested schema objects."""
    result = {}
    for key, value in obj.items():
        if key in _DEEP_SKIP_KEYS:
            continue
        if isinstance(value, dict):
            result[key] = _clean_schema_deep(value)
        elif isinstance(value, list):
            result[key] = [
                _clean_schema_deep(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result
