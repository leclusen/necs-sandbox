import numpy as np
import pytest
from structure_aligner.config import AlignmentConfig
from structure_aligner.alignment.thread_detector import detect_threads


class TestDetectThreads:
    def test_known_clusters(self):
        """Known well-separated clusters produce correct threads."""
        values = np.array([0.0, 0.01, 0.02,
                           5.0, 5.01, 5.02,
                           10.0, 10.01, 10.02])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        threads = detect_threads(values, "X", config)
        assert len(threads) == 3
        # Sorted by reference
        assert threads[0].reference < threads[1].reference < threads[2].reference
        # Check axis
        for t in threads:
            assert t.axis == "X"

    def test_thread_merge(self):
        """Two threads closer than 2*alpha should merge."""
        # Two clusters at 1.0 and 1.08, with alpha=0.05 -> threshold=0.10
        # Distance = 0.08 < 0.10 -> should merge
        values = np.array([1.0, 1.0, 1.0,
                           1.08, 1.08, 1.08])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        threads = detect_threads(values, "Y", config)
        assert len(threads) == 1
        # Merged reference is weighted average
        assert threads[0].vertex_count == 6

    def test_single_thread(self):
        values = np.array([2.0, 2.01, 2.02, 2.03])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        threads = detect_threads(values, "Z", config)
        assert len(threads) == 1
        assert threads[0].axis == "Z"
        assert threads[0].fil_id == "Z_001"

    def test_isolated_vertices_not_assigned(self):
        """Isolated points should not form threads."""
        values = np.array([0.0, 0.01, 0.02,  # cluster
                           100.0])             # isolated
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        threads = detect_threads(values, "X", config)
        total_in_threads = sum(t.vertex_count for t in threads)
        assert total_in_threads == 3  # Only the cluster, not the isolated point

    def test_range_uses_alpha_not_delta(self):
        """range_min/max should use alpha, not delta."""
        values = np.array([5.0, 5.001, 5.002])  # Very tight cluster, delta << alpha
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        threads = detect_threads(values, "X", config)
        assert len(threads) == 1
        t = threads[0]
        assert t.range_min == pytest.approx(t.reference - config.alpha)
        assert t.range_max == pytest.approx(t.reference + config.alpha)
        # delta should be small (cluster std), NOT alpha
        assert t.delta < config.alpha

    def test_rounding_uses_config(self):
        """Reference should be rounded per config.rounding_ndigits."""
        values = np.array([1.12345, 1.12345, 1.12345])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3, rounding_precision=0.01)
        threads = detect_threads(values, "X", config)
        assert len(threads) == 1
        # rounding_ndigits = 2 -> reference rounded to 2 decimals
        assert threads[0].reference == pytest.approx(1.12)

    def test_fil_id_numbering(self):
        """Thread IDs should be numbered sequentially per axis."""
        values = np.array([0.0, 0.01, 0.02,
                           5.0, 5.01, 5.02,
                           10.0, 10.01, 10.02])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        threads = detect_threads(values, "Z", config)
        assert threads[0].fil_id == "Z_001"
        assert threads[1].fil_id == "Z_002"
        assert threads[2].fil_id == "Z_003"

    def test_delta_capped_at_alpha(self):
        """delta = min(std, alpha), so delta should never exceed alpha."""
        values = np.array([0.0, 0.01, 0.02, 0.03, 0.04])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        threads = detect_threads(values, "X", config)
        for t in threads:
            assert t.delta <= config.alpha

    def test_no_clusters_returns_empty(self):
        """All noise data returns no threads."""
        values = np.array([0.0, 1.0, 2.0, 3.0])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        threads = detect_threads(values, "X", config)
        assert len(threads) == 0
