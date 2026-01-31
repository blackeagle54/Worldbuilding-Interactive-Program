"""
hooks/end_session.py -- SessionEnd Hook for the Worldbuilding Interactive Program

Hook Type: SessionEnd
Trigger:   Runs when a Claude Code session ends

Purpose:
    - Logs session_end event to the bookkeeper
    - Creates final session summary in bookkeeping/sessions/
    - Closes SQLite connection
    - Prints session statistics (entities created, steps completed, time spent)

Usage:
    python C:/Worldbuilding-Interactive-Program/hooks/end_session.py
"""

import sys
import os
import json
from datetime import datetime, timezone

PROJECT_ROOT = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from engine.utils import safe_read_json as _safe_read_json


def main():
    state_path = os.path.join(PROJECT_ROOT, "user-world", "state.json")
    state = _safe_read_json(state_path, default={})

    current_step = state.get("current_step", 1)
    entity_index = state.get("entity_index", {})
    completed_steps = state.get("completed_steps", [])
    entity_count = len(entity_index)

    # --- End bookkeeper session ---
    session_summary_path = None
    session_id = "N/A"
    try:
        from engine.bookkeeper import BookkeepingManager
        bookkeeping_root = os.path.join(PROJECT_ROOT, "bookkeeping")
        bk = BookkeepingManager(bookkeeping_root)

        if bk.session_active:
            session_id = bk.current_session_id or "N/A"
            summary_text = (
                f"Session ended at step {current_step}. "
                f"{entity_count} total entities in the world."
            )
            session_summary_path = bk.end_session(summary=summary_text)
    except Exception as e:
        print(f"[end_session] Bookkeeper: {e}")

    # --- Close SQLite connection ---
    try:
        from engine.sqlite_sync import SQLiteSyncEngine
        sync = SQLiteSyncEngine(PROJECT_ROOT)

        # Get final stats before closing
        db_stats = sync.get_stats()
        sync.close()
    except Exception as e:
        print(f"[end_session] SQLite stats: {e}")
        db_stats = {}

    # --- Count entities by status ---
    draft_count = 0
    canon_count = 0
    for eid, emeta in entity_index.items():
        status = emeta.get("status", "draft")
        if status == "draft":
            draft_count += 1
        elif status == "canon":
            canon_count += 1

    # --- Count entities by type ---
    type_counts = {}
    for eid, emeta in entity_index.items():
        etype = emeta.get("entity_type", "unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1

    # --- Print session end summary ---
    print()
    print("=" * 60)
    print("  WORLDBUILDING INTERACTIVE PROGRAM -- SESSION END")
    print("=" * 60)
    print()
    print(f"  Session ID:        {session_id}")
    print(f"  Current Step:      {current_step}")
    print(f"  Steps Completed:   {len(completed_steps)}/52")
    print(f"  Total Entities:    {entity_count}")
    print(f"    Draft:           {draft_count}")
    print(f"    Canon:           {canon_count}")

    if db_stats:
        print(f"  Cross-References:  {db_stats.get('total_cross_references', 0)}")
        print(f"  Canon Claims:      {db_stats.get('total_canon_claims', 0)}")

    if type_counts:
        print()
        print("  ENTITIES BY TYPE:")
        for etype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {etype}: {count}")

    if session_summary_path:
        print()
        print(f"  Session summary saved to: {session_summary_path}")

    print()
    print("  All data has been saved. See you next session!")
    print()
    print("=" * 60)
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[end_session] Error: {e}")
