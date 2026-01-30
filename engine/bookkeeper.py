"""
Bookkeeping Manager for the Worldbuilding Interactive Program.

An event-sourced bookkeeping system that silently records every decision,
draft, revision, and session. The user never interacts with it directly --
Claude Code manages it automatically.

Architecture (three layers):
    Layer 1: Event Log (Source of Truth)
        Append-only JSONL files in bookkeeping/events/
        One file per month (events-YYYY-MM.jsonl)

    Layer 2: Derived Index Files (Fast Querying)
        JSON files in bookkeeping/indexes/ rebuilt from the event log

    Layer 3: Session Summaries (Human-Readable)
        Markdown files in bookkeeping/sessions/

Dependencies: Python standard library only (json, datetime, os, pathlib, glob).
"""

import json
import os
import glob
from datetime import datetime, timezone
from pathlib import Path


class BookkeepingManager:
    """Manages event logging, derived indexes, and session summaries.

    All events are append-only -- never edited or deleted. The JSONL event
    log is the single source of truth. Derived index files are caches that
    can always be rebuilt via ``rebuild_indexes()``.
    """

    # Event type constants
    EVENT_SESSION_STARTED = "session_started"
    EVENT_SESSION_ENDED = "session_ended"
    EVENT_DECISION_MADE = "decision_made"
    EVENT_DRAFT_CREATED = "draft_created"
    EVENT_STATUS_CHANGED = "status_changed"
    EVENT_ENTITY_REVISED = "entity_revised"
    EVENT_CROSS_REFERENCE_CREATED = "cross_reference_created"
    EVENT_CONTRADICTION_FOUND = "contradiction_found"
    EVENT_CONTRADICTION_RESOLVED = "contradiction_resolved"
    EVENT_STEP_STATUS_CHANGED = "step_status_changed"

    def __init__(self, bookkeeping_root):
        """Initialize the BookkeepingManager.

        Args:
            bookkeeping_root: Absolute path to the bookkeeping/ directory.
                Example: ``"C:/Worldbuilding-Interactive-Program/bookkeeping"``
        """
        self.root = Path(bookkeeping_root)
        self.events_dir = self.root / "events"
        self.indexes_dir = self.root / "indexes"
        self.revisions_dir = self.root / "revisions"
        self.sessions_dir = self.root / "sessions"
        self.snapshots_dir = self.root / "snapshots"

        # Paths to derived index files
        self.decisions_index = self.indexes_dir / "decisions.json"
        self.progression_index = self.indexes_dir / "progression.json"
        self.entity_registry_index = self.indexes_dir / "entity-registry.json"
        self.cross_references_index = self.indexes_dir / "cross-references.json"
        self.contradictions_index = self.indexes_dir / "contradictions.json"
        self.revisions_index = self.revisions_dir / "revisions-by-entity.json"

        # Session state
        self._current_session_id = None
        self._session_number = None
        self._session_start_time = None
        self._session_events = []

        # Ensure all directories exist
        self._ensure_directories()

        # Ensure all index files exist with empty structures
        self._ensure_index_files()

    # ------------------------------------------------------------------
    # Directory and file initialization
    # ------------------------------------------------------------------

    def _ensure_directories(self):
        """Create the bookkeeping directory tree if it does not exist."""
        for directory in [
            self.events_dir,
            self.indexes_dir,
            self.revisions_dir,
            self.revisions_dir / "snapshots",
            self.sessions_dir,
            self.snapshots_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def _ensure_index_files(self):
        """Create empty index files if they do not already exist."""
        defaults = {
            self.decisions_index: {"decisions": []},
            self.progression_index: {"steps": {}},
            self.entity_registry_index: {"entities": {}},
            self.cross_references_index: {"cross_references": []},
            self.contradictions_index: {"contradictions": []},
            self.revisions_index: {"revisions": {}},
        }
        for path, empty_structure in defaults.items():
            if not path.exists():
                self._write_json(path, empty_structure)

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _now(self):
        """Return the current UTC time as an ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()

    def _today(self):
        """Return today's date as ``YYYY-MM-DD``."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _current_month(self):
        """Return the current month as ``YYYY-MM``."""
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _event_log_path(self):
        """Return the path to the current month's JSONL event log."""
        return self.events_dir / f"events-{self._current_month()}.jsonl"

    def _read_json(self, path):
        """Read and return a JSON file. Returns ``None`` on failure."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _write_json(self, path, data):
        """Write *data* as pretty-printed JSON to *path*."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

    def _append_event(self, event_type, data):
        """Append an event to the JSONL log and in-memory session list.

        Args:
            event_type: One of the ``EVENT_*`` constants.
            data: Dict with event-specific payload.

        Returns:
            The full event dict that was written.
        """
        event = {
            "timestamp": self._now(),
            "session_id": self._current_session_id or "no-session",
            "event_type": event_type,
            "data": data,
        }
        log_path = self._event_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

        # Track events within the current session for summary generation
        self._session_events.append(event)
        return event

    def _load_all_events(self):
        """Load every event from all JSONL log files, sorted by timestamp.

        Returns:
            A list of event dicts.
        """
        events = []
        pattern = str(self.events_dir / "events-*.jsonl")
        for filepath in sorted(glob.glob(pattern)):
            try:
                with open(filepath, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                events.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
            except OSError:
                continue
        return events

    def _next_session_number(self):
        """Determine the next session number by scanning existing events."""
        events = self._load_all_events()
        max_num = 0
        for ev in events:
            if ev.get("event_type") == self.EVENT_SESSION_STARTED:
                sid = ev.get("data", {}).get("session_number", 0)
                if isinstance(sid, int) and sid > max_num:
                    max_num = sid
        return max_num + 1

    def _next_contradiction_id(self):
        """Generate the next contradiction ID from existing contradictions."""
        index = self._read_json(self.contradictions_index) or {"contradictions": []}
        existing = index.get("contradictions", [])
        return f"contradiction-{len(existing) + 1:04d}"

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def start_session(self, focus=""):
        """Start a new bookkeeping session.

        Args:
            focus: A short description of what this session will focus on.

        Returns:
            The session ID string (e.g., ``"session-001"``).
        """
        self._session_number = self._next_session_number()
        self._current_session_id = f"session-{self._session_number:03d}"
        self._session_start_time = self._now()
        self._session_events = []

        self._append_event(self.EVENT_SESSION_STARTED, {
            "session_number": self._session_number,
            "focus": focus,
        })
        return self._current_session_id

    def end_session(self, summary=""):
        """End the current session.

        Records a ``session_ended`` event, generates a session summary
        markdown file, and rebuilds all derived index files.

        Args:
            summary: A brief summary of what was accomplished.

        Returns:
            The path to the generated session summary markdown file,
            or ``None`` if no session was active.
        """
        if not self._current_session_id:
            return None

        # Gather session statistics from in-memory events
        steps_worked = set()
        decisions_made = []
        entities_created = []
        entities_modified = []
        contradictions_found = []
        contradictions_resolved = []

        for ev in self._session_events:
            etype = ev.get("event_type")
            edata = ev.get("data", {})

            if etype == self.EVENT_DECISION_MADE:
                decisions_made.append(edata)
                step = edata.get("step_id")
                if step:
                    steps_worked.add(step)

            elif etype == self.EVENT_DRAFT_CREATED:
                entities_created.append(edata)

            elif etype == self.EVENT_ENTITY_REVISED:
                entities_modified.append(edata)

            elif etype == self.EVENT_STATUS_CHANGED:
                entities_modified.append(edata)

            elif etype == self.EVENT_STEP_STATUS_CHANGED:
                steps_worked.add(edata.get("step_id", ""))

            elif etype == self.EVENT_CONTRADICTION_FOUND:
                contradictions_found.append(edata)

            elif etype == self.EVENT_CONTRADICTION_RESOLVED:
                contradictions_resolved.append(edata)

        session_data = {
            "summary": summary,
            "steps_worked": sorted(steps_worked),
            "decisions_count": len(decisions_made),
            "entities_created_count": len(entities_created),
            "entities_modified_count": len(entities_modified),
            "contradictions_found_count": len(contradictions_found),
            "contradictions_resolved_count": len(contradictions_resolved),
        }

        self._append_event(self.EVENT_SESSION_ENDED, session_data)

        # Generate session summary markdown
        summary_path = self._generate_session_summary(
            steps_worked=sorted(steps_worked),
            decisions_made=decisions_made,
            entities_created=entities_created,
            entities_modified=entities_modified,
            contradictions_found=contradictions_found,
            contradictions_resolved=contradictions_resolved,
            summary_text=summary,
        )

        # Rebuild all derived indexes from the full event log
        self.rebuild_indexes()

        # Reset session state
        self._current_session_id = None
        self._session_number = None
        self._session_start_time = None
        self._session_events = []

        return summary_path

    def _generate_session_summary(
        self,
        steps_worked,
        decisions_made,
        entities_created,
        entities_modified,
        contradictions_found,
        contradictions_resolved,
        summary_text,
    ):
        """Write a structured markdown session summary file.

        Returns:
            The ``Path`` to the generated file.
        """
        today = self._today()
        # Determine the NNN suffix for today
        existing = sorted(glob.glob(
            str(self.sessions_dir / f"session-{today}-*.md")
        ))
        next_num = len(existing) + 1
        filename = f"session-{today}-{next_num:03d}.md"
        filepath = self.sessions_dir / filename

        lines = [
            f"# Session {self._session_number} -- {today}",
            "",
        ]

        if summary_text:
            lines += [f"**Summary:** {summary_text}", ""]

        # Steps worked on
        lines.append("## Steps Worked On")
        lines.append("")
        if steps_worked:
            for step in steps_worked:
                lines.append(f"- {step}")
        else:
            lines.append("- (none)")
        lines.append("")

        # Decisions made
        lines.append("## Decisions Made")
        lines.append("")
        if decisions_made:
            for dec in decisions_made:
                question = dec.get("question", "(no question recorded)")
                chosen = dec.get("chosen", "(unknown)")
                lines.append(f"- **Q:** {question}")
                lines.append(f"  **Chosen:** {chosen}")
                rationale = dec.get("rationale", "")
                if rationale:
                    lines.append(f"  **Rationale:** {rationale}")
        else:
            lines.append("- (none)")
        lines.append("")

        # Entities created
        lines.append("## Entities Created")
        lines.append("")
        if entities_created:
            for ent in entities_created:
                eid = ent.get("entity_id", "?")
                etype = ent.get("entity_type", "?")
                lines.append(f"- {eid} ({etype})")
        else:
            lines.append("- (none)")
        lines.append("")

        # Entities modified
        lines.append("## Entities Modified")
        lines.append("")
        if entities_modified:
            for ent in entities_modified:
                eid = ent.get("entity_id", "?")
                change = ent.get("change_summary", ent.get("new_status", "modified"))
                lines.append(f"- {eid}: {change}")
        else:
            lines.append("- (none)")
        lines.append("")

        # Contradictions
        lines.append("## Contradictions Found")
        lines.append("")
        if contradictions_found:
            for c in contradictions_found:
                desc = c.get("description", "?")
                lines.append(f"- {desc}")
        else:
            lines.append("- (none)")
        lines.append("")

        lines.append("## Contradictions Resolved")
        lines.append("")
        if contradictions_resolved:
            for c in contradictions_resolved:
                res = c.get("resolution", "?")
                lines.append(f"- {res}")
        else:
            lines.append("- (none)")
        lines.append("")

        # Notes
        lines.append("## Notes")
        lines.append("")
        lines.append("(auto-generated by bookkeeper)")
        lines.append("")

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        return filepath

    # ------------------------------------------------------------------
    # Event recording methods
    # ------------------------------------------------------------------

    def record_decision(self, step_id, question, options, chosen, rationale=""):
        """Record a decision made by the user.

        Args:
            step_id: The progression step ID (e.g., ``"step-07"``).
            question: The question that was posed.
            options: A list of dicts, each with at least ``"name"`` and
                ``"description"`` keys representing one option presented.
            chosen: The name/identifier of the chosen option.
            rationale: The user's reason for the choice.

        Returns:
            The recorded event dict.
        """
        rejected = [
            opt.get("name", str(opt)) for opt in options
            if opt.get("name") != chosen
        ]

        return self._append_event(self.EVENT_DECISION_MADE, {
            "step_id": step_id,
            "question": question,
            "options": options,
            "chosen": chosen,
            "rejected": rejected,
            "rationale": rationale,
        })

    def record_entity_created(self, entity_id, entity_type, file_path, status="draft"):
        """Record the creation of a new entity.

        Args:
            entity_id: The unique entity ID (e.g., ``"thorin-stormkeeper-a1b2"``).
            entity_type: The entity type (e.g., ``"gods"``).
            file_path: The path where the entity JSON was saved.
            status: Initial status, typically ``"draft"``.

        Returns:
            The recorded event dict.
        """
        return self._append_event(self.EVENT_DRAFT_CREATED, {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "file_path": str(file_path),
            "status": status,
        })

    def record_status_change(self, entity_id, old_status, new_status, reason=""):
        """Record a status change on an entity (e.g., draft -> canon).

        Args:
            entity_id: The entity's unique ID.
            old_status: Previous status string.
            new_status: New status string.
            reason: Why the status was changed.

        Returns:
            The recorded event dict.
        """
        return self._append_event(self.EVENT_STATUS_CHANGED, {
            "entity_id": entity_id,
            "old_status": old_status,
            "new_status": new_status,
            "reason": reason,
        })

    def record_entity_revised(self, entity_id, revision_number, change_summary, reason, snapshot_path):
        """Record a revision to an existing entity.

        Args:
            entity_id: The entity's unique ID.
            revision_number: The ordinal revision number.
            change_summary: A brief description of what changed.
            reason: Why the revision was made.
            snapshot_path: Path to the saved snapshot of the previous version.

        Returns:
            The recorded event dict.
        """
        return self._append_event(self.EVENT_ENTITY_REVISED, {
            "entity_id": entity_id,
            "revision_number": revision_number,
            "change_summary": change_summary,
            "reason": reason,
            "snapshot_path": str(snapshot_path),
        })

    def record_cross_reference(self, source_id, target_id, relationship_type, bidirectional=False):
        """Record a cross-reference between two entities.

        Args:
            source_id: The source entity ID.
            target_id: The target entity ID.
            relationship_type: The type of relationship (e.g., ``"spouse"``).
            bidirectional: Whether the relationship goes both ways.

        Returns:
            The recorded event dict.
        """
        return self._append_event(self.EVENT_CROSS_REFERENCE_CREATED, {
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": relationship_type,
            "bidirectional": bidirectional,
        })

    def record_contradiction(self, entities, description, severity):
        """Record a contradiction detected by the consistency checker.

        Args:
            entities: List of entity IDs involved in the contradiction.
            description: Human-readable description of the contradiction.
            severity: Severity level (e.g., ``"critical"``, ``"warning"``).

        Returns:
            The recorded event dict.
        """
        contradiction_id = self._next_contradiction_id()
        return self._append_event(self.EVENT_CONTRADICTION_FOUND, {
            "contradiction_id": contradiction_id,
            "entities": entities,
            "description": description,
            "severity": severity,
            "status": "open",
        })

    def resolve_contradiction(self, contradiction_id, resolution, entities_modified):
        """Record the resolution of a previously found contradiction.

        Args:
            contradiction_id: The ID of the contradiction being resolved.
            resolution: Description of how it was resolved.
            entities_modified: List of entity IDs that were modified.

        Returns:
            The recorded event dict.
        """
        return self._append_event(self.EVENT_CONTRADICTION_RESOLVED, {
            "contradiction_id": contradiction_id,
            "resolution": resolution,
            "entities_modified": entities_modified,
        })

    def record_step_change(self, step_id, old_status, new_status):
        """Record a progression step status change.

        Args:
            step_id: The step ID (e.g., ``"step-07"``).
            old_status: Previous status (e.g., ``"not_started"``).
            new_status: New status (e.g., ``"in_progress"``, ``"completed"``).

        Returns:
            The recorded event dict.
        """
        return self._append_event(self.EVENT_STEP_STATUS_CHANGED, {
            "step_id": step_id,
            "old_status": old_status,
            "new_status": new_status,
        })

    # ------------------------------------------------------------------
    # Index rebuilding
    # ------------------------------------------------------------------

    def rebuild_indexes(self):
        """Rebuild all derived index files from the event log.

        This is the recovery mechanism: if any index file becomes corrupt
        or out of sync, calling ``rebuild_indexes()`` restores them from
        the append-only event log (the single source of truth).
        """
        events = self._load_all_events()

        decisions = []
        steps = {}
        entities = {}
        cross_refs = []
        contradictions = {}
        revisions = {}

        for ev in events:
            etype = ev.get("event_type")
            edata = ev.get("data", {})
            timestamp = ev.get("timestamp", "")

            # --- Decisions ---
            if etype == self.EVENT_DECISION_MADE:
                decisions.append({
                    "timestamp": timestamp,
                    "session_id": ev.get("session_id"),
                    "step_id": edata.get("step_id"),
                    "question": edata.get("question"),
                    "options": edata.get("options", []),
                    "chosen": edata.get("chosen"),
                    "rejected": edata.get("rejected", []),
                    "rationale": edata.get("rationale", ""),
                })

            # --- Progression ---
            elif etype == self.EVENT_STEP_STATUS_CHANGED:
                step_id = edata.get("step_id", "")
                steps[step_id] = {
                    "step_id": step_id,
                    "status": edata.get("new_status", "unknown"),
                    "last_updated": timestamp,
                }

            # --- Entity Registry ---
            elif etype == self.EVENT_DRAFT_CREATED:
                eid = edata.get("entity_id", "")
                entities[eid] = {
                    "entity_id": eid,
                    "entity_type": edata.get("entity_type", ""),
                    "file_path": edata.get("file_path", ""),
                    "status": edata.get("status", "draft"),
                    "revision_count": 0,
                    "created": timestamp,
                    "last_updated": timestamp,
                }

            elif etype == self.EVENT_STATUS_CHANGED:
                eid = edata.get("entity_id", "")
                if eid in entities:
                    entities[eid]["status"] = edata.get("new_status", entities[eid]["status"])
                    entities[eid]["last_updated"] = timestamp

            elif etype == self.EVENT_ENTITY_REVISED:
                eid = edata.get("entity_id", "")
                if eid in entities:
                    entities[eid]["revision_count"] = edata.get("revision_number", 0)
                    entities[eid]["last_updated"] = timestamp

                # Revisions by entity
                if eid not in revisions:
                    revisions[eid] = []
                revisions[eid].append({
                    "revision_number": edata.get("revision_number"),
                    "change_summary": edata.get("change_summary", ""),
                    "reason": edata.get("reason", ""),
                    "snapshot_path": edata.get("snapshot_path", ""),
                    "timestamp": timestamp,
                })

            # --- Cross-references ---
            elif etype == self.EVENT_CROSS_REFERENCE_CREATED:
                ref = {
                    "source_id": edata.get("source_id"),
                    "target_id": edata.get("target_id"),
                    "relationship_type": edata.get("relationship_type"),
                    "bidirectional": edata.get("bidirectional", False),
                    "timestamp": timestamp,
                }
                cross_refs.append(ref)

            # --- Contradictions ---
            elif etype == self.EVENT_CONTRADICTION_FOUND:
                cid = edata.get("contradiction_id", "")
                contradictions[cid] = {
                    "contradiction_id": cid,
                    "entities": edata.get("entities", []),
                    "description": edata.get("description", ""),
                    "severity": edata.get("severity", ""),
                    "status": "open",
                    "found_at": timestamp,
                    "resolved_at": None,
                    "resolution": None,
                }

            elif etype == self.EVENT_CONTRADICTION_RESOLVED:
                cid = edata.get("contradiction_id", "")
                if cid in contradictions:
                    contradictions[cid]["status"] = "resolved"
                    contradictions[cid]["resolved_at"] = timestamp
                    contradictions[cid]["resolution"] = edata.get("resolution", "")
                    contradictions[cid]["entities_modified"] = edata.get("entities_modified", [])

        # Write all index files
        self._write_json(self.decisions_index, {"decisions": decisions})
        self._write_json(self.progression_index, {"steps": steps})
        self._write_json(self.entity_registry_index, {"entities": entities})
        self._write_json(self.cross_references_index, {"cross_references": cross_refs})
        self._write_json(self.contradictions_index, {
            "contradictions": list(contradictions.values())
        })
        self._write_json(self.revisions_index, {"revisions": revisions})

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_decisions(self, step_id=None, keyword=None):
        """Query the decisions index.

        Args:
            step_id: Filter decisions to a specific step (optional).
            keyword: Filter decisions whose question or chosen option
                contains this keyword, case-insensitive (optional).

        Returns:
            A list of decision dicts matching the filters.
        """
        index = self._read_json(self.decisions_index) or {"decisions": []}
        results = index.get("decisions", [])

        if step_id is not None:
            results = [d for d in results if d.get("step_id") == step_id]

        if keyword is not None:
            kw = keyword.lower()
            results = [
                d for d in results
                if kw in d.get("question", "").lower()
                or kw in d.get("chosen", "").lower()
                or kw in d.get("rationale", "").lower()
            ]

        return results

    def get_entity_history(self, entity_id):
        """Return the full revision history for an entity.

        Args:
            entity_id: The entity's unique ID.

        Returns:
            A list of revision dicts sorted by revision number,
            or an empty list if the entity has no revisions.
        """
        index = self._read_json(self.revisions_index) or {"revisions": {}}
        revisions = index.get("revisions", {}).get(entity_id, [])
        return sorted(revisions, key=lambda r: r.get("revision_number", 0))

    def get_contradictions(self, status=None):
        """Query the contradictions index.

        Args:
            status: Filter by status (``"open"`` or ``"resolved"``).
                If ``None``, returns all contradictions.

        Returns:
            A list of contradiction dicts matching the filter.
        """
        index = self._read_json(self.contradictions_index) or {"contradictions": []}
        results = index.get("contradictions", [])

        if status is not None:
            results = [c for c in results if c.get("status") == status]

        return results

    def get_session_summaries(self, last_n=3):
        """Read the last N session summary markdown files.

        Args:
            last_n: Number of most-recent summaries to return.

        Returns:
            A list of dicts with ``"filename"`` and ``"content"`` keys,
            ordered most-recent first.
        """
        pattern = str(self.sessions_dir / "session-*.md")
        files = sorted(glob.glob(pattern))

        # Take the last N files (most recent by filename sort)
        recent = files[-last_n:] if last_n > 0 else files
        recent.reverse()  # Most recent first

        summaries = []
        for filepath in recent:
            try:
                with open(filepath, "r", encoding="utf-8") as fh:
                    content = fh.read()
                summaries.append({
                    "filename": os.path.basename(filepath),
                    "content": content,
                })
            except OSError:
                continue

        return summaries

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def current_session_id(self):
        """The ID of the active session, or ``None``."""
        return self._current_session_id

    @property
    def session_active(self):
        """Whether a session is currently in progress."""
        return self._current_session_id is not None
