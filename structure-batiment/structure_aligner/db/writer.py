import logging
import shutil
import sqlite3
from pathlib import Path

from structure_aligner.config import AlignedVertex

logger = logging.getLogger(__name__)

# New columns to add to the vertices table (PRD F-08, lines 298-321)
ALTER_TABLE_COLUMNS = [
    ("x_original", "REAL"),
    ("y_original", "REAL"),
    ("z_original", "REAL"),
    ("aligned_axis", "VARCHAR(10) NOT NULL DEFAULT 'none'"),
    ("fil_x_id", "VARCHAR(20)"),
    ("fil_y_id", "VARCHAR(20)"),
    ("fil_z_id", "VARCHAR(20)"),
    ("displacement_total", "REAL NOT NULL DEFAULT 0.0"),
]

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_vertices_aligned_axis ON vertices(aligned_axis);",
    "CREATE INDEX IF NOT EXISTS idx_vertices_displacement ON vertices(displacement_total);",
]


def write_aligned_db(
    input_db: Path,
    output_path: Path,
    aligned_vertices: list[AlignedVertex],
) -> Path:
    """
    Create output database with enriched vertices table.

    Copies the input database, then uses ALTER TABLE to add enrichment
    columns to the existing vertices table. This preserves the table name
    (PRD F-08 compliance), all existing FK constraints, and indexes.

    Then updates each vertex row with aligned coordinates and metadata.

    Args:
        input_db: Path to the input PRD-compliant database.
        output_path: Path for the output database.
        aligned_vertices: List of aligned vertices to write.

    Returns:
        Path to the created output database.
    """
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(input_db), str(output_path))

    conn = sqlite3.connect(str(output_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        cursor = conn.cursor()

        # Add new columns to existing vertices table
        # Note: col_name/col_type come from ALTER_TABLE_COLUMNS constant, not user input
        for col_name, col_type in ALTER_TABLE_COLUMNS:
            cursor.execute(f"ALTER TABLE vertices ADD COLUMN {col_name} {col_type};")

        # Update each vertex with aligned data
        cursor.executemany(
            """UPDATE vertices
               SET x = ?, y = ?, z = ?,
                   x_original = ?, y_original = ?, z_original = ?,
                   aligned_axis = ?, fil_x_id = ?, fil_y_id = ?, fil_z_id = ?,
                   displacement_total = ?
               WHERE id = ?""",
            [
                (v.x, v.y, v.z,
                 v.x_original, v.y_original, v.z_original,
                 v.aligned_axis, v.fil_x_id, v.fil_y_id, v.fil_z_id,
                 v.displacement_total,
                 v.id)
                for v in aligned_vertices
            ],
        )

        # Create new indexes
        for sql in CREATE_INDEXES_SQL:
            cursor.execute(sql)

        conn.commit()
        logger.info("Written %d aligned vertices to %s", len(aligned_vertices), output_path)

    except Exception:
        conn.rollback()
        output_path.unlink(missing_ok=True)
        raise
    finally:
        conn.close()

    return output_path
