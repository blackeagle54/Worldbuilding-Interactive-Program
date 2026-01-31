"""
Tests for engine/backup_manager.py

Covers:
    - Creating backups (normal, labeled, empty world)
    - Listing and sorting backups
    - Comparing backups to current state
    - Restoring full backups (safe extraction)
    - Restoring single entities
    - Cleanup of old backups
    - Error handling (bad paths, corrupt zips, unbound tmp_path)
"""

import json
import os
import shutil
import zipfile

import pytest

from engine.backup_manager import BackupManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def backup_mgr(temp_world):
    """Return a BackupManager instance with a populated temp world."""
    return BackupManager(temp_world)


@pytest.fixture
def empty_backup_mgr(tmp_path):
    """Return a BackupManager with an empty project (no entities)."""
    root = tmp_path / "empty-project"
    root.mkdir()
    (root / "user-world").mkdir(parents=True)
    state = {"current_step": 1, "entity_index": {}}
    with open(str(root / "user-world" / "state.json"), "w") as fh:
        json.dump(state, fh)
    (root / "backups").mkdir()
    return BackupManager(str(root))


# ---------------------------------------------------------------------------
# Create backup tests
# ---------------------------------------------------------------------------

class TestCreateBackup:
    def test_create_backup_returns_metadata(self, backup_mgr):
        meta = backup_mgr.create_backup()
        assert "path" in meta
        assert "timestamp" in meta
        assert os.path.exists(meta["path"])

    def test_backup_is_valid_zip(self, backup_mgr):
        meta = backup_mgr.create_backup()
        assert zipfile.is_zipfile(meta["path"])

    def test_backup_contains_manifest(self, backup_mgr):
        meta = backup_mgr.create_backup()
        with zipfile.ZipFile(meta["path"], "r") as zf:
            assert "manifest.json" in zf.namelist()

    def test_backup_contains_state_json(self, backup_mgr):
        meta = backup_mgr.create_backup()
        with zipfile.ZipFile(meta["path"], "r") as zf:
            names = zf.namelist()
            assert any("state.json" in n for n in names)

    def test_backup_contains_entity_files(self, backup_mgr):
        meta = backup_mgr.create_backup()
        with zipfile.ZipFile(meta["path"], "r") as zf:
            names = zf.namelist()
            entity_files = [n for n in names if "entities/" in n and n.endswith(".json")]
            assert len(entity_files) >= 2  # god + settlement

    def test_labeled_backup(self, backup_mgr):
        meta = backup_mgr.create_backup(label="my-test-label")
        assert "my-test-label" in meta["path"]

    def test_manifest_has_entity_count(self, backup_mgr):
        meta = backup_mgr.create_backup()
        with zipfile.ZipFile(meta["path"], "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["entity_count"] >= 2

    def test_empty_world_backup(self, empty_backup_mgr):
        meta = empty_backup_mgr.create_backup()
        assert os.path.exists(meta["path"])
        with zipfile.ZipFile(meta["path"], "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["entity_count"] == 0


# ---------------------------------------------------------------------------
# List backups tests
# ---------------------------------------------------------------------------

class TestListBackups:
    def test_list_empty(self, backup_mgr):
        backups = backup_mgr.list_backups()
        assert backups == []

    def test_list_after_create(self, backup_mgr):
        backup_mgr.create_backup()
        backups = backup_mgr.list_backups()
        assert len(backups) == 1

    def test_list_multiple_sorted_newest_first(self, backup_mgr):
        backup_mgr.create_backup(label="first")
        backup_mgr.create_backup(label="second")
        backups = backup_mgr.list_backups()
        assert len(backups) == 2
        # Newest first
        assert "second" in backups[0]["path"]
        assert "first" in backups[1]["path"]


# ---------------------------------------------------------------------------
# Compare backup tests
# ---------------------------------------------------------------------------

class TestCompareBackup:
    def test_compare_identical(self, backup_mgr):
        meta = backup_mgr.create_backup()
        diff = backup_mgr.compare_backup(meta["path"])
        # No changes since backup was just created
        assert diff.get("added", []) == []
        assert diff.get("removed", []) == []

    def test_compare_after_entity_added(self, backup_mgr, temp_world):
        meta = backup_mgr.create_backup()

        # Add a new entity
        new_entity_dir = os.path.join(temp_world, "user-world", "entities", "gods")
        new_entity = {
            "name": "New God",
            "_meta": {"id": "new-god-1234", "entity_type": "gods"},
        }
        with open(os.path.join(new_entity_dir, "new-god-1234.json"), "w") as fh:
            json.dump(new_entity, fh)

        diff = backup_mgr.compare_backup(meta["path"])
        added = diff.get("added", [])
        assert len(added) >= 1


# ---------------------------------------------------------------------------
# Restore backup tests
# ---------------------------------------------------------------------------

class TestRestoreBackup:
    def test_restore_without_confirm_returns_diff(self, backup_mgr):
        meta = backup_mgr.create_backup()
        result = backup_mgr.restore_backup(meta["path"], confirm=False)
        assert "restored" not in result or not result.get("restored")

    def test_restore_with_confirm(self, backup_mgr, temp_world):
        meta = backup_mgr.create_backup()

        # Modify an entity
        god_path = os.path.join(
            temp_world, "user-world", "entities", "gods",
            "thorin-stormkeeper-a1b2.json"
        )
        with open(god_path, "r") as fh:
            data = json.load(fh)
        data["name"] = "MODIFIED NAME"
        with open(god_path, "w") as fh:
            json.dump(data, fh)

        # Restore
        result = backup_mgr.restore_backup(meta["path"], confirm=True)
        assert result["restored"] is True
        assert "pre_restore_backup" in result

        # Verify original name is back
        with open(god_path, "r") as fh:
            restored_data = json.load(fh)
        assert restored_data["name"] == "Thorin Stormkeeper"

    def test_restore_creates_pre_restore_backup(self, backup_mgr):
        meta = backup_mgr.create_backup()
        result = backup_mgr.restore_backup(meta["path"], confirm=True)
        assert os.path.exists(result["pre_restore_backup"])


# ---------------------------------------------------------------------------
# Restore entity tests
# ---------------------------------------------------------------------------

class TestRestoreEntity:
    def test_restore_single_entity(self, backup_mgr, temp_world):
        meta = backup_mgr.create_backup()

        # Delete the god entity
        god_path = os.path.join(
            temp_world, "user-world", "entities", "gods",
            "thorin-stormkeeper-a1b2.json"
        )
        os.remove(god_path)
        assert not os.path.exists(god_path)

        # Restore just that entity
        result = backup_mgr.restore_entity(meta["path"], "thorin-stormkeeper-a1b2")
        assert result["restored"] is True
        assert os.path.exists(god_path)

    def test_restore_nonexistent_entity_raises(self, backup_mgr):
        meta = backup_mgr.create_backup()
        with pytest.raises(FileNotFoundError):
            backup_mgr.restore_entity(meta["path"], "nonexistent-entity-9999")


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_restore_bad_zip_raises(self, backup_mgr, tmp_path):
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_text("not a zip file")
        with pytest.raises((ValueError, RuntimeError)):
            backup_mgr.restore_backup(str(bad_zip), confirm=True)

    def test_restore_nonexistent_path_raises(self, backup_mgr):
        with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
            backup_mgr.restore_backup("/nonexistent/path.zip", confirm=True)

    def test_compare_nonexistent_raises(self, backup_mgr):
        with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
            backup_mgr.compare_backup("/nonexistent/path.zip")


# ---------------------------------------------------------------------------
# Cleanup tests
# ---------------------------------------------------------------------------

class TestCleanup:
    def test_cleanup_keeps_recent(self, backup_mgr):
        for i in range(5):
            backup_mgr.create_backup(label=f"test-{i}")

        backups_before = backup_mgr.list_backups()
        assert len(backups_before) == 5

        backup_mgr.cleanup_old_backups(keep_count=3)
        backups_after = backup_mgr.list_backups()
        assert len(backups_after) == 3

    def test_cleanup_noop_when_under_limit(self, backup_mgr):
        backup_mgr.create_backup()
        backup_mgr.cleanup_old_backups(keep_count=10)
        assert len(backup_mgr.list_backups()) == 1
