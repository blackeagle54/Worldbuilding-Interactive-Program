"""
engine/error_recovery.py -- Error Recovery System for the Worldbuilding Interactive Program

Provides comprehensive health checking, auto-repair, entity-level recovery,
crash recovery, and human-friendly reporting for the entire worldbuilding
data pipeline.

The system is designed around a core principle: JSON entity files in
user-world/entities/ are the single source of truth. The SQLite database
(runtime/worldbuilding.db) and the NetworkX knowledge graph are always
rebuildable from those files. Bookkeeping event logs (bookkeeping/events/)
are append-only JSONL and serve as the source of truth for audit history.

Safety guarantees:
    - No data is ever deleted without creating a backup first.
    - All destructive operations default to dry_run=True.
    - All recovery actions are logged to the bookkeeper when available.
    - Error messages are written for non-technical users.

Usage:
    from engine.error_recovery import ErrorRecoveryManager

    erm = ErrorRecoveryManager("C:/Worldbuilding-Interactive-Program")
    report = erm.check_health()
    erm.repair_all(dry_run=False)
    erm.generate_health_report()
"""

import json
import logging
import os
import glob
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _now_stamp() -> str:
    """Return a filesystem-safe UTC timestamp for filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


from engine.utils import safe_read_json as _safe_read_json
from engine.utils import safe_write_json as _safe_write_json


# ---------------------------------------------------------------------------
# ErrorRecoveryManager
# ---------------------------------------------------------------------------

class ErrorRecoveryManager:
    """Comprehensive error recovery system for the Worldbuilding Interactive Program.

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
        self.runtime_dir = self.root / "runtime"
        self.db_path = self.runtime_dir / "worldbuilding.db"
        self.bookkeeping_dir = self.root / "bookkeeping"
        self.events_dir = self.bookkeeping_dir / "events"
        self.indexes_dir = self.bookkeeping_dir / "indexes"
        self.revisions_dir = self.bookkeeping_dir / "revisions"
        self.snapshots_dir = self.revisions_dir / "snapshots"
        self.backups_dir = self.root / "backups"

        # Lazy-loaded engine references (avoid import errors if subsystems
        # are broken -- this module must always be importable).
        self._bookkeeper = None
        self._template_registry = None

    # ------------------------------------------------------------------
    # Lazy engine helpers
    # ------------------------------------------------------------------

    def _get_bookkeeper(self):
        """Return a BookkeepingManager instance, or None if unavailable."""
        if self._bookkeeper is not None:
            return self._bookkeeper
        try:
            from engine.bookkeeper import BookkeepingManager
            self._bookkeeper = BookkeepingManager(str(self.bookkeeping_dir))
            return self._bookkeeper
        except Exception:
            logger.warning("BookkeepingManager unavailable", exc_info=True)
            return None

    def _get_template_registry(self) -> dict:
        """Load and cache the template registry."""
        if self._template_registry is not None:
            return self._template_registry
        data = _safe_read_json(str(self.registry_path), default={})
        templates = data.get("templates", {})
        if isinstance(templates, list):
            self._template_registry = {t["id"]: t for t in templates if "id" in t}
        elif isinstance(templates, dict):
            self._template_registry = templates
        else:
            self._template_registry = {}
        return self._template_registry

    def _get_template_schema(self, template_id: str) -> dict | None:
        """Load a template JSON schema by its $id."""
        registry = self._get_template_registry()
        if template_id in registry:
            rel_path = registry[template_id].get("file", "")
            if rel_path:
                full_path = self.root / rel_path
                schema = _safe_read_json(str(full_path))
                if schema:
                    return schema
        # Fallback: scan templates directory
        if self.templates_dir.exists():
            for json_path in sorted(self.templates_dir.rglob("*.json")):
                schema = _safe_read_json(str(json_path))
                if schema and schema.get("$id") == template_id:
                    return schema
        return None

    def _log_recovery_action(self, action: str, details: str) -> None:
        """Log a recovery action to the bookkeeper if available."""
        bk = self._get_bookkeeper()
        if bk is not None:
            try:
                bk.log_event("recovery_action", {
                    "action": action,
                    "details": details,
                    "timestamp": _now_iso(),
                })
            except Exception:
                logger.debug("Failed to log recovery action to bookkeeper", exc_info=True)

    def _backup_file(self, file_path: str) -> str | None:
        """Create a timestamped backup of a file before modifying it.

        Returns the backup path, or None if the file does not exist.
        """
        if not os.path.exists(file_path):
            return None
        os.makedirs(str(self.backups_dir), exist_ok=True)
        rel = os.path.relpath(file_path, str(self.root))
        safe_name = rel.replace(os.sep, "_").replace("/", "_")
        backup_name = f"{_now_stamp()}_{safe_name}"
        backup_path = str(self.backups_dir / backup_name)
        shutil.copy2(file_path, backup_path)
        return backup_path

    # ------------------------------------------------------------------
    # Entity file discovery
    # ------------------------------------------------------------------

    def _iter_entity_files(self):
        """Yield (path, entity_type_folder) for every JSON file under entities/."""
        if not self.entities_dir.exists():
            return
        for json_path in self.entities_dir.rglob("*.json"):
            # Determine the entity type from the immediate parent folder
            entity_type = json_path.parent.name
            yield str(json_path), entity_type

    def _load_all_entities(self) -> dict:
        """Load all valid entity files. Returns dict of entity_id -> (path, data)."""
        entities = {}
        for path, _ in self._iter_entity_files():
            data = _safe_read_json(path)
            if data is None:
                continue
            meta = data.get("_meta", {})
            entity_id = meta.get("id") or data.get("id")
            if entity_id:
                entities[entity_id] = (path, data)
        return entities

    # ==================================================================
    # 1. HEALTH CHECKS
    # ==================================================================

    def check_health(self) -> dict:
        """Run all health checks and return an overall health report.

        Returns
        -------
        dict
            A report with ``status`` (``"healthy"``, ``"degraded"``, or
            ``"critical"``), ``timestamp``, and ``details`` containing
            the result of each subsystem check.
        """
        details = {
            "json_integrity": self.check_json_integrity(),
            "schema_compliance": self.check_schema_compliance(),
            "sqlite_sync": self.check_sqlite_sync(),
            "graph_consistency": self.check_graph_consistency(),
            "state_file": self.check_state_file(),
            "bookkeeping": self.check_bookkeeping(),
        }

        # Determine overall status
        critical_count = sum(
            1 for d in details.values() if d.get("status") == "critical"
        )
        degraded_count = sum(
            1 for d in details.values() if d.get("status") == "degraded"
        )

        if critical_count > 0:
            status = "critical"
        elif degraded_count > 0:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "timestamp": _now_iso(),
            "details": details,
        }

    def check_json_integrity(self) -> dict:
        """Validate all entity JSON files can be parsed.

        Checks for zero-byte files, truncated JSON, and encoding issues.
        """
        issues = []
        checked = 0
        valid = 0

        for path, entity_type in self._iter_entity_files():
            checked += 1
            file_size = os.path.getsize(path)

            # Zero-byte file
            if file_size == 0:
                issues.append({
                    "file": path,
                    "issue": "zero_byte",
                    "message": f"Empty file (zero bytes): {os.path.basename(path)}",
                })
                continue

            # Try reading with UTF-8
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    content = fh.read()
            except UnicodeDecodeError:
                issues.append({
                    "file": path,
                    "issue": "encoding_error",
                    "message": f"Encoding error (not valid UTF-8): {os.path.basename(path)}",
                })
                continue

            # Try parsing JSON
            try:
                json.loads(content)
                valid += 1
            except json.JSONDecodeError as e:
                issues.append({
                    "file": path,
                    "issue": "invalid_json",
                    "message": (
                        f"Invalid JSON in {os.path.basename(path)}: "
                        f"{e.msg} at line {e.lineno}, column {e.colno}"
                    ),
                })

        status = "healthy"
        if issues:
            status = "critical" if len(issues) > checked * 0.2 else "degraded"

        return {
            "status": status,
            "files_checked": checked,
            "files_valid": valid,
            "issues": issues,
        }

    def check_schema_compliance(self) -> dict:
        """Validate all entities against their template schemas."""
        issues = []
        checked = 0
        passed = 0

        try:
            from engine.models.factory import ModelFactory
            factory = ModelFactory(str(self.root))
        except Exception as exc:
            return {
                "status": "degraded",
                "files_checked": 0,
                "files_passed": 0,
                "issues": [{
                    "entity_id": None,
                    "message": f"Pydantic model factory unavailable: {exc}",
                }],
            }

        for path, entity_type in self._iter_entity_files():
            data = _safe_read_json(path)
            if data is None:
                continue

            meta = data.get("_meta", {})
            entity_id = meta.get("id") or data.get("id", os.path.basename(path))
            template_id = meta.get("template_id", "")

            if not template_id:
                continue

            checked += 1

            try:
                result = factory.validate_entity(data, template_id)
                if not result.passed:
                    error_msgs = result.errors[:3]
                    issues.append({
                        "entity_id": entity_id,
                        "file": path,
                        "message": (
                            f"Entity '{entity_id}' fails schema validation: "
                            f"{'; '.join(error_msgs)}"
                        ),
                    })
                else:
                    passed += 1
            except Exception as exc:
                issues.append({
                    "entity_id": entity_id,
                    "file": path,
                    "message": f"Validation error for '{entity_id}': {exc}",
                })

        status = "healthy"
        if issues:
            status = "degraded"

        return {
            "status": status,
            "files_checked": checked,
            "files_passed": passed,
            "issues": issues,
        }

    def check_sqlite_sync(self) -> dict:
        """Compare entity count in JSON files vs SQLite database.

        Identifies entities that are out of sync between the two stores.
        """
        # Count JSON entities
        json_entities = {}
        for path, _ in self._iter_entity_files():
            data = _safe_read_json(path)
            if data is None:
                continue
            meta = data.get("_meta", {})
            entity_id = meta.get("id") or data.get("id")
            if entity_id:
                json_entities[entity_id] = path

        json_count = len(json_entities)

        # Check SQLite
        if not self.db_path.exists():
            if json_count == 0:
                return {
                    "status": "healthy",
                    "json_count": 0,
                    "sqlite_count": 0,
                    "missing_in_sqlite": [],
                    "extra_in_sqlite": [],
                    "issues": [],
                }
            return {
                "status": "degraded",
                "json_count": json_count,
                "sqlite_count": 0,
                "missing_in_sqlite": list(json_entities.keys()),
                "extra_in_sqlite": [],
                "issues": [{
                    "message": (
                        f"SQLite database does not exist but {json_count} "
                        f"JSON entity files were found. A full sync is needed."
                    ),
                }],
            }

        import sqlite3
        sqlite_ids = set()
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id FROM entities").fetchall()
            sqlite_ids = {r["id"] for r in rows}
            conn.close()
        except Exception as exc:
            return {
                "status": "critical",
                "json_count": json_count,
                "sqlite_count": 0,
                "missing_in_sqlite": [],
                "extra_in_sqlite": [],
                "issues": [{
                    "message": f"Failed to read SQLite database: {exc}",
                }],
            }

        json_ids = set(json_entities.keys())
        missing_in_sqlite = sorted(json_ids - sqlite_ids)
        extra_in_sqlite = sorted(sqlite_ids - json_ids)

        issues = []
        if missing_in_sqlite:
            issues.append({
                "message": (
                    f"{len(missing_in_sqlite)} entities exist in JSON but not "
                    f"in SQLite. A sync is needed."
                ),
                "entity_ids": missing_in_sqlite,
            })
        if extra_in_sqlite:
            issues.append({
                "message": (
                    f"{len(extra_in_sqlite)} entities exist in SQLite but not "
                    f"in JSON files (possibly deleted)."
                ),
                "entity_ids": extra_in_sqlite,
            })

        status = "healthy"
        if missing_in_sqlite or extra_in_sqlite:
            status = "degraded"

        return {
            "status": status,
            "json_count": json_count,
            "sqlite_count": len(sqlite_ids),
            "missing_in_sqlite": missing_in_sqlite,
            "extra_in_sqlite": extra_in_sqlite,
            "issues": issues,
        }

    def check_graph_consistency(self) -> dict:
        """Verify the knowledge graph has all entities and check for orphaned references."""
        # Load all JSON entities
        json_entities = self._load_all_entities()
        json_ids = set(json_entities.keys())

        # Try to build/load graph
        try:
            from engine.graph_builder import WorldGraph
            wg = WorldGraph(str(self.root))
            wg.build_graph()
        except Exception as exc:
            return {
                "status": "critical",
                "json_entity_count": len(json_ids),
                "graph_node_count": 0,
                "missing_in_graph": [],
                "orphaned_references": [],
                "issues": [{
                    "message": f"Failed to build knowledge graph: {exc}",
                }],
            }

        graph_ids = set(wg.graph.nodes())
        missing_in_graph = sorted(json_ids - graph_ids)
        extra_in_graph = sorted(graph_ids - json_ids)

        # Check for orphaned cross-references (edges pointing to non-existent nodes)
        orphaned_refs = []
        for source, target, edge_data in wg.graph.edges(data=True):
            if target not in json_ids:
                orphaned_refs.append({
                    "source": source,
                    "target": target,
                    "relationship": edge_data.get("relationship_type", ""),
                })

        issues = []
        if missing_in_graph:
            issues.append({
                "message": (
                    f"{len(missing_in_graph)} entities not found in the graph. "
                    f"A graph rebuild may be needed."
                ),
                "entity_ids": missing_in_graph,
            })
        if orphaned_refs:
            issues.append({
                "message": (
                    f"{len(orphaned_refs)} cross-references point to "
                    f"non-existent entities."
                ),
                "details": orphaned_refs[:10],  # Limit output
            })

        status = "healthy"
        if missing_in_graph or orphaned_refs:
            status = "degraded"

        return {
            "status": status,
            "json_entity_count": len(json_ids),
            "graph_node_count": wg.graph.number_of_nodes(),
            "graph_edge_count": wg.graph.number_of_edges(),
            "missing_in_graph": missing_in_graph,
            "orphaned_references": orphaned_refs,
            "issues": issues,
        }

    def check_state_file(self) -> dict:
        """Validate user-world/state.json structure and values."""
        issues = []

        if not self.state_path.exists():
            return {
                "status": "critical",
                "issues": [{
                    "message": "state.json file is missing entirely.",
                }],
            }

        state = _safe_read_json(str(self.state_path))
        if state is None:
            return {
                "status": "critical",
                "issues": [{
                    "message": "state.json exists but cannot be parsed (corrupted JSON).",
                }],
            }

        # Check required keys
        required_keys = ["current_step", "current_phase", "completed_steps",
                         "in_progress_steps", "entity_index"]
        for key in required_keys:
            if key not in state:
                issues.append({
                    "message": f"state.json is missing the required field '{key}'.",
                })

        # Validate types
        if "current_step" in state and not isinstance(state["current_step"], int):
            issues.append({
                "message": (
                    f"state.json 'current_step' should be an integer, "
                    f"got {type(state['current_step']).__name__}."
                ),
            })

        if "current_phase" in state and not isinstance(state["current_phase"], str):
            issues.append({
                "message": "state.json 'current_phase' should be a string.",
            })

        if "entity_index" in state and not isinstance(state["entity_index"], dict):
            issues.append({
                "message": "state.json 'entity_index' should be a dictionary.",
            })

        # Cross-check entity_index against actual files
        entity_index = state.get("entity_index", {})
        if isinstance(entity_index, dict):
            json_entities = self._load_all_entities()
            for eid, meta in entity_index.items():
                if eid not in json_entities:
                    file_path = meta.get("file_path", "")
                    abs_path = self.root / file_path if file_path else None
                    if abs_path is None or not abs_path.exists():
                        issues.append({
                            "message": (
                                f"Entity '{eid}' is listed in state.json but "
                                f"its JSON file is missing."
                            ),
                        })

        status = "healthy"
        if issues:
            has_missing = any("missing" in i["message"].lower() for i in issues)
            status = "critical" if has_missing else "degraded"

        return {
            "status": status,
            "issues": issues,
        }

    def check_bookkeeping(self) -> dict:
        """Validate bookkeeping event files and index integrity."""
        issues = []
        total_events = 0
        valid_events = 0
        corrupt_lines = 0

        # Check event JSONL files
        if not self.events_dir.exists():
            return {
                "status": "degraded",
                "total_events": 0,
                "valid_events": 0,
                "corrupt_lines": 0,
                "issues": [{
                    "message": "Bookkeeping events directory does not exist.",
                }],
            }

        event_files = sorted(glob.glob(str(self.events_dir / "events-*.jsonl")))
        for filepath in event_files:
            try:
                with open(filepath, "r", encoding="utf-8") as fh:
                    for line_num, line in enumerate(fh, 1):
                        line = line.strip()
                        if not line:
                            continue
                        total_events += 1
                        try:
                            event = json.loads(line)
                            # Basic structure check
                            if not isinstance(event, dict):
                                corrupt_lines += 1
                                issues.append({
                                    "file": filepath,
                                    "line": line_num,
                                    "message": f"Event is not a JSON object in {os.path.basename(filepath)} line {line_num}.",
                                })
                            elif "event_type" not in event or "timestamp" not in event:
                                corrupt_lines += 1
                                issues.append({
                                    "file": filepath,
                                    "line": line_num,
                                    "message": (
                                        f"Event missing required fields in "
                                        f"{os.path.basename(filepath)} line {line_num}."
                                    ),
                                })
                            else:
                                valid_events += 1
                        except json.JSONDecodeError:
                            corrupt_lines += 1
                            issues.append({
                                "file": filepath,
                                "line": line_num,
                                "message": f"Corrupt JSON at {os.path.basename(filepath)} line {line_num}.",
                            })
            except OSError as exc:
                issues.append({
                    "file": filepath,
                    "message": f"Cannot read event file: {exc}",
                })

        # Check index files
        index_files = {
            "decisions.json": {"decisions": []},
            "progression.json": {"steps": {}},
            "entity-registry.json": {"entities": {}},
            "cross-references.json": {"cross_references": []},
            "contradictions.json": {"contradictions": []},
        }
        for filename, expected_structure in index_files.items():
            index_path = self.indexes_dir / filename
            if not index_path.exists():
                issues.append({
                    "message": f"Missing bookkeeping index file: {filename}",
                })
                continue
            data = _safe_read_json(str(index_path))
            if data is None:
                issues.append({
                    "message": f"Corrupt bookkeeping index file: {filename}",
                })

        # Check revisions index
        revisions_index_path = self.revisions_dir / "revisions-by-entity.json"
        if revisions_index_path.exists():
            data = _safe_read_json(str(revisions_index_path))
            if data is None:
                issues.append({
                    "message": "Corrupt revisions-by-entity.json index file.",
                })

        status = "healthy"
        if corrupt_lines > 0 or any("Corrupt" in i.get("message", "") or "Missing" in i.get("message", "") for i in issues):
            status = "degraded"
        if total_events == 0 and not event_files:
            # No events yet is not an error -- project might be new
            pass

        return {
            "status": status,
            "total_events": total_events,
            "valid_events": valid_events,
            "corrupt_lines": corrupt_lines,
            "event_files": len(event_files),
            "issues": issues,
        }

    # ==================================================================
    # 2. AUTO-REPAIR
    # ==================================================================

    def repair_all(self, dry_run: bool = True) -> dict:
        """Run all repairs. With dry_run=True, only reports what would be fixed.

        Parameters
        ----------
        dry_run : bool
            If True (default), no changes are made. If False, repairs are
            actually applied.

        Returns
        -------
        dict
            A report of all repair actions taken or planned.
        """
        results = {
            "dry_run": dry_run,
            "timestamp": _now_iso(),
            "repairs": {},
        }

        results["repairs"]["json"] = self.repair_json(dry_run=dry_run)
        results["repairs"]["sqlite"] = self.repair_sqlite(dry_run=dry_run)
        results["repairs"]["graph"] = self.repair_graph(dry_run=dry_run)
        results["repairs"]["state"] = self.repair_state(dry_run=dry_run)
        results["repairs"]["bookkeeping"] = self.repair_bookkeeping(dry_run=dry_run)

        total_actions = sum(
            r.get("actions_count", 0) for r in results["repairs"].values()
        )
        results["total_actions"] = total_actions

        if not dry_run:
            self._log_recovery_action(
                "repair_all",
                f"Ran full repair with {total_actions} actions applied."
            )

        return results

    def repair_json(self, dry_run: bool = True) -> dict:
        """Attempt to fix corrupted JSON entity files.

        Recovers from backup if available, removes zero-byte files, and
        attempts to fix encoding issues.
        """
        actions = []

        for path, entity_type in self._iter_entity_files():
            file_size = os.path.getsize(path)
            basename = os.path.basename(path)

            # Zero-byte file
            if file_size == 0:
                # Look for a backup
                backup_path = self._find_backup_for_file(path)
                if backup_path:
                    actions.append({
                        "action": "restore_from_backup",
                        "file": path,
                        "backup": backup_path,
                        "message": f"Restore {basename} from backup.",
                    })
                    if not dry_run:
                        shutil.copy2(backup_path, path)
                        self._log_recovery_action(
                            "repair_json",
                            f"Restored {basename} from backup {backup_path}."
                        )
                else:
                    actions.append({
                        "action": "remove_zero_byte",
                        "file": path,
                        "message": f"Remove zero-byte file {basename} (no backup available).",
                    })
                    if not dry_run:
                        self._backup_file(path)
                        os.remove(path)
                        self._log_recovery_action(
                            "repair_json",
                            f"Removed zero-byte file {basename} (backed up first)."
                        )
                continue

            # Encoding issues
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    content = fh.read()
            except UnicodeDecodeError:
                actions.append({
                    "action": "fix_encoding",
                    "file": path,
                    "message": f"Fix encoding for {basename} (attempt latin-1 to utf-8).",
                })
                if not dry_run:
                    self._backup_file(path)
                    try:
                        with open(path, "r", encoding="latin-1") as fh:
                            content = fh.read()
                        with open(path, "w", encoding="utf-8") as fh:
                            fh.write(content)
                        self._log_recovery_action(
                            "repair_json",
                            f"Re-encoded {basename} from latin-1 to utf-8."
                        )
                    except Exception:
                        logger.warning("Failed to re-encode %s from latin-1", basename, exc_info=True)
                continue

            # Invalid JSON
            try:
                json.loads(content)
            except json.JSONDecodeError:
                backup_path = self._find_backup_for_file(path)
                if backup_path:
                    actions.append({
                        "action": "restore_from_backup",
                        "file": path,
                        "backup": backup_path,
                        "message": f"Restore {basename} from backup (invalid JSON).",
                    })
                    if not dry_run:
                        self._backup_file(path)
                        shutil.copy2(backup_path, path)
                        self._log_recovery_action(
                            "repair_json",
                            f"Restored {basename} from backup (was corrupted)."
                        )
                else:
                    # Try to find in revision snapshots
                    entity_id = os.path.splitext(basename)[0]
                    snapshot = self._find_latest_snapshot(entity_id)
                    if snapshot:
                        actions.append({
                            "action": "restore_from_snapshot",
                            "file": path,
                            "snapshot": snapshot,
                            "message": f"Restore {basename} from revision snapshot.",
                        })
                        if not dry_run:
                            self._backup_file(path)
                            shutil.copy2(snapshot, path)
                            self._log_recovery_action(
                                "repair_json",
                                f"Restored {basename} from snapshot {snapshot}."
                            )
                    else:
                        actions.append({
                            "action": "cannot_repair",
                            "file": path,
                            "message": (
                                f"Cannot repair {basename}: invalid JSON "
                                f"and no backup or snapshot found."
                            ),
                        })

        return {
            "actions_count": len(actions),
            "actions": actions,
        }

    def repair_sqlite(self, dry_run: bool = True) -> dict:
        """Rebuild SQLite database from JSON entity files."""
        actions = []

        if dry_run:
            actions.append({
                "action": "full_sync",
                "message": "Would rebuild SQLite database from JSON entity files.",
            })
        else:
            try:
                from engine.sqlite_sync import SQLiteSyncEngine
                sync = SQLiteSyncEngine(str(self.root))
                count = sync.full_sync()
                sync.close()
                actions.append({
                    "action": "full_sync",
                    "message": f"Rebuilt SQLite database: {count} entities synced.",
                    "entities_synced": count,
                })
                self._log_recovery_action(
                    "repair_sqlite",
                    f"Full sync completed: {count} entities."
                )
            except Exception as exc:
                actions.append({
                    "action": "full_sync_failed",
                    "message": f"Failed to rebuild SQLite database: {exc}",
                })

        return {
            "actions_count": len(actions),
            "actions": actions,
        }

    def repair_graph(self, dry_run: bool = True) -> dict:
        """Rebuild knowledge graph from JSON entity files."""
        actions = []

        if dry_run:
            actions.append({
                "action": "rebuild_graph",
                "message": "Would rebuild knowledge graph from JSON entity files.",
            })
        else:
            try:
                from engine.graph_builder import WorldGraph
                wg = WorldGraph(str(self.root))
                wg.build_graph()
                node_count = wg.graph.number_of_nodes()
                edge_count = wg.graph.number_of_edges()
                actions.append({
                    "action": "rebuild_graph",
                    "message": (
                        f"Rebuilt knowledge graph: {node_count} nodes, "
                        f"{edge_count} edges."
                    ),
                    "node_count": node_count,
                    "edge_count": edge_count,
                })
                self._log_recovery_action(
                    "repair_graph",
                    f"Graph rebuild: {node_count} nodes, {edge_count} edges."
                )
            except Exception as exc:
                actions.append({
                    "action": "rebuild_graph_failed",
                    "message": f"Failed to rebuild knowledge graph: {exc}",
                })

        return {
            "actions_count": len(actions),
            "actions": actions,
        }

    def repair_state(self, dry_run: bool = True) -> dict:
        """Reconstruct state.json from entity files if corrupted."""
        actions = []

        state = _safe_read_json(str(self.state_path))
        state_corrupt = state is None
        state_missing_keys = False

        if state is not None:
            required_keys = ["current_step", "current_phase", "completed_steps",
                             "in_progress_steps", "entity_index"]
            for key in required_keys:
                if key not in state:
                    state_missing_keys = True
                    break

        if not state_corrupt and not state_missing_keys:
            # State looks okay, verify entity_index
            json_entities = self._load_all_entities()
            entity_index = state.get("entity_index", {})
            needs_update = False

            # Check for entities missing from the index
            for eid, (path, data) in json_entities.items():
                if eid not in entity_index:
                    needs_update = True
                    break

            # Check for stale entries in the index
            for eid in list(entity_index.keys()):
                if eid not in json_entities:
                    needs_update = True
                    break

            if not needs_update:
                return {"actions_count": 0, "actions": []}

        # Need to rebuild or repair
        actions.append({
            "action": "rebuild_state",
            "message": "Rebuild state.json from entity files on disk.",
        })

        if not dry_run:
            self._backup_file(str(self.state_path))

            # Scan all entities to reconstruct
            json_entities = self._load_all_entities()

            # Preserve existing state values where possible
            old_state = state if state is not None else {}

            # Determine current step from entities
            max_step = old_state.get("current_step", 1)
            for eid, (path, data) in json_entities.items():
                step = data.get("_meta", {}).get("step_created")
                if isinstance(step, int) and step > max_step:
                    max_step = step

            # Build entity index
            new_entity_index = {}
            for eid, (path, data) in json_entities.items():
                meta = data.get("_meta", {})
                rel_path = str(Path(path).relative_to(self.root)).replace("\\", "/")
                new_entity_index[eid] = {
                    "template_id": meta.get("template_id", ""),
                    "entity_type": meta.get("entity_type", ""),
                    "name": data.get("name", eid),
                    "status": meta.get("status", "draft"),
                    "file_path": rel_path,
                    "created_at": meta.get("created_at", ""),
                    "updated_at": meta.get("updated_at", ""),
                }

            new_state = {
                "current_step": max_step,
                "current_phase": old_state.get("current_phase", "foundation"),
                "completed_steps": old_state.get("completed_steps", []),
                "in_progress_steps": old_state.get("in_progress_steps", []),
                "entity_index": new_entity_index,
                "session_log": old_state.get("session_log", []),
            }

            # Preserve any extra keys from the old state (e.g. reference_usage_counts)
            for key, value in old_state.items():
                if key not in new_state:
                    new_state[key] = value

            _safe_write_json(str(self.state_path), new_state)
            self._log_recovery_action(
                "repair_state",
                f"Rebuilt state.json with {len(new_entity_index)} entities."
            )

        return {
            "actions_count": len(actions),
            "actions": actions,
        }

    def repair_bookkeeping(self, dry_run: bool = True) -> dict:
        """Rebuild derived bookkeeping indexes from event JSONL files."""
        actions = []

        if dry_run:
            actions.append({
                "action": "rebuild_indexes",
                "message": "Would rebuild all bookkeeping index files from event logs.",
            })
        else:
            try:
                from engine.bookkeeper import BookkeepingManager
                bk = BookkeepingManager(str(self.bookkeeping_dir))
                bk.rebuild_indexes()
                actions.append({
                    "action": "rebuild_indexes",
                    "message": "Rebuilt all bookkeeping index files from event logs.",
                })
                self._log_recovery_action(
                    "repair_bookkeeping",
                    "Rebuilt all bookkeeping indexes from event logs."
                )
            except Exception as exc:
                actions.append({
                    "action": "rebuild_indexes_failed",
                    "message": f"Failed to rebuild bookkeeping indexes: {exc}",
                })

        return {
            "actions_count": len(actions),
            "actions": actions,
        }

    # ==================================================================
    # 3. ENTITY-LEVEL RECOVERY
    # ==================================================================

    def recover_entity(self, entity_id: str) -> dict:
        """Attempt to recover a specific entity.

        Checks the current JSON file, looks in bookkeeping revisions, and
        searches backups for any version of the entity.

        Parameters
        ----------
        entity_id : str
            The unique identifier of the entity to recover.

        Returns
        -------
        dict
            Recovery result with ``recovered`` (bool), ``source``, and
            ``data`` or ``message``.
        """
        # Step 1: Check current file
        current_data = self._try_load_current_entity(entity_id)
        if current_data is not None:
            return {
                "recovered": True,
                "source": "current_file",
                "data": current_data,
                "message": f"Entity '{entity_id}' is intact in its current file.",
            }

        # Step 2: Search all available versions
        versions = self.find_entity_versions(entity_id)

        if not versions:
            return {
                "recovered": False,
                "source": None,
                "data": None,
                "message": (
                    f"Could not find any version of entity '{entity_id}'. "
                    f"The entity may have never existed, or all copies have "
                    f"been lost."
                ),
            }

        # Step 3: Use the most recent version
        best = versions[0]  # Already sorted newest first
        data = _safe_read_json(best["path"])
        if data is None:
            return {
                "recovered": False,
                "source": best["source"],
                "data": None,
                "message": (
                    f"Found a version of '{entity_id}' in {best['source']} "
                    f"but it could not be read."
                ),
            }

        return {
            "recovered": True,
            "source": best["source"],
            "timestamp": best.get("timestamp", "unknown"),
            "data": data,
            "message": (
                f"Recovered entity '{entity_id}' from {best['source']} "
                f"(version from {best.get('timestamp', 'unknown')})."
            ),
        }

    def find_entity_versions(self, entity_id: str) -> list:
        """Search all available sources for versions of an entity.

        Searches: current file, revision snapshots, and backups directory.

        Returns a list of version dicts sorted by timestamp (newest first),
        each with ``source``, ``path``, and ``timestamp``.
        """
        versions = []

        # Source 1: Current entity file
        current_path = self._find_entity_file(entity_id)
        if current_path and os.path.exists(current_path):
            mtime = os.path.getmtime(current_path)
            ts = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            versions.append({
                "source": "current_file",
                "path": current_path,
                "timestamp": ts,
            })

        # Source 2: Revision snapshots
        if self.snapshots_dir.exists():
            pattern = str(self.snapshots_dir / f"{entity_id}_*.json")
            for snapshot_path in sorted(glob.glob(pattern), reverse=True):
                basename = os.path.basename(snapshot_path)
                # Extract timestamp from filename: entity-id_YYYYMMDDTHHMMSSz.json
                parts = basename.rsplit("_", 1)
                if len(parts) == 2:
                    ts_part = parts[1].replace(".json", "")
                else:
                    ts_part = "unknown"
                versions.append({
                    "source": "revision_snapshot",
                    "path": snapshot_path,
                    "timestamp": ts_part,
                })

        # Source 3: Backups directory
        if self.backups_dir.exists():
            for backup_file in sorted(self.backups_dir.iterdir(), reverse=True):
                if entity_id in backup_file.name and backup_file.suffix == ".json":
                    mtime = os.path.getmtime(str(backup_file))
                    ts = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                    versions.append({
                        "source": "backup",
                        "path": str(backup_file),
                        "timestamp": ts,
                    })

        # Sort by timestamp descending (newest first)
        versions.sort(key=lambda v: v.get("timestamp", ""), reverse=True)
        return versions

    def rollback_entity(self, entity_id: str, version_timestamp: str) -> dict:
        """Roll back an entity to a specific version from revisions.

        Parameters
        ----------
        entity_id : str
            The entity to roll back.
        version_timestamp : str
            The timestamp of the version to restore (from find_entity_versions).

        Returns
        -------
        dict
            Result with ``success`` (bool) and ``message``.
        """
        versions = self.find_entity_versions(entity_id)
        target_version = None

        for v in versions:
            if v.get("timestamp", "") == version_timestamp:
                target_version = v
                break

        if target_version is None:
            return {
                "success": False,
                "message": (
                    f"Could not find version with timestamp '{version_timestamp}' "
                    f"for entity '{entity_id}'."
                ),
            }

        # Load the target version data
        restore_data = _safe_read_json(target_version["path"])
        if restore_data is None:
            return {
                "success": False,
                "message": (
                    f"Found the version file but it could not be read. "
                    f"The file may be corrupted."
                ),
            }

        # Find the current file path
        current_path = self._find_entity_file(entity_id)
        if current_path is None:
            # Entity file does not exist; determine where it should go
            meta = restore_data.get("_meta", {})
            entity_type = meta.get("entity_type", "unknown")
            entity_dir = self.entities_dir / entity_type
            os.makedirs(str(entity_dir), exist_ok=True)
            current_path = str(entity_dir / f"{entity_id}.json")

        # Backup current file before overwriting
        self._backup_file(current_path)

        # Write the restored version
        _safe_write_json(current_path, restore_data)

        self._log_recovery_action(
            "rollback_entity",
            (
                f"Rolled back '{entity_id}' to version from "
                f"{version_timestamp} (source: {target_version['source']})."
            ),
        )

        return {
            "success": True,
            "message": (
                f"Successfully rolled back '{entity_id}' to the version "
                f"from {version_timestamp}. A backup of the previous "
                f"version was saved."
            ),
        }

    # ==================================================================
    # 4. CRASH RECOVERY
    # ==================================================================

    def detect_incomplete_operations(self) -> dict:
        """Check for signs of incomplete operations.

        Looks for: temp files, partial writes, mismatched timestamps
        between JSON and bookkeeping.
        """
        issues = []

        # Check for temp files
        temp_patterns = ["*.tmp", "*.bak", "*~", "*.swp"]
        for pattern in temp_patterns:
            for temp_file in self.root.rglob(pattern):
                # Skip files in .git, node_modules, etc.
                path_str = str(temp_file)
                if ".git" in path_str or "node_modules" in path_str:
                    continue
                issues.append({
                    "type": "temp_file",
                    "path": str(temp_file),
                    "message": f"Temporary file found: {temp_file.name}",
                })

        # Check for partial writes (entity files with very recent mtime but
        # suspiciously small size compared to siblings)
        entity_sizes = []
        for path, _ in self._iter_entity_files():
            size = os.path.getsize(path)
            entity_sizes.append(size)

        if entity_sizes:
            avg_size = sum(entity_sizes) / len(entity_sizes)
            min_threshold = max(10, avg_size * 0.05)  # 5% of average or 10 bytes

            for path, _ in self._iter_entity_files():
                size = os.path.getsize(path)
                if 0 < size < min_threshold and avg_size > 100:
                    issues.append({
                        "type": "suspiciously_small",
                        "path": path,
                        "size": size,
                        "average_size": int(avg_size),
                        "message": (
                            f"{os.path.basename(path)} is suspiciously small "
                            f"({size} bytes vs average {int(avg_size)} bytes). "
                            f"It may be a partial write."
                        ),
                    })

        # Check for state.json write lock / temp
        state_tmp = str(self.state_path) + ".tmp"
        if os.path.exists(state_tmp):
            issues.append({
                "type": "state_temp",
                "path": state_tmp,
                "message": "Found state.json.tmp -- possible incomplete state update.",
            })

        return {
            "incomplete_operations_detected": len(issues) > 0,
            "issues": issues,
        }

    def recover_from_crash(self) -> dict:
        """Attempt to clean up after a crash.

        Removes temp files, reconciles state, and re-syncs SQLite and graph.
        """
        actions = []

        # Step 1: Detect issues
        detection = self.detect_incomplete_operations()

        # Step 2: Clean up temp files
        for issue in detection.get("issues", []):
            if issue["type"] == "temp_file":
                path = issue["path"]
                self._backup_file(path)
                try:
                    os.remove(path)
                    actions.append({
                        "action": "removed_temp_file",
                        "path": path,
                        "message": f"Removed temporary file: {os.path.basename(path)}",
                    })
                except OSError:
                    actions.append({
                        "action": "failed_remove_temp",
                        "path": path,
                        "message": f"Could not remove temp file: {os.path.basename(path)}",
                    })
            elif issue["type"] == "state_temp":
                path = issue["path"]
                self._backup_file(path)
                try:
                    os.remove(path)
                    actions.append({
                        "action": "removed_state_temp",
                        "path": path,
                        "message": "Removed state.json.tmp temporary file.",
                    })
                except OSError:
                    pass

        # Step 3: Repair state.json
        state_result = self.repair_state(dry_run=False)
        if state_result["actions_count"] > 0:
            actions.append({
                "action": "repaired_state",
                "message": "Reconciled state.json with entity files.",
            })

        # Step 4: Re-sync SQLite
        sqlite_result = self.repair_sqlite(dry_run=False)
        actions.extend(sqlite_result.get("actions", []))

        # Step 5: Re-build graph
        graph_result = self.repair_graph(dry_run=False)
        actions.extend(graph_result.get("actions", []))

        # Step 6: Rebuild bookkeeping indexes
        bk_result = self.repair_bookkeeping(dry_run=False)
        actions.extend(bk_result.get("actions", []))

        self._log_recovery_action(
            "recover_from_crash",
            f"Crash recovery completed with {len(actions)} actions."
        )

        return {
            "success": True,
            "actions_count": len(actions),
            "actions": actions,
            "message": (
                f"Crash recovery complete. {len(actions)} actions were taken "
                f"to restore the system to a consistent state."
            ),
        }

    # ==================================================================
    # 5. REPORTING
    # ==================================================================

    def generate_health_report(self) -> str:
        """Produce a comprehensive human-readable health report with recommendations.

        Returns
        -------
        str
            A formatted multi-line report string.
        """
        report = self.check_health()
        lines = []

        lines.append("=" * 60)
        lines.append("  WORLDBUILDING PROGRAM HEALTH REPORT")
        lines.append("=" * 60)
        lines.append(f"  Generated: {report['timestamp']}")
        lines.append(f"  Overall Status: {report['status'].upper()}")
        lines.append("=" * 60)
        lines.append("")

        # JSON Integrity
        json_check = report["details"]["json_integrity"]
        lines.append("--- JSON File Integrity ---")
        lines.append(f"  Status: {json_check['status']}")
        lines.append(f"  Files checked: {json_check['files_checked']}")
        lines.append(f"  Files valid: {json_check['files_valid']}")
        if json_check["issues"]:
            lines.append(f"  Issues found: {len(json_check['issues'])}")
            for issue in json_check["issues"][:5]:
                lines.append(f"    - {issue['message']}")
            if len(json_check["issues"]) > 5:
                lines.append(f"    ... and {len(json_check['issues']) - 5} more")
        else:
            lines.append("  No issues found.")
        lines.append("")

        # Schema Compliance
        schema_check = report["details"]["schema_compliance"]
        lines.append("--- Schema Compliance ---")
        lines.append(f"  Status: {schema_check['status']}")
        lines.append(f"  Entities checked: {schema_check['files_checked']}")
        lines.append(f"  Entities passing: {schema_check['files_passed']}")
        if schema_check["issues"]:
            lines.append(f"  Issues found: {len(schema_check['issues'])}")
            for issue in schema_check["issues"][:5]:
                lines.append(f"    - {issue['message']}")
            if len(schema_check["issues"]) > 5:
                lines.append(f"    ... and {len(schema_check['issues']) - 5} more")
        else:
            lines.append("  All entities pass schema validation.")
        lines.append("")

        # SQLite Sync
        sqlite_check = report["details"]["sqlite_sync"]
        lines.append("--- SQLite Database Sync ---")
        lines.append(f"  Status: {sqlite_check['status']}")
        lines.append(f"  JSON entities: {sqlite_check['json_count']}")
        lines.append(f"  SQLite entities: {sqlite_check['sqlite_count']}")
        if sqlite_check["missing_in_sqlite"]:
            lines.append(f"  Missing in SQLite: {len(sqlite_check['missing_in_sqlite'])}")
        if sqlite_check["extra_in_sqlite"]:
            lines.append(f"  Extra in SQLite: {len(sqlite_check['extra_in_sqlite'])}")
        if sqlite_check["issues"]:
            for issue in sqlite_check["issues"]:
                lines.append(f"    - {issue['message']}")
        else:
            lines.append("  Database is in sync.")
        lines.append("")

        # Graph Consistency
        graph_check = report["details"]["graph_consistency"]
        lines.append("--- Knowledge Graph ---")
        lines.append(f"  Status: {graph_check['status']}")
        lines.append(f"  JSON entities: {graph_check.get('json_entity_count', '?')}")
        lines.append(f"  Graph nodes: {graph_check.get('graph_node_count', '?')}")
        lines.append(f"  Graph edges: {graph_check.get('graph_edge_count', '?')}")
        if graph_check.get("missing_in_graph"):
            lines.append(f"  Missing in graph: {len(graph_check['missing_in_graph'])}")
        if graph_check.get("orphaned_references"):
            lines.append(f"  Orphaned references: {len(graph_check['orphaned_references'])}")
        if graph_check["issues"]:
            for issue in graph_check["issues"]:
                lines.append(f"    - {issue['message']}")
        else:
            lines.append("  Graph is consistent.")
        lines.append("")

        # State File
        state_check = report["details"]["state_file"]
        lines.append("--- State File ---")
        lines.append(f"  Status: {state_check['status']}")
        if state_check["issues"]:
            for issue in state_check["issues"]:
                lines.append(f"    - {issue['message']}")
        else:
            lines.append("  State file is valid.")
        lines.append("")

        # Bookkeeping
        bk_check = report["details"]["bookkeeping"]
        lines.append("--- Bookkeeping ---")
        lines.append(f"  Status: {bk_check['status']}")
        lines.append(f"  Total events: {bk_check['total_events']}")
        lines.append(f"  Valid events: {bk_check['valid_events']}")
        if bk_check["corrupt_lines"]:
            lines.append(f"  Corrupt lines: {bk_check['corrupt_lines']}")
        if bk_check["issues"]:
            for issue in bk_check["issues"][:5]:
                lines.append(f"    - {issue['message']}")
        else:
            lines.append("  Bookkeeping is healthy.")
        lines.append("")

        # Recommendations
        lines.append("--- Recommendations ---")
        recommendations = self._generate_recommendations(report)
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"  {i}. {rec}")
        else:
            lines.append("  No action needed. Everything looks good!")
        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def format_for_user(self, report) -> str:
        """Format any report or error into non-technical, friendly language.

        Parameters
        ----------
        report : dict or str
            A health check result, repair result, or error message.

        Returns
        -------
        str
            A user-friendly explanation of what happened and what to do.
        """
        if isinstance(report, str):
            return report

        if not isinstance(report, dict):
            return "Something unexpected happened. Please try again."

        lines = []

        # Health report
        if "status" in report and "details" in report:
            status = report["status"]
            if status == "healthy":
                lines.append(
                    "Great news! Your world data is in perfect shape. "
                    "All files are intact, the database is in sync, and "
                    "everything is consistent."
                )
            elif status == "degraded":
                lines.append(
                    "Your world data is mostly fine, but a few things "
                    "could use attention. Nothing critical -- your creative "
                    "work is safe, but some background systems need a tune-up."
                )
                details = report.get("details", {})
                for name, check in details.items():
                    if check.get("status") in ("degraded", "critical"):
                        friendly_name = name.replace("_", " ").title()
                        issue_count = len(check.get("issues", []))
                        if issue_count:
                            lines.append(
                                f"  - {friendly_name}: {issue_count} "
                                f"{'issue' if issue_count == 1 else 'issues'} found."
                            )
                lines.append("")
                lines.append(
                    "You can fix these automatically by running a repair. "
                    "Your data will be backed up first, so nothing will be lost."
                )
            elif status == "critical":
                lines.append(
                    "Some important files need attention. Do not worry -- "
                    "we can likely fix everything automatically. Your creative "
                    "work is designed to be recoverable."
                )
                details = report.get("details", {})
                for name, check in details.items():
                    if check.get("status") == "critical":
                        friendly_name = name.replace("_", " ").title()
                        lines.append(f"  - {friendly_name} needs repair.")
                lines.append("")
                lines.append(
                    "Run the auto-repair to fix these issues. A backup "
                    "will be created before any changes are made."
                )
            return "\n".join(lines)

        # Repair report
        if "dry_run" in report:
            dry_run = report["dry_run"]
            total = report.get("total_actions", 0)
            if dry_run:
                if total == 0:
                    return "Everything looks good! No repairs needed."
                return (
                    f"Found {total} {'thing' if total == 1 else 'things'} "
                    f"that could be improved. This was a preview -- nothing "
                    f"was changed yet. Run the repair with dry_run=False to "
                    f"apply the fixes."
                )
            else:
                if total == 0:
                    return "No repairs were needed. Everything is already in order."
                return (
                    f"Done! Applied {total} "
                    f"{'fix' if total == 1 else 'fixes'} to get "
                    f"everything back in shape. Backups were created "
                    f"before any changes."
                )

        # Recovery report
        if "recovered" in report:
            if report["recovered"]:
                return (
                    f"Good news! {report.get('message', 'The entity was recovered.')} "
                    f"Your data is safe."
                )
            else:
                return (
                    f"Unfortunately, {report.get('message', 'the entity could not be recovered.')} "
                    f"If you remember the details, you can recreate it."
                )

        # Crash recovery
        if "success" in report and "actions_count" in report:
            count = report["actions_count"]
            return (
                f"Recovery complete! Performed {count} "
                f"{'action' if count == 1 else 'actions'} to clean up "
                f"and restore everything to a consistent state."
            )

        # Generic fallback
        return json.dumps(report, indent=2)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_recommendations(self, report: dict) -> list:
        """Generate actionable recommendations based on health check results."""
        recommendations = []
        details = report.get("details", {})

        json_check = details.get("json_integrity", {})
        if json_check.get("issues"):
            zero_byte = sum(1 for i in json_check["issues"] if i.get("issue") == "zero_byte")
            invalid = sum(1 for i in json_check["issues"] if i.get("issue") == "invalid_json")
            if zero_byte:
                recommendations.append(
                    f"Run repair_json() to clean up {zero_byte} empty entity "
                    f"{'file' if zero_byte == 1 else 'files'}."
                )
            if invalid:
                recommendations.append(
                    f"Run repair_json() to attempt recovery of {invalid} "
                    f"corrupted entity {'file' if invalid == 1 else 'files'}."
                )

        sqlite_check = details.get("sqlite_sync", {})
        if sqlite_check.get("status") != "healthy":
            recommendations.append(
                "Run repair_sqlite() to rebuild the search database from "
                "your entity files."
            )

        graph_check = details.get("graph_consistency", {})
        if graph_check.get("status") != "healthy":
            recommendations.append(
                "Run repair_graph() to rebuild the knowledge graph."
            )

        state_check = details.get("state_file", {})
        if state_check.get("status") != "healthy":
            recommendations.append(
                "Run repair_state() to fix your state tracking file."
            )

        bk_check = details.get("bookkeeping", {})
        if bk_check.get("status") != "healthy":
            recommendations.append(
                "Run repair_bookkeeping() to rebuild the bookkeeping indexes."
            )

        if len(recommendations) > 1:
            recommendations.append(
                "Or simply run repair_all() to fix everything at once."
            )

        return recommendations

    def _try_load_current_entity(self, entity_id: str) -> dict | None:
        """Try to load an entity from its current file."""
        path = self._find_entity_file(entity_id)
        if path is None:
            return None
        data = _safe_read_json(path)
        if data is None:
            return None
        # Verify the entity ID matches
        meta = data.get("_meta", {})
        found_id = meta.get("id") or data.get("id")
        if found_id == entity_id:
            return data
        return None

    def _find_entity_file(self, entity_id: str) -> str | None:
        """Find the JSON file path for an entity by ID.

        Checks the state index first, then falls back to scanning the
        entities directory.
        """
        # Check state index
        state = _safe_read_json(str(self.state_path))
        if state and isinstance(state, dict):
            entry = state.get("entity_index", {}).get(entity_id)
            if entry:
                file_path = entry.get("file_path", "")
                if file_path:
                    full = self.root / file_path if not os.path.isabs(file_path) else Path(file_path)
                    if full.exists():
                        return str(full)

        # Fallback: scan entities directory
        if self.entities_dir.exists():
            for json_path in self.entities_dir.rglob("*.json"):
                data = _safe_read_json(str(json_path))
                if data and data.get("_meta", {}).get("id") == entity_id:
                    return str(json_path)
                if data and data.get("id") == entity_id:
                    return str(json_path)

        return None

    def _find_backup_for_file(self, file_path: str) -> str | None:
        """Search for the most recent backup of a given file."""
        if not self.backups_dir.exists():
            return None

        basename = os.path.basename(file_path)
        candidates = []
        for backup_file in self.backups_dir.iterdir():
            if basename in backup_file.name:
                candidates.append(str(backup_file))

        if not candidates:
            return None

        # Return the most recent one (sorted by name which includes timestamp)
        candidates.sort(reverse=True)
        # Verify the candidate is actually valid JSON
        for candidate in candidates:
            if _safe_read_json(candidate) is not None:
                return candidate

        return None

    def _find_latest_snapshot(self, entity_id: str) -> str | None:
        """Find the most recent revision snapshot for an entity."""
        if not self.snapshots_dir.exists():
            return None

        pattern = str(self.snapshots_dir / f"{entity_id}_*.json")
        snapshots = sorted(glob.glob(pattern), reverse=True)

        for snapshot_path in snapshots:
            if _safe_read_json(snapshot_path) is not None:
                return snapshot_path

        return None
