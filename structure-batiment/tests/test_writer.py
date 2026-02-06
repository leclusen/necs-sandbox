"""Tests for structure_aligner.db.writer."""
import sqlite3
from pathlib import Path

import pytest

from structure_aligner.config import AlignedVertex
from structure_aligner.db.writer import write_aligned_db

# Path to the real PRD database
REAL_DB = Path(__file__).resolve().parent.parent / "data" / "geometrie_2_prd.db"


def _make_aligned_vertex(id: int, x: float = 10.0, y: float = 20.0, z: float = 30.0,
                         element_id: int = 6233, vertex_index: int = 0,
                         x_original: float = 10.03, y_original: float = 20.02,
                         z_original: float = 30.01, aligned_axis: str = "XYZ",
                         fil_x_id: str = "X_001", fil_y_id: str = "Y_001",
                         fil_z_id: str = "Z_001",
                         displacement_total: float = 0.037417) -> AlignedVertex:
    return AlignedVertex(
        id=id, element_id=element_id, x=x, y=y, z=z, vertex_index=vertex_index,
        x_original=x_original, y_original=y_original, z_original=z_original,
        aligned_axis=aligned_axis, fil_x_id=fil_x_id, fil_y_id=fil_y_id,
        fil_z_id=fil_z_id, displacement_total=displacement_total,
    )


@pytest.fixture
def setup_db(tmp_path):
    """Create a minimal input DB for testing."""
    db_path = tmp_path / "input.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute(
        "CREATE TABLE elements (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "type VARCHAR(50) NOT NULL, nom VARCHAR(100) NOT NULL)"
    )
    conn.execute("INSERT INTO elements (id, type, nom) VALUES (6233, 'beam', 'B1')")
    conn.execute(
        "CREATE TABLE vertices (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "element_id INTEGER NOT NULL, x REAL NOT NULL, y REAL NOT NULL, "
        "z REAL NOT NULL, vertex_index INTEGER NOT NULL, "
        "FOREIGN KEY (element_id) REFERENCES elements(id))"
    )
    conn.execute(
        "INSERT INTO vertices (id, element_id, x, y, z, vertex_index) "
        "VALUES (1, 6233, 10.03, 20.02, 30.01, 0)"
    )
    conn.execute(
        "INSERT INTO vertices (id, element_id, x, y, z, vertex_index) "
        "VALUES (2, 6233, 10.04, 20.01, 30.02, 1)"
    )
    conn.execute("CREATE INDEX idx_vertices_element_id ON vertices(element_id)")
    conn.commit()
    conn.close()
    return db_path, tmp_path


class TestWriteAlignedDB:

    def test_creates_output_with_enriched_columns(self, setup_db):
        db_path, tmp_path = setup_db
        output = tmp_path / "output.db"
        avs = [
            _make_aligned_vertex(1),
            _make_aligned_vertex(2, x=10.0, y=20.0, z=30.0,
                                 x_original=10.04, y_original=20.01, z_original=30.02),
        ]

        result = write_aligned_db(db_path, output, avs)

        assert result == output
        assert output.exists()

        conn = sqlite3.connect(str(output))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(vertices)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        expected_new = {"x_original", "y_original", "z_original", "aligned_axis",
                        "fil_x_id", "fil_y_id", "fil_z_id", "displacement_total"}
        assert expected_new.issubset(columns)

    def test_aligned_coordinates_written(self, setup_db):
        db_path, tmp_path = setup_db
        output = tmp_path / "output.db"
        avs = [_make_aligned_vertex(1, x=10.0, y=20.0, z=30.0)]

        write_aligned_db(db_path, output, avs)

        conn = sqlite3.connect(str(output))
        row = conn.execute("SELECT x, y, z FROM vertices WHERE id = 1").fetchone()
        conn.close()

        assert row == (10.0, 20.0, 30.0)

    def test_originals_preserved_in_output(self, setup_db):
        db_path, tmp_path = setup_db
        output = tmp_path / "output.db"
        avs = [_make_aligned_vertex(1, x_original=10.03, y_original=20.02, z_original=30.01)]

        write_aligned_db(db_path, output, avs)

        conn = sqlite3.connect(str(output))
        row = conn.execute("SELECT x_original, y_original, z_original FROM vertices WHERE id = 1").fetchone()
        conn.close()

        assert row == (10.03, 20.02, 30.01)

    def test_elements_table_preserved(self, setup_db):
        db_path, tmp_path = setup_db
        output = tmp_path / "output.db"

        write_aligned_db(db_path, output, [_make_aligned_vertex(1)])

        conn = sqlite3.connect(str(output))
        row = conn.execute("SELECT id, type, nom FROM elements WHERE id = 6233").fetchone()
        conn.close()

        assert row == (6233, "beam", "B1")

    def test_original_indexes_preserved(self, setup_db):
        db_path, tmp_path = setup_db
        output = tmp_path / "output.db"

        write_aligned_db(db_path, output, [_make_aligned_vertex(1)])

        conn = sqlite3.connect(str(output))
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='vertices'"
        ).fetchall()
        conn.close()
        index_names = {row[0] for row in indexes}

        assert "idx_vertices_element_id" in index_names

    def test_new_indexes_created(self, setup_db):
        db_path, tmp_path = setup_db
        output = tmp_path / "output.db"

        write_aligned_db(db_path, output, [_make_aligned_vertex(1)])

        conn = sqlite3.connect(str(output))
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='vertices'"
        ).fetchall()
        conn.close()
        index_names = {row[0] for row in indexes}

        assert "idx_vertices_aligned_axis" in index_names
        assert "idx_vertices_displacement" in index_names

    def test_fk_integrity_maintained(self, setup_db):
        db_path, tmp_path = setup_db
        output = tmp_path / "output.db"

        write_aligned_db(db_path, output, [_make_aligned_vertex(1)])

        conn = sqlite3.connect(str(output))
        conn.execute("PRAGMA foreign_keys=ON;")
        fk = conn.execute("PRAGMA foreign_key_list(vertices)").fetchall()
        conn.close()

        assert len(fk) > 0
        assert fk[0][2] == "elements"  # references elements table

    def test_output_already_exists_raises(self, setup_db):
        db_path, tmp_path = setup_db
        output = tmp_path / "output.db"
        output.touch()

        with pytest.raises(FileExistsError, match="Output already exists"):
            write_aligned_db(db_path, output, [_make_aligned_vertex(1)])

    def test_with_real_db(self, tmp_path):
        """Integration test using the real PRD database."""
        if not REAL_DB.exists():
            pytest.skip(f"Real DB not found: {REAL_DB}")

        output = tmp_path / "output_real.db"
        # Just align vertex id=1 for a minimal test
        avs = [_make_aligned_vertex(1)]

        write_aligned_db(REAL_DB, output, avs)

        conn = sqlite3.connect(str(output))
        row = conn.execute(
            "SELECT x, y, z, x_original, aligned_axis, displacement_total "
            "FROM vertices WHERE id = 1"
        ).fetchone()
        conn.close()

        assert row[0] == 10.0       # aligned x
        assert row[3] == 10.03      # x_original
        assert row[4] == "XYZ"      # aligned_axis
        assert isinstance(row[5], float)  # displacement_total
