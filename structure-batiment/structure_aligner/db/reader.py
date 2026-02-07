import sqlite3
from pathlib import Path
from dataclasses import dataclass
import logging

from structure_aligner.config import ElementInfo

logger = logging.getLogger(__name__)


@dataclass
class InputVertex:
    """A vertex loaded from the input PRD database."""
    id: int
    element_id: int
    x: float
    y: float
    z: float
    vertex_index: int


def load_vertices(db_path: Path) -> list[InputVertex]:
    """
    Load all vertices from a PRD-compliant database.

    Args:
        db_path: Path to the input .db file.

    Returns:
        List of InputVertex records.

    Raises:
        FileNotFoundError: If db_path does not exist.
        ValueError: If the database lacks a 'vertices' table or expected columns.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # Validate schema
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vertices'")
        if cursor.fetchone() is None:
            raise ValueError(f"Database {db_path} does not contain a 'vertices' table")

        cursor.execute("SELECT id, element_id, x, y, z, vertex_index FROM vertices ORDER BY id")
        vertices = [
            InputVertex(id=row[0], element_id=row[1], x=row[2], y=row[3], z=row[4], vertex_index=row[5])
            for row in cursor.fetchall()
        ]
        logger.info("Loaded %d vertices from %s", len(vertices), db_path)
        return vertices
    finally:
        conn.close()


def load_vertices_with_elements(
    db_path: Path,
) -> tuple[list[InputVertex], dict[int, ElementInfo]]:
    """Load vertices AND element metadata for per-element alignment.

    Args:
        db_path: Path to the PRD-compliant .db file.

    Returns:
        Tuple of (vertices, elements_dict) where elements_dict maps
        element_id -> ElementInfo.

    Raises:
        FileNotFoundError: If db_path does not exist.
        ValueError: If the database lacks required tables.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # Validate schema
        for table in ("vertices", "elements"):
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if cursor.fetchone() is None:
                raise ValueError(
                    f"Database {db_path} does not contain a '{table}' table"
                )

        # Load elements
        cursor.execute("SELECT id, type, nom, geometry_type FROM elements")
        elements: dict[int, ElementInfo] = {}
        for row in cursor.fetchall():
            elements[row[0]] = ElementInfo(
                id=row[0],
                name=row[2],
                type=row[1],
                geometry_type=row[3],
            )

        # Load vertices
        cursor.execute(
            "SELECT id, element_id, x, y, z, vertex_index FROM vertices ORDER BY id"
        )
        vertices = [
            InputVertex(
                id=row[0],
                element_id=row[1],
                x=row[2],
                y=row[3],
                z=row[4],
                vertex_index=row[5],
            )
            for row in cursor.fetchall()
        ]

        logger.info(
            "Loaded %d vertices and %d elements from %s",
            len(vertices),
            len(elements),
            db_path,
        )
        return vertices, elements
    finally:
        conn.close()
