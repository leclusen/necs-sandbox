"""Tests for structure_aligner.db.reader."""
import sqlite3
from pathlib import Path

import pytest

from structure_aligner.db.reader import InputVertex, load_vertices

# Path to the real PRD database
REAL_DB = Path(__file__).resolve().parent.parent / "data" / "geometrie_2_prd.db"


class TestLoadVerticesRealDB:
    """Tests using the real geometrie_2_prd.db."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_db(self):
        if not REAL_DB.exists():
            pytest.skip(f"Real DB not found: {REAL_DB}")

    def test_loads_expected_count(self):
        vertices = load_vertices(REAL_DB)
        assert len(vertices) == 20994

    def test_returns_input_vertex_instances(self):
        vertices = load_vertices(REAL_DB)
        assert all(isinstance(v, InputVertex) for v in vertices[:10])

    def test_first_vertex_fields(self):
        vertices = load_vertices(REAL_DB)
        v = vertices[0]
        assert v.id == 1
        assert v.element_id == 6233
        assert isinstance(v.x, float)
        assert isinstance(v.y, float)
        assert isinstance(v.z, float)
        assert isinstance(v.vertex_index, int)

    def test_ordered_by_id(self):
        vertices = load_vertices(REAL_DB)
        ids = [v.id for v in vertices]
        assert ids == sorted(ids)


class TestLoadVerticesErrors:
    """Tests for error handling."""

    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Database not found"):
            load_vertices(tmp_path / "nonexistent.db")

    def test_db_without_vertices_table_raises_value_error(self, tmp_path):
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE other (id INTEGER)")
        conn.commit()
        conn.close()

        with pytest.raises(ValueError, match="does not contain a 'vertices' table"):
            load_vertices(db_path)

    def test_empty_vertices_table_returns_empty_list(self, tmp_path):
        db_path = tmp_path / "empty_vertices.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE vertices (id INTEGER PRIMARY KEY, element_id INTEGER, "
            "x REAL, y REAL, z REAL, vertex_index INTEGER)"
        )
        conn.commit()
        conn.close()

        vertices = load_vertices(db_path)
        assert vertices == []
