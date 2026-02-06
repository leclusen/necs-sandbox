from dataclasses import dataclass, field
from pathlib import Path
import logging
import sqlite3

logger = logging.getLogger(__name__)


@dataclass
class AlignedVertexCoord:
    vertex_index: int
    x: float
    y: float
    z: float


@dataclass
class AlignedElement:
    element_id: int
    nom: str
    geometry_type: str | None
    vertices: list[AlignedVertexCoord] = field(default_factory=list)


def read_aligned_elements(db_path: Path) -> dict[str, AlignedElement]:
    """Read aligned DB, return dict keyed by element name (nom).

    Works with both aligned DBs (has x_original columns) and
    PRD-compliant DBs (no alignment columns).

    Raises:
        FileNotFoundError: If db_path does not exist.
        ValueError: If duplicate element names are detected or required tables missing.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # Validate required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='elements'")
        if cursor.fetchone() is None:
            raise ValueError(f"Database {db_path} does not contain an 'elements' table")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vertices'")
        if cursor.fetchone() is None:
            raise ValueError(f"Database {db_path} does not contain a 'vertices' table")

        # Check if geometry_type column exists
        cursor.execute("PRAGMA table_info(elements)")
        columns = {row[1] for row in cursor.fetchall()}
        has_geometry_type = "geometry_type" in columns

        # Read elements
        if has_geometry_type:
            cursor.execute("SELECT id, nom, geometry_type FROM elements")
        else:
            cursor.execute("SELECT id, nom FROM elements")

        elements_by_id: dict[int, AlignedElement] = {}
        name_to_id: dict[str, list[int]] = {}

        for row in cursor.fetchall():
            eid = row[0]
            nom = row[1]
            geom_type = row[2] if has_geometry_type else None
            elements_by_id[eid] = AlignedElement(
                element_id=eid, nom=nom, geometry_type=geom_type
            )
            name_to_id.setdefault(nom, []).append(eid)

        # Detect duplicate names
        duplicates = {name: ids for name, ids in name_to_id.items() if len(ids) > 1}
        if duplicates:
            dup_details = [f"'{name}' (element_ids: {ids})" for name, ids in duplicates.items()]
            raise ValueError(
                f"Duplicate element names detected: {', '.join(dup_details)}"
            )

        # Read vertices grouped by element_id, ordered by vertex_index
        cursor.execute("""
            SELECT element_id, vertex_index, x, y, z
            FROM vertices
            ORDER BY element_id, vertex_index
        """)

        for row in cursor.fetchall():
            eid = row[0]
            if eid in elements_by_id:
                elements_by_id[eid].vertices.append(
                    AlignedVertexCoord(
                        vertex_index=row[1], x=row[2], y=row[3], z=row[4]
                    )
                )

        # Build name-keyed dict
        result: dict[str, AlignedElement] = {}
        for element in elements_by_id.values():
            result[element.nom] = element

        logger.info(
            "Read %d elements (%d with vertices) from %s",
            len(result),
            sum(1 for e in result.values() if e.vertices),
            db_path,
        )
        return result

    finally:
        conn.close()
