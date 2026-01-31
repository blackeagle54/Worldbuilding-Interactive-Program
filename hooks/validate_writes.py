"""
hooks/validate_writes.py -- PostToolUse Hook for the Worldbuilding Interactive
Program (triggers after Write/Edit tools)

Hook Type: PostToolUse
Trigger:   After Write or Edit tool writes to user-world/entities/**/*.json

Purpose:
    - Watches for writes to user-world/entities/**/*.json files
    - When detected, runs ConsistencyChecker.check_entity() on the written file
    - If validation fails, prints the human-readable error message
    - If validation passes, syncs the entity to SQLite via sync_entity()
    - Updates the knowledge graph with the new/changed entity
    - Logs the write event to the bookkeeper
    - Accepts the file path as a command line argument or from environment

Usage:
    python C:/Worldbuilding-Interactive-Program/hooks/validate_writes.py <file_path>

    Or set the environment variable:
        CLAUDE_HOOK_FILE_PATH=<file_path>
"""

import sys
import os
import json

PROJECT_ROOT = "C:/Worldbuilding-Interactive-Program"
sys.path.insert(0, PROJECT_ROOT)

from engine.utils import safe_read_json as _safe_read_json


def _is_entity_file(file_path):
    """Check if the given path is an entity JSON file."""
    normalized = file_path.replace("\\", "/")
    return (
        "user-world/entities/" in normalized
        and normalized.endswith(".json")
    )


def main():
    # Get the file path from command line argument or environment
    file_path = None
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = os.environ.get("CLAUDE_HOOK_FILE_PATH", "")

    if not file_path:
        # No file path provided -- nothing to validate
        return

    # Normalize the path
    file_path = file_path.replace("\\", "/")

    # Only process entity files
    if not _is_entity_file(file_path):
        return

    # Resolve to absolute path
    if not os.path.isabs(file_path):
        file_path = os.path.join(PROJECT_ROOT, file_path)

    if not os.path.exists(file_path):
        print(f"[validate_writes] File not found: {file_path}")
        return

    # Load the entity data
    entity_data = _safe_read_json(file_path)
    if entity_data is None:
        print(f"[validate_writes] Could not parse JSON: {file_path}")
        return

    meta = entity_data.get("_meta", {})
    entity_id = meta.get("id") or entity_data.get("id", "")
    entity_name = entity_data.get("name", entity_id or "Unknown")
    template_id = meta.get("template_id", "")

    if not entity_id:
        print(f"[validate_writes] No entity ID found in: {file_path}")
        return

    # --- Run ConsistencyChecker ---
    validation_passed = True
    try:
        from engine.consistency_checker import ConsistencyChecker
        cc = ConsistencyChecker(PROJECT_ROOT)
        result = cc.check_entity(entity_data, template_id=template_id)

        if not result.get("passed", False):
            validation_passed = False
            human_message = result.get("human_message", "Validation failed.")
            print()
            print("[CONSISTENCY CHECK FAILED]")
            print(human_message)
            print()
        else:
            # Check for warnings even on pass
            human_message = result.get("human_message", "")
            if "NOTES" in human_message or "semantic review" in human_message.lower():
                print()
                print("[CONSISTENCY CHECK PASSED WITH NOTES]")
                print(human_message)
                print()
    except Exception as e:
        print(f"[validate_writes] Consistency check error: {e}")

    # --- Sync to SQLite (even if validation has warnings, sync on pass) ---
    if validation_passed:
        try:
            from engine.sqlite_sync import SQLiteSyncEngine
            sync = SQLiteSyncEngine(PROJECT_ROOT)
            sync.sync_entity(entity_id, entity_data)
            sync.close()
        except Exception as e:
            print(f"[validate_writes] SQLite sync error: {e}")

        # --- Update the knowledge graph ---
        try:
            from engine.graph_builder import WorldGraph
            wg = WorldGraph(PROJECT_ROOT)
            wg.build_graph()
            wg.add_entity(entity_id, entity_data)
        except Exception as e:
            print(f"[validate_writes] Graph update error: {e}")

    # --- Log to bookkeeper ---
    try:
        from engine.bookkeeper import BookkeepingManager
        bookkeeping_root = os.path.join(PROJECT_ROOT, "bookkeeping")
        bk = BookkeepingManager(bookkeeping_root)

        entity_type = meta.get("entity_type", "unknown")
        rel_path = meta.get("file_path", file_path)

        if validation_passed:
            bk.record_entity_created(
                entity_id=entity_id,
                entity_type=entity_type,
                file_path=rel_path,
                status=meta.get("status", "draft"),
            )
        else:
            # Log the failed validation as a contradiction
            bk.record_contradiction(
                entities=[entity_id],
                description=f"Validation failed for '{entity_name}' ({template_id})",
                severity="warning",
            )
    except Exception as e:
        print(f"[validate_writes] Bookkeeper error: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[validate_writes] Error: {e}")
