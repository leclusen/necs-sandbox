from pathlib import Path
import pytest
from structure_aligner.etl.extractor import extract_vertices
from structure_aligner.etl.transformer import transform, _load_db_elements

DATA_DIR = Path(__file__).parent.parent / "data"
DM_FILE = DATA_DIR / "geometrie_2.3dm"
DB_FILE = DATA_DIR / "geometrie_2.db"


@pytest.mark.skipif(not (DM_FILE.exists() and DB_FILE.exists()), reason="Test data not available")
class TestTransformer:

    @pytest.fixture(scope="class")
    def extraction(self):
        return extract_vertices(DM_FILE)

    @pytest.fixture(scope="class")
    def result(self, extraction):
        return transform(extraction, DB_FILE)

    def test_all_db_elements_included(self, result):
        assert len(result.elements) == 5825

    def test_element_types_normalized(self, result):
        types = {e.type for e in result.elements}
        assert types == {"poteau", "poutre", "voile", "dalle", "appui"}

    def test_element_type_counts(self, result):
        from collections import Counter
        counts = Counter(e.type for e in result.elements)
        assert counts["poteau"] == 1527
        assert counts["poutre"] == 1192
        assert counts["voile"] == 2669
        assert counts["dalle"] == 284
        assert counts["appui"] == 153

    def test_matched_count(self, result):
        assert result.matched_count == 5824

    def test_unmatched_count(self, result):
        # 1 in 3dm only + 1 in db only
        assert len(result.unmatched) == 2

    def test_unmatched_names(self, result):
        names = {name for name, _ in result.unmatched}
        assert "Filaire_7415" in names
        assert "Filaire_7416" in names

    def test_vertex_count(self, result):
        # 20996 total minus vertices belonging to Filaire_7415 (2 vertices for a LineCurve)
        assert len(result.vertices) == 20994

    def test_no_null_coordinates(self, result):
        for v in result.vertices:
            assert v.x is not None
            assert v.y is not None
            assert v.z is not None

    def test_all_vertex_element_ids_exist(self, result):
        element_ids = {e.id for e in result.elements}
        for v in result.vertices:
            assert v.element_id in element_ids, f"Orphan vertex: element_id={v.element_id}"

    def test_elements_have_geometry_type(self, result):
        valid_types = {"brep", "line_curve", "polyline_curve", "nurbs_curve", "point"}
        for e in result.elements:
            if e.geometry_type is not None:
                assert e.geometry_type in valid_types

    def test_template_fingerprint(self, result):
        assert result.template_object_count == 5825
        assert len(result.template_names_hash) == 64


class TestLoadDbElements:

    @pytest.mark.skipif(not DB_FILE.exists(), reason="Test data not available")
    def test_loads_correct_count(self):
        elements = _load_db_elements(DB_FILE)
        assert len(elements) == 5825

    @pytest.mark.skipif(not DB_FILE.exists(), reason="Test data not available")
    def test_no_duplicate_ids(self):
        elements = _load_db_elements(DB_FILE)
        ids = [e.id for e in elements]
        assert len(ids) == len(set(ids)), "Duplicate element IDs found"
