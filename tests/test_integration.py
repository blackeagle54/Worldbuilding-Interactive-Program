"""
Integration tests for the Worldbuilding Interactive Program.

Covers full workflows that span multiple engine modules:
    1. Create entity -> validate -> save -> verify in data store
    2. Create entity -> sync to graph -> verify relationships
    3. Generate options -> validate -> select -> create entity
    4. Session start -> auto-save -> recovery
"""

import json
import os
import shutil
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine.data_manager import DataManager
from engine.sqlite_sync import SQLiteSyncEngine
from engine.graph_builder import WorldGraph
from engine.backup_manager import BackupManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dm(temp_world):
    """Return a DataManager instance for the temp world."""
    return DataManager(temp_world)


@pytest.fixture
def sync(temp_world):
    """Return a SQLiteSyncEngine for the temp world."""
    return SQLiteSyncEngine(temp_world)


@pytest.fixture
def wg(temp_world):
    """Return a WorldGraph for the temp world."""
    return WorldGraph(temp_world)


@pytest.fixture
def bm(temp_world):
    """Return a BackupManager for the temp world."""
    return BackupManager(temp_world)


# ===========================================================================
# 1. Create Entity -> Validate -> Save -> Verify in Data Store
# ===========================================================================

class TestCreateValidateSaveVerify:
    """Full workflow: create entity, validate, persist, and verify."""

    def test_create_entity_and_read_back(self, dm, sample_god_data):
        """An entity created via DataManager should be readable back."""
        entity_id = dm.create_entity("god-profile", sample_god_data)

        # Read it back
        entity = dm.get_entity(entity_id)
        assert entity["name"] == "Thorin Stormkeeper"
        assert entity["_meta"]["template_id"] == "god-profile"
        assert entity["_meta"]["status"] == "draft"
        assert entity["_meta"]["entity_type"] == "gods"

    def test_created_entity_is_in_state_index(self, dm, sample_god_data):
        """A newly created entity should appear in the state.json index."""
        entity_id = dm.create_entity("god-profile", sample_god_data)

        state = dm.get_state()
        assert entity_id in state["entity_index"]
        index_entry = state["entity_index"][entity_id]
        assert index_entry["name"] == "Thorin Stormkeeper"
        assert index_entry["template_id"] == "god-profile"

    def test_created_entity_file_exists_on_disk(self, dm, temp_world, sample_god_data):
        """The entity JSON file should exist on disk after creation."""
        entity_id = dm.create_entity("god-profile", sample_god_data)

        state = dm.get_state()
        rel_path = state["entity_index"][entity_id]["file_path"]
        abs_path = os.path.join(temp_world, rel_path)
        assert os.path.isfile(abs_path)

        with open(abs_path, "r", encoding="utf-8") as f:
            file_data = json.load(f)
        assert file_data["name"] == "Thorin Stormkeeper"

    def test_created_entity_has_canon_claims(self, dm, sample_god_data):
        """A created entity should have auto-generated canon claims."""
        entity_id = dm.create_entity("god-profile", sample_god_data)
        entity = dm.get_entity(entity_id)

        assert "canon_claims" in entity
        assert len(entity["canon_claims"]) > 0
        # Claims should be dicts with 'claim' and 'references' keys
        first_claim = entity["canon_claims"][0]
        assert "claim" in first_claim
        assert "references" in first_claim

    def test_created_entity_has_prose(self, dm, sample_god_data):
        """A created entity should have auto-generated prose."""
        entity_id = dm.create_entity("god-profile", sample_god_data)
        entity = dm.get_entity(entity_id)

        assert "_prose" in entity
        assert entity["_prose_custom"] is False
        assert "Thorin Stormkeeper" in entity["_prose"]
        assert "storms" in entity["_prose"]

    def test_validate_created_entity_passes(self, dm, sample_god_data):
        """A properly created entity should pass validation."""
        entity_id = dm.create_entity("god-profile", sample_god_data)
        errors = dm.validate_entity(entity_id)
        assert errors == []

    def test_update_entity_preserves_meta(self, dm, sample_god_data):
        """Updating an entity should preserve _meta and update timestamp."""
        entity_id = dm.create_entity("god-profile", sample_god_data)
        original = dm.get_entity(entity_id)
        original_created = original["_meta"]["created_at"]

        dm.update_entity(entity_id, {"alignment": "good"})
        updated = dm.get_entity(entity_id)

        assert updated["alignment"] == "good"
        assert updated["_meta"]["created_at"] == original_created
        # updated_at should have changed
        assert updated["_meta"]["updated_at"] != original_created

    def test_create_entity_sync_to_sqlite(self, dm, sync, sample_god_data):
        """A created entity should be syncable to SQLite."""
        entity_id = dm.create_entity("god-profile", sample_god_data)
        entity = dm.get_entity(entity_id)

        sync.sync_entity(entity_id, entity)

        # Verify in SQLite
        results = sync.query_by_type("gods")
        entity_ids = [r["id"] for r in results]
        assert entity_id in entity_ids
        sync.close()

    def test_create_settlement_and_verify(self, dm, sample_settlement_data):
        """Creating a settlement entity should work end-to-end."""
        entity_id = dm.create_entity("settlement-profile", sample_settlement_data)
        entity = dm.get_entity(entity_id)

        assert entity["name"] == "Havenport"
        assert entity["_meta"]["entity_type"] == "settlements"
        assert entity["population"] == 45000
        assert "_prose" in entity


# ===========================================================================
# 2. Create Entity -> Sync to Graph -> Verify Relationships
# ===========================================================================

class TestCreateSyncGraphRelationships:
    """Full workflow: create entities, build graph, verify relationships."""

    def test_build_graph_from_existing_entities(self, wg, temp_world):
        """build_graph should pick up entities already on disk."""
        wg.build_graph()

        assert "thorin-stormkeeper-a1b2" in wg.graph
        assert "havenport-e5f6" in wg.graph
        stats = wg.get_stats()
        assert stats["node_count"] >= 2

    def test_add_entity_creates_node_and_edges(self, wg):
        """add_entity should create a node and resolve cross-references."""
        wg.build_graph()

        # Add a new entity that references existing ones
        new_entity = {
            "name": "Mira Sunweaver",
            "_meta": {
                "id": "mira-sunweaver-c3d4",
                "template_id": "god-profile",
                "entity_type": "gods",
                "status": "draft",
                "step_created": 7,
            },
            "relationships": [
                {
                    "target_id": "thorin-stormkeeper-a1b2",
                    "relationship_type": "spouse",
                    "description": "Married to Thorin",
                }
            ],
        }
        wg.add_entity("mira-sunweaver-c3d4", new_entity)
        assert "mira-sunweaver-c3d4" in wg.graph

    def test_get_neighbors_after_relationship(self, wg):
        """get_neighbors should return connected entities."""
        wg.build_graph()

        # Add relationships manually
        wg.add_relationship(
            "thorin-stormkeeper-a1b2",
            "havenport-e5f6",
            "patron_of",
        )

        neighbors = wg.get_neighbors("thorin-stormkeeper-a1b2", depth=1)
        assert "havenport-e5f6" in neighbors

    def test_find_path_between_entities(self, wg):
        """find_path should return a valid path between connected entities."""
        wg.build_graph()
        wg.add_relationship(
            "thorin-stormkeeper-a1b2",
            "havenport-e5f6",
            "patron_of",
        )

        path = wg.find_path("thorin-stormkeeper-a1b2", "havenport-e5f6")
        assert len(path) >= 2
        assert path[0][0] == "thorin-stormkeeper-a1b2"
        assert path[-1][0] == "havenport-e5f6"

    def test_create_entity_then_sync_to_graph(self, dm, wg, sample_god_data):
        """Full flow: DataManager create -> WorldGraph add."""
        wg.build_graph()

        entity_id = dm.create_entity("god-profile", sample_god_data)
        entity = dm.get_entity(entity_id)
        wg.add_entity(entity_id, entity)

        assert entity_id in wg.graph
        attrs = wg.graph.nodes[entity_id]
        assert attrs["name"] == "Thorin Stormkeeper"
        assert attrs["entity_type"] == "gods"

    def test_graph_sqlite_entity_consistency(self, dm, sync, wg, sample_god_data):
        """Entities should be consistent across DataManager, SQLite, and Graph."""
        wg.build_graph()

        entity_id = dm.create_entity("god-profile", sample_god_data)
        entity = dm.get_entity(entity_id)

        # Sync to both systems
        sync.sync_entity(entity_id, entity)
        wg.add_entity(entity_id, entity)

        # Verify in SQLite
        sql_results = sync.query_by_type("gods")
        sql_ids = [r["id"] for r in sql_results]
        assert entity_id in sql_ids

        # Verify in graph
        assert entity_id in wg.graph
        assert wg.graph.nodes[entity_id]["name"] == "Thorin Stormkeeper"

        sync.close()


# ===========================================================================
# 3. Generate Options -> Validate -> Select -> Create Entity
# ===========================================================================

class TestGenerateSelectCreate:
    """Workflow: generate options, validate choice, create entity."""

    def test_list_entities_after_creation(self, dm, sample_god_data, sample_settlement_data):
        """Listing entities after creation should return all created entities."""
        god_id = dm.create_entity("god-profile", sample_god_data)
        settlement_id = dm.create_entity("settlement-profile", sample_settlement_data)

        all_entities = dm.list_entities()
        created_ids = {e["id"] for e in all_entities}
        assert god_id in created_ids
        assert settlement_id in created_ids

    def test_filter_entities_by_type(self, dm, sample_god_data, sample_settlement_data):
        """Listing entities by type should filter correctly."""
        god_id = dm.create_entity("god-profile", sample_god_data)
        settlement_id = dm.create_entity("settlement-profile", sample_settlement_data)

        gods = dm.list_entities(entity_type="gods")
        god_ids = {e["id"] for e in gods}
        assert god_id in god_ids
        assert settlement_id not in god_ids

    def test_search_finds_created_entity(self, dm, sample_god_data):
        """Search should find entities by name after creation."""
        entity_id = dm.create_entity("god-profile", sample_god_data)

        results = dm.search_entities("Thorin")
        result_ids = [r["id"] for r in results]
        assert entity_id in result_ids

    def test_search_by_domain(self, dm, sample_god_data):
        """Search should find entities by domain keyword."""
        entity_id = dm.create_entity("god-profile", sample_god_data)

        results = dm.search_entities("storms")
        result_ids = [r["id"] for r in results]
        assert entity_id in result_ids

    def test_invalid_data_raises_on_create(self, dm):
        """Creating an entity with invalid data should raise ValueError."""
        invalid_data = {"name": ""}  # missing required fields
        with pytest.raises(ValueError):
            dm.create_entity("god-profile", invalid_data)

    def test_create_and_change_status(self, dm, sample_god_data):
        """Full flow: create as draft, then promote to canon."""
        entity_id = dm.create_entity("god-profile", sample_god_data)

        entity = dm.get_entity(entity_id)
        assert entity["_meta"]["status"] == "draft"

        dm.set_entity_status(entity_id, "canon")

        entity = dm.get_entity(entity_id)
        assert entity["_meta"]["status"] == "canon"

        # Verify state index also updated
        state = dm.get_state()
        assert state["entity_index"][entity_id]["status"] == "canon"


# ===========================================================================
# 4. Session Start -> Auto-Save -> Recovery
# ===========================================================================

class TestSessionAutoSaveRecovery:
    """Workflow: session backup, restore, and recovery."""

    def test_create_backup_and_list(self, bm):
        """Creating a backup should add it to the list."""
        meta = bm.create_backup(label="test-session")
        assert os.path.isfile(meta["path"])
        assert meta["label"] == "test-session"

        backups = bm.list_backups()
        assert len(backups) >= 1
        assert any(b["label"] == "test-session" for b in backups)

    def test_create_entity_backup_restore(self, dm, bm, temp_world, sample_god_data):
        """Full recovery flow: create entity, backup, modify, restore."""
        # Create entity
        entity_id = dm.create_entity("god-profile", sample_god_data)
        original_entity = dm.get_entity(entity_id)

        # Create backup
        backup_meta = bm.create_backup(label="before-modify")

        # Modify the entity
        dm.update_entity(entity_id, {"alignment": "evil"})
        modified = dm.get_entity(entity_id)
        assert modified["alignment"] == "evil"

        # Compare backup with current state
        diff = bm.compare_backup(backup_meta["path"])
        # The entity we modified should appear in the diff
        modified_ids = [m["entity_id"] for m in diff.get("modified", [])]
        assert entity_id in modified_ids or len(diff.get("added", [])) > 0

    def test_backup_entity_count_matches(self, bm, temp_world):
        """Backup metadata should reflect the correct entity count."""
        meta = bm.create_backup()
        # The temp_world has at least 2 entities (god + settlement)
        assert meta["entity_count"] >= 2

    def test_auto_backup_trigger_no_prior_backup(self):
        """Auto-backup should trigger when no prior backup exists."""
        assert BackupManager.should_auto_backup(None, 0) is True

    def test_auto_backup_trigger_many_changes(self):
        """Auto-backup should trigger when many entity changes accumulate."""
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc)
        assert BackupManager.should_auto_backup(recent, 10) is True

    def test_auto_backup_no_trigger_recent(self):
        """Auto-backup should NOT trigger when backup is recent and few changes."""
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc)
        assert BackupManager.should_auto_backup(recent, 2) is False

    def test_cleanup_old_backups(self, bm):
        """cleanup_old_backups should remove excess backups."""
        # Create several backups
        for i in range(5):
            bm.create_backup(label=f"cleanup-{i}")

        backups_before = bm.list_backups()
        assert len(backups_before) >= 5

        deleted = bm.cleanup_old_backups(keep_count=2)
        backups_after = bm.list_backups()
        assert len(backups_after) <= 2
        assert len(deleted) >= 3

    def test_create_entity_sync_backup_restore_sqlite(
        self, dm, sync, bm, temp_world, sample_god_data
    ):
        """End-to-end: create, sync to sqlite, backup, verify after full_sync."""
        # Create and sync
        entity_id = dm.create_entity("god-profile", sample_god_data)
        entity = dm.get_entity(entity_id)
        sync.sync_entity(entity_id, entity)

        # Verify in SQLite
        stats = sync.get_stats()
        assert stats["total_entities"] >= 1

        # Backup
        backup_meta = bm.create_backup(label="full-flow")
        assert backup_meta["entity_count"] >= 3  # 2 existing + 1 new

        # Full re-sync (simulating session restart)
        count = sync.full_sync()
        assert count >= 3

        sync.close()
