from dataclasses import dataclass
from pathlib import Path
import json
import logging
import shutil
import sqlite3
from datetime import datetime, timezone

from structure_aligner.etl.transformer import TransformResult

logger = logging.getLogger(__name__)


@dataclass
class LoadReport:
    """Report generated after loading data."""
    report_path: Path
    elements_inserted: int
    vertices_inserted: int
    validation_passed: bool


# SQL for PRD-compliant tables
CREATE_ELEMENTS_SQL = """
CREATE TABLE IF NOT EXISTS elements (
    id INTEGER PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    nom VARCHAR(100) NOT NULL,
    geometry_type VARCHAR(30)
);
"""

CREATE_VERTICES_SQL = """
CREATE TABLE IF NOT EXISTS vertices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    element_id INTEGER NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL NOT NULL,
    vertex_index INTEGER NOT NULL,
    FOREIGN KEY (element_id) REFERENCES elements(id)
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_vertices_element_id ON vertices(element_id);",
    "CREATE INDEX IF NOT EXISTS idx_vertices_x ON vertices(x);",
    "CREATE INDEX IF NOT EXISTS idx_vertices_y ON vertices(y);",
    "CREATE INDEX IF NOT EXISTS idx_vertices_z ON vertices(z);",
]


def load(result: TransformResult, source_db: Path, output_path: Path) -> LoadReport:
    """
    Copy source database and add PRD-compliant elements + vertices tables.

    The source database is copied to output_path first (preserving all
    original tables), then elements and vertices tables are created and
    populated in a single atomic transaction.

    Args:
        result: TransformResult from the transform step.
        source_db: Path to the original .db file.
        output_path: Path for the output .db file.

    Returns:
        LoadReport with insertion counts and validation status.

    Raises:
        FileExistsError: If output_path already exists.
        sqlite3.Error: If database operations fail (transaction is rolled back).
    """
    if output_path.exists():
        raise FileExistsError(f"Output file already exists: {output_path}. Remove it first or choose a different path.")

    # Step 1: Copy source database
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source_db), str(output_path))
    logger.info("Copied source database to %s", output_path)

    # Step 2: Create tables and insert data in a single transaction
    conn = sqlite3.connect(str(output_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        cursor = conn.cursor()

        # Create tables
        cursor.execute(CREATE_ELEMENTS_SQL)
        cursor.execute(CREATE_VERTICES_SQL)

        # Insert elements
        cursor.executemany(
            "INSERT INTO elements (id, type, nom, geometry_type) VALUES (?, ?, ?, ?)",
            [(e.id, e.type, e.nom, e.geometry_type) for e in result.elements],
        )
        elements_inserted = len(result.elements)

        # Insert vertices
        cursor.executemany(
            "INSERT INTO vertices (element_id, x, y, z, vertex_index) VALUES (?, ?, ?, ?, ?)",
            [(v.element_id, v.x, v.y, v.z, v.vertex_index) for v in result.vertices],
        )
        vertices_inserted = len(result.vertices)

        # Create indexes
        for sql in CREATE_INDEXES_SQL:
            cursor.execute(sql)

        conn.commit()
        logger.info("Inserted %d elements, %d vertices", elements_inserted, vertices_inserted)

    except Exception:
        conn.rollback()
        # Clean up the copied file on failure
        output_path.unlink(missing_ok=True)
        raise
    finally:
        conn.close()

    # Step 3: Validate
    validation_passed = _validate_output(output_path, result)

    # Step 4: Generate report
    report_path = output_path.with_suffix(".etl_report.json")
    report = _generate_report(
        report_path, output_path, result,
        elements_inserted, vertices_inserted, validation_passed,
    )

    return report


def _validate_output(output_path: Path, result: TransformResult) -> bool:
    """Run post-load validation checks."""
    conn = sqlite3.connect(str(output_path))
    passed = True
    try:
        cursor = conn.cursor()

        # Check element count
        cursor.execute("SELECT COUNT(*) FROM elements")
        db_count = cursor.fetchone()[0]
        if db_count != len(result.elements):
            logger.error("Element count mismatch: expected %d, got %d", len(result.elements), db_count)
            passed = False

        # Check vertex count
        cursor.execute("SELECT COUNT(*) FROM vertices")
        db_count = cursor.fetchone()[0]
        if db_count != len(result.vertices):
            logger.error("Vertex count mismatch: expected %d, got %d", len(result.vertices), db_count)
            passed = False

        # Check no NULL coordinates
        cursor.execute("SELECT COUNT(*) FROM vertices WHERE x IS NULL OR y IS NULL OR z IS NULL")
        null_count = cursor.fetchone()[0]
        if null_count > 0:
            logger.error("%d vertices with NULL coordinates in output", null_count)
            passed = False

        # Check FK integrity
        cursor.execute("""
            SELECT COUNT(*) FROM vertices v
            LEFT JOIN elements e ON v.element_id = e.id
            WHERE e.id IS NULL
        """)
        orphan_count = cursor.fetchone()[0]
        if orphan_count > 0:
            logger.error("%d vertices with invalid element_id references", orphan_count)
            passed = False

        # Check element types
        cursor.execute("SELECT DISTINCT type FROM elements")
        types = {row[0] for row in cursor.fetchall()}
        expected_types = {"poteau", "poutre", "voile", "dalle", "appui"}
        if types != expected_types:
            logger.error("Unexpected element types: %s (expected %s)", types, expected_types)
            passed = False

    finally:
        conn.close()

    if passed:
        logger.info("All post-load validation checks passed")
    else:
        logger.error("Post-load validation FAILED")

    return passed


def _generate_report(
    report_path: Path,
    output_path: Path,
    result: TransformResult,
    elements_inserted: int,
    vertices_inserted: int,
    validation_passed: bool,
) -> LoadReport:
    """Write a JSON validation report."""
    from collections import Counter

    type_counts = Counter(e.type for e in result.elements)
    xs = [v.x for v in result.vertices]
    ys = [v.y for v in result.vertices]
    zs = [v.z for v in result.vertices]

    report_data = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output_database": str(output_path),
            "pipeline": "etl",
            "software_version": "0.1.0",
        },
        "statistics": {
            "elements_total": elements_inserted,
            "elements_by_type": dict(type_counts),
            "vertices_total": vertices_inserted,
            "matched_elements": result.matched_count,
            "unmatched_elements": len(result.unmatched),
            "unmatched_details": [
                {"name": name, "source": source}
                for name, source in result.unmatched
            ],
        },
        "coordinate_ranges": {
            "x": {"min": min(xs), "max": max(xs)} if xs else None,
            "y": {"min": min(ys), "max": max(ys)} if ys else None,
            "z": {"min": min(zs), "max": max(zs)} if zs else None,
        },
        "template_fingerprint": {
            "object_count": result.template_object_count,
            "element_names_hash": result.template_names_hash,
        },
        "validation": {
            "passed": validation_passed,
            "checks": [
                "element_count",
                "vertex_count",
                "no_null_coordinates",
                "fk_integrity",
                "element_types",
            ],
        },
    }

    report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
    logger.info("Validation report written to %s", report_path)

    return LoadReport(
        report_path=report_path,
        elements_inserted=elements_inserted,
        vertices_inserted=vertices_inserted,
        validation_passed=validation_passed,
    )
