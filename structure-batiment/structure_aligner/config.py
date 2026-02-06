import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AlignmentConfig:
    """Configuration for the alignment pipeline."""
    alpha: float = 0.05           # Max tolerance in meters (per-axis, PRD CF-02)
    min_cluster_size: int = 3     # Min vertices per thread (PRD F-04)
    rounding_precision: float = 0.01  # Centimeter precision
    merge_threshold_factor: float = 2.0  # Merge threads closer than factor * alpha

    @property
    def rounding_ndigits(self) -> int:
        """Number of decimal places for rounding, derived from rounding_precision.

        Examples: 0.01 -> 2, 0.001 -> 3, 0.1 -> 1
        """
        return max(0, round(-math.log10(self.rounding_precision)))


@dataclass
class Thread:
    """A detected alignment thread (fil)."""
    fil_id: str           # e.g. "X_001"
    axis: str             # "X", "Y", or "Z"
    reference: float      # Rounded reference coordinate
    delta: float          # Actual cluster std (informational, NOT used for matching)
    vertex_count: int     # Number of vertices in this thread
    range_min: float      # reference - alpha (matching range)
    range_max: float      # reference + alpha (matching range)


@dataclass
class AlignedVertex:
    """A vertex after alignment processing."""
    id: int               # Original vertex ID from DB
    element_id: int
    x: float              # Aligned coordinate
    y: float
    z: float
    vertex_index: int
    x_original: float     # Original coordinate before alignment
    y_original: float
    z_original: float
    aligned_axis: str     # "X", "Y", "Z", "XY", "XZ", "YZ", "XYZ", "none"
    fil_x_id: str | None  # Thread ID or None
    fil_y_id: str | None
    fil_z_id: str | None
    displacement_total: float  # 3D Euclidean displacement (for reporting only)


@dataclass
class AxisStatistics:
    """Statistical summary for one axis."""
    axis: str
    mean: float
    median: float
    std: float            # Population std (ddof=0)
    min: float
    max: float
    q1: float
    q3: float
    unique_count: int
    total_count: int


@dataclass
class AlignmentResult:
    """Complete result of the alignment pipeline."""
    threads: list[Thread]
    aligned_vertices: list[AlignedVertex]
    statistics: list[AxisStatistics]  # One per axis (X, Y, Z)
    config: AlignmentConfig
