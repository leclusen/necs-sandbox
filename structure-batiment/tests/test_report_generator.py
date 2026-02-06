import json
import math
from pathlib import Path

from structure_aligner.config import (
    AlignmentConfig,
    AlignmentResult,
    AlignedVertex,
    AxisStatistics,
    Thread,
)
from structure_aligner.output.report_generator import generate_report
from structure_aligner.output.validator import ValidationCheck, ValidationResult


def _make_vertex(
    id=1, element_id=1, x=0.0, y=0.0, z=0.0, vertex_index=0,
    x_original=0.0, y_original=0.0, z_original=0.0,
    aligned_axis="X", fil_x_id="X_001", fil_y_id=None, fil_z_id=None,
    displacement_total=0.0,
):
    return AlignedVertex(
        id=id, element_id=element_id, x=x, y=y, z=z,
        vertex_index=vertex_index,
        x_original=x_original, y_original=y_original, z_original=z_original,
        aligned_axis=aligned_axis,
        fil_x_id=fil_x_id, fil_y_id=fil_y_id, fil_z_id=fil_z_id,
        displacement_total=displacement_total,
    )


def _make_result(vertices=None, threads=None, statistics=None, config=None):
    if config is None:
        config = AlignmentConfig(alpha=0.05)
    if vertices is None:
        vertices = [
            _make_vertex(id=1, x=1.0, x_original=1.02, displacement_total=0.02),
            _make_vertex(id=2, x=2.0, x_original=2.01, displacement_total=0.01),
        ]
    if threads is None:
        threads = [
            Thread(fil_id="X_001", axis="X", reference=1.0, delta=0.01,
                   vertex_count=5, range_min=0.95, range_max=1.05),
            Thread(fil_id="Y_001", axis="Y", reference=2.0, delta=0.02,
                   vertex_count=3, range_min=1.95, range_max=2.05),
            Thread(fil_id="Z_001", axis="Z", reference=3.0, delta=0.005,
                   vertex_count=10, range_min=2.95, range_max=3.05),
        ]
    if statistics is None:
        statistics = [
            AxisStatistics(axis="X", mean=1.0, median=1.0, std=0.01,
                           min=0.5, max=1.5, q1=0.8, q3=1.2,
                           unique_count=100, total_count=500),
            AxisStatistics(axis="Y", mean=2.0, median=2.0, std=0.02,
                           min=1.5, max=2.5, q1=1.8, q3=2.2,
                           unique_count=120, total_count=500),
            AxisStatistics(axis="Z", mean=3.0, median=3.0, std=0.005,
                           min=2.5, max=3.5, q1=2.8, q3=3.2,
                           unique_count=13, total_count=500),
        ]
    return AlignmentResult(
        threads=threads, aligned_vertices=vertices,
        statistics=statistics, config=config,
    )


def _make_validation(passed=True):
    return ValidationResult(
        passed=passed,
        checks=[
            ValidationCheck("max_per_axis_displacement", "PASS", "OK"),
            ValidationCheck("no_null_coordinates", "PASS", "0 NULL"),
            ValidationCheck("vertex_count_preserved", "PASS", "Count OK"),
            ValidationCheck("alignment_rate", "PASS", "100%"),
        ],
    )


class TestGenerateReport:
    """Tests for generate_report."""

    def test_produces_valid_json(self, tmp_path):
        """Report file should contain valid JSON."""
        report_path = tmp_path / "report.json"
        generate_report(
            result=_make_result(),
            validation=_make_validation(),
            input_db=Path("input.db"),
            output_db=Path("output.db"),
            execution_time_seconds=1.23,
            report_path=report_path,
        )
        data = json.loads(report_path.read_text())
        assert isinstance(data, dict)

    def test_all_prd_f10_fields_present(self, tmp_path):
        """All PRD F-10 top-level fields must be present."""
        report_path = tmp_path / "report.json"
        generate_report(
            result=_make_result(),
            validation=_make_validation(),
            input_db=Path("input.db"),
            output_db=Path("output.db"),
            execution_time_seconds=1.0,
            report_path=report_path,
        )
        data = json.loads(report_path.read_text())
        required_keys = [
            "metadata", "parameters", "statistics", "axis_statistics",
            "threads_detected", "displacement_statistics",
            "isolated_vertices", "isolated_vertices_total", "validation",
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_metadata_fields(self, tmp_path):
        """Metadata should contain required sub-fields."""
        report_path = tmp_path / "report.json"
        generate_report(
            result=_make_result(),
            validation=_make_validation(),
            input_db=Path("input.db"),
            output_db=Path("output.db"),
            execution_time_seconds=5.67,
            report_path=report_path,
        )
        data = json.loads(report_path.read_text())
        meta = data["metadata"]
        assert "timestamp" in meta
        assert "T" in meta["timestamp"]  # ISO 8601 format
        assert meta["execution_time_seconds"] == 5.67
        assert meta["software_version"] == "0.1.0"
        assert meta["dry_run"] is False
        assert meta["input_database"] == "input.db"
        assert meta["output_database"] == "output.db"

    def test_dry_run_mode(self, tmp_path):
        """Dry-run: output_db=None -> dry_run=True, output_database=None."""
        report_path = tmp_path / "report.json"
        generate_report(
            result=_make_result(),
            validation=_make_validation(),
            input_db=Path("input.db"),
            output_db=None,
            execution_time_seconds=1.0,
            report_path=report_path,
        )
        data = json.loads(report_path.read_text())
        assert data["metadata"]["dry_run"] is True
        assert data["metadata"]["output_database"] is None

    def test_thread_grouping_by_axis(self, tmp_path):
        """Threads should be grouped into X, Y, Z arrays."""
        report_path = tmp_path / "report.json"
        generate_report(
            result=_make_result(),
            validation=_make_validation(),
            input_db=Path("input.db"),
            output_db=Path("output.db"),
            execution_time_seconds=1.0,
            report_path=report_path,
        )
        data = json.loads(report_path.read_text())
        threads = data["threads_detected"]
        assert "X" in threads and "Y" in threads and "Z" in threads
        assert len(threads["X"]) == 1
        assert len(threads["Y"]) == 1
        assert len(threads["Z"]) == 1
        assert threads["X"][0]["fil_id"] == "X_001"

    def test_displacement_statistics(self, tmp_path):
        """Displacement stats should be computed correctly."""
        vertices = [
            _make_vertex(id=1, displacement_total=0.02),
            _make_vertex(id=2, displacement_total=0.04),
        ]
        report_path = tmp_path / "report.json"
        generate_report(
            result=_make_result(vertices=vertices),
            validation=_make_validation(),
            input_db=Path("input.db"),
            output_db=Path("output.db"),
            execution_time_seconds=1.0,
            report_path=report_path,
        )
        data = json.loads(report_path.read_text())
        disp = data["displacement_statistics"]
        assert disp["mean_meters"] == 0.03
        assert disp["max_meters"] == 0.04
        assert "note" in disp

    def test_displacement_note_field(self, tmp_path):
        """displacement_statistics must include note about 3D vs per-axis."""
        report_path = tmp_path / "report.json"
        generate_report(
            result=_make_result(),
            validation=_make_validation(),
            input_db=Path("input.db"),
            output_db=Path("output.db"),
            execution_time_seconds=1.0,
            report_path=report_path,
        )
        data = json.loads(report_path.read_text())
        note = data["displacement_statistics"]["note"]
        assert "per-axis" in note.lower() or "Per-axis" in note

    def test_isolated_vertices_capped_at_100(self, tmp_path):
        """isolated_vertices array should be capped at 100 entries."""
        # Create 150 isolated vertices
        vertices = [
            _make_vertex(id=i, aligned_axis="none", fil_x_id=None,
                         displacement_total=0.0)
            for i in range(150)
        ]
        report_path = tmp_path / "report.json"
        generate_report(
            result=_make_result(vertices=vertices),
            validation=_make_validation(),
            input_db=Path("input.db"),
            output_db=Path("output.db"),
            execution_time_seconds=1.0,
            report_path=report_path,
        )
        data = json.loads(report_path.read_text())
        assert len(data["isolated_vertices"]) == 100
        assert data["isolated_vertices_total"] == 150

    def test_validation_section(self, tmp_path):
        """Validation section should mirror the ValidationResult."""
        report_path = tmp_path / "report.json"
        validation = _make_validation(passed=False)
        validation.checks.append(
            ValidationCheck("test_check", "FAIL", "something failed")
        )
        generate_report(
            result=_make_result(),
            validation=validation,
            input_db=Path("input.db"),
            output_db=Path("output.db"),
            execution_time_seconds=1.0,
            report_path=report_path,
        )
        data = json.loads(report_path.read_text())
        assert data["validation"]["passed"] is False
        check_names = [c["name"] for c in data["validation"]["checks"]]
        assert "test_check" in check_names

    def test_axis_statistics_present(self, tmp_path):
        """axis_statistics should have entries for each axis."""
        report_path = tmp_path / "report.json"
        generate_report(
            result=_make_result(),
            validation=_make_validation(),
            input_db=Path("input.db"),
            output_db=Path("output.db"),
            execution_time_seconds=1.0,
            report_path=report_path,
        )
        data = json.loads(report_path.read_text())
        for axis in ("X", "Y", "Z"):
            assert axis in data["axis_statistics"]
            stat = data["axis_statistics"][axis]
            for key in ("mean", "median", "std", "min", "max", "q1", "q3", "unique_count"):
                assert key in stat, f"Missing {key} in axis_statistics[{axis}]"

    def test_report_creates_parent_directories(self, tmp_path):
        """Report should create parent directories if they don't exist."""
        report_path = tmp_path / "subdir" / "deep" / "report.json"
        result_path = generate_report(
            result=_make_result(),
            validation=_make_validation(),
            input_db=Path("input.db"),
            output_db=Path("output.db"),
            execution_time_seconds=1.0,
            report_path=report_path,
        )
        assert result_path.exists()
        assert json.loads(result_path.read_text()) is not None
