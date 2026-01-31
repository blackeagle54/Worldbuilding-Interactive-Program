"""
hooks/inject_step_context.py -- UserPromptSubmit Hook for the Worldbuilding
Interactive Program

Hook Type: UserPromptSubmit
Trigger:   Runs on every user message

Purpose:
    - Reads user-world/state.json to get current_step
    - Uses ChunkPuller.pull_condensed() to get condensed guidance for the
      current step
    - Uses FairRepresentationManager to select featured sources for this
      interaction
    - Queries SQLite for entities relevant to current step (by step number
      and cross-references)
    - Builds a context injection block that includes:
        * Current step name and phase
        * Key book guidance (condensed)
        * Featured reference sources for this step
        * Relevant existing entities (names, types, key claims)
        * Any pending consistency warnings
    - Prints the context block to stdout (Claude Code hooks capture stdout)

Usage:
    python C:/Worldbuilding-Interactive-Program/hooks/inject_step_context.py
"""

import sys
import os
import json

PROJECT_ROOT = "C:/Worldbuilding-Interactive-Program"
sys.path.insert(0, PROJECT_ROOT)

from engine.utils import safe_read_json as _safe_read_json


def main():
    state_path = os.path.join(PROJECT_ROOT, "user-world", "state.json")
    state = _safe_read_json(state_path, default={})

    current_step = state.get("current_step", 1)
    current_phase = state.get("current_phase", "foundation")

    parts = []

    # --- Header ---
    parts.append("[WORLDBUILDING CONTEXT]")
    parts.append(f"Step: {current_step} | Phase: {current_phase}")
    parts.append("")

    # --- Condensed guidance from ChunkPuller ---
    try:
        from engine.chunk_puller import ChunkPuller
        cp = ChunkPuller(PROJECT_ROOT)
        condensed = cp.pull_condensed(current_step)
        if condensed:
            parts.append(condensed)
            parts.append("")
    except Exception:
        pass

    # --- Featured reference sources from FairRepresentationManager ---
    try:
        from engine.fair_representation import FairRepresentationManager
        frm = FairRepresentationManager(state_path)
        selection = frm.select_featured(current_step)
        frm.save_state()

        featured_myths = selection.get("featured_mythologies", [])
        featured_auths = selection.get("featured_authors", [])

        if featured_myths or featured_auths:
            parts.append("FEATURED SOURCES THIS INTERACTION:")
            if featured_myths:
                parts.append(f"  Mythologies: {', '.join(featured_myths)}")
            if featured_auths:
                parts.append(f"  Authors: {', '.join(featured_auths)}")
            parts.append("")
    except Exception:
        pass

    # --- Relevant entities from SQLite ---
    try:
        from engine.sqlite_sync import SQLiteSyncEngine
        sync = SQLiteSyncEngine(PROJECT_ROOT)

        # Query entities created at this step
        step_entities = sync.query_by_step(current_step)

        # Also get all entities for general awareness
        all_stats = sync.get_stats()
        total_entities = all_stats.get("total_entities", 0)

        if total_entities > 0:
            parts.append(f"EXISTING ENTITIES ({total_entities} total):")

            # Show entities for current step
            if step_entities:
                parts.append(f"  Created at Step {current_step}:")
                for ent in step_entities[:8]:
                    name = ent.get("name", "?")
                    etype = ent.get("entity_type", "?")
                    status = ent.get("status", "draft")
                    parts.append(f"    - {name} ({etype}, {status})")
                if len(step_entities) > 8:
                    parts.append(f"    ... and {len(step_entities) - 8} more")

            # Show type breakdown
            by_type = all_stats.get("by_type", {})
            if by_type:
                type_summary = ", ".join(
                    f"{t}: {c}" for t, c in sorted(by_type.items(), key=lambda x: -x[1])
                )
                parts.append(f"  By type: {type_summary}")

            parts.append("")

        sync.close()
    except Exception:
        pass

    # --- Pending consistency warnings ---
    try:
        from engine.bookkeeper import BookkeepingManager
        bookkeeping_root = os.path.join(PROJECT_ROOT, "bookkeeping")
        bk = BookkeepingManager(bookkeeping_root)

        open_contradictions = bk.get_contradictions(status="open")
        if open_contradictions:
            parts.append(f"PENDING CONSISTENCY WARNINGS ({len(open_contradictions)}):")
            for contradiction in open_contradictions[:5]:
                desc = contradiction.get("description", "Unknown issue")
                severity = contradiction.get("severity", "warning")
                parts.append(f"  [{severity.upper()}] {desc}")
            if len(open_contradictions) > 5:
                parts.append(f"  ... and {len(open_contradictions) - 5} more")
            parts.append("")
    except Exception:
        pass

    # --- Print the context block ---
    output = "\n".join(parts).strip()
    if output:
        print(output)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[inject_step_context] Error: {e}")
