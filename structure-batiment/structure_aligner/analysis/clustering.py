import logging
import numpy as np
from sklearn.cluster import DBSCAN
from structure_aligner.config import AlignmentConfig

logger = logging.getLogger(__name__)


def cluster_axis(values: np.ndarray, config: AlignmentConfig) -> list[dict]:
    """
    Run DBSCAN clustering on a single axis's coordinate values, then
    validate that all cluster points are within alpha of the cluster centroid.

    DBSCAN with eps=alpha guarantees density-reachability, but NOT that all
    points in a cluster are within alpha of the centroid (chaining effect).
    This function adds a post-clustering validation step that prunes outlier
    points, ensuring the per-axis displacement constraint is satisfiable.

    Args:
        values: 1D array of coordinate values.
        config: Alignment configuration (alpha, min_cluster_size).

    Returns:
        List of cluster dicts with keys:
          - "indices": array of indices into the original values array
          - "values": array of coordinate values in this cluster
          - "mean": mean value of the cluster (centroid)
          - "std": standard deviation of the cluster
        All returned cluster points are guaranteed within alpha of their centroid.
    """
    # DBSCAN needs 2D input
    X = values.reshape(-1, 1)
    db = DBSCAN(eps=config.alpha, min_samples=config.min_cluster_size).fit(X)

    clusters = []
    for label in sorted(set(db.labels_)):
        if label == -1:
            continue  # Noise points (isolated vertices)
        mask = db.labels_ == label
        cluster_values = values[mask]
        cluster_indices = np.where(mask)[0]

        # Post-clustering validation: prune points > alpha from centroid
        centroid = float(np.mean(cluster_values))
        within_alpha = np.abs(cluster_values - centroid) <= config.alpha
        valid_values = cluster_values[within_alpha]
        valid_indices = cluster_indices[within_alpha]

        pruned_count = len(cluster_values) - len(valid_values)
        if pruned_count > 0:
            logger.debug(
                "Cluster %d: pruned %d/%d points beyond alpha=%.4fm from centroid %.4fm",
                label, pruned_count, len(cluster_values), config.alpha, centroid,
            )

        # Recompute centroid after pruning
        if len(valid_values) >= config.min_cluster_size:
            centroid = float(np.mean(valid_values))
            clusters.append({
                "indices": valid_indices,
                "values": valid_values,
                "mean": centroid,
                "std": float(np.std(valid_values, ddof=0)),
            })
        else:
            logger.debug(
                "Cluster %d: discarded after pruning (only %d points remain, need %d)",
                label, len(valid_values), config.min_cluster_size,
            )

    return clusters
