import numpy as np
from structure_aligner.config import AxisStatistics


def compute_axis_statistics(values: np.ndarray, axis: str) -> AxisStatistics:
    """
    Compute statistical distribution for a single axis.

    Uses population std (ddof=0) since we compute over the full
    population of coordinates, not a sample.

    Args:
        values: 1D array of coordinate values for this axis.
        axis: Axis name ("X", "Y", or "Z").

    Returns:
        AxisStatistics with mean, median, std, min, max, quartiles, unique count.
    """
    return AxisStatistics(
        axis=axis,
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        std=float(np.std(values, ddof=0)),
        min=float(np.min(values)),
        max=float(np.max(values)),
        q1=float(np.percentile(values, 25)),
        q3=float(np.percentile(values, 75)),
        # Hardcoded 2 decimals: unique_count is a centimeter-level statistical
        # summary, independent of alignment rounding_precision.
        unique_count=int(len(np.unique(np.round(values, 2)))),
        total_count=len(values),
    )
