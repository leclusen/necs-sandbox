from pathlib import Path
import json
import pytest

from structure_aligner.etl.extractor import extract_vertices
from structure_aligner.etl.reverse_reader import read_aligned_elements
from structure_aligner.etl.reverse_writer import write_aligned_3dm

DATA_DIR = Path(__file__).parent.parent / "data"
DM_FILE = DATA_DIR / "geometrie_2.3dm"
PRD_DB = DATA_DIR / "geometrie_2_prd.db"
ALIGNED_DB = sorted(DATA_DIR.glob("*_aligned_*.db"))
ALIGNED_DB = ALIGNED_DB[0] if ALIGNED_DB else None


@pytest.mark.skipif(
    not (DM_FILE.exists() and PRD_DB.exists()),
    reason="Test data not available",
)
class TestReverseETLIntegration:

    @pytest.fixture(scope="class")
    def roundtrip_result(self, tmp_path_factory):
        """Full roundtrip: aligned DB + template .3dm -> aligned .3dm -> re-extract -> compare."""
        tmp = tmp_path_factory.mktemp("reverse_etl")

        # Use aligned DB if available, else PRD DB
        input_db = ALIGNED_DB if ALIGNED_DB and ALIGNED_DB.exists() else PRD_DB

        # Step 1: Read aligned elements
        aligned_elements = read_aligned_elements(input_db)

        # Step 2: Write aligned .3dm
        output_3dm = tmp / "aligned_output.3dm"
        report = write_aligned_3dm(DM_FILE, aligned_elements, output_3dm)

        # Step 3: Re-extract vertices from the output .3dm
        re_extracted = extract_vertices(output_3dm)

        return aligned_elements, report, re_extracted, output_3dm

    def test_output_file_created(self, roundtrip_result):
        _, _, _, output_3dm = roundtrip_result
        assert output_3dm.exists()

    def test_object_count_preserved(self, roundtrip_result):
        _, report, re_extracted, _ = roundtrip_result
        assert re_extracted.total_objects == report.total_objects

    def test_updated_objects_count(self, roundtrip_result):
        _, report, _, _ = roundtrip_result
        # Should update most objects (5824 matched elements out of 5825)
        assert report.updated_objects >= 5800

    def test_re_extracted_coordinates_match(self, roundtrip_result):
        """Re-extracted vertices should match aligned DB within floating-point tolerance."""
        aligned_elements, _, re_extracted, _ = roundtrip_result

        # Build lookup: name -> list of (vertex_index, x, y, z) from re-extraction
        re_by_name: dict[str, list] = {}
        for v in re_extracted.vertices:
            re_by_name.setdefault(v.element_name, []).append(v)

        mismatches = 0
        total_checked = 0
        max_error = 0.0

        for name, element in aligned_elements.items():
            if not element.vertices:
                continue
            re_verts = re_by_name.get(name)
            if re_verts is None:
                continue

            # Sort both by vertex_index
            db_sorted = sorted(element.vertices, key=lambda v: v.vertex_index)
            re_sorted = sorted(re_verts, key=lambda v: v.vertex_index)

            if len(db_sorted) != len(re_sorted):
                continue

            for db_v, re_v in zip(db_sorted, re_sorted):
                total_checked += 1
                error = max(abs(db_v.x - re_v.x), abs(db_v.y - re_v.y), abs(db_v.z - re_v.z))
                max_error = max(max_error, error)
                if error > 1e-4:  # 0.1mm tolerance for .3dm serialization
                    mismatches += 1

        assert total_checked > 20000, f"Only checked {total_checked} vertices"
        assert mismatches == 0, f"{mismatches}/{total_checked} vertices exceed tolerance, max_error={max_error}"

    def test_no_skipped_unsupported(self, roundtrip_result):
        _, report, _, _ = roundtrip_result
        assert len(report.skipped_unsupported) == 0

    def test_report_json_valid(self, roundtrip_result):
        _, report, _, _ = roundtrip_result
        assert report.report_path.exists()
        data = json.loads(report.report_path.read_text())
        assert "statistics" in data
        assert "brep_edge_desync" in data

    def test_vertex_count_per_element_preserved(self, roundtrip_result):
        """Each element should have same number of vertices before and after."""
        aligned_elements, _, re_extracted, _ = roundtrip_result

        re_by_name: dict[str, int] = {}
        for v in re_extracted.vertices:
            re_by_name[v.element_name] = re_by_name.get(v.element_name, 0) + 1

        mismatches = []
        for name, element in aligned_elements.items():
            if not element.vertices:
                continue
            expected = len(element.vertices)
            actual = re_by_name.get(name, 0)
            if expected != actual:
                mismatches.append(f"{name}: expected {expected}, got {actual}")

        assert len(mismatches) == 0, f"Vertex count mismatches:\n" + "\n".join(mismatches[:10])
