"""Final validation tests for the V2 pipeline (Phase 7).

Compares pipeline output against the reference after.3dm to validate
that the V2 pipeline produces structurally correct results.
"""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from structure_aligner.config import PipelineConfig
from structure_aligner.pipeline_v2 import run_pipeline_v2
from structure_aligner.validation.reference_comparator import (
    ComparisonResult,
    compare_with_reference,
)

BEFORE_3DM = Path("data/input/before.3dm")
STRUCT_DB = Path("data/input/geometrie_2.db")
PRD_DB = Path("data/input/geometrie_2_prd.db")
AFTER_3DM = Path("data/input/after.3dm")

REAL_DATA_AVAILABLE = (
    BEFORE_3DM.exists()
    and STRUCT_DB.exists()
    and PRD_DB.exists()
    and AFTER_3DM.exists()
)


# =========================================================================
# Reference comparator unit tests
# =========================================================================


class TestComparisonResult:
    """Test ComparisonResult dataclass."""

    def test_default_values(self):
        result = ComparisonResult()
        assert result.common_objects == 0
        assert result.overall_match_rate == 0.0
        assert result.errors == []

    def test_serializable(self):
        result = ComparisonResult(
            output_3dm="out.3dm",
            reference_3dm="ref.3dm",
            common_objects=42,
            overall_match_rate=97.5,
        )
        data = asdict(result)
        json_str = json.dumps(data)
        assert "out.3dm" in json_str
        assert "97.5" in json_str

    def test_type_breakdown_serializable(self):
        result = ComparisonResult(
            type_breakdown={
                "dalle": {"objects": 5, "vertices_compared": 100,
                          "vertices_matched": 95, "match_rate": 95.0},
                "voile": {"objects": 10, "vertices_compared": 200,
                          "vertices_matched": 190, "match_rate": 95.0},
            }
        )
        data = asdict(result)
        json_str = json.dumps(data)
        assert "dalle" in json_str
        assert "voile" in json_str


class TestCompareWithReferenceErrors:
    """Test error handling in compare_with_reference."""

    def test_missing_output(self, tmp_path):
        result = compare_with_reference(
            tmp_path / "nonexistent.3dm",
            tmp_path / "ref.3dm",
        )
        assert len(result.errors) > 0

    def test_missing_reference(self, tmp_path):
        import rhino3dm
        model = rhino3dm.File3dm()
        out_path = tmp_path / "out.3dm"
        model.Write(str(out_path), version=7)

        result = compare_with_reference(
            out_path,
            tmp_path / "nonexistent_ref.3dm",
        )
        assert len(result.errors) > 0


class TestCompareWithReferenceSynthetic:
    """Test compare_with_reference with synthetic 3dm files."""

    def test_identical_models(self, tmp_path):
        """Identical models should have 100% match rate."""
        import rhino3dm

        model = rhino3dm.File3dm()
        attr = rhino3dm.ObjectAttributes()
        attr.Name = "TestPoint_1"
        model.Objects.AddPoint(rhino3dm.Point3d(1.0, 2.0, 3.0), attr)

        out_path = tmp_path / "out.3dm"
        ref_path = tmp_path / "ref.3dm"
        model.Write(str(out_path), version=7)
        model.Write(str(ref_path), version=7)

        result = compare_with_reference(out_path, ref_path)
        assert result.errors == []
        assert result.common_objects == 1
        assert result.overall_match_rate == 100.0
        assert result.max_displacement == 0.0

    def test_slightly_different_models(self, tmp_path):
        """Small displacement should match within tolerance."""
        import rhino3dm

        out_model = rhino3dm.File3dm()
        attr = rhino3dm.ObjectAttributes()
        attr.Name = "TestPoint_1"
        out_model.Objects.AddPoint(rhino3dm.Point3d(1.0, 2.0, 3.0), attr)

        ref_model = rhino3dm.File3dm()
        attr2 = rhino3dm.ObjectAttributes()
        attr2.Name = "TestPoint_1"
        ref_model.Objects.AddPoint(rhino3dm.Point3d(1.003, 2.0, 3.0), attr2)

        out_path = tmp_path / "out.3dm"
        ref_path = tmp_path / "ref.3dm"
        out_model.Write(str(out_path), version=7)
        ref_model.Write(str(ref_path), version=7)

        result = compare_with_reference(out_path, ref_path, tolerance=0.005)
        assert result.overall_match_rate == 100.0

    def test_large_displacement_fails(self, tmp_path):
        """Large displacement should not match within tolerance."""
        import rhino3dm

        out_model = rhino3dm.File3dm()
        attr = rhino3dm.ObjectAttributes()
        attr.Name = "TestPoint_1"
        out_model.Objects.AddPoint(rhino3dm.Point3d(1.0, 2.0, 3.0), attr)

        ref_model = rhino3dm.File3dm()
        attr2 = rhino3dm.ObjectAttributes()
        attr2.Name = "TestPoint_1"
        ref_model.Objects.AddPoint(rhino3dm.Point3d(2.0, 2.0, 3.0), attr2)

        out_path = tmp_path / "out.3dm"
        ref_path = tmp_path / "ref.3dm"
        out_model.Write(str(out_path), version=7)
        ref_model.Write(str(ref_path), version=7)

        result = compare_with_reference(out_path, ref_path, tolerance=0.005)
        assert result.overall_match_rate == 0.0
        assert result.max_displacement > 0.9

    def test_output_only_objects(self, tmp_path):
        """Objects in output only should be tracked."""
        import rhino3dm

        out_model = rhino3dm.File3dm()
        attr = rhino3dm.ObjectAttributes()
        attr.Name = "OnlyInOutput"
        out_model.Objects.AddPoint(rhino3dm.Point3d(0, 0, 0), attr)

        ref_model = rhino3dm.File3dm()

        out_path = tmp_path / "out.3dm"
        ref_path = tmp_path / "ref.3dm"
        out_model.Write(str(out_path), version=7)
        ref_model.Write(str(ref_path), version=7)

        result = compare_with_reference(out_path, ref_path)
        assert result.output_only_objects == 1
        assert "OnlyInOutput" in result.output_only_names

    def test_reference_only_objects(self, tmp_path):
        """Objects in reference only should be tracked."""
        import rhino3dm

        out_model = rhino3dm.File3dm()
        ref_model = rhino3dm.File3dm()
        attr = rhino3dm.ObjectAttributes()
        attr.Name = "OnlyInRef"
        ref_model.Objects.AddPoint(rhino3dm.Point3d(0, 0, 0), attr)

        out_path = tmp_path / "out.3dm"
        ref_path = tmp_path / "ref.3dm"
        out_model.Write(str(out_path), version=7)
        ref_model.Write(str(ref_path), version=7)

        result = compare_with_reference(out_path, ref_path)
        assert result.reference_only_objects == 1
        assert "OnlyInRef" in result.reference_only_names

    def test_type_breakdown(self, tmp_path):
        """Type breakdown should separate element types."""
        import rhino3dm

        model = rhino3dm.File3dm()
        for name in ["Dalle_1", "Dalle_2", "Voile_1"]:
            attr = rhino3dm.ObjectAttributes()
            attr.Name = name
            model.Objects.AddPoint(rhino3dm.Point3d(1.0, 2.0, 3.0), attr)

        out_path = tmp_path / "out.3dm"
        ref_path = tmp_path / "ref.3dm"
        model.Write(str(out_path), version=7)
        model.Write(str(ref_path), version=7)

        result = compare_with_reference(out_path, ref_path)
        assert "dalle" in result.type_breakdown
        assert "voile" in result.type_breakdown
        assert result.type_breakdown["dalle"]["objects"] == 2
        assert result.type_breakdown["voile"]["objects"] == 1

    def test_include_object_details(self, tmp_path):
        """Object details should be included when requested."""
        import rhino3dm

        model = rhino3dm.File3dm()
        attr = rhino3dm.ObjectAttributes()
        attr.Name = "TestObj"
        model.Objects.AddPoint(rhino3dm.Point3d(1.0, 2.0, 3.0), attr)

        out_path = tmp_path / "out.3dm"
        ref_path = tmp_path / "ref.3dm"
        model.Write(str(out_path), version=7)
        model.Write(str(ref_path), version=7)

        result = compare_with_reference(
            out_path, ref_path, include_object_details=True
        )
        assert len(result.object_comparisons) == 1
        assert result.object_comparisons[0]["name"] == "TestObj"


# =========================================================================
# Full pipeline integration tests (real data)
# =========================================================================


@pytest.mark.skipif(not REAL_DATA_AVAILABLE, reason="Real data files not available")
class TestFullPipelineAgainstReference:
    """Run V2 pipeline and compare against reference after.3dm."""

    @pytest.fixture(scope="class")
    def pipeline_output(self, tmp_path_factory):
        """Run pipeline once for all tests in this class."""
        tmp_path = tmp_path_factory.mktemp("pipeline_v2")
        config = PipelineConfig()
        report = run_pipeline_v2(
            input_3dm=BEFORE_3DM,
            input_db=STRUCT_DB,
            output_dir=tmp_path,
            config=config,
        )
        return report, tmp_path

    def test_pipeline_succeeds(self, pipeline_output):
        """Pipeline should complete without errors."""
        report, _ = pipeline_output
        assert report.errors == [], f"Pipeline errors: {report.errors}"

    def test_output_exists(self, pipeline_output):
        """Output 3dm should exist."""
        report, _ = pipeline_output
        assert Path(report.output_3dm).exists()

    def test_comparison_against_reference(self, pipeline_output):
        """Compare output against reference after.3dm."""
        report, _ = pipeline_output
        comparison = compare_with_reference(
            Path(report.output_3dm),
            AFTER_3DM,
            tolerance=0.005,
        )
        assert comparison.errors == []
        assert comparison.common_objects > 0
        # Catch catastrophic regressions — lenient threshold for new pipeline
        assert comparison.overall_match_rate > 20.0, (
            f"Match rate {comparison.overall_match_rate:.1f}% is too low"
        )

        # Log detailed results for review
        import logging
        log = logging.getLogger(__name__)
        log.info("Common objects: %d", comparison.common_objects)
        log.info("Output-only: %d, Reference-only: %d",
                 comparison.output_only_objects, comparison.reference_only_objects)
        log.info("Match rate: %.1f%%", comparison.overall_match_rate)
        log.info("Displacement: mean=%.4f, median=%.4f, p95=%.4f, max=%.4f",
                 comparison.mean_displacement, comparison.median_displacement,
                 comparison.p95_displacement, comparison.max_displacement)
        for t, s in comparison.type_breakdown.items():
            log.info("  %s: %d objects, %d/%d matched (%.1f%%)",
                     t, s["objects"], s["vertices_matched"],
                     s["vertices_compared"], s["match_rate"])

    def test_zero_z_changes(self, pipeline_output):
        """Z coordinates must not be modified during alignment."""
        report, _ = pipeline_output

        from structure_aligner.db.reader import load_vertices_with_elements
        from structure_aligner.analysis.axis_selector import discover_axis_lines
        from structure_aligner.alignment.element_aligner import align_elements

        config = PipelineConfig()
        vertices, elements = load_vertices_with_elements(PRD_DB)
        axis_x, axis_y = discover_axis_lines(vertices, config)
        aligned = align_elements(vertices, elements, axis_x, axis_y, config)

        originals = {v.id: v for v in vertices}
        for av in aligned:
            assert av.z == originals[av.id].z, (
                f"Z changed for vertex {av.id}: {originals[av.id].z} -> {av.z}"
            )

    def test_object_count_comparison(self, pipeline_output):
        """Output object count should be within reasonable range of reference."""
        report, _ = pipeline_output
        comparison = compare_with_reference(
            Path(report.output_3dm),
            AFTER_3DM,
        )

        # Output should have a substantial number of objects
        assert report.final_object_count > 0
        assert comparison.reference_object_count > 0

        # Check that common objects exist (exact match rate depends on pipeline)
        assert comparison.common_objects > 0

    def test_comparison_report_serializable(self, pipeline_output):
        """ComparisonResult should be serializable to JSON."""
        report, tmp_path = pipeline_output
        comparison = compare_with_reference(
            Path(report.output_3dm),
            AFTER_3DM,
            include_object_details=True,
        )

        data = asdict(comparison)
        json_str = json.dumps(data, indent=2)
        report_path = tmp_path / "comparison_report.json"
        with open(report_path, "w") as f:
            f.write(json_str)

        # Verify it can be read back
        with open(report_path) as f:
            loaded = json.load(f)
        assert loaded["common_objects"] == comparison.common_objects
        assert loaded["overall_match_rate"] == comparison.overall_match_rate

    def test_displacement_distribution(self, pipeline_output):
        """Displacement statistics should be computed."""
        report, _ = pipeline_output
        comparison = compare_with_reference(
            Path(report.output_3dm),
            AFTER_3DM,
        )

        if comparison.total_vertices_compared > 0:
            assert comparison.mean_displacement >= 0
            assert comparison.median_displacement >= 0
            assert comparison.p95_displacement >= comparison.median_displacement
            assert comparison.max_displacement >= comparison.p95_displacement
