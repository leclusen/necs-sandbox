import numpy as np
import pytest
from structure_aligner.config import AlignmentConfig
from structure_aligner.analysis.clustering import cluster_axis


class TestClusterAxis:
    def test_clear_clusters(self):
        """Three well-separated clusters."""
        values = np.array([0.0, 0.01, 0.02, 5.0, 5.01, 5.02, 10.0, 10.01, 10.02])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        clusters = cluster_axis(values, config)
        assert len(clusters) == 3
        means = sorted(c["mean"] for c in clusters)
        assert means[0] == pytest.approx(0.01, abs=0.02)
        assert means[1] == pytest.approx(5.01, abs=0.02)
        assert means[2] == pytest.approx(10.01, abs=0.02)

    def test_all_same_value(self):
        """All identical values form one cluster."""
        values = np.array([3.0, 3.0, 3.0, 3.0, 3.0])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        clusters = cluster_axis(values, config)
        assert len(clusters) == 1
        assert clusters[0]["mean"] == pytest.approx(3.0)
        assert clusters[0]["std"] == pytest.approx(0.0)

    def test_noise_only(self):
        """All isolated points, no clusters formed."""
        values = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        clusters = cluster_axis(values, config)
        assert len(clusters) == 0

    def test_min_cluster_size_threshold(self):
        """Cluster with fewer than min_cluster_size is noise."""
        values = np.array([0.0, 0.01, 5.0, 5.01, 5.02])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        clusters = cluster_axis(values, config)
        # Only the cluster around 5.0 has 3+ points
        assert len(clusters) == 1
        assert clusters[0]["mean"] == pytest.approx(5.01, abs=0.02)

    def test_dbscan_chaining_pruning(self):
        """
        CRITICAL: DBSCAN chains points [0.0, 0.04, 0.08, 0.12] into one cluster
        with eps=0.05 because each consecutive pair is within 0.05.
        But centroid ~ 0.06, and 0.12 is 0.06 from centroid (> alpha=0.05).
        Post-clustering validation should prune the outlier(s).
        """
        values = np.array([0.0, 0.04, 0.08, 0.12])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        clusters = cluster_axis(values, config)
        # After pruning, cluster may have fewer points or be discarded
        for cluster in clusters:
            centroid = cluster["mean"]
            for v in cluster["values"]:
                assert abs(v - centroid) <= config.alpha, (
                    f"Point {v} is {abs(v - centroid):.4f} from centroid {centroid:.4f}, "
                    f"exceeds alpha={config.alpha}"
                )

    def test_chaining_cluster_discarded_if_too_small(self):
        """
        If pruning reduces cluster below min_cluster_size, it should be discarded.
        [0.0, 0.04, 0.08, 0.12] with min_cluster_size=4 -> DBSCAN finds 1 cluster of 4,
        but pruning removes outlier(s), leaving < 4 -> discarded.
        """
        values = np.array([0.0, 0.04, 0.08, 0.12])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=4)
        clusters = cluster_axis(values, config)
        # After pruning, cluster should have < 4 valid points, so discarded
        assert len(clusters) == 0

    def test_cluster_values_within_alpha_of_centroid(self):
        """All returned cluster values must be within alpha of their centroid."""
        values = np.array([0.0, 0.01, 0.02, 0.03, 0.04,
                           5.0, 5.01, 5.02, 5.03, 5.04])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        clusters = cluster_axis(values, config)
        for cluster in clusters:
            centroid = cluster["mean"]
            for v in cluster["values"]:
                assert abs(v - centroid) <= config.alpha

    def test_returns_correct_keys(self):
        values = np.array([1.0, 1.01, 1.02])
        config = AlignmentConfig(alpha=0.05, min_cluster_size=3)
        clusters = cluster_axis(values, config)
        assert len(clusters) == 1
        c = clusters[0]
        assert "indices" in c
        assert "values" in c
        assert "mean" in c
        assert "std" in c
        assert isinstance(c["mean"], float)
        assert isinstance(c["std"], float)
