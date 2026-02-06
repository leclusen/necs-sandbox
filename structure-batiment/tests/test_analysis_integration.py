import logging
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from structure_aligner.config import AlignmentConfig
from structure_aligner.alignment.thread_detector import detect_threads
from structure_aligner.analysis.statistics import compute_axis_statistics

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "geometrie_2_prd.db"


@pytest.fixture
def vertex_data():
    """Load all vertex coordinates from the production database."""
    if not DB_PATH.exists():
        pytest.skip(f"Test database not found: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cursor = conn.execute("SELECT x, y, z FROM vertices")
        rows = cursor.fetchall()
    finally:
        conn.close()
    assert len(rows) > 0, "No vertices found in database"
    data = np.array(rows)
    return {
        "X": data[:, 0],
        "Y": data[:, 1],
        "Z": data[:, 2],
    }


class TestAnalysisIntegration:
    def test_threads_detected_on_all_axes(self, vertex_data):
        """Each axis should produce at least one thread."""
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        for axis in ("X", "Y", "Z"):
            threads = detect_threads(vertex_data[axis], axis, config)
            logger.info("Axis %s: %d threads detected", axis, len(threads))
            assert len(threads) > 0, f"No threads detected on axis {axis}"

    def test_no_thread_delta_exceeds_alpha(self, vertex_data):
        """Every thread's delta must be <= alpha."""
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        for axis in ("X", "Y", "Z"):
            threads = detect_threads(vertex_data[axis], axis, config)
            for t in threads:
                assert t.delta <= config.alpha, (
                    f"Thread {t.fil_id} delta={t.delta:.6f} exceeds alpha={config.alpha}"
                )

    def test_statistics_computed(self, vertex_data):
        """Statistics should be computable for each axis."""
        for axis in ("X", "Y", "Z"):
            stats = compute_axis_statistics(vertex_data[axis], axis)
            assert stats.total_count > 0
            assert stats.std >= 0
            assert stats.min <= stats.max
            logger.info(
                "Axis %s stats: mean=%.4f, std=%.4f, min=%.4f, max=%.4f, unique=%d, total=%d",
                axis, stats.mean, stats.std, stats.min, stats.max,
                stats.unique_count, stats.total_count,
            )

    def test_z_axis_threads_for_floor_levels(self, vertex_data):
        """Z axis should detect multiple threads corresponding to floor levels."""
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        threads = detect_threads(vertex_data["Z"], "Z", config)
        # Building should have multiple floor levels
        assert len(threads) >= 2, (
            f"Expected multiple Z threads for floor levels, got {len(threads)}"
        )
        logger.info("Z axis threads (floor levels):")
        for t in threads:
            logger.info("  %s: ref=%.4fm, delta=%.4fm, count=%d",
                       t.fil_id, t.reference, t.delta, t.vertex_count)

    def test_thread_references_are_sorted(self, vertex_data):
        """Thread references should be in ascending order."""
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        for axis in ("X", "Y", "Z"):
            threads = detect_threads(vertex_data[axis], axis, config)
            refs = [t.reference for t in threads]
            assert refs == sorted(refs), f"Threads on axis {axis} are not sorted"
