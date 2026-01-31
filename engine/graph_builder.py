"""
engine/graph_builder.py -- In-Memory Knowledge Graph (NetworkX)

Builds and maintains a directed graph of all worldbuilding entities and their
cross-references.  Each entity is a node; each cross-reference is a directed
edge.  Provides graph-query helpers used by the option generator, chunk
puller, consistency checker, and hook scripts.

Usage:
    from engine.graph_builder import WorldGraph

    wg = WorldGraph("C:/Worldbuilding-Interactive-Program")
    wg.build_graph()                        # full rebuild from entity files
    neighbors = wg.get_neighbors("thorin-stormkeeper-a1b2", depth=2)
    path = wg.find_path("thorin-stormkeeper-a1b2", "mira-sunweaver-c3d4")
    stats = wg.get_stats()
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import networkx as nx
except ImportError:
    raise ImportError(
        "The 'networkx' package is required but not installed. "
        "Install it with: pip install networkx"
    )

from engine.utils import safe_read_json as _safe_read_json


# ---------------------------------------------------------------------------
# WorldGraph
# ---------------------------------------------------------------------------

class WorldGraph:
    """In-memory directed graph of worldbuilding entities and relationships.

    Parameters
    ----------
    project_root : str
        Absolute path to the Worldbuilding Interactive Program root directory,
        e.g. ``"C:/Worldbuilding-Interactive-Program"``.
    """

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.entities_dir = self.root / "user-world" / "entities"
        self.templates_dir = self.root / "templates"
        self.state_path = self.root / "user-world" / "state.json"

        # The directed graph -- nodes are entity IDs, edges are relationships
        self.graph: nx.DiGraph = nx.DiGraph()

        # Cache of loaded template schemas keyed by template $id
        self._schema_cache: dict[str, dict] = {}

        # Reverse index: target_id -> [(source_id, field_name, rel_type), ...]
        # Tracks all cross-reference targets so that when a new entity is added,
        # we can instantly find which existing entities reference it without
        # re-reading all files from disk.
        self._pending_inbound: dict[str, list[tuple[str, str, str]]] = {}

        # Dirty tracking: set of entity IDs that have been modified since
        # the last full build.  When non-empty, rebuild_if_dirty() will
        # rebuild only those entities rather than re-reading everything.
        self._dirty_ids: set[str] = set()
        # Whether a full rebuild has ever been performed
        self._built: bool = False

    # ------------------------------------------------------------------
    # Full rebuild
    # ------------------------------------------------------------------

    def build_graph(self) -> None:
        """Rebuild the entire graph from entity files on disk.

        Reads every JSON file under ``user-world/entities/``, creates a node
        for each entity, then scans template schemas for ``x-cross-reference``
        annotations to create directed edges.

        This is called at session start.  During a session the graph is
        updated incrementally via :meth:`add_entity` and
        :meth:`add_relationship`.
        """
        self.graph.clear()
        self._pending_inbound.clear()
        self._dirty_ids.clear()
        self._built = True

        if not self.entities_dir.exists():
            return

        # Pass 1: load every entity file and create nodes
        entity_files: dict[str, dict] = {}  # entity_id -> entity_data
        for json_path in self.entities_dir.rglob("*.json"):
            data = _safe_read_json(str(json_path))
            if not data:
                continue

            meta = data.get("_meta", {})
            entity_id = meta.get("id") or data.get("id")
            if not entity_id:
                continue

            entity_files[entity_id] = data

            # Add the node with attributes
            self.graph.add_node(
                entity_id,
                entity_type=meta.get("entity_type", ""),
                name=data.get("name", entity_id),
                file_path=meta.get("file_path", str(json_path.relative_to(self.root))),
                step_created=meta.get("step_created"),
                status=meta.get("status", "draft"),
            )

        # Pass 2: extract cross-references and create edges.
        # References to entities not yet in the graph are stored in the
        # reverse index so they can be resolved instantly when the target
        # entity is later added via add_entity().
        for entity_id, data in entity_files.items():
            template_id = data.get("_meta", {}).get("template_id", "")
            if not template_id:
                continue
            schema = self._get_template_schema(template_id)
            if not schema:
                continue

            refs = self._extract_cross_references(data, schema)
            for target_id, field_name, rel_type in refs:
                if target_id in self.graph:
                    self.graph.add_edge(
                        entity_id,
                        target_id,
                        relationship_type=rel_type,
                        source_field=field_name,
                    )
                else:
                    # Target doesn't exist yet -- record for future resolution
                    self._pending_inbound.setdefault(target_id, []).append(
                        (entity_id, field_name, rel_type)
                    )

    # ------------------------------------------------------------------
    # Incremental updates
    # ------------------------------------------------------------------

    def add_entity(self, entity_id: str, entity_data: dict) -> None:
        """Add a single entity node to the graph.

        Also scans the entity's data for cross-references and creates edges
        for any targets that already exist in the graph.

        Parameters
        ----------
        entity_id : str
            The entity's unique identifier.
        entity_data : dict
            The full entity document (including ``_meta``).
        """
        meta = entity_data.get("_meta", {})
        self.graph.add_node(
            entity_id,
            entity_type=meta.get("entity_type", ""),
            name=entity_data.get("name", entity_id),
            file_path=meta.get("file_path", ""),
            step_created=meta.get("step_created"),
            status=meta.get("status", "draft"),
        )

        # Extract and add outbound edges
        template_id = meta.get("template_id", "")
        if template_id:
            schema = self._get_template_schema(template_id)
            if schema:
                refs = self._extract_cross_references(entity_data, schema)
                for target_id, field_name, rel_type in refs:
                    if target_id in self.graph:
                        self.graph.add_edge(
                            entity_id,
                            target_id,
                            relationship_type=rel_type,
                            source_field=field_name,
                        )
                    else:
                        # Target doesn't exist yet -- store in reverse index
                        self._pending_inbound.setdefault(target_id, []).append(
                            (entity_id, field_name, rel_type)
                        )

        # Resolve any pending inbound edges for this entity using the
        # reverse index (O(1) lookup instead of O(n) file scan).
        self._add_inbound_edges_for(entity_id)

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        source_field: str = "",
    ) -> None:
        """Add a single directed edge between two entities.

        Parameters
        ----------
        source_id : str
            The source entity ID.
        target_id : str
            The target entity ID.
        relationship_type : str
            A label for the relationship (e.g. ``"worships"``, ``"rules"``).
        source_field : str, optional
            The schema field that created this link.
        """
        # Ensure both nodes exist (add minimal stubs if not)
        if source_id not in self.graph:
            self.graph.add_node(source_id)
        if target_id not in self.graph:
            self.graph.add_node(target_id)

        self.graph.add_edge(
            source_id,
            target_id,
            relationship_type=relationship_type,
            source_field=source_field,
        )

    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity node and all of its edges from the graph.

        Parameters
        ----------
        entity_id : str
            The entity to remove.  Silently does nothing if the entity
            is not in the graph.
        """
        if entity_id in self.graph:
            self.graph.remove_node(entity_id)  # also removes all edges

    def mark_dirty(self, entity_id: str) -> None:
        """Mark an entity as needing a graph refresh.

        Call this after an entity is created, updated, or deleted
        externally.  Use :meth:`rebuild_if_dirty` to apply changes
        without a full rebuild.
        """
        self._dirty_ids.add(entity_id)

    def rebuild_if_dirty(self) -> bool:
        """Incrementally refresh only dirty entities.

        If no full build has been performed yet, falls back to a full
        :meth:`build_graph`.  Returns ``True`` if any work was done.
        """
        if not self._built:
            self.build_graph()
            return True

        if not self._dirty_ids:
            return False

        dirty = set(self._dirty_ids)
        self._dirty_ids.clear()

        for eid in dirty:
            # Remove old node (and edges) if present
            if eid in self.graph:
                self.graph.remove_node(eid)

            # Re-read entity from disk and re-add
            entity_file = None
            if self.entities_dir.exists():
                for json_path in self.entities_dir.rglob("*.json"):
                    data = _safe_read_json(str(json_path))
                    if not data:
                        continue
                    meta = data.get("_meta", {})
                    if (meta.get("id") or data.get("id")) == eid:
                        entity_file = data
                        break

            if entity_file is not None:
                self.add_entity(eid, entity_file)

        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_neighbors(self, entity_id: str, depth: int = 1) -> list[str]:
        """Return all entity IDs reachable within *depth* relationship hops.

        Parameters
        ----------
        entity_id : str
            The starting entity.
        depth : int
            How many hops to traverse.  ``depth=1`` returns direct
            connections; ``depth=2`` includes connections-of-connections.

        Returns
        -------
        list[str]
            Entity IDs within the requested depth (excluding the starting
            entity itself).  Returns an empty list if the entity is not in
            the graph.
        """
        if entity_id not in self.graph:
            return []

        # Use BFS on the undirected view so we traverse both inbound and
        # outbound edges.
        undirected = self.graph.to_undirected()
        visited: set[str] = set()
        frontier: set[str] = {entity_id}

        for _ in range(depth):
            next_frontier: set[str] = set()
            for node in frontier:
                for neighbor in undirected.neighbors(node):
                    if neighbor not in visited and neighbor != entity_id:
                        next_frontier.add(neighbor)
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break

        return list(visited)

    def get_related_entities(self, entity_id: str) -> dict:
        """Return all directly connected entities grouped by direction.

        Parameters
        ----------
        entity_id : str
            The entity to inspect.

        Returns
        -------
        dict
            ``{"outgoing": [...], "incoming": [...]}``.
            Each item is a dict with ``id``, ``relationship``, and ``name``.
            Returns empty lists if the entity is not in the graph.
        """
        result: dict[str, list[dict]] = {"outgoing": [], "incoming": []}

        if entity_id not in self.graph:
            return result

        # Outgoing edges (this entity -> others)
        for _, target, edge_data in self.graph.out_edges(entity_id, data=True):
            target_attrs = self.graph.nodes.get(target, {})
            result["outgoing"].append({
                "id": target,
                "relationship": edge_data.get("relationship_type", ""),
                "name": target_attrs.get("name", target),
            })

        # Incoming edges (others -> this entity)
        for source, _, edge_data in self.graph.in_edges(entity_id, data=True):
            source_attrs = self.graph.nodes.get(source, {})
            result["incoming"].append({
                "id": source,
                "relationship": edge_data.get("relationship_type", ""),
                "name": source_attrs.get("name", source),
            })

        return result

    def find_path(self, entity_a: str, entity_b: str) -> list[tuple[str, str]]:
        """Find the shortest relationship path between two entities.

        Traverses the graph as undirected so that both inbound and outbound
        edges are followed.

        Parameters
        ----------
        entity_a : str
            Starting entity ID.
        entity_b : str
            Ending entity ID.

        Returns
        -------
        list[tuple[str, str]]
            A list of ``(entity_id, relationship_type)`` tuples representing
            the path.  The first tuple has ``relationship_type=""`` (the
            starting node).  Returns an empty list if no path exists or
            either entity is missing.
        """
        if entity_a not in self.graph or entity_b not in self.graph:
            return []

        undirected = self.graph.to_undirected()

        try:
            path_nodes = nx.shortest_path(undirected, entity_a, entity_b)
        except nx.NetworkXNoPath:
            return []
        except nx.NodeNotFound:
            return []

        # Build the result with relationship labels between consecutive nodes
        result: list[tuple[str, str]] = [(path_nodes[0], "")]
        for i in range(len(path_nodes) - 1):
            src, tgt = path_nodes[i], path_nodes[i + 1]
            # Check for a directed edge in either direction
            if self.graph.has_edge(src, tgt):
                rel = self.graph.edges[src, tgt].get("relationship_type", "")
            elif self.graph.has_edge(tgt, src):
                rel = self.graph.edges[tgt, src].get("relationship_type", "")
            else:
                rel = ""
            result.append((tgt, rel))

        return result

    def get_entity_cluster(self, entity_id: str) -> list[str]:
        """Return the community/cluster that *entity_id* belongs to.

        Uses NetworkX's ``greedy_modularity_communities`` on the undirected
        view of the graph.  Falls back gracefully if the graph is too small
        or the entity is isolated.

        Parameters
        ----------
        entity_id : str
            The entity whose cluster to find.

        Returns
        -------
        list[str]
            Entity IDs in the same community (including *entity_id* itself).
            Returns ``[entity_id]`` if the entity is isolated or not in the
            graph.
        """
        if entity_id not in self.graph:
            return []

        undirected = self.graph.to_undirected()

        # If the graph has fewer than 2 nodes, no community detection needed
        if undirected.number_of_nodes() < 2:
            return [entity_id]

        try:
            communities = nx.community.greedy_modularity_communities(undirected)
            for community in communities:
                if entity_id in community:
                    return sorted(community)
        except Exception:
            # Fallback: return the connected component containing entity_id
            logger.debug("Community detection unavailable, falling back to connected component", exc_info=True)

        # Fallback: return the connected component
        try:
            component = nx.node_connected_component(undirected, entity_id)
            return sorted(component)
        except Exception:
            logger.debug("Connected component lookup failed for %s", entity_id, exc_info=True)
            return [entity_id]

    def get_orphans(self) -> list[str]:
        """Return entity IDs that have zero connections (in + out degree = 0).

        These represent potential gaps in the worldbuilding -- entities that
        are not linked to anything else.

        Returns
        -------
        list[str]
            Sorted list of orphaned entity IDs.
        """
        orphans = [
            node for node in self.graph.nodes()
            if self.graph.degree(node) == 0
        ]
        return sorted(orphans)

    def get_most_connected(self, top_n: int = 10) -> list[dict]:
        """Return entities ranked by total connections (in + out degree).

        These are the most important / central entities in the world.

        Parameters
        ----------
        top_n : int
            How many to return.

        Returns
        -------
        list[dict]
            Each dict has ``id``, ``name``, ``entity_type``, ``degree``.
            Sorted by degree descending.
        """
        degree_list = []
        for node, degree in self.graph.degree():
            attrs = self.graph.nodes[node]
            degree_list.append({
                "id": node,
                "name": attrs.get("name", node),
                "entity_type": attrs.get("entity_type", ""),
                "degree": degree,
            })

        degree_list.sort(key=lambda x: x["degree"], reverse=True)
        return degree_list[:top_n]

    def get_stats(self) -> dict:
        """Return summary statistics about the graph.

        Returns
        -------
        dict
            Keys: ``node_count``, ``edge_count``, ``most_connected`` (top 5),
            ``orphan_count``, ``cluster_count``.
        """
        undirected = self.graph.to_undirected()

        # Cluster count: number of connected components
        cluster_count = nx.number_connected_components(undirected) if undirected.number_of_nodes() > 0 else 0

        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "most_connected": self.get_most_connected(top_n=5),
            "orphan_count": len(self.get_orphans()),
            "cluster_count": cluster_count,
        }

    def get_entities_by_type(self, entity_type: str) -> list[str]:
        """Return all entity IDs of a given type from the graph.

        Parameters
        ----------
        entity_type : str
            The type to filter by (e.g. ``"gods"``, ``"settlements"``).

        Returns
        -------
        list[str]
            Sorted list of matching entity IDs.
        """
        return sorted(
            node for node, attrs in self.graph.nodes(data=True)
            if attrs.get("entity_type") == entity_type
        )

    def get_entities_for_step(self, step_number: int) -> list[str]:
        """Return all entity IDs created at a specific progression step.

        Parameters
        ----------
        step_number : int
            The step number to filter by.

        Returns
        -------
        list[str]
            Sorted list of matching entity IDs.
        """
        return sorted(
            node for node, attrs in self.graph.nodes(data=True)
            if attrs.get("step_created") == step_number
        )

    # ------------------------------------------------------------------
    # Template schema loading
    # ------------------------------------------------------------------

    def _get_template_schema(self, template_id: str) -> dict | None:
        """Load a template JSON schema by its ``$id``.

        Returns ``None`` if the template cannot be found (rather than
        raising, since build_graph should not crash on a missing template).
        """
        if template_id in self._schema_cache:
            return self._schema_cache[template_id]

        # Scan all template files for matching $id
        if self.templates_dir.exists():
            for json_path in sorted(self.templates_dir.rglob("*.json")):
                schema = _safe_read_json(str(json_path))
                if schema and schema.get("$id") == template_id:
                    self._schema_cache[template_id] = schema
                    return schema

        return None

    # ------------------------------------------------------------------
    # Cross-reference extraction
    # ------------------------------------------------------------------

    def _extract_cross_references(
        self, entity: dict, schema: dict
    ) -> list[tuple[str, str, str]]:
        """Walk an entity's data and its template schema to find all
        cross-referenced entity IDs.

        Returns a list of ``(target_entity_id, field_name, relationship_type)``
        tuples.  ``relationship_type`` is derived from the field name or, for
        structured relationship arrays, from the ``relationship_type`` sub-field.
        """
        refs: list[tuple[str, str, str]] = []
        props = schema.get("properties", {})

        for field_key, field_schema in props.items():
            value = entity.get(field_key)
            if value is None:
                continue

            # --- Direct cross-reference field (string) ---
            if "x-cross-reference" in field_schema and isinstance(value, str) and value:
                rel_type = self._derive_relationship_type(field_key, field_schema)
                refs.append((value, field_key, rel_type))

            # --- Array fields ---
            elif isinstance(value, list):
                item_schema = field_schema.get("items", {})

                # Array of cross-reference strings
                if "x-cross-reference" in item_schema:
                    rel_type = self._derive_relationship_type(field_key, field_schema)
                    for v in value:
                        if isinstance(v, str) and v:
                            refs.append((v, field_key, rel_type))

                # Array of objects with nested cross-reference sub-fields
                # (e.g. relationships[].target_id, species_breakdown[].species_id)
                elif isinstance(item_schema, dict) and "properties" in item_schema:
                    for item in value:
                        if not isinstance(item, dict):
                            continue
                        # Look for the explicit relationship_type sub-field
                        # (common in god relationships, etc.)
                        explicit_rel = item.get("relationship_type", "")
                        for sub_key, sub_schema in item_schema["properties"].items():
                            if "x-cross-reference" in sub_schema:
                                sub_val = item.get(sub_key)
                                if isinstance(sub_val, str) and sub_val:
                                    rel = explicit_rel or self._derive_relationship_type(
                                        f"{field_key}.{sub_key}", field_schema
                                    )
                                    refs.append((
                                        sub_val,
                                        f"{field_key}.{sub_key}",
                                        rel,
                                    ))

        return refs

    @staticmethod
    def _derive_relationship_type(field_key: str, field_schema: dict) -> str:
        """Derive a human-readable relationship label from the field name
        and schema metadata.

        Examples:
            ``"pantheon_id"``                -> ``"pantheon"``
            ``"gods_worshiped"``             -> ``"gods_worshiped"``
            ``"sovereign_power_id"``         -> ``"sovereign_power"``
            ``"species_breakdown.species_id"`` -> ``"species"``
        """
        # Use the x-cross-reference value as a hint if present
        xref = field_schema.get("x-cross-reference", "")
        if not xref:
            # Check items-level schema
            xref = field_schema.get("items", {}).get("x-cross-reference", "")

        # Clean up the field key: strip trailing _id, collapse dotted paths
        base = field_key
        if "." in base:
            # Take the parent part (e.g. "species_breakdown.species_id" -> "species_breakdown")
            base = base.split(".")[0]
        base = base.removesuffix("_id")

        # If we have an xref hint, prefer it (e.g. "god-profile" -> "god_profile")
        if xref:
            return xref.replace("-", "_")

        return base

    # ------------------------------------------------------------------
    # Inbound edge discovery
    # ------------------------------------------------------------------

    def _add_inbound_edges_for(self, entity_id: str) -> None:
        """Resolve pending inbound edges for *entity_id* using the reverse index.

        When entities are added, any outbound references to not-yet-existing
        targets are stored in ``_pending_inbound``.  When the target is later
        added, this method creates the edges in O(k) where k is the number of
        pending references (instead of the previous O(n) full-scan approach).
        """
        pending = self._pending_inbound.pop(entity_id, [])
        for source_id, field_name, rel_type in pending:
            if source_id in self.graph and not self.graph.has_edge(source_id, entity_id):
                self.graph.add_edge(
                    source_id,
                    entity_id,
                    relationship_type=rel_type,
                    source_field=field_name,
                )
