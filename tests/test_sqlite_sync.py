"""
Tests for engine/sqlite_sync.py -- SQLiteSyncEngine for FTS5 search.

Validates:
    - full_sync with sample entities
    - sync_entity (incremental)
    - search with FTS5
    - query_by_type, query_by_step, query_by_status
    - query_cross_references
    - query_claims
    - advanced_query blocks dangerous SQL
    - get_stats

Uses temp directories and in-memory strategies to avoid touching real data.
"""

import json
import os
import pytest

from engine.sqlite_sync import SQLiteSyncEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sample_entity(entity_id, name, entity_type, template_id, step=7, status="draft"):
    """Create a sample entity dict for testing."""
    return {
        "name": name,
        "id": entity_id,
        "_meta": {
            "id": entity_id,
            "template_id": template_id,
            "entity_type": entity_type,
            "status": status,
            "step_created": step,
            "file_path": f"user-world/entities/{entity_type}/{entity_id}.json",
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        },
        "domain_primary": "storms",
        "description": "A powerful deity of storms and lightning",
        "canon_claims": [
            {"claim": f"{name}'s primary domain is storms", "references": []},
            {"claim": f"{name} is a greater god", "references": []},
        ],
        "relationships": [
            {"target_id": "other-entity-0001", "relationship_type": "spouse"}
        ],
        "pantheon_id": "celestial-court",
    }


# ---------------------------------------------------------------------------
# Full Sync
# ---------------------------------------------------------------------------

class TestFullSync:
    """Tests for SQLiteSyncEngine.full_sync."""

    def test_full_sync_counts_entities(self, temp_world):
        """full_sync should return the number of entities synced."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            count = sync.full_sync()
            assert count >= 2  # god + settlement from temp_world
        finally:
            sync.close()

    def test_full_sync_populates_entities_table(self, temp_world):
        """After full_sync, the entities table should contain all entities."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            stats = sync.get_stats()
            assert stats["total_entities"] >= 2
        finally:
            sync.close()

    def test_full_sync_populates_claims(self, temp_world):
        """After full_sync, the canon_claims table should be populated."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            stats = sync.get_stats()
            assert stats["total_canon_claims"] >= 1
        finally:
            sync.close()


# ---------------------------------------------------------------------------
# Incremental Sync
# ---------------------------------------------------------------------------

class TestSyncEntity:
    """Tests for SQLiteSyncEngine.sync_entity."""

    def test_sync_new_entity(self, temp_world):
        """sync_entity should add a new entity to the database."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            entity = _make_sample_entity("new-god-1111", "Kael", "gods", "god-profile")
            sync.sync_entity("new-god-1111", entity)

            results = sync.query_by_type("gods")
            ids = [r["id"] for r in results]
            assert "new-god-1111" in ids
        finally:
            sync.close()

    def test_sync_updates_existing(self, temp_world):
        """sync_entity on an existing entity should update it."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()

            # Update the entity
            entity = _make_sample_entity(
                "thorin-stormkeeper-a1b2", "Thorin Updated", "gods", "god-profile"
            )
            sync.sync_entity("thorin-stormkeeper-a1b2", entity)

            results = sync.query_by_type("gods")
            names = [r["name"] for r in results]
            assert "Thorin Updated" in names
        finally:
            sync.close()

    def test_remove_entity(self, temp_world):
        """remove_entity should remove the entity from all tables."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            sync.remove_entity("thorin-stormkeeper-a1b2")

            results = sync.query_by_type("gods")
            ids = [r["id"] for r in results]
            assert "thorin-stormkeeper-a1b2" not in ids
        finally:
            sync.close()


# ---------------------------------------------------------------------------
# FTS5 Search
# ---------------------------------------------------------------------------

class TestSearch:
    """Tests for full-text search via FTS5."""

    def test_search_by_name(self, temp_world):
        """Searching by entity name should return matching results."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            results = sync.search("Thorin")
            assert len(results) >= 1
            assert any("Thorin" in r.get("name", "") for r in results)
        finally:
            sync.close()

    def test_search_empty_query(self, temp_world):
        """An empty search query should return no results."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            results = sync.search("")
            assert results == []
        finally:
            sync.close()

    def test_search_no_results(self, temp_world):
        """Searching for a nonexistent term should return empty list."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            results = sync.search("xyzzyplughfrobozz")
            assert results == []
        finally:
            sync.close()

    def test_search_by_description(self, temp_world):
        """Searching by content in the description field should work."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            entity = _make_sample_entity("searchable-0001", "Searchable God", "gods", "god-profile")
            entity["description"] = "A unique deity of crystalline formations"
            sync.sync_entity("searchable-0001", entity)

            results = sync.search("crystalline")
            assert len(results) >= 1
        finally:
            sync.close()


# ---------------------------------------------------------------------------
# Query Methods
# ---------------------------------------------------------------------------

class TestQueryMethods:
    """Tests for query_by_type, query_by_step, query_by_status."""

    def test_query_by_type(self, temp_world):
        """query_by_type should return entities of the specified type."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            gods = sync.query_by_type("gods")
            assert all(r["entity_type"] == "gods" for r in gods)

            settlements = sync.query_by_type("settlements")
            assert all(r["entity_type"] == "settlements" for r in settlements)
        finally:
            sync.close()

    def test_query_by_step(self, temp_world):
        """query_by_step should return entities created at the specified step."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            step7 = sync.query_by_step(7)
            assert all(r["step_created"] == 7 for r in step7)
            assert len(step7) >= 1
        finally:
            sync.close()

    def test_query_by_status(self, temp_world):
        """query_by_status should return entities with the given status."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            drafts = sync.query_by_status("draft")
            assert all(r["status"] == "draft" for r in drafts)
        finally:
            sync.close()


# ---------------------------------------------------------------------------
# Cross-References
# ---------------------------------------------------------------------------

class TestQueryCrossReferences:
    """Tests for query_cross_references."""

    def test_query_cross_references(self, temp_world):
        """query_cross_references should return outgoing and incoming refs."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            refs = sync.query_cross_references("thorin-stormkeeper-a1b2")
            assert "outgoing" in refs
            assert "incoming" in refs
            assert isinstance(refs["outgoing"], list)
            assert isinstance(refs["incoming"], list)
        finally:
            sync.close()


# ---------------------------------------------------------------------------
# Canon Claims
# ---------------------------------------------------------------------------

class TestQueryClaims:
    """Tests for query_claims."""

    def test_query_claims_by_entity(self, temp_world):
        """query_claims with entity_id should return only that entity's claims."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            claims = sync.query_claims(entity_id="thorin-stormkeeper-a1b2")
            assert all(c["entity_id"] == "thorin-stormkeeper-a1b2" for c in claims)
        finally:
            sync.close()

    def test_query_claims_by_keyword(self, temp_world):
        """query_claims with keyword should filter claims by text."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            claims = sync.query_claims(keyword="storms")
            assert all("storms" in c["claim"].lower() for c in claims)
        finally:
            sync.close()

    def test_query_claims_all(self, temp_world):
        """query_claims with no filters should return all claims."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            all_claims = sync.query_claims()
            assert len(all_claims) >= 1
        finally:
            sync.close()


# ---------------------------------------------------------------------------
# Advanced Query (Safety)
# ---------------------------------------------------------------------------

class TestAdvancedQuery:
    """Tests for advanced_query SQL safety."""

    def test_select_allowed(self, temp_world):
        """A simple SELECT query should succeed."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            results = sync.advanced_query("SELECT COUNT(*) AS cnt FROM entities")
            assert len(results) == 1
            assert results[0]["cnt"] >= 1
        finally:
            sync.close()

    def test_insert_blocked(self, temp_world):
        """An INSERT query should be blocked with ValueError."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            with pytest.raises(ValueError):
                sync.advanced_query("INSERT INTO entities (id) VALUES ('hack')")
        finally:
            sync.close()

    def test_delete_blocked(self, temp_world):
        """A DELETE query should be blocked with ValueError."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            with pytest.raises(ValueError):
                sync.advanced_query("DELETE FROM entities WHERE id='test'")
        finally:
            sync.close()

    def test_drop_blocked(self, temp_world):
        """A DROP query should be blocked with ValueError."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            with pytest.raises(ValueError):
                sync.advanced_query("DROP TABLE entities")
        finally:
            sync.close()

    def test_update_blocked(self, temp_world):
        """An UPDATE query should be blocked with ValueError."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            with pytest.raises(ValueError):
                sync.advanced_query("UPDATE entities SET name='hacked'")
        finally:
            sync.close()


# ---------------------------------------------------------------------------
# Get Stats
# ---------------------------------------------------------------------------

class TestGetStats:
    """Tests for get_stats."""

    def test_stats_structure(self, temp_world):
        """get_stats should return a dict with expected keys."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            stats = sync.get_stats()
            assert "total_entities" in stats
            assert "by_type" in stats
            assert "by_status" in stats
            assert "total_cross_references" in stats
            assert "total_canon_claims" in stats
        finally:
            sync.close()

    def test_stats_counts_match(self, temp_world):
        """Stats should be consistent (sum of by_type == total)."""
        sync = SQLiteSyncEngine(temp_world)
        try:
            sync.full_sync()
            stats = sync.get_stats()
            type_total = sum(stats["by_type"].values())
            assert type_total == stats["total_entities"]
        finally:
            sync.close()


# ---------------------------------------------------------------------------
# Context Manager
# ---------------------------------------------------------------------------

class TestContextManager:
    """Tests for context manager support."""

    def test_with_statement(self, temp_world):
        """SQLiteSyncEngine should work as a context manager."""
        with SQLiteSyncEngine(temp_world) as sync:
            sync.full_sync()
            stats = sync.get_stats()
            assert stats["total_entities"] >= 1
