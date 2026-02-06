from pathlib import Path
import json
import sqlite3
import pytest
from structure_aligner.etl.extractor import extract_vertices
from structure_aligner.etl.transformer import transform
from structure_aligner.etl.loader import load

DATA_DIR = Path(__file__).parent.parent / "data"
DM_FILE = DATA_DIR / "geometrie_2.3dm"
DB_FILE = DATA_DIR / "geometrie_2.db"


@pytest.mark.skipif(not (DM_FILE.exists() and DB_FILE.exists()), reason="Test data not available")
class TestLoader:

    @pytest.fixture(scope="class")
    def etl_result(self, tmp_path_factory):
        """Run full ETL pipeline once for all tests in this class."""
        tmp = tmp_path_factory.mktemp("loader")
        output_path = tmp / "output.db"

        extraction = extract_vertices(DM_FILE)
        result = transform(extraction, DB_FILE)
        report = load(result, DB_FILE, output_path)

        return output_path, report

    def test_output_file_created(self, etl_result):
        output_path, _ = etl_result
        assert output_path.exists()

    def test_elements_count(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        count = conn.execute("SELECT COUNT(*) FROM elements").fetchone()[0]
        conn.close()
        assert count == 5825

    def test_vertices_count(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        count = conn.execute("SELECT COUNT(*) FROM vertices").fetchone()[0]
        conn.close()
        assert count == 20994

    def test_original_tables_preserved(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        # Original tables still present
        assert "filaire" in tables
        assert "shell" in tables
        assert "support" in tables
        assert "material" in tables
        # New tables added
        assert "elements" in tables
        assert "vertices" in tables

    def test_element_types(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        types = {row[0] for row in conn.execute("SELECT DISTINCT type FROM elements").fetchall()}
        conn.close()
        assert types == {"poteau", "poutre", "voile", "dalle", "appui"}

    def test_no_null_vertices(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        count = conn.execute("SELECT COUNT(*) FROM vertices WHERE x IS NULL OR y IS NULL OR z IS NULL").fetchone()[0]
        conn.close()
        assert count == 0

    def test_fk_integrity(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        orphans = conn.execute("""
            SELECT COUNT(*) FROM vertices v
            LEFT JOIN elements e ON v.element_id = e.id
            WHERE e.id IS NULL
        """).fetchone()[0]
        conn.close()
        assert orphans == 0

    def test_validation_passed(self, etl_result):
        _, report = etl_result
        assert report.validation_passed is True

    def test_report_file_created(self, etl_result):
        _, report = etl_result
        assert report.report_path.exists()

    def test_report_is_valid_json(self, etl_result):
        _, report = etl_result
        data = json.loads(report.report_path.read_text())
        assert data["validation"]["passed"] is True
        assert data["statistics"]["elements_total"] == 5825
        assert data["statistics"]["vertices_total"] == 20994

    def test_output_exists_error(self, etl_result):
        output_path, _ = etl_result
        extraction = extract_vertices(DM_FILE)
        result = transform(extraction, DB_FILE)
        with pytest.raises(FileExistsError):
            load(result, DB_FILE, output_path)

    def test_geometry_type_column_populated(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        count = conn.execute("SELECT COUNT(*) FROM elements WHERE geometry_type IS NOT NULL").fetchone()[0]
        conn.close()
        assert count > 0

    def test_report_has_template_fingerprint(self, etl_result):
        _, report = etl_result
        data = json.loads(report.report_path.read_text())
        assert "template_fingerprint" in data
        assert data["template_fingerprint"]["object_count"] == 5825
        assert len(data["template_fingerprint"]["element_names_hash"]) == 64

    def test_indexes_created(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='vertices'"
        ).fetchall()}
        conn.close()
        assert "idx_vertices_element_id" in indexes
        assert "idx_vertices_x" in indexes
        assert "idx_vertices_y" in indexes
        assert "idx_vertices_z" in indexes
