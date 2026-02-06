"""End-to-end integration tests for the alignment pipeline."""

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from structure_aligner.config import AlignmentConfig, AlignmentResult
from structure_aligner.db.reader import load_vertices
from structure_aligner.analysis.statistics import compute_axis_statistics
from structure_aligner.alignment.thread_detector import detect_threads
from structure_aligner.alignment.processor import align_vertices
from structure_aligner.output.validator import validate_alignment
from structure_aligner.output.report_generator import generate_report
from structure_aligner.db.writer import write_aligned_db
from structure_aligner.main import cli

DATA_DIR = Path(__file__).parent.parent / "data"
INPUT_DB = DATA_DIR / "geometrie_2_prd.db"


def _run_pipeline(alpha, tmp_path, dry_run=False):
    """Helper: run the full alignment pipeline and return results dict."""
    config = AlignmentConfig(alpha=alpha)
    vertices = load_vertices(INPUT_DB)

    xs = np.array([v.x for v in vertices])
    ys = np.array([v.y for v in vertices])
    zs = np.array([v.z for v in vertices])

    stats = [
        compute_axis_statistics(xs, "X"),
        compute_axis_statistics(ys, "Y"),
        compute_axis_statistics(zs, "Z"),
    ]

    threads_x = detect_threads(xs, "X", config)
    threads_y = detect_threads(ys, "Y", config)
    threads_z = detect_threads(zs, "Z", config)

    aligned = align_vertices(vertices, threads_x, threads_y, threads_z, config)
    validation = validate_alignment(aligned, len(vertices), config)

    all_threads = threads_x + threads_y + threads_z
    result = AlignmentResult(
        threads=all_threads,
        aligned_vertices=aligned,
        statistics=stats,
        config=config,
    )

    output_db = None
    if not dry_run:
        output_db = tmp_path / "aligned_output.db"
        write_aligned_db(INPUT_DB, output_db, aligned)

    report_path = tmp_path / "report.json"
    generate_report(result, validation, INPUT_DB, output_db, 0.0, report_path)

    return {
        "vertices": vertices,
        "aligned": aligned,
        "validation": validation,
        "threads_x": threads_x,
        "threads_y": threads_y,
        "threads_z": threads_z,
        "all_threads": all_threads,
        "output_db": output_db,
        "report_path": report_path,
        "config": config,
    }


@pytest.fixture(scope="module")
def pipeline_result(tmp_path_factory):
    """Run the pipeline once and share results across tests in this module."""
    tmp = tmp_path_factory.mktemp("align")
    return _run_pipeline(alpha=0.05, tmp_path=tmp)


class TestFullAlignmentPipeline:
    """test_full_alignment_pipeline: end-to-end with alpha=0.05."""

    def test_output_db_created(self, pipeline_result):
        assert pipeline_result["output_db"].exists()

    def test_vertex_count_preserved(self, pipeline_result):
        aligned = pipeline_result["aligned"]
        assert len(aligned) == 20994

    def test_alignment_rate_cq01(self, pipeline_result):
        aligned = pipeline_result["aligned"]
        aligned_count = sum(1 for v in aligned if v.aligned_axis != "none")
        rate = aligned_count / len(aligned) * 100
        assert rate >= 85, f"CQ-01 failed: alignment rate {rate:.1f}% < 85%"

    def test_max_per_axis_displacement(self, pipeline_result):
        config = pipeline_result["config"]
        for v in pipeline_result["aligned"]:
            if v.fil_x_id:
                assert abs(v.x - v.x_original) <= config.alpha + 1e-9
            if v.fil_y_id:
                assert abs(v.y - v.y_original) <= config.alpha + 1e-9
            if v.fil_z_id:
                assert abs(v.z - v.z_original) <= config.alpha + 1e-9

    def test_validation_passed(self, pipeline_result):
        assert pipeline_result["validation"].passed

    def test_report_has_required_fields(self, pipeline_result):
        report = json.loads(pipeline_result["report_path"].read_text())
        assert "metadata" in report
        assert "parameters" in report
        assert "statistics" in report
        assert "threads_detected" in report
        assert "displacement_statistics" in report
        assert "validation" in report
        assert "axis_statistics" in report

        assert report["metadata"]["input_database"] == str(INPUT_DB)
        assert report["parameters"]["alpha"] == 0.05
        assert report["statistics"]["total_vertices"] == 20994


class TestDryRun:
    """test_dry_run_no_output_db."""

    def test_no_output_db_created(self, tmp_path):
        result = _run_pipeline(alpha=0.05, tmp_path=tmp_path, dry_run=True)
        assert result["output_db"] is None

    def test_report_still_generated(self, tmp_path):
        result = _run_pipeline(alpha=0.05, tmp_path=tmp_path, dry_run=True)
        assert result["report_path"].exists()

    def test_dry_run_flag_in_report(self, tmp_path):
        result = _run_pipeline(alpha=0.05, tmp_path=tmp_path, dry_run=True)
        report = json.loads(result["report_path"].read_text())
        assert report["metadata"]["dry_run"] is True


class TestDifferentAlphaValues:
    """test_different_alpha_values: verify rate increases with alpha."""

    def test_rate_increases_with_alpha(self, tmp_path):
        result_strict = _run_pipeline(alpha=0.01, tmp_path=tmp_path / "strict")
        (tmp_path / "permissive").mkdir()
        result_permissive = _run_pipeline(alpha=0.10, tmp_path=tmp_path / "permissive")

        strict_aligned = sum(1 for v in result_strict["aligned"] if v.aligned_axis != "none")
        permissive_aligned = sum(1 for v in result_permissive["aligned"] if v.aligned_axis != "none")

        strict_rate = strict_aligned / len(result_strict["aligned"]) * 100
        permissive_rate = permissive_aligned / len(result_permissive["aligned"]) * 100

        assert permissive_rate >= strict_rate, (
            f"Expected permissive rate ({permissive_rate:.1f}%) >= strict rate ({strict_rate:.1f}%)"
        )


class TestAxisThreadDetection:
    """test_axis_thread_detection."""

    def test_threads_on_all_axes(self, pipeline_result):
        assert len(pipeline_result["threads_x"]) > 0, "No X threads detected"
        assert len(pipeline_result["threads_y"]) > 0, "No Y threads detected"
        assert len(pipeline_result["threads_z"]) > 0, "No Z threads detected"

    def test_thread_counts_logged(self, pipeline_result, capfd):
        # Just verify we can access thread counts (logging tested elsewhere)
        tx = len(pipeline_result["threads_x"])
        ty = len(pipeline_result["threads_y"])
        tz = len(pipeline_result["threads_z"])
        print(f"Thread counts: X={tx}, Y={ty}, Z={tz}")
        assert tx + ty + tz == len(pipeline_result["all_threads"])


class TestMultiAxisDisplacement:
    """test_multi_axis_displacement."""

    def test_multi_axis_3d_displacement_can_exceed_alpha(self, pipeline_result):
        config = pipeline_result["config"]
        multi_axis = [v for v in pipeline_result["aligned"] if len(v.aligned_axis) >= 2 and v.aligned_axis != "none"]

        found_exceeding = False
        for v in multi_axis:
            if v.displacement_total > config.alpha:
                found_exceeding = True
                # Per-axis must still be <= alpha
                if v.fil_x_id:
                    assert abs(v.x - v.x_original) <= config.alpha + 1e-9
                if v.fil_y_id:
                    assert abs(v.y - v.y_original) <= config.alpha + 1e-9
                if v.fil_z_id:
                    assert abs(v.z - v.z_original) <= config.alpha + 1e-9

        # It's possible but not guaranteed; just log it
        if found_exceeding:
            print("Found multi-axis vertices with 3D displacement > alpha (expected and correct)")
        else:
            print("No multi-axis vertices with 3D displacement > alpha found (also valid)")


class TestCliInvocation:
    """test_cli_invocation: use CliRunner."""

    def test_cli_exit_code_zero(self, tmp_path):
        runner = CliRunner()
        output_db = str(tmp_path / "cli_output.db")
        report_path = str(tmp_path / "cli_report.json")
        result = runner.invoke(cli, [
            "align",
            "--input", str(INPUT_DB),
            "--output", output_db,
            "--report", report_path,
            "--alpha", "0.05",
        ])
        assert result.exit_code == 0, f"CLI failed with: {result.output}\n{result.exception}"

    def test_cli_dry_run(self, tmp_path):
        runner = CliRunner()
        report_path = str(tmp_path / "cli_dry_report.json")
        result = runner.invoke(cli, [
            "align",
            "--input", str(INPUT_DB),
            "--dry-run",
            "--report", report_path,
        ])
        assert result.exit_code == 0, f"CLI failed with: {result.output}\n{result.exception}"
        assert Path(report_path).exists()


class TestOutputDbSchema:
    """test_output_db_schema: verify PRD F-08 columns, elements table, FK constraints."""

    def test_vertices_table_has_f08_columns(self, pipeline_result):
        db_path = pipeline_result["output_db"]
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA table_info(vertices)")
            columns = {row[1] for row in cursor.fetchall()}
            expected = {
                "id", "element_id", "x", "y", "z", "vertex_index",
                "x_original", "y_original", "z_original",
                "aligned_axis", "fil_x_id", "fil_y_id", "fil_z_id",
                "displacement_total",
            }
            missing = expected - columns
            assert not missing, f"Missing columns: {missing}"
        finally:
            conn.close()

    def test_elements_table_preserved(self, pipeline_result):
        db_path = pipeline_result["output_db"]
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='elements'")
            assert cursor.fetchone() is not None, "elements table missing"
        finally:
            conn.close()

    def test_fk_constraints_preserved(self, pipeline_result):
        db_path = pipeline_result["output_db"]
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA foreign_key_list(vertices)")
            fks = cursor.fetchall()
            assert len(fks) > 0, "No FK constraints on vertices table"
            # FK should reference elements table
            fk_tables = {row[2] for row in fks}
            assert "elements" in fk_tables, f"FK does not reference elements: {fk_tables}"
        finally:
            conn.close()

    def test_enrichment_indexes_exist(self, pipeline_result):
        db_path = pipeline_result["output_db"]
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = {row[0] for row in cursor.fetchall()}
            assert "idx_vertices_aligned_axis" in indexes
            assert "idx_vertices_displacement" in indexes
        finally:
            conn.close()
