import logging
import numpy as np
from structure_aligner.config import AlignmentConfig, Thread
from structure_aligner.analysis.clustering import cluster_axis

logger = logging.getLogger(__name__)


def detect_threads(values: np.ndarray, axis: str, config: AlignmentConfig) -> list[Thread]:
    """
    Detect alignment threads for a single axis.

    Runs DBSCAN clustering (with post-validation), then converts each
    cluster into a Thread. Handles edge cases:
      - F-06 Case 1: Merges threads closer than 2*alpha
      - F-06 Case 3: Clusters with < min_cluster_size are discarded (in cluster_axis)

    Args:
        values: 1D array of all coordinate values for this axis.
        axis: "X", "Y", or "Z".
        config: Alignment configuration.

    Returns:
        Sorted list of Thread objects for this axis.
    """
    clusters = cluster_axis(values, config)

    # Convert clusters to threads
    threads = []
    for i, cluster in enumerate(clusters):
        reference = round(cluster["mean"], config.rounding_ndigits)
        delta = min(cluster["std"], config.alpha)
        threads.append(Thread(
            fil_id=f"{axis}_{i+1:03d}",
            axis=axis,
            reference=reference,
            delta=delta,
            vertex_count=len(cluster["values"]),
            range_min=reference - config.alpha,
            range_max=reference + config.alpha,
        ))

    # Sort by reference value
    threads.sort(key=lambda t: t.reference)

    # F-06 Case 1: Merge threads that are too close
    merge_threshold = config.alpha * config.merge_threshold_factor
    threads = _merge_close_threads(threads, merge_threshold, axis, config)

    # Renumber after merge
    for i, thread in enumerate(threads):
        thread.fil_id = f"{axis}_{i+1:03d}"

    logger.info("Axis %s: %d threads detected from %d values", axis, len(threads), len(values))
    for t in threads:
        logger.debug("  %s: ref=%.4fm, delta=%.4fm, count=%d", t.fil_id, t.reference, t.delta, t.vertex_count)

    return threads


def _merge_close_threads(threads: list[Thread], threshold: float, axis: str,
                         config: AlignmentConfig) -> list[Thread]:
    """
    Merge threads whose reference values are closer than threshold.
    Keeps the thread with more vertices as the base; recalculates reference
    as weighted average.
    """
    if len(threads) <= 1:
        return threads

    merged = [threads[0]]
    for thread in threads[1:]:
        prev = merged[-1]
        if abs(thread.reference - prev.reference) < threshold:
            # Weighted average reference
            total = prev.vertex_count + thread.vertex_count
            new_ref = round(
                (prev.reference * prev.vertex_count + thread.reference * thread.vertex_count) / total,
                config.rounding_ndigits,
            )
            new_delta = max(prev.delta, thread.delta)
            merged[-1] = Thread(
                fil_id=prev.fil_id,
                axis=axis,
                reference=new_ref,
                delta=new_delta,
                vertex_count=total,
                range_min=new_ref - config.alpha,
                range_max=new_ref + config.alpha,
            )
            logger.info("Merged threads at %.4fm and %.4fm -> %.4fm (%d vertices)",
                       prev.reference, thread.reference, new_ref, total)
        else:
            merged.append(thread)

    return merged
