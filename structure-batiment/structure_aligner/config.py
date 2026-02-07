import math
from dataclasses import dataclass, field


# =============================================================================
# V2 Pipeline Config & Data Models
# =============================================================================

@dataclass(frozen=True)
class PipelineConfig:
    """Configuration for the V2 alignment pipeline."""

    # Axis line discovery
    min_floors: int = 3                    # Min Z-levels for axis line candidacy
    cluster_radius: float = 0.002          # 2mm tolerance for dedup nearby positions

    # Snapping
    max_snap_distance: float = 0.75        # Max snap distance for normal vertices
    outlier_snap_distance: float = 4.0     # Max snap for extreme corrections
    z_enabled: bool = False                # Never modify Z

    # Rounding
    rounding_precision: float = 0.005      # 5mm precision

    # Floor matching
    floor_match_tolerance: float = 0.05    # 50mm tolerance for Z-to-floor matching

    # Object rules
    remove_dalles: bool = True             # Remove all DALLE except roof
    roof_z_threshold: float = 30.0         # Z above which dalles are kept
    consolidate_dalles: bool = True        # Generate consolidated slab Breps
    simplify_voiles: bool = True           # Replace multi-face voiles
    add_support_points: bool = True        # Add Appuis at grid intersections
    add_filaire: bool = True               # Add column/beam centerlines
    add_grid_lines: bool = True            # Add structural grid lines

    # Floor levels (from research - invariant Z values)
    floor_z_levels: tuple[float, ...] = (
        -4.44, -1.56, 2.12, 5.48, 8.20,
        13.32, 17.96, 22.12, 26.28, 29.64, 32.36,
    )

    # Validation
    reference_3dm: str | None = None       # Optional reference for comparison

    @property
    def rounding_ndigits(self) -> int:
        return max(0, math.ceil(-math.log10(self.rounding_precision)))

    @property
    def floor_heights(self) -> tuple[float, ...]:
        """Floor-to-floor heights derived from Z-levels."""
        zs = self.floor_z_levels
        return tuple(round(zs[i + 1] - zs[i], 2) for i in range(len(zs) - 1))


@dataclass
class AxisLine:
    """A canonical structural axis line position."""
    axis: str           # "X" or "Y"
    position: float     # The canonical coordinate value
    floor_count: int    # Number of Z-levels this position appears on
    vertex_count: int   # Total vertices at this position in before data


@dataclass
class ElementInfo:
    """Element metadata from DB."""
    id: int
    name: str
    type: str           # poteau, voile, dalle, appui, poutre
    geometry_type: str | None = None


@dataclass
class ElementAlignment:
    """Alignment result for a single element."""
    element_id: int
    element_name: str
    element_type: str
    snap_x: list[tuple[float, float]] = field(default_factory=list)  # [(before, after), ...]
    snap_y: list[tuple[float, float]] = field(default_factory=list)
    vertices_moved: int = 0
    max_displacement: float = 0.0


# =============================================================================
# V1 Pipeline Config & Data Models (kept for backward compatibility)
# =============================================================================

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
