"""
hooks/save_checkpoint.py -- PreCompact Hook for the Worldbuilding Interactive
Program (before context compaction)

Hook Type: PreCompact
Trigger:   Runs before Claude Code context compaction

Purpose:
    - Saves a full checkpoint of the current session state
    - Creates a bookkeeping session summary
    - Snapshots user-world/state.json
    - Records all entities created/modified this session
    - Saves the checkpoint to bookkeeping/sessions/ with timestamp
    - Prints a summary of what was saved (for the compaction context)

Usage:
    python C:/Worldbuilding-Interactive-Program/hooks/save_checkpoint.py
"""

import sys
import os
import json
import shutil
from datetime import datetime, timezone

PROJECT_ROOT = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from engine.utils import safe_read_json as _safe_read_json
from engine.utils import safe_write_json as _safe_write_json


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    state_path = os.path.join(PROJECT_ROOT, "user-world", "state.json")
    state = _safe_read_json(state_path, default={})

    current_step = state.get("current_step", 1)
    entity_index = state.get("entity_index", {})
    completed_steps = state.get("completed_steps", [])
    entity_count = len(entity_index)

    # --- Snapshot state.json ---
    sessions_dir = os.path.join(PROJECT_ROOT, "bookkeeping", "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    snapshot_filename = f"checkpoint-{timestamp}.json"
    snapshot_path = os.path.join(sessions_dir, snapshot_filename)

    checkpoint_data = {
        "checkpoint_timestamp": timestamp,
        "checkpoint_type": "pre_compact",
        "current_step": current_step,
        "completed_steps": completed_steps,
        "entity_count": entity_count,
        "state_snapshot": state,
    }

    # Gather entity summaries
    entity_summaries = []
    for eid, emeta in entity_index.items():
        entity_summaries.append({
            "id": eid,
            "name": emeta.get("name", eid),
            "entity_type": emeta.get("entity_type", "?"),
            "status": emeta.get("status", "draft"),
            "template_id": emeta.get("template_id", ""),
            "created_at": emeta.get("created_at", ""),
            "updated_at": emeta.get("updated_at", ""),
        })

    checkpoint_data["entities"] = entity_summaries

    # Save the checkpoint
    _safe_write_json(snapshot_path, checkpoint_data)

    # --- Also snapshot the raw state.json ---
    state_snapshot_path = os.path.join(
        sessions_dir, f"state-snapshot-{timestamp}.json"
    )
    try:
        shutil.copy2(state_path, state_snapshot_path)
    except (FileNotFoundError, OSError):
        pass

    # --- Create a session summary via bookkeeper ---
    try:
        from engine.bookkeeper import BookkeepingManager
        bookkeeping_root = os.path.join(PROJECT_ROOT, "bookkeeping")
        bk = BookkeepingManager(bookkeeping_root)

        # If a session is active, record a checkpoint event
        if bk.session_active:
            bk.log_event("checkpoint_saved", {
                "checkpoint_path": snapshot_path,
                "current_step": current_step,
                "entity_count": entity_count,
                "reason": "pre_compact",
            })
    except Exception as e:
        print(f"[save_checkpoint] Bookkeeper: {e}")

    # --- Print summary for compaction context ---
    print()
    print("[PRE-COMPACTION CHECKPOINT SAVED]")
    print(f"  Timestamp:       {timestamp}")
    print(f"  Current Step:    {current_step}")
    print(f"  Steps Completed: {len(completed_steps)}/52")
    print(f"  Total Entities:  {entity_count}")
    print(f"  Checkpoint File: {snapshot_filename}")
    print()

    # Summarize entities by type for context continuity
    type_counts = {}
    for ent in entity_summaries:
        etype = ent.get("entity_type", "unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1

    if type_counts:
        print("  ENTITY BREAKDOWN:")
        for etype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {etype}: {count}")
        print()

    # List most recently modified entities (useful for context after compaction)
    recent = sorted(
        entity_summaries,
        key=lambda e: e.get("updated_at", ""),
        reverse=True,
    )[:5]
    if recent:
        print("  RECENTLY MODIFIED ENTITIES:")
        for ent in recent:
            name = ent.get("name", "?")
            etype = ent.get("entity_type", "?")
            print(f"    - {name} ({etype})")
        print()

    print("  Session state preserved for continuity after compaction.")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[save_checkpoint] Error: {e}")
