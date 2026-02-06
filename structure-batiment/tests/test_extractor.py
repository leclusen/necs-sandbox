from pathlib import Path
import pytest
from structure_aligner.etl.extractor import extract_vertices

DATA_DIR = Path(__file__).parent.parent / "data"
DM_FILE = DATA_DIR / "geometrie_2.3dm"


@pytest.mark.skipif(not DM_FILE.exists(), reason="Test data not available")
class TestExtractor:

    @pytest.fixture(scope="class")
    def result(self):
        return extract_vertices(DM_FILE)

    def test_extracts_correct_total_objects(self, result):
        assert result.total_objects == 5825

    def test_extracts_correct_total_vertices(self, result):
        assert result.total_vertices == 20996

    def test_all_vertices_have_names(self, result):
        for v in result.vertices:
            assert v.element_name, "Vertex has empty name"

    def test_all_vertices_have_valid_category(self, result):
        valid = {"poteau", "poutre", "voile", "dalle", "appui"}
        for v in result.vertices:
            assert v.category in valid, f"Invalid category: {v.category} for {v.element_name}"

    def test_category_counts(self, result):
        # Count unique element names per category
        elements_by_cat = {}
        for v in result.vertices:
            elements_by_cat.setdefault(v.category, set()).add(v.element_name)
        counts = {cat: len(names) for cat, names in elements_by_cat.items()}
        assert counts["poteau"] == 1527
        assert counts["poutre"] == 1192
        assert counts["voile"] == 2669
        assert counts["dalle"] == 284
        assert counts["appui"] == 153

    def test_coordinate_ranges(self, result):
        xs = [v.x for v in result.vertices]
        zs = [v.z for v in result.vertices]
        assert min(xs) == pytest.approx(-72.1752, abs=0.01)
        assert max(xs) == pytest.approx(46.80, abs=0.01)
        assert min(zs) == pytest.approx(-4.44, abs=0.01)
        assert max(zs) == pytest.approx(37.21, abs=0.01)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            extract_vertices(Path("/nonexistent/file.3dm"))

    def test_no_skipped_objects(self, result):
        assert len(result.skipped_objects) == 0, f"Skipped: {result.skipped_objects[:5]}"

    def test_all_vertices_have_geometry_type(self, result):
        valid_types = {"brep", "line_curve", "polyline_curve", "nurbs_curve", "point"}
        for v in result.vertices:
            assert v.geometry_type in valid_types, f"Invalid geometry_type: {v.geometry_type} for {v.element_name}"

    def test_geometry_type_counts(self, result):
        from collections import Counter
        types = Counter(v.geometry_type for v in result.vertices)
        assert types["brep"] > 0
        assert types["line_curve"] > 0
        assert types["polyline_curve"] > 0
        assert types["nurbs_curve"] > 0
        assert types["point"] > 0
