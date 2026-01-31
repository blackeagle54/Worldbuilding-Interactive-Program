"""
engine/backup_manager.py -- Automated Backup System for the Worldbuilding Interactive Program

Provides full backup, restore, comparison, and cleanup capabilities for the
user-world/ directory.  Backups are stored as timestamped ZIP files in the
backups/ directory at the project root.

What is backed up:
    - All entity JSON files  (user-world/entities/**)
    - State file             (user-world/state.json)
    - Worksheets             (user-world/worksheets/**)
    - Registries             (user-world/registries/**)
    - Timelines              (user-world/timelines/**)
    - Travel data            (user-world/travel/**)
    - Maps                   (user-world/maps/**)

What is NOT backed up:
    - runtime/*.db           (always rebuildable from JSON)
    - bookkeeping/           (append-only logs, never overwritten)
    - reference-databases/   (static reference data shipped with the program)

Usage:
    from engine.backup_manager import BackupManager

    bm = BackupManager("C:/Worldbuilding-Interactive-Program")
    meta = bm.create_backup(label="before-gods-rework")
    backups = bm.list_backups()
    diff = bm.compare_backup(backups[0]["path"])
    bm.restore_backup(backups[0]["path"], confirm=True)

Dependencies: Python standard library only (json, zipfile, os, shutil, tempfile,
              datetime, pathlib).
"""

import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from engine.utils import safe_read_json as _safe_read_json


def _now_utc() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# BackupManager
# ---------------------------------------------------------------------------

class BackupManager:
    """Manages creation, listing, restoration, comparison, and cleanup of
    worldbuilding backups.

    Parameters
    ----------
    project_root : str
        Absolute path to the Worldbuilding Interactive Program root directory,
        e.g. ``"C:/Worldbuilding-Interactive-Program"``.
    """

    # Current manifest schema version -- bump when the manifest format changes
    MANIFEST_VERSION = 1

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.user_world_dir = self.root / "user-world"
        self.state_path = self.user_world_dir / "state.json"
        self.backups_dir = self.root / "backups"

        # Ensure the backups directory exists
        os.makedirs(str(self.backups_dir), exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Automatic / manual backup creation
    # ------------------------------------------------------------------

    def create_backup(self, label: str | None = None) -> dict:
        """Create a timestamped ZIP backup of the entire ``user-world/`` directory.

        Parameters
        ----------
        label : str, optional
            A human-readable label appended to the filename
            (e.g. ``"before-gods-rework"``).  Spaces are replaced with
            hyphens and the string is lowercased.

        Returns
        -------
        dict
            Backup metadata with keys: ``path``, ``filename``, ``size_bytes``,
            ``entity_count``, ``file_count``, ``timestamp``, ``label``.

        Raises
        ------
        RuntimeError
            If the backup cannot be created (e.g. disk space issue).
        """
        now = _now_utc()
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")

        # Sanitise label
        safe_label = ""
        if label:
            safe_label = label.strip().lower().replace(" ", "-")
            # Remove characters that are unsafe in filenames
            safe_label = "".join(
                c for c in safe_label if c.isalnum() or c in ("-", "_")
            )

        if safe_label:
            filename = f"backup_{timestamp_str}_{safe_label}.zip"
        else:
            filename = f"backup_{timestamp_str}.zip"

        final_path = self.backups_dir / filename

        # Collect files to back up
        files_to_backup = self._collect_backup_files()

        # Count entities (JSON files inside entities/ subdirectory)
        entity_count = 0
        entity_counts_by_type: dict[str, int] = {}
        for rel_path in files_to_backup:
            parts = rel_path.replace("\\", "/").split("/")
            # Pattern: user-world/entities/<type>/<file>.json
            if len(parts) >= 3 and parts[0] == "user-world" and parts[1] == "entities":
                entity_type = parts[2]
                entity_counts_by_type[entity_type] = entity_counts_by_type.get(entity_type, 0) + 1
                entity_count += 1

        # Read current state for the manifest
        state = _safe_read_json(str(self.state_path), default={})
        current_step = state.get("current_step", None)

        # Build manifest
        manifest = {
            "backup_version": self.MANIFEST_VERSION,
            "timestamp": now.isoformat(),
            "label": label or "",
            "entity_count": entity_count,
            "entity_counts_by_type": entity_counts_by_type,
            "current_progression_step": current_step,
            "total_file_count": len(files_to_backup),
        }

        # Write to a temp file first, then move (atomic-ish operation)
        try:
            fd, tmp_path = tempfile.mkstemp(
                suffix=".zip", prefix="backup_tmp_", dir=str(self.backups_dir)
            )
            os.close(fd)

            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Write manifest first
                zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

                # Write all collected files
                for rel_path in files_to_backup:
                    abs_path = self.root / rel_path
                    zf.write(str(abs_path), rel_path)

            # Rename temp file to final destination
            shutil.move(tmp_path, str(final_path))

        except OSError as exc:
            # Clean up temp file if it still exists
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise RuntimeError(
                f"Could not create backup. There may be a disk space or "
                f"permissions issue. Technical detail: {exc}"
            ) from exc

        size_bytes = os.path.getsize(str(final_path))

        return {
            "path": str(final_path),
            "filename": filename,
            "size_bytes": size_bytes,
            "entity_count": entity_count,
            "file_count": len(files_to_backup),
            "timestamp": now.isoformat(),
            "label": label or "",
        }

    def _collect_backup_files(self) -> list[str]:
        """Return a sorted list of relative paths (from project root) of all
        files that should be included in a backup.

        Walks the ``user-world/`` directory and includes everything it finds.
        Does NOT include runtime/, bookkeeping/, or reference-databases/.
        """
        files: list[str] = []
        uw = self.user_world_dir
        if not uw.exists():
            return files

        for dirpath_str, _dirnames, filenames in os.walk(str(uw)):
            dirpath = Path(dirpath_str)
            for fname in filenames:
                abs_path = dirpath / fname
                rel_path = str(abs_path.relative_to(self.root)).replace("\\", "/")
                files.append(rel_path)

        files.sort()
        return files

    # ------------------------------------------------------------------
    # 2. Backup management
    # ------------------------------------------------------------------

    def list_backups(self) -> list[dict]:
        """Return all backups sorted by date (newest first) with metadata.

        Returns
        -------
        list[dict]
            Each dict contains: ``path``, ``filename``, ``size_bytes``,
            ``timestamp``, ``label``, ``entity_count``, ``file_count``.
        """
        backups: list[dict] = []
        if not self.backups_dir.exists():
            return backups

        for entry in os.scandir(str(self.backups_dir)):
            if entry.is_file() and entry.name.endswith(".zip"):
                info = self._read_backup_metadata(entry.path)
                if info is not None:
                    backups.append(info)

        # Sort newest first
        backups.sort(key=lambda b: b.get("timestamp", ""), reverse=True)
        return backups

    def get_backup_info(self, backup_path: str) -> dict:
        """Return detailed information about a specific backup.

        Parameters
        ----------
        backup_path : str
            Absolute path to the backup ZIP file.

        Returns
        -------
        dict
            Backup metadata including entity count, size, date, label, and
            entity counts by type.

        Raises
        ------
        FileNotFoundError
            If the backup file does not exist.
        ValueError
            If the file is not a valid backup archive.
        """
        if not os.path.isfile(backup_path):
            raise FileNotFoundError(
                f"The backup file was not found at: {backup_path}\n"
                f"It may have been moved or deleted."
            )

        info = self._read_backup_metadata(backup_path)
        if info is None:
            raise ValueError(
                f"The file at '{backup_path}' does not appear to be a valid "
                f"backup. It may be corrupted or not a backup created by "
                f"this program."
            )

        # Enrich with manifest data if available
        manifest = self._read_manifest(backup_path)
        if manifest:
            info["entity_counts_by_type"] = manifest.get("entity_counts_by_type", {})
            info["current_progression_step"] = manifest.get("current_progression_step")
            info["backup_version"] = manifest.get("backup_version")

        return info

    def delete_backup(self, backup_path: str) -> None:
        """Remove a specific backup file.

        Parameters
        ----------
        backup_path : str
            Absolute path to the backup ZIP file.

        Raises
        ------
        FileNotFoundError
            If the backup file does not exist.
        """
        if not os.path.isfile(backup_path):
            raise FileNotFoundError(
                f"The backup file was not found at: {backup_path}\n"
                f"It may have already been deleted."
            )

        try:
            os.remove(backup_path)
        except OSError as exc:
            raise RuntimeError(
                f"Could not delete the backup file. It may be in use by "
                f"another program. Technical detail: {exc}"
            ) from exc

    def cleanup_old_backups(self, keep_count: int = 10) -> list[str]:
        """Keep only the *keep_count* most recent backups, deleting older ones.

        Parameters
        ----------
        keep_count : int
            Number of most-recent backups to retain (default 10).

        Returns
        -------
        list[str]
            Paths of backups that were deleted.
        """
        all_backups = self.list_backups()  # Already sorted newest-first
        to_delete = all_backups[keep_count:]
        deleted: list[str] = []

        for backup in to_delete:
            path = backup["path"]
            try:
                os.remove(path)
                deleted.append(path)
            except OSError:
                # Skip files we cannot delete; do not interrupt the loop
                pass

        return deleted

    # ------------------------------------------------------------------
    # 3. Restore capabilities
    # ------------------------------------------------------------------

    def restore_backup(self, backup_path: str, confirm: bool = False) -> dict:
        """Restore the world from a backup ZIP.

        Without ``confirm=True``, returns a preview of what would change
        (a dry-run diff).  With ``confirm=True``, actually performs the
        restore.

        A pre-restore safety backup labelled ``"pre_restore"`` is
        automatically created before any destructive operation.

        Parameters
        ----------
        backup_path : str
            Absolute path to the backup ZIP file.
        confirm : bool
            If False (default), return a preview.  If True, execute the
            restore.

        Returns
        -------
        dict
            If ``confirm=False``: the diff preview (same shape as
            ``compare_backup``).
            If ``confirm=True``: ``{"restored": True, "pre_restore_backup": <path>,
            "diff": <diff_dict>}``.

        Raises
        ------
        FileNotFoundError / ValueError
            If the backup file is missing or invalid.
        """
        # Validate the backup first
        self._validate_backup_file(backup_path)

        # Always compute the diff
        diff = self.compare_backup(backup_path)

        if not confirm:
            return diff

        # --- Confirmed restore ---

        # 1. Create a safety backup before restoring
        pre_restore_meta = self.create_backup(label="pre_restore")

        # 2. Remove the current user-world/ contents
        if self.user_world_dir.exists():
            shutil.rmtree(str(self.user_world_dir))

        # 3. Extract the backup into the project root
        #    The ZIP contains paths like "user-world/state.json", so extracting
        #    at the project root recreates the directory tree.
        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                for member in zf.namelist():
                    # Skip the manifest -- it is backup metadata, not world data
                    if member == "manifest.json":
                        continue
                    zf.extract(member, str(self.root))
        except (zipfile.BadZipFile, OSError) as exc:
            raise RuntimeError(
                f"The restore failed while extracting the backup. "
                f"A pre-restore backup was saved at: "
                f"{pre_restore_meta['path']}\n"
                f"You can use that backup to recover. "
                f"Technical detail: {exc}"
            ) from exc

        return {
            "restored": True,
            "pre_restore_backup": pre_restore_meta["path"],
            "diff": diff,
        }

    def restore_entity(self, backup_path: str, entity_id: str) -> dict:
        """Restore a single entity from a backup.

        Automatically creates a pre-restore backup before making changes.

        Parameters
        ----------
        backup_path : str
            Absolute path to the backup ZIP file.
        entity_id : str
            The ID of the entity to restore.

        Returns
        -------
        dict
            ``{"restored": True, "entity_id": ..., "file_path": ...,
            "pre_restore_backup": ...}``.

        Raises
        ------
        FileNotFoundError
            If the backup or entity is not found.
        """
        self._validate_backup_file(backup_path)

        # Find the entity file inside the backup
        entity_member = None
        entity_data = None

        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                for member in zf.namelist():
                    if member == "manifest.json":
                        continue
                    # Check if this is a JSON entity file
                    if not member.endswith(".json"):
                        continue
                    try:
                        raw = zf.read(member)
                        data = json.loads(raw.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    # Match by entity ID
                    meta_id = data.get("_meta", {}).get("id", "")
                    top_id = data.get("id", "")
                    if meta_id == entity_id or top_id == entity_id:
                        entity_member = member
                        entity_data = data
                        break
        except zipfile.BadZipFile:
            raise ValueError(
                f"The backup file appears to be corrupted and could not be "
                f"read: {backup_path}"
            )

        if entity_member is None or entity_data is None:
            raise FileNotFoundError(
                f"Could not find entity '{entity_id}' in the backup. "
                f"The entity may not have existed when this backup was "
                f"created."
            )

        # Create safety backup
        pre_restore_meta = self.create_backup(label="pre_restore")

        # Write the entity file to its correct location
        target_path = self.root / entity_member
        os.makedirs(str(target_path.parent), exist_ok=True)
        with open(str(target_path), "w", encoding="utf-8") as fh:
            json.dump(entity_data, fh, indent=2, ensure_ascii=False)

        return {
            "restored": True,
            "entity_id": entity_id,
            "file_path": str(target_path),
            "pre_restore_backup": pre_restore_meta["path"],
        }

    # ------------------------------------------------------------------
    # 4. Diff and comparison
    # ------------------------------------------------------------------

    def compare_backup(self, backup_path: str) -> dict:
        """Compare a backup against the current state of ``user-world/``.

        Returns
        -------
        dict
            ``{"added": [...], "removed": [...], "modified": [...]}``
            where:
            - ``added`` = entities present now but absent in the backup
            - ``removed`` = entities in the backup but absent now
            - ``modified`` = entities present in both but with differences
              (each entry includes ``field_diffs``)

        Raises
        ------
        FileNotFoundError / ValueError
            If the backup is missing or invalid.
        """
        self._validate_backup_file(backup_path)

        # Load entity data from the backup
        backup_entities = self._load_entities_from_zip(backup_path)

        # Load current entity data from disk
        current_entities = self._load_current_entities()

        backup_ids = set(backup_entities.keys())
        current_ids = set(current_entities.keys())

        added: list[dict] = []
        removed: list[dict] = []
        modified: list[dict] = []

        # Entities added since the backup (present now, absent in backup)
        for eid in sorted(current_ids - backup_ids):
            data = current_entities[eid]
            added.append({
                "entity_id": eid,
                "name": data.get("name", eid),
                "entity_type": data.get("_meta", {}).get("entity_type", "unknown"),
            })

        # Entities removed since the backup (in backup, absent now)
        for eid in sorted(backup_ids - current_ids):
            data = backup_entities[eid]
            removed.append({
                "entity_id": eid,
                "name": data.get("name", eid),
                "entity_type": data.get("_meta", {}).get("entity_type", "unknown"),
            })

        # Entities in both -- check for modifications
        for eid in sorted(backup_ids & current_ids):
            field_diffs = self._compute_field_diffs(
                backup_entities[eid], current_entities[eid]
            )
            if field_diffs:
                modified.append({
                    "entity_id": eid,
                    "name": current_entities[eid].get("name", eid),
                    "entity_type": current_entities[eid].get("_meta", {}).get("entity_type", "unknown"),
                    "field_diffs": field_diffs,
                })

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
        }

    def get_entity_history(self, entity_id: str) -> list[dict]:
        """Search all backups for versions of a specific entity.

        Returns a timeline of changes sorted oldest to newest.

        Parameters
        ----------
        entity_id : str
            The entity ID to search for.

        Returns
        -------
        list[dict]
            Each entry contains: ``backup_path``, ``backup_timestamp``,
            ``backup_label``, ``entity_data``.  Sorted oldest-first.
        """
        history: list[dict] = []

        all_backups = self.list_backups()  # Newest first
        for backup_info in all_backups:
            bpath = backup_info["path"]
            try:
                entities = self._load_entities_from_zip(bpath)
            except (ValueError, OSError):
                continue

            if entity_id in entities:
                history.append({
                    "backup_path": bpath,
                    "backup_timestamp": backup_info.get("timestamp", ""),
                    "backup_label": backup_info.get("label", ""),
                    "entity_data": entities[entity_id],
                })

        # Reverse to oldest-first
        history.reverse()
        return history

    # ------------------------------------------------------------------
    # 5. Auto-backup triggers
    # ------------------------------------------------------------------

    @staticmethod
    def should_auto_backup(
        last_backup_time: datetime | None,
        entity_change_count: int,
    ) -> bool:
        """Determine whether an automatic backup should be created.

        The hooks system calls this method to decide when to trigger an
        auto-backup.  Returns ``True`` if:

        - More than 1 hour has elapsed since *last_backup_time*, **or**
        - *entity_change_count* exceeds 5 since the last backup, **or**
        - No backup has ever been created (*last_backup_time* is ``None``).

        Parameters
        ----------
        last_backup_time : datetime or None
            UTC datetime of the most recent backup, or ``None`` if no
            backup has been created yet.
        entity_change_count : int
            Number of entity create/update/delete operations since the
            last backup.

        Returns
        -------
        bool
        """
        if last_backup_time is None:
            return True

        if entity_change_count > 5:
            return True

        elapsed = _now_utc() - last_backup_time
        if elapsed.total_seconds() > 3600:  # 1 hour
            return True

        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_backup_file(self, backup_path: str) -> None:
        """Raise a friendly error if *backup_path* is not a valid backup."""
        if not os.path.isfile(backup_path):
            raise FileNotFoundError(
                f"The backup file was not found at: {backup_path}\n"
                f"It may have been moved or deleted."
            )
        if not zipfile.is_zipfile(backup_path):
            raise ValueError(
                f"The file at '{backup_path}' is not a valid ZIP archive. "
                f"It may be corrupted."
            )

    def _read_manifest(self, backup_path: str) -> dict | None:
        """Read the manifest.json from inside a backup ZIP.

        Returns ``None`` if the manifest is missing or unreadable.
        """
        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                if "manifest.json" in zf.namelist():
                    raw = zf.read("manifest.json")
                    return json.loads(raw.decode("utf-8"))
        except (zipfile.BadZipFile, json.JSONDecodeError, OSError):
            pass
        return None

    def _read_backup_metadata(self, backup_path: str) -> dict | None:
        """Build a metadata dict for a backup file by reading its manifest
        and filesystem attributes.

        Returns ``None`` if the file is not a valid backup.
        """
        if not zipfile.is_zipfile(backup_path):
            return None

        manifest = self._read_manifest(backup_path)

        filename = os.path.basename(backup_path)
        size_bytes = os.path.getsize(backup_path)

        # Parse timestamp and label from filename as fallback
        ts_from_name = ""
        label_from_name = ""
        base = filename.replace(".zip", "")
        # Expected pattern: backup_YYYYMMDD_HHMMSS or backup_YYYYMMDD_HHMMSS_label
        parts = base.split("_", 3)  # ["backup", "YYYYMMDD", "HHMMSS", ...]
        if len(parts) >= 3:
            try:
                dt = datetime.strptime(
                    f"{parts[1]}_{parts[2]}", "%Y%m%d_%H%M%S"
                ).replace(tzinfo=timezone.utc)
                ts_from_name = dt.isoformat()
            except ValueError:
                pass
            if len(parts) >= 4:
                label_from_name = parts[3]

        # Prefer manifest data when available
        entity_count = 0
        file_count = 0
        timestamp = ts_from_name
        label = label_from_name

        if manifest:
            entity_count = manifest.get("entity_count", 0)
            file_count = manifest.get("total_file_count", 0)
            timestamp = manifest.get("timestamp", ts_from_name)
            label = manifest.get("label", label_from_name)

        return {
            "path": str(Path(backup_path).resolve()),
            "filename": filename,
            "size_bytes": size_bytes,
            "timestamp": timestamp,
            "label": label,
            "entity_count": entity_count,
            "file_count": file_count,
        }

    def _load_entities_from_zip(self, backup_path: str) -> dict[str, dict]:
        """Load all entity JSON files from a backup ZIP.

        Returns a dict mapping entity_id -> entity_data.
        """
        entities: dict[str, dict] = {}

        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                for member in zf.namelist():
                    if member == "manifest.json":
                        continue
                    if not member.endswith(".json"):
                        continue
                    # Only load entities (files under user-world/entities/)
                    norm = member.replace("\\", "/")
                    if not norm.startswith("user-world/entities/"):
                        continue
                    try:
                        raw = zf.read(member)
                        data = json.loads(raw.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue

                    eid = data.get("_meta", {}).get("id", "") or data.get("id", "")
                    if eid:
                        entities[eid] = data
        except zipfile.BadZipFile:
            raise ValueError(
                f"The backup file appears to be corrupted and could not be "
                f"read: {backup_path}"
            )

        return entities

    def _load_current_entities(self) -> dict[str, dict]:
        """Load all entity JSON files from the current ``user-world/entities/``
        directory on disk.

        Returns a dict mapping entity_id -> entity_data.
        """
        entities: dict[str, dict] = {}
        entities_dir = self.user_world_dir / "entities"
        if not entities_dir.exists():
            return entities

        for dirpath_str, _dirnames, filenames in os.walk(str(entities_dir)):
            for fname in filenames:
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(dirpath_str, fname)
                data = _safe_read_json(fpath)
                if data is None:
                    continue
                eid = data.get("_meta", {}).get("id", "") or data.get("id", "")
                if eid:
                    entities[eid] = data

        return entities

    @staticmethod
    def _compute_field_diffs(old_data: dict, new_data: dict) -> list[dict]:
        """Compute field-level differences between two entity dicts.

        Ignores metadata fields (``_meta``, ``canon_claims``, fields
        starting with ``_``) to focus on user-visible content changes.

        Returns a list of diffs, each with ``field``, ``old_value``,
        ``new_value``.
        """
        skip_fields = {"_meta", "id", "canon_claims"}
        diffs: list[dict] = []

        all_keys = set(old_data.keys()) | set(new_data.keys())

        for key in sorted(all_keys):
            if key in skip_fields or key.startswith("_"):
                continue

            old_val = old_data.get(key)
            new_val = new_data.get(key)

            if old_val != new_val:
                diffs.append({
                    "field": key,
                    "old_value": old_val,
                    "new_value": new_val,
                })

        return diffs
