"""
engine/sqlite_sync.py -- SQLite Sync Engine for the Worldbuilding Interactive Program

Maintains a SQLite runtime database (runtime/worldbuilding.db) that mirrors
all JSON entity files stored in user-world/entities/.  The JSON files remain
the authoritative source of truth; SQLite provides fast indexed queries and
FTS5 full-text search.

The database is always rebuildable from the JSON files via ``full_sync()``.

Usage:
    from engine.sqlite_sync import SQLiteSyncEngine

    sync = SQLiteSyncEngine("C:/Worldbuilding-Interactive-Program")
    sync.full_sync()

    results = sync.search("storm god")
    gods = sync.query_by_type("gods")
    step7 = sync.query_by_step(7)
    stats = sync.get_stats()
    sync.close()
"""

import json
import os
import sqlite3
from pathlib import Path


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- Main entity table
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    template_id TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    step_created INTEGER,
    file_path TEXT NOT NULL,
    data JSON NOT NULL,
    created_at TEXT,
    updated_at TEXT
);

-- Cross-reference table
-- Note: no FOREIGN KEY constraints on target_id because referenced
-- entities may not yet exist in the database (they may be synced later
-- or may live outside the entities directory).
CREATE TABLE IF NOT EXISTS cross_references (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    source_field TEXT
);

-- Canon claims table (for contradiction checking)
CREATE TABLE IF NOT EXISTS canon_claims (
    entity_id TEXT NOT NULL,
    claim TEXT NOT NULL,
    refs TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entity_status ON entities(status);
CREATE INDEX IF NOT EXISTS idx_entity_step ON entities(step_created);
CREATE INDEX IF NOT EXISTS idx_xref_source ON cross_references(source_id);
CREATE INDEX IF NOT EXISTS idx_xref_target ON cross_references(target_id);
CREATE INDEX IF NOT EXISTS idx_claims_entity ON canon_claims(entity_id);
"""

# FTS5 virtual table -- created separately because DROP/CREATE is used
# during full rebuilds.
_FTS_CREATE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS entity_search USING fts5(
    name,
    entity_type,
    tags,
    description,
    canon_claims_text,
    content='entities',
    content_rowid='rowid',
    tokenize='porter unicode61'
);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from engine.utils import safe_read_json as _safe_read_json


def _extract_text_field(entity: dict, field: str) -> str:
    """Extract a text value from an entity, handling strings and lists."""
    val = entity.get(field)
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return ", ".join(str(v) for v in val if v)
    return str(val)


def _extract_canon_claims_text(entity: dict) -> str:
    """Concatenate all canon claim strings into a single searchable blob."""
    claims = entity.get("canon_claims", [])
    parts = []
    for claim in claims:
        if isinstance(claim, dict):
            parts.append(claim.get("claim", ""))
        elif isinstance(claim, str):
            parts.append(claim)
    return "; ".join(parts)


def _extract_cross_references(entity: dict) -> list[tuple[str, str, str]]:
    """Extract cross-reference triples from an entity's canon_claims.

    Returns a list of (target_id, relationship_type, source_field) tuples.
    """
    refs: list[tuple[str, str, str]] = []

    # Primary strategy: scan canon_claims for entries with references
    claims = entity.get("canon_claims", [])
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        for ref_id in claim.get("references", []):
            if isinstance(ref_id, str) and ref_id.strip():
                refs.append((ref_id, "canon_claim", "canon_claims"))

    # Secondary strategy: look for common cross-reference field patterns
    # These are fields that typically contain entity IDs
    xref_fields = [
        "pantheon_id", "ruler_id", "creator_god", "parent_species",
        "religion_id", "settlement_id", "sovereign_power_id",
        "allied_with", "rival_of", "spouse", "parent", "children",
        "member_of", "located_in", "created_by", "worships",
    ]
    for field in xref_fields:
        val = entity.get(field)
        if val is None:
            continue
        if isinstance(val, str) and val.strip():
            refs.append((val, field, field))
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.strip():
                    refs.append((item, field, field))

    # Tertiary: scan relationship-style arrays of objects
    for field in ("relationships", "divine_relationships", "alliances",
                  "conflicts", "trade_partners"):
        items = entity.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            # Look for common id-like keys within relationship objects
            for key in ("entity_id", "target_id", "god_id", "partner_id",
                        "ally_id", "enemy_id", "id", "with"):
                target = item.get(key)
                if isinstance(target, str) and target.strip():
                    rel_type = item.get("type", item.get("relationship_type",
                                item.get("relationship", field)))
                    refs.append((target, str(rel_type), field))

    # De-duplicate
    seen = set()
    unique: list[tuple[str, str, str]] = []
    for triple in refs:
        key = (triple[0], triple[2])
        if key not in seen:
            seen.add(key)
            unique.append(triple)
    return unique


# ---------------------------------------------------------------------------
# SQLiteSyncEngine
# ---------------------------------------------------------------------------

class SQLiteSyncEngine:
    """Sync layer that mirrors JSON entity files into a SQLite database.

    Parameters
    ----------
    project_root : str
        Absolute path to the Worldbuilding Interactive Program root,
        e.g. ``"C:/Worldbuilding-Interactive-Program"``.
    """

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.entities_dir = self.root / "user-world" / "entities"
        self.runtime_dir = self.root / "runtime"
        self.db_path = self.runtime_dir / "worldbuilding.db"

        # Ensure runtime/ exists
        os.makedirs(str(self.runtime_dir), exist_ok=True)

        # Open (or create) the database
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent read performance
        self._conn.execute("PRAGMA journal_mode=WAL")
        # Foreign keys are intentionally NOT enforced because
        # cross-references may point to entities not yet synced
        self._conn.execute("PRAGMA foreign_keys=OFF")

        # Create tables if they do not exist
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create all tables, indexes, and the FTS5 virtual table."""
        self._conn.executescript(_SCHEMA_SQL)
        # FTS5 must be created in its own statement (not inside executescript
        # for some SQLite builds, but generally fine).
        try:
            self._conn.executescript(_FTS_CREATE_SQL)
        except sqlite3.OperationalError:
            # FTS5 may already exist; that is fine.
            pass
        self._conn.commit()

    # ------------------------------------------------------------------
    # Full sync (session start)
    # ------------------------------------------------------------------

    def full_sync(self) -> int:
        """Rebuild the entire database from JSON entity files.

        Reads every ``*.json`` file under ``user-world/entities/``,
        clears all existing data, and repopulates all tables including
        the FTS5 search index.

        Returns
        -------
        int
            The number of entities synced.
        """
        # Collect all entity files
        entity_files = list(self.entities_dir.rglob("*.json"))

        # Clear existing data
        self._conn.execute("DELETE FROM cross_references")
        self._conn.execute("DELETE FROM canon_claims")
        self._conn.execute("DELETE FROM entities")
        # Rebuild FTS: drop and recreate
        try:
            self._conn.execute("DROP TABLE IF EXISTS entity_search")
        except sqlite3.OperationalError:
            pass
        try:
            self._conn.executescript(_FTS_CREATE_SQL)
        except sqlite3.OperationalError:
            pass

        count = 0
        for file_path in entity_files:
            entity = _safe_read_json(str(file_path))
            if entity is None:
                continue
            meta = entity.get("_meta", {})
            entity_id = meta.get("id", entity.get("id"))
            if not entity_id:
                continue

            rel_path = str(file_path.relative_to(self.root)).replace("\\", "/")
            self._upsert_entity_row(entity_id, entity, meta, rel_path)
            self._upsert_cross_references(entity_id, entity)
            self._upsert_canon_claims(entity_id, entity)
            self._upsert_fts(entity_id, entity)
            count += 1

        self._conn.commit()
        return count

    # ------------------------------------------------------------------
    # Incremental sync (single entity)
    # ------------------------------------------------------------------

    def sync_entity(self, entity_id: str, entity_data: dict) -> None:
        """Create or update a single entity in the database.

        Call this when the DataManager creates or updates an entity so
        that the SQLite mirror stays current without a full rebuild.

        Parameters
        ----------
        entity_id : str
            The entity's unique identifier.
        entity_data : dict
            The full entity document (including ``_meta`` and ``canon_claims``).
        """
        meta = entity_data.get("_meta", {})
        file_path = meta.get("file_path", "")

        # Remove old data for this entity
        self._remove_entity_data(entity_id)

        # Insert fresh data
        self._upsert_entity_row(entity_id, entity_data, meta, file_path)
        self._upsert_cross_references(entity_id, entity_data)
        self._upsert_canon_claims(entity_id, entity_data)
        self._upsert_fts(entity_id, entity_data)
        self._conn.commit()

    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity from all database tables.

        Parameters
        ----------
        entity_id : str
            The entity to remove.
        """
        self._remove_entity_data(entity_id)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[dict]:
        """Full-text search via FTS5.

        Parameters
        ----------
        query : str
            The search query.  Supports FTS5 query syntax (implicit OR,
            quoted phrases, column filters).

        Returns
        -------
        list[dict]
            Matching entities with a ``rank`` score (lower is more relevant).
        """
        if not query or not query.strip():
            return []

        # Sanitise the query: escape special FTS5 characters for safety,
        # but allow simple multi-word queries to work as implicit AND.
        safe_query = self._sanitise_fts_query(query.strip())

        try:
            rows = self._conn.execute(
                """
                SELECT e.*, s.rank
                FROM entity_search s
                JOIN entities e ON e.rowid = s.rowid
                WHERE entity_search MATCH ?
                ORDER BY s.rank
                """,
                (safe_query,),
            ).fetchall()
        except sqlite3.OperationalError:
            # If the FTS query syntax is invalid, fall back to LIKE search
            return self._fallback_search(query.strip())

        return [self._row_to_dict(r) for r in rows]

    def query_by_type(self, entity_type: str) -> list[dict]:
        """Return all entities of a given type.

        Parameters
        ----------
        entity_type : str
            The entity type (e.g. ``"gods"``, ``"settlements"``).

        Returns
        -------
        list[dict]
            Matching entity rows.
        """
        rows = self._conn.execute(
            "SELECT * FROM entities WHERE entity_type = ? ORDER BY name",
            (entity_type,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def query_by_step(self, step_number: int) -> list[dict]:
        """Return all entities created at a specific step.

        Parameters
        ----------
        step_number : int
            The progression step number.

        Returns
        -------
        list[dict]
            Matching entity rows.
        """
        rows = self._conn.execute(
            "SELECT * FROM entities WHERE step_created = ? ORDER BY name",
            (step_number,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def query_by_status(self, status: str) -> list[dict]:
        """Return all entities with the given status.

        Parameters
        ----------
        status : str
            Typically ``"draft"`` or ``"canon"``.

        Returns
        -------
        list[dict]
            Matching entity rows.
        """
        rows = self._conn.execute(
            "SELECT * FROM entities WHERE status = ? ORDER BY name",
            (status,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def query_cross_references(self, entity_id: str) -> dict:
        """Return all cross-references for an entity.

        Parameters
        ----------
        entity_id : str
            The entity to look up.

        Returns
        -------
        dict
            ``{"outgoing": [...], "incoming": [...]}``.
            Each item is a dict with ``source_id`` or ``target_id``,
            ``relationship_type``, and ``source_field``.
        """
        outgoing = self._conn.execute(
            """
            SELECT cr.target_id, cr.relationship_type, cr.source_field,
                   e.name AS target_name, e.entity_type AS target_type
            FROM cross_references cr
            LEFT JOIN entities e ON e.id = cr.target_id
            WHERE cr.source_id = ?
            """,
            (entity_id,),
        ).fetchall()

        incoming = self._conn.execute(
            """
            SELECT cr.source_id, cr.relationship_type, cr.source_field,
                   e.name AS source_name, e.entity_type AS source_type
            FROM cross_references cr
            LEFT JOIN entities e ON e.id = cr.source_id
            WHERE cr.target_id = ?
            """,
            (entity_id,),
        ).fetchall()

        return {
            "outgoing": [dict(r) for r in outgoing],
            "incoming": [dict(r) for r in incoming],
        }

    def query_claims(self, entity_id: str | None = None,
                     keyword: str | None = None) -> list[dict]:
        """Return canon claims, optionally filtered.

        Parameters
        ----------
        entity_id : str, optional
            If provided, only claims for this entity are returned.
        keyword : str, optional
            If provided, only claims containing this keyword are returned
            (case-insensitive).

        Returns
        -------
        list[dict]
            Each dict has ``entity_id``, ``claim``, and ``refs``.
        """
        conditions = []
        params: list = []

        if entity_id is not None:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        if keyword is not None:
            conditions.append("claim LIKE ?")
            params.append(f"%{keyword}%")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        rows = self._conn.execute(
            f"SELECT entity_id, claim, refs FROM canon_claims {where_clause}",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # Allowed tables and columns for structured queries
    _ALLOWED_TABLES = frozenset({"entities", "cross_references", "canon_claims"})
    _ALLOWED_COLUMNS = frozenset({
        "id", "entity_type", "name", "template_id", "status",
        "step_created", "file_path", "data", "created_at", "updated_at",
        "source_id", "target_id", "relationship_type", "source_field",
        "entity_id", "claim", "refs",
    })
    _ALLOWED_OPERATORS = frozenset({
        "=", "!=", "<>", "<", ">", "<=", ">=", "LIKE", "NOT LIKE",
        "IN", "NOT IN", "IS", "IS NOT", "BETWEEN",
    })
    _DANGEROUS_KEYWORDS = frozenset({
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
        "REPLACE", "ATTACH", "DETACH", "REINDEX", "VACUUM",
        "PRAGMA", "LOAD_EXTENSION",
    })

    def advanced_query(self, sql: str, params: tuple | list | None = None) -> list[dict]:
        """Execute an arbitrary read-only SQL query.

        Only SELECT statements are allowed.  Any attempt to execute
        a write statement (INSERT, UPDATE, DELETE, DROP, etc.) will
        raise a ``ValueError``.

        Parameters
        ----------
        sql : str
            A SQL SELECT statement.
        params : tuple or list, optional
            Bind parameters for the query.

        Returns
        -------
        list[dict]
            Query results as a list of dicts.
        """
        # Safety: only allow SELECT/WITH
        stripped = sql.strip()
        upper = stripped.upper()
        if not upper.startswith("SELECT") and not upper.startswith("WITH"):
            raise ValueError(
                "Only SELECT queries are allowed via advanced_query(). "
                "The provided statement starts with: "
                f"'{stripped[:20]}...'"
            )

        # Strip comments that could hide dangerous keywords
        import re
        no_comments = re.sub(r"--[^\n]*", " ", stripped)
        no_comments = re.sub(r"/\*.*?\*/", " ", no_comments, flags=re.DOTALL)

        # Block dangerous keywords (check against cleaned SQL)
        tokens = set(no_comments.upper().split())
        found = tokens & self._DANGEROUS_KEYWORDS
        if found:
            raise ValueError(
                f"The query contains disallowed keywords: {found}. "
                "Only pure read queries are permitted."
            )

        # Block semicolons (prevents statement stacking)
        if ";" in no_comments.rstrip().rstrip(";"):
            raise ValueError(
                "Multiple statements are not allowed. "
                "Only a single SELECT query is permitted."
            )

        if params is None:
            params = ()
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_entities(
        self,
        filters=None,
        order_by=None,
        limit=100,
        offset=0,
    ):
        """Execute a safe, structured query against the entities table.

        Uses whitelisted column names and parameterised values to prevent
        SQL injection.  Prefer this over :meth:`advanced_query` when
        querying entities.

        Parameters
        ----------
        filters : list[tuple], optional
            List of ``(column, operator, value)`` tuples.  Column and
            operator are validated against whitelists.
        order_by : str, optional
            Column name to sort by (must be in whitelist).
        limit : int
            Maximum rows to return (default 100, max 1000).
        offset : int
            Number of rows to skip.

        Returns
        -------
        list[dict]
        """
        clauses = []
        params = []

        for col, op, val in (filters or []):
            if col not in self._ALLOWED_COLUMNS:
                raise ValueError(f"Column '{col}' is not in the allowed list")
            op_upper = op.upper().strip()
            if op_upper not in self._ALLOWED_OPERATORS:
                raise ValueError(f"Operator '{op}' is not allowed")
            clauses.append(f"{col} {op_upper} ?")
            params.append(val)

        sql = "SELECT * FROM entities"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        if order_by:
            if order_by.lstrip("-") not in self._ALLOWED_COLUMNS:
                raise ValueError(f"Order column '{order_by}' is not allowed")
            direction = "DESC" if order_by.startswith("-") else "ASC"
            col_name = order_by.lstrip("-")
            sql += f" ORDER BY {col_name} {direction}"

        limit = min(max(1, limit), 1000)
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Return database statistics.

        Returns
        -------
        dict
            Contains ``total_entities``, ``by_type`` (dict),
            ``by_status`` (dict), ``total_cross_references``,
            ``total_canon_claims``.
        """
        total = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM entities"
        ).fetchone()["cnt"]

        by_type_rows = self._conn.execute(
            "SELECT entity_type, COUNT(*) AS cnt FROM entities "
            "GROUP BY entity_type ORDER BY cnt DESC"
        ).fetchall()
        by_type = {r["entity_type"]: r["cnt"] for r in by_type_rows}

        by_status_rows = self._conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM entities "
            "GROUP BY status ORDER BY cnt DESC"
        ).fetchall()
        by_status = {r["status"]: r["cnt"] for r in by_status_rows}

        xref_count = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM cross_references"
        ).fetchone()["cnt"]

        claims_count = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM canon_claims"
        ).fetchone()["cnt"]

        return {
            "total_entities": total,
            "by_type": by_type,
            "by_status": by_status,
            "total_cross_references": xref_count,
            "total_canon_claims": claims_count,
        }

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        """Support usage as a context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close on context manager exit."""
        self.close()
        return False

    # ------------------------------------------------------------------
    # Internal: row insertion helpers
    # ------------------------------------------------------------------

    def _upsert_entity_row(self, entity_id: str, entity: dict,
                           meta: dict, file_path: str) -> None:
        """Insert or replace a single entity row."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO entities
                (id, entity_type, name, template_id, status,
                 step_created, file_path, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                meta.get("entity_type", ""),
                entity.get("name", entity_id),
                meta.get("template_id", ""),
                meta.get("status", "draft"),
                meta.get("step_created"),
                file_path,
                json.dumps(entity, ensure_ascii=False),
                meta.get("created_at", ""),
                meta.get("updated_at", ""),
            ),
        )

    def _upsert_cross_references(self, entity_id: str, entity: dict) -> None:
        """Insert cross-reference rows for an entity."""
        xrefs = _extract_cross_references(entity)
        for target_id, rel_type, source_field in xrefs:
            self._conn.execute(
                """
                INSERT INTO cross_references
                    (source_id, target_id, relationship_type, source_field)
                VALUES (?, ?, ?, ?)
                """,
                (entity_id, target_id, rel_type, source_field),
            )

    def _upsert_canon_claims(self, entity_id: str, entity: dict) -> None:
        """Insert canon claim rows for an entity."""
        claims = entity.get("canon_claims", [])
        for claim in claims:
            if isinstance(claim, dict):
                claim_text = claim.get("claim", "")
                refs = json.dumps(claim.get("references", []), ensure_ascii=False)
            elif isinstance(claim, str):
                claim_text = claim
                refs = "[]"
            else:
                continue
            if claim_text:
                self._conn.execute(
                    "INSERT INTO canon_claims (entity_id, claim, refs) VALUES (?, ?, ?)",
                    (entity_id, claim_text, refs),
                )

    def _upsert_fts(self, entity_id: str, entity: dict) -> None:
        """Insert a row into the FTS5 index for full-text search.

        The FTS5 table uses content='entities' and content_rowid='rowid',
        so we need to supply the rowid of the corresponding entities row.
        """
        # Get the rowid assigned to this entity
        row = self._conn.execute(
            "SELECT rowid FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            return
        rowid = row["rowid"]

        name = entity.get("name", "")
        entity_type = entity.get("_meta", {}).get("entity_type", "")
        tags = _extract_text_field(entity, "tags")
        description = _extract_text_field(entity, "description")
        claims_text = _extract_canon_claims_text(entity)

        self._conn.execute(
            """
            INSERT INTO entity_search(rowid, name, entity_type, tags,
                                      description, canon_claims_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (rowid, name, entity_type, tags, description, claims_text),
        )

    def _remove_entity_data(self, entity_id: str) -> None:
        """Remove all data for an entity from all tables (including FTS)."""
        # Get the rowid before deleting (needed for FTS cleanup)
        row = self._conn.execute(
            "SELECT rowid FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()

        if row is not None:
            rowid = row["rowid"]
            # Remove from FTS index
            try:
                # For content-synced FTS5, we must supply the old content
                # when deleting.  Fetch the current FTS data first.
                fts_row = self._conn.execute(
                    "SELECT name, entity_type, tags, description, canon_claims_text "
                    "FROM entity_search WHERE rowid = ?",
                    (rowid,),
                ).fetchone()
                if fts_row:
                    self._conn.execute(
                        """
                        INSERT INTO entity_search(entity_search, rowid,
                            name, entity_type, tags, description, canon_claims_text)
                        VALUES ('delete', ?, ?, ?, ?, ?, ?)
                        """,
                        (rowid, fts_row["name"], fts_row["entity_type"],
                         fts_row["tags"], fts_row["description"],
                         fts_row["canon_claims_text"]),
                    )
            except sqlite3.OperationalError:
                # If FTS is in a bad state, just proceed
                pass

        # Remove from relational tables
        self._conn.execute(
            "DELETE FROM cross_references WHERE source_id = ? OR target_id = ?",
            (entity_id, entity_id),
        )
        self._conn.execute(
            "DELETE FROM canon_claims WHERE entity_id = ?",
            (entity_id,),
        )
        self._conn.execute(
            "DELETE FROM entities WHERE id = ?",
            (entity_id,),
        )

    # ------------------------------------------------------------------
    # Internal: search helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitise_fts_query(query: str) -> str:
        """Convert a plain-text query into a safe FTS5 query string.

        Wraps each word in double quotes to prevent FTS5 syntax errors
        from user input containing special characters like ``*``, ``-``,
        ``(``, etc.  Multiple words become implicit AND matches.
        """
        words = query.split()
        if not words:
            return '""'
        # Quote each word individually, then join with spaces (implicit AND)
        safe_parts = []
        for word in words:
            # Remove any embedded double quotes
            clean = word.replace('"', '')
            if clean:
                safe_parts.append(f'"{clean}"')
        return " ".join(safe_parts) if safe_parts else '""'

    def _fallback_search(self, query: str) -> list[dict]:
        """Simple LIKE-based search used when FTS5 fails."""
        pattern = f"%{query}%"
        rows = self._conn.execute(
            """
            SELECT * FROM entities
            WHERE name LIKE ? OR entity_type LIKE ?
               OR data LIKE ?
            ORDER BY name
            """,
            (pattern, pattern, pattern),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        """Convert a sqlite3.Row to a plain dict.

        If the row contains a ``data`` column with a JSON string, it is
        left as-is (callers can ``json.loads()`` it if they need the
        nested structure).
        """
        return dict(row)
