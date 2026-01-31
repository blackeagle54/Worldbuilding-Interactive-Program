"""
hooks/check_completion.py -- PostToolUse Hook for the Worldbuilding Interactive
Program (triggers periodically)

Hook Type: PostToolUse
Trigger:   Triggers periodically to check step completion status

Purpose:
    - Checks if the current progression step's requirements are met
    - Reads the template for the current step from template_registry
    - Checks if all required entities for this step exist and pass validation
    - If step is complete:
        * Prints a congratulatory message with what was accomplished
        * Suggests advancing to the next step
        * Shows what the next step will cover (brief preview)
    - If not complete:
        * Shows remaining requirements
        * Shows completion percentage

Usage:
    python C:/Worldbuilding-Interactive-Program/hooks/check_completion.py
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
    entity_index = state.get("entity_index", {})
    completed_steps = state.get("completed_steps", [])

    # --- Load template registry to find requirements for this step ---
    registry_path = os.path.join(PROJECT_ROOT, "engine", "template_registry.json")
    registry_data = _safe_read_json(registry_path, default={})

    raw_templates = registry_data.get("templates", [])
    if isinstance(raw_templates, list):
        templates_list = raw_templates
    elif isinstance(raw_templates, dict):
        templates_list = list(raw_templates.values())
    else:
        templates_list = []

    # Find templates for the current step
    step_templates = [t for t in templates_list if t.get("step") == current_step]

    # --- Use ChunkPuller for step info ---
    step_title = f"Step {current_step}"
    step_phase = ""
    next_step_title = f"Step {current_step + 1}"
    next_step_condensed = ""

    try:
        from engine.chunk_puller import ChunkPuller
        cp = ChunkPuller(PROJECT_ROOT)

        step_info = cp._get_step_info(current_step)
        step_title = f"Step {current_step}: {step_info.get('title', '')}"
        step_phase = step_info.get("phase_name", "")

        # Get next step preview
        if current_step < 52:
            next_info = cp._get_step_info(current_step + 1)
            next_step_title = f"Step {current_step + 1}: {next_info.get('title', '')}"
            next_step_condensed = cp.pull_condensed(current_step + 1)
            # Truncate the condensed preview
            if len(next_step_condensed) > 300:
                next_step_condensed = next_step_condensed[:300] + "..."
    except Exception as e:
        print(f"[check_completion] ChunkPuller step info: {e}")

    # --- Calculate completion for this step ---
    total_minimum = 0
    existing_count = 0
    template_ids = []
    primary_entity_type = ""

    for tmpl in step_templates:
        tid = tmpl.get("id", "")
        template_ids.append(tid)
        total_minimum += tmpl.get("minimum_count", 1)
        if not primary_entity_type:
            primary_entity_type = tmpl.get("entity_type", "")

    # Count existing entities matching this step's templates
    existing_entities = []
    for eid, emeta in entity_index.items():
        if emeta.get("template_id") in template_ids:
            existing_entities.append(emeta)
        elif primary_entity_type and emeta.get("entity_type") == primary_entity_type:
            existing_entities.append(emeta)

    existing_count = len(existing_entities)

    # --- Check dependencies ---
    dependencies_met = True
    missing_deps = []
    try:
        from engine.chunk_puller import ChunkPuller
        cp = ChunkPuller(PROJECT_ROOT)
        deps = cp.get_step_dependencies(current_step)
        dependencies_met = deps.get("dependencies_met", True)
        missing_deps = deps.get("missing_dependencies", [])
    except Exception as e:
        print(f"[check_completion] Dependency check: {e}")

    # --- Determine completion status ---
    if total_minimum == 0:
        # Steps without templates (strategy/planning steps)
        # Consider complete if the step is in completed_steps
        is_complete = current_step in completed_steps
        completion_pct = 100 if is_complete else 0
    else:
        completion_pct = min(100, int((existing_count / total_minimum) * 100)) if total_minimum > 0 else 0
        is_complete = existing_count >= total_minimum and dependencies_met

    # --- Print completion status ---
    if is_complete:
        print()
        print("=" * 50)
        print(f"  STEP COMPLETE: {step_title}")
        if step_phase:
            print(f"  Phase: {step_phase}")
        print("=" * 50)
        print()
        print(f"  You have created {existing_count} entities for this step.")

        # Show what was accomplished
        if existing_entities:
            print()
            print("  ENTITIES CREATED:")
            for ent in existing_entities[:10]:
                name = ent.get("name", "?")
                status = ent.get("status", "draft")
                print(f"    - {name} ({status})")
            if len(existing_entities) > 10:
                print(f"    ... and {len(existing_entities) - 10} more")

        # Suggest next step
        if current_step < 52:
            print()
            print(f"  NEXT: {next_step_title}")
            if next_step_condensed:
                # Show just the first few lines of the preview
                preview_lines = next_step_condensed.split("\n")[:5]
                for line in preview_lines:
                    if line.strip():
                        print(f"    {line}")
            print()
            print("  Ready to advance? Update state.json to move to the next step.")
        else:
            print()
            print("  CONGRATULATIONS! You have completed all 52 steps!")
            print("  Your world is built. Time for final review and polish.")

        print()
        print("=" * 50)
        print()
    else:
        # Not complete -- show remaining work
        print()
        print(f"[STEP PROGRESS: {step_title}]")
        if step_phase:
            print(f"Phase: {step_phase}")
        print()

        if total_minimum > 0:
            bar_width = 30
            filled = int(bar_width * completion_pct / 100)
            bar = "#" * filled + "-" * (bar_width - filled)
            print(f"  Progress: [{bar}] {completion_pct}%")
            print(f"  Entities: {existing_count}/{total_minimum}")
            print()

            remaining = total_minimum - existing_count
            if remaining > 0:
                print(f"  REMAINING: Create {remaining} more entity(ies) for this step.")
        else:
            print("  This step does not require entity creation.")
            print("  It may involve planning, strategy, or written statements.")
            print(f"  Mark step {current_step} as complete in state.json when done.")

        if not dependencies_met and missing_deps:
            print()
            print(f"  BLOCKED: The following prerequisite steps are not complete:")
            for dep in missing_deps[:10]:
                print(f"    - Step {dep}")
            if len(missing_deps) > 10:
                print(f"    ... and {len(missing_deps) - 10} more")

        if template_ids:
            print()
            print(f"  Templates: {', '.join(template_ids)}")

        print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[check_completion] Error: {e}")
