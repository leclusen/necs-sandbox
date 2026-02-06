from pathlib import Path
import sqlite3
import pytest
from structure_aligner.etl.reverse_reader import read_aligned_elements

DATA_DIR = Path(__file__).parent.parent / "data"
PRD_DB = DATA_DIR / "geometrie_2_prd.db"
ALIGNED_DB = sorted(DATA_DIR.glob("*_aligned_*.db"))
ALIGNED_DB = ALIGNED_DB[0] if ALIGNED_DB else None


def _create_test_db(path, elements, vertices, add_geometry_type=True):
    """Helper: create a minimal test DB with elements + vertices tables."""
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()
    if add_geometry_type:
        cursor.execute("""
            CREATE TABLE elements (
                id INTEGER PRIMARY KEY,
                type VARCHAR(50) NOT NULL,
                nom VARCHAR(100) NOT NULL,
                geometry_type VARCHAR(30)
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE elements (
                id INTEGER PRIMARY KEY,
                type VARCHAR(50) NOT NULL,
                nom VARCHAR(100) NOT NULL
            )
        """)
    cursor.execute("""
        CREATE TABLE vertices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            element_id INTEGER NOT NULL,
            x REAL NOT NULL,
            y REAL NOT NULL,
            z REAL NOT NULL,
            vertex_index INTEGER NOT NULL,
            FOREIGN KEY (element_id) REFERENCES elements(id)
        )
    """)
    cursor.executemany(
        "INSERT INTO elements (id, type, nom" + (", geometry_type" if add_geometry_type else "") + ") VALUES (?" + ", ?" * (3 if add_geometry_type else 2) + ")",
        elements,
    )
    cursor.executemany(
        "INSERT INTO vertices (element_id, x, y, z, vertex_index) VALUES (?, ?, ?, ?, ?)",
        vertices,
    )
    conn.commit()
    conn.close()


class TestReadAlignedElements:

    def test_reads_elements_correctly(self, tmp_path):
        db = tmp_path / "test.db"
        _create_test_db(
            db,
            elements=[(1, "poteau", "P1", "point"), (2, "poutre", "B1", "line_curve")],
            vertices=[
                (1, 1.0, 2.0, 3.0, 0),
                (2, 4.0, 5.0, 6.0, 0),
                (2, 7.0, 8.0, 9.0, 1),
            ],
        )
        result = read_aligned_elements(db)
        assert len(result) == 2
        assert "P1" in result
        assert "B1" in result
        assert len(result["P1"].vertices) == 1
        assert len(result["B1"].vertices) == 2

    def test_vertices_sorted_by_index(self, tmp_path):
        db = tmp_path / "test.db"
        _create_test_db(
            db,
            elements=[(1, "poutre", "B1", "line_curve")],
            vertices=[
                (1, 7.0, 8.0, 9.0, 1),
                (1, 4.0, 5.0, 6.0, 0),
            ],
        )
        result = read_aligned_elements(db)
        assert result["B1"].vertices[0].vertex_index == 0
        assert result["B1"].vertices[1].vertex_index == 1

    def test_handles_no_geometry_type_column(self, tmp_path):
        db = tmp_path / "test.db"
        _create_test_db(
            db,
            elements=[(1, "poteau", "P1")],
            vertices=[(1, 1.0, 2.0, 3.0, 0)],
            add_geometry_type=False,
        )
        result = read_aligned_elements(db)
        assert result["P1"].geometry_type is None

    def test_handles_empty_db(self, tmp_path):
        db = tmp_path / "test.db"
        _create_test_db(db, elements=[], vertices=[])
        result = read_aligned_elements(db)
        assert len(result) == 0

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            read_aligned_elements(Path("/nonexistent/db.db"))

    def test_missing_elements_table(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE foo (id INTEGER)")
        conn.close()
        with pytest.raises(ValueError, match="elements"):
            read_aligned_elements(db)

    def test_duplicate_names_raises(self, tmp_path):
        db = tmp_path / "test.db"
        _create_test_db(
            db,
            elements=[(1, "poteau", "Dup", "point"), (2, "poutre", "Dup", "line_curve")],
            vertices=[],
        )
        with pytest.raises(ValueError, match="Duplicate"):
            read_aligned_elements(db)

    def test_elements_with_zero_vertices(self, tmp_path):
        db = tmp_path / "test.db"
        _create_test_db(
            db,
            elements=[(1, "poteau", "P1", "point"), (2, "poutre", "B1", "line_curve")],
            vertices=[(1, 1.0, 2.0, 3.0, 0)],
        )
        result = read_aligned_elements(db)
        assert len(result["P1"].vertices) == 1
        assert len(result["B1"].vertices) == 0

    @pytest.mark.skipif(PRD_DB is None or not PRD_DB.exists(), reason="Test data not available")
    def test_reads_prd_db(self):
        result = read_aligned_elements(PRD_DB)
        assert len(result) == 5825

    @pytest.mark.skipif(ALIGNED_DB is None or not ALIGNED_DB.exists(), reason="Test data not available")
    def test_reads_aligned_db(self):
        result = read_aligned_elements(ALIGNED_DB)
        assert len(result) == 5825
