"""Tests for the V2 pipeline integration (Phase 6)."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from structure_aligner.main import cli
from structure_aligner.config import PipelineConfig
from structure_aligner.pipeline_v2 import PipelineV2Report, run_pipeline_v2


BEFORE_3DM = Path("data/input/before.3dm")
STRUCT_DB = Path("data/input/geometrie_2.db")
PRD_DB = Path("data/input/geometrie_2_prd.db")
AFTER_3DM = Path("data/input/after.3dm")


# =========================================================================
# CLI tests
# =========================================================================


class TestCLIHelp:
    """Test CLI help output."""

    def test_pipeline_v2_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["pipeline-v2", "--help"])
        assert result.exit_code == 0
        assert "pipeline-v2" in result.output or "V2 Pipeline" in result.output
        assert "--input-3dm" in result.output
        assert "--input-db" in result.output
        assert "--output" in result.output

    def test_pipeline_v2_options_present(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["pipeline-v2", "--help"])
        assert "--max-snap-distance" in result.output
        assert "--min-floors" in result.output
        assert "--reference-3dm" in result.output
        assert "--log-level" in result.output

    def test_pipeline_v2_missing_required(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["pipeline-v2"])
        assert result.exit_code != 0
        assert "Missing" in result.output or "required" in result.output.lower()


# =========================================================================
# Report dataclass tests
# =========================================================================


class TestPipelineV2Report:
    """Test report dataclass."""

    def test_default_values(self):
        report = PipelineV2Report()
        assert report.total_vertices == 0
        assert report.aligned_vertices == 0
        assert report.errors == []
        assert report.dalles_removed == 0

    def test_serializable(self):
        from dataclasses import asdict
        report = PipelineV2Report(
            input_3dm="test.3dm",
            total_vertices=100,
            aligned_vertices=95,
        )
        data = asdict(report)
        json_str = json.dumps(data)
        assert "test.3dm" in json_str
        assert "100" in json_str


# =========================================================================
# Pipeline function tests (unit-level)
# =========================================================================


class TestPipelineV2Function:
    """Test run_pipeline_v2 with missing inputs."""

    def test_missing_3dm(self, tmp_path):
        """Should return error for non-existent 3dm."""
        report = run_pipeline_v2(
            input_3dm=tmp_path / "nonexistent.3dm",
            input_db=tmp_path / "nonexistent.db",
            output_dir=tmp_path / "output",
        )
        assert len(report.errors) > 0


# =========================================================================
# Integration tests with real data
# =========================================================================


@pytest.mark.skipif(
    not BEFORE_3DM.exists() or not STRUCT_DB.exists() or not PRD_DB.exists(),
    reason="Real data files not available",
)
class TestPipelineV2RealData:
    """Full pipeline integration tests on real data."""

    def test_end_to_end(self, tmp_path):
        """Run complete pipeline and verify outputs."""
        config = PipelineConfig()
        report = run_pipeline_v2(
            input_3dm=BEFORE_3DM,
            input_db=STRUCT_DB,
            output_dir=tmp_path,
            config=config,
        )

        # No errors
        assert report.errors == [], f"Pipeline errors: {report.errors}"

        # Output files exist
        assert Path(report.output_3dm).exists()
        report_path = tmp_path / "pipeline_v2_report.json"
        assert report_path.exists()

        # Axis lines discovered
        assert report.axis_lines_x_count > 100
        assert report.axis_lines_y_count > 100

        # Alignment rate > 50%
        assert report.alignment_rate_pct > 50.0

        # Object removal counts
        assert report.dalles_removed >= 200
        assert report.supports_removed == 7
        assert report.voiles_removed >= 40

        # Object addition counts
        assert report.dalles_consolidated >= 10
        assert report.supports_added > 0
        assert report.grid_lines_added > 0

        # Final model has objects
        assert report.final_object_count > 0

    def test_report_json_valid(self, tmp_path):
        """Report JSON should be valid and complete."""
        config = PipelineConfig()
        run_pipeline_v2(
            input_3dm=BEFORE_3DM,
            input_db=STRUCT_DB,
            output_dir=tmp_path,
            config=config,
        )

        report_path = tmp_path / "pipeline_v2_report.json"
        with open(report_path) as f:
            data = json.load(f)

        assert "axis_lines_x_count" in data
        assert "aligned_vertices" in data
        assert "dalles_removed" in data
        assert "execution_time_s" in data
        assert data["execution_time_s"] > 0

    def test_output_3dm_readable(self, tmp_path):
        """Output 3dm should be readable by rhino3dm."""
        import rhino3dm

        config = PipelineConfig()
        report = run_pipeline_v2(
            input_3dm=BEFORE_3DM,
            input_db=STRUCT_DB,
            output_dir=tmp_path,
            config=config,
        )

        model = rhino3dm.File3dm.Read(report.output_3dm)
        assert model is not None
        assert len(model.Objects) > 0

    def test_z_coordinates_unchanged(self, tmp_path):
        """Z coordinates must not be modified in alignment."""
        config = PipelineConfig()
        report = run_pipeline_v2(
            input_3dm=BEFORE_3DM,
            input_db=STRUCT_DB,
            output_dir=tmp_path,
            config=config,
        )

        # Verify via the aligned vertices (loaded during pipeline)
        from structure_aligner.db.reader import load_vertices_with_elements
        from structure_aligner.analysis.axis_selector import discover_axis_lines
        from structure_aligner.alignment.element_aligner import align_elements

        vertices, elements = load_vertices_with_elements(PRD_DB)
        axis_x, axis_y = discover_axis_lines(vertices, config)
        aligned = align_elements(vertices, elements, axis_x, axis_y, config)

        originals = {v.id: v for v in vertices}
        for av in aligned:
            assert av.z == originals[av.id].z, (
                f"Z changed for vertex {av.id}: {originals[av.id].z} -> {av.z}"
            )


@pytest.mark.skipif(
    not BEFORE_3DM.exists() or not STRUCT_DB.exists() or not PRD_DB.exists(),
    reason="Real data files not available",
)
class TestCLIIntegration:
    """CLI integration tests with real data."""

    def test_cli_runs_successfully(self, tmp_path):
        """CLI pipeline-v2 should run without errors."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "pipeline-v2",
            "--input-3dm", str(BEFORE_3DM),
            "--input-db", str(STRUCT_DB),
            "--output", str(tmp_path),
            "--log-level", "WARNING",
        ])
        assert result.exit_code == 0, (
            f"CLI failed with exit code {result.exit_code}:\n{result.output}"
        )
