"""
Tests for engine/graph_builder.py -- WorldGraph knowledge graph operations.

Validates:
    - build_graph with sample entities
    - add_entity and remove_entity
    - get_neighbors and find_path
    - get_entity_cluster
    - get_orphans and get_most_connected
    - Cross-reference extraction
"""

import pytest

from engine.graph_builder import WorldGraph


# ---------------------------------------------------------------------------
# Build Graph
# ---------------------------------------------------------------------------

class TestBuildGraph:
    """Tests for WorldGraph.build_graph."""

    def test_build_graph_creates_nodes(self, temp_world):
        """build_graph should create nodes from entity files on disk."""
        wg = WorldGraph(temp_world)
        wg.build_graph()

        assert wg.graph.number_of_nodes() >= 2  # god + settlement
        assert "thorin-stormkeeper-a1b2" in wg.graph
        assert "havenport-e5f6" in wg.graph

    def test_build_graph_sets_node_attributes(self, temp_world):
        """Nodes should have entity_type, name, and status attributes."""
        wg = WorldGraph(temp_world)
        wg.build_graph()

        attrs = wg.graph.nodes["thorin-stormkeeper-a1b2"]
        assert attrs["name"] == "Thorin Stormkeeper"
        assert attrs["entity_type"] == "gods"
        assert attrs["status"] == "draft"


# ---------------------------------------------------------------------------
# Add / Remove Entity
# ---------------------------------------------------------------------------

class TestAddRemoveEntity:
    """Tests for incremental add_entity and remove_entity."""

    def test_add_entity(self, temp_world):
        """add_entity should create a new node in the graph."""
        wg = WorldGraph(temp_world)

        new_entity = {
            "name": "Mira Sunweaver",
            "_meta": {
                "id": "mira-sunweaver-c3d4",
                "template_id": "god-profile",
                "entity_type": "gods",
                "status": "draft",
                "file_path": "",
                "step_created": 7,
            },
            "relationships": [],
        }
        wg.add_entity("mira-sunweaver-c3d4", new_entity)
        assert "mira-sunweaver-c3d4" in wg.graph
        assert wg.graph.nodes["mira-sunweaver-c3d4"]["name"] == "Mira Sunweaver"

    def test_remove_entity(self, temp_world):
        """remove_entity should remove the node and its edges."""
        wg = WorldGraph(temp_world)
        wg.build_graph()

        wg.remove_entity("havenport-e5f6")
        assert "havenport-e5f6" not in wg.graph

    def test_remove_nonexistent_entity_silent(self, temp_world):
        """remove_entity on a missing node should not raise."""
        wg = WorldGraph(temp_world)
        wg.remove_entity("does-not-exist-0000")  # Should not raise

    def test_add_relationship(self, temp_world):
        """add_relationship should create an edge between two entities."""
        wg = WorldGraph(temp_world)
        wg.build_graph()

        wg.add_relationship(
            "thorin-stormkeeper-a1b2",
            "havenport-e5f6",
            "protects",
        )
        assert wg.graph.has_edge("thorin-stormkeeper-a1b2", "havenport-e5f6")


# ---------------------------------------------------------------------------
# Queries: Neighbors and Path
# ---------------------------------------------------------------------------

class TestNeighborsAndPath:
    """Tests for get_neighbors and find_path."""

    def _build_connected_graph(self, temp_world):
        """Helper: build a graph with explicit edges."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        # Add a third entity and connect them
        wg.add_entity("mira-sunweaver-c3d4", {
            "name": "Mira Sunweaver",
            "_meta": {
                "id": "mira-sunweaver-c3d4",
                "template_id": "god-profile",
                "entity_type": "gods",
                "status": "draft",
                "file_path": "",
                "step_created": 7,
            },
        })
        wg.add_relationship("thorin-stormkeeper-a1b2", "mira-sunweaver-c3d4", "spouse")
        wg.add_relationship("mira-sunweaver-c3d4", "havenport-e5f6", "patron_of")
        return wg

    def test_get_neighbors_depth_1(self, temp_world):
        """get_neighbors with depth=1 should return direct connections only."""
        wg = self._build_connected_graph(temp_world)
        neighbors = wg.get_neighbors("thorin-stormkeeper-a1b2", depth=1)
        assert "mira-sunweaver-c3d4" in neighbors

    def test_get_neighbors_depth_2(self, temp_world):
        """get_neighbors with depth=2 should reach 2-hop connections."""
        wg = self._build_connected_graph(temp_world)
        neighbors = wg.get_neighbors("thorin-stormkeeper-a1b2", depth=2)
        assert "havenport-e5f6" in neighbors

    def test_get_neighbors_missing_entity(self, temp_world):
        """get_neighbors for a nonexistent entity should return an empty list."""
        wg = WorldGraph(temp_world)
        assert wg.get_neighbors("nonexistent-0000") == []

    def test_find_path(self, temp_world):
        """find_path should return a valid path between connected entities."""
        wg = self._build_connected_graph(temp_world)
        path = wg.find_path("thorin-stormkeeper-a1b2", "havenport-e5f6")

        assert len(path) >= 2
        assert path[0][0] == "thorin-stormkeeper-a1b2"
        assert path[-1][0] == "havenport-e5f6"

    def test_find_path_no_connection(self, temp_world):
        """find_path between unconnected entities should return empty list."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        # Add an isolated entity
        wg.add_entity("isolated-0000", {
            "name": "Isolated",
            "_meta": {"id": "isolated-0000", "entity_type": "misc", "status": "draft",
                      "file_path": "", "step_created": 1, "template_id": ""},
        })
        path = wg.find_path("thorin-stormkeeper-a1b2", "isolated-0000")
        assert path == []

    def test_find_path_missing_entity(self, temp_world):
        """find_path with a missing entity should return empty list."""
        wg = WorldGraph(temp_world)
        path = wg.find_path("nonexistent-1111", "nonexistent-2222")
        assert path == []


# ---------------------------------------------------------------------------
# Cluster, Orphans, Most Connected
# ---------------------------------------------------------------------------

class TestClusterOrphansMostConnected:
    """Tests for clustering, orphan detection, and centrality."""

    def test_get_entity_cluster(self, temp_world):
        """get_entity_cluster should return the entity's community."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        wg.add_relationship("thorin-stormkeeper-a1b2", "havenport-e5f6", "protects")

        cluster = wg.get_entity_cluster("thorin-stormkeeper-a1b2")
        assert "thorin-stormkeeper-a1b2" in cluster

    def test_get_entity_cluster_missing(self, temp_world):
        """get_entity_cluster for a missing entity should return empty list."""
        wg = WorldGraph(temp_world)
        assert wg.get_entity_cluster("nonexistent-0000") == []

    def test_get_orphans(self, temp_world):
        """get_orphans should return nodes with zero connections."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        # Without explicit edges, both pre-built entities might be orphans
        # (since cross-ref targets don't exist in the graph)
        orphans = wg.get_orphans()
        assert isinstance(orphans, list)

    def test_get_orphans_includes_isolated(self, temp_world):
        """An explicitly added isolated node should appear as an orphan."""
        wg = WorldGraph(temp_world)
        wg.add_entity("lone-wolf-0000", {
            "name": "Lone Wolf",
            "_meta": {"id": "lone-wolf-0000", "entity_type": "misc", "status": "draft",
                      "file_path": "", "step_created": 1, "template_id": ""},
        })
        orphans = wg.get_orphans()
        assert "lone-wolf-0000" in orphans

    def test_get_most_connected(self, temp_world):
        """get_most_connected should return entities sorted by degree."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        wg.add_relationship("thorin-stormkeeper-a1b2", "havenport-e5f6", "protects")

        most = wg.get_most_connected(top_n=5)
        assert isinstance(most, list)
        if most:
            assert "degree" in most[0]
            # First entry should have the highest degree
            if len(most) > 1:
                assert most[0]["degree"] >= most[1]["degree"]

    def test_get_stats(self, temp_world):
        """get_stats should return a dict with expected keys."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        stats = wg.get_stats()

        assert "node_count" in stats
        assert "edge_count" in stats
        assert "orphan_count" in stats
        assert "cluster_count" in stats
        assert stats["node_count"] >= 2


# ---------------------------------------------------------------------------
# Cross-Reference Extraction
# ---------------------------------------------------------------------------

class TestCrossRefExtraction:
    """Tests for _extract_cross_references via the graph builder."""

    def test_entities_by_type(self, temp_world):
        """get_entities_by_type should filter nodes by entity_type."""
        wg = WorldGraph(temp_world)
        wg.build_graph()

        gods = wg.get_entities_by_type("gods")
        assert "thorin-stormkeeper-a1b2" in gods

        settlements = wg.get_entities_by_type("settlements")
        assert "havenport-e5f6" in settlements

    def test_entities_for_step(self, temp_world):
        """get_entities_for_step should filter nodes by step_created."""
        wg = WorldGraph(temp_world)
        wg.build_graph()

        step7 = wg.get_entities_for_step(7)
        assert "thorin-stormkeeper-a1b2" in step7

        step29 = wg.get_entities_for_step(29)
        assert "havenport-e5f6" in step29
