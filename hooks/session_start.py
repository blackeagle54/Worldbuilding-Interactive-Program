"""
hooks/session_start.py -- SessionStart Hook for the Worldbuilding Interactive Program

Hook Type: SessionStart
Trigger:   Runs when a Claude Code session begins

Purpose:
    - Initializes all engine modules (DataManager, BookkeepingManager,
      WorldGraph, SQLiteSyncEngine)
    - Runs SQLite full_sync() to rebuild runtime DB from JSON entities
    - Rebuilds the NetworkX knowledge graph
    - Loads bookkeeping state and prints a session summary:
        * Current progression step (from user-world/state.json)
        * Number of entities created
        * Last session date
        * Any incomplete work from prior sessions
    - Logs a session_start event to the bookkeeper

Usage:
    python C:/Worldbuilding-Interactive-Program/hooks/session_start.py
"""

import sys
import os
import json
from datetime import datetime, timezone

PROJECT_ROOT = "C:/Worldbuilding-Interactive-Program"
sys.path.insert(0, PROJECT_ROOT)


def _safe_read_json(path, default=None):
    """Read a JSON file, returning default on failure."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def main():
    state_path = os.path.join(PROJECT_ROOT, "user-world", "state.json")
    state = _safe_read_json(state_path, default={})

    current_step = state.get("current_step", 1)
    current_phase = state.get("current_phase", "foundation")
    completed_steps = state.get("completed_steps", [])
    in_progress_steps = state.get("in_progress_steps", [])
    entity_index = state.get("entity_index", {})
    entity_count = len(entity_index)

    # --- Initialize SQLite Sync Engine and run full_sync ---
    synced_count = 0
    try:
        from engine.sqlite_sync import SQLiteSyncEngine
        sync = SQLiteSyncEngine(PROJECT_ROOT)
        synced_count = sync.full_sync()
    except Exception as e:
        print(f"[session_start] SQLite sync: {e}")

    # --- Rebuild the NetworkX knowledge graph ---
    graph_stats = {}
    try:
        from engine.graph_builder import WorldGraph
        wg = WorldGraph(PROJECT_ROOT)
        wg.build_graph()
        graph_stats = wg.get_stats()
    except Exception as e:
        print(f"[session_start] Graph build: {e}")

    # --- Initialize Bookkeeper and start session ---
    last_session_date = "N/A"
    session_id = None
    try:
        from engine.bookkeeper import BookkeepingManager
        bookkeeping_root = os.path.join(PROJECT_ROOT, "bookkeeping")
        bk = BookkeepingManager(bookkeeping_root)

        # Find last session date from recent summaries
        summaries = bk.get_session_summaries(last_n=1)
        if summaries:
            filename = summaries[0].get("filename", "")
            # Filename format: session-YYYY-MM-DD-NNN.md
            parts = filename.replace("session-", "").replace(".md", "")
            # Extract date portion (first 10 chars after prefix removal)
            if len(parts) >= 10:
                last_session_date = parts[:10]

        # Start the new session
        session_id = bk.start_session(focus=f"Step {current_step} - {current_phase}")
    except Exception as e:
        print(f"[session_start] Bookkeeper: {e}")

    # --- Print Session Summary ---
    print("=" * 60)
    print("  WORLDBUILDING INTERACTIVE PROGRAM -- SESSION START")
    print("=" * 60)
    print()
    print(f"  Current Step:      {current_step}")
    print(f"  Current Phase:     {current_phase}")
    print(f"  Steps Completed:   {len(completed_steps)}/52")
    print(f"  Entities Created:  {entity_count}")
    print(f"  SQLite Synced:     {synced_count} entities")
    print(f"  Last Session:      {last_session_date}")

    if session_id:
        print(f"  Session ID:        {session_id}")

    if graph_stats:
        print(f"  Graph Nodes:       {graph_stats.get('node_count', 0)}")
        print(f"  Graph Edges:       {graph_stats.get('edge_count', 0)}")
        print(f"  Orphan Entities:   {graph_stats.get('orphan_count', 0)}")

    # Show incomplete work
    if in_progress_steps:
        print()
        print("  INCOMPLETE WORK FROM PRIOR SESSIONS:")
        for step in in_progress_steps:
            print(f"    - Step {step}")

    # Show entities in draft status
    draft_entities = [
        eid for eid, meta in entity_index.items()
        if meta.get("status") == "draft"
    ]
    if draft_entities:
        print()
        print(f"  DRAFT ENTITIES ({len(draft_entities)}):")
        for eid in draft_entities[:10]:
            meta = entity_index[eid]
            print(f"    - {meta.get('name', eid)} ({meta.get('entity_type', '?')})")
        if len(draft_entities) > 10:
            print(f"    ... and {len(draft_entities) - 10} more")

    print()
    print("=" * 60)
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[session_start] Error: {e}")
