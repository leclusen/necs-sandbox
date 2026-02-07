"""Axis line discovery via multi-floor position filtering.

Replaces DBSCAN clustering (V1) with a selection-based approach:
axis lines are a subset of existing before positions that appear
on multiple Z-levels (floors).
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict

from structure_aligner.config import AxisLine, PipelineConfig
from structure_aligner.db.reader import InputVertex

logger = logging.getLogger(__name__)


def discover_axis_lines(
    vertices: list[InputVertex],
    config: PipelineConfig,
) -> tuple[list[AxisLine], list[AxisLine]]:
    """Discover canonical axis line positions from vertex data.

    Algorithm:
    1. For each unique X position (deduplicated within cluster_radius):
       a. Find all Z-levels (floors) where this X position appears
       b. Count distinct Z-levels
    2. Keep positions with >= min_floors Z-levels
    3. Repeat for Y positions
    4. Return sorted (axis_lines_x, axis_lines_y)

    Args:
        vertices: All vertices from the before file.
        config: Pipeline configuration.

    Returns:
        Tuple of (x_axis_lines, y_axis_lines), each sorted by position.
    """
    # Collect (coordinate, z) pairs for each axis
    x_pairs: list[tuple[float, float]] = []
    y_pairs: list[tuple[float, float]] = []

    for v in vertices:
        x_pairs.append((v.x, v.z))
        y_pairs.append((v.y, v.z))

    axis_x = _discover_for_axis(
        "X", x_pairs, config.cluster_radius, config.min_floors,
        config.rounding_precision, config.floor_z_levels,
        config.floor_match_tolerance,
    )
    axis_y = _discover_for_axis(
        "Y", y_pairs, config.cluster_radius, config.min_floors,
        config.rounding_precision, config.floor_z_levels,
        config.floor_match_tolerance,
    )

    logger.info(
        "Discovered %d X axis lines and %d Y axis lines (min_floors=%d)",
        len(axis_x), len(axis_y), config.min_floors,
    )

    return axis_x, axis_y


def _discover_for_axis(
    axis_name: str,
    coord_z_pairs: list[tuple[float, float]],
    cluster_radius: float,
    min_floors: int,
    rounding_precision: float,
    floor_z_levels: tuple[float, ...],
    floor_match_tolerance: float = 0.05,
) -> list[AxisLine]:
    """Discover axis lines for a single axis (X or Y).

    Steps:
    1. Round coordinates to rounding_precision to handle floating-point noise.
    2. Group by rounded coordinate, collecting Z values and vertex counts.
    3. Merge groups within cluster_radius (keep the position with most vertices).
    4. For each group, count distinct Z-levels (using floor matching).
    5. Filter: keep positions with floor_count >= min_floors.
    """
    ndigits = _precision_ndigits(rounding_precision)

    # Step 1-2: Group by rounded coordinate
    groups: dict[float, dict] = defaultdict(lambda: {"z_set": set(), "count": 0})
    for coord, z in coord_z_pairs:
        rounded = round(coord, ndigits)
        groups[rounded]["z_set"].add(_match_floor(z, floor_z_levels, floor_match_tolerance))
        groups[rounded]["count"] += 1

    # Step 3: Merge nearby groups within cluster_radius
    sorted_positions = sorted(groups.keys())
    merged = _merge_nearby(sorted_positions, groups, cluster_radius)

    # Step 4-5: Filter by floor count
    result = []
    for pos, data in merged:
        # Remove None from z_set (unmatched Z values)
        floor_set = {z for z in data["z_set"] if z is not None}
        floor_count = len(floor_set)
        if floor_count >= min_floors:
            result.append(AxisLine(
                axis=axis_name,
                position=pos,
                floor_count=floor_count,
                vertex_count=data["count"],
            ))

    result.sort(key=lambda a: a.position)
    return result


def _match_floor(
    z: float, floor_z_levels: tuple[float, ...], tolerance: float = 0.02
) -> float | None:
    """Match a Z value to the nearest floor level within tolerance."""
    if not floor_z_levels:
        return round(z, 1)  # Fallback: round to 0.1m for floor grouping

    best = min(floor_z_levels, key=lambda fz: abs(z - fz))
    if abs(z - best) <= tolerance:
        return best
    return None


def _merge_nearby(
    sorted_positions: list[float],
    groups: dict[float, dict],
    cluster_radius: float,
) -> list[tuple[float, dict]]:
    """Merge positions within cluster_radius using fixed-window grouping.

    Groups are anchored to the first position: all positions within
    cluster_radius of the group's first element are merged. This prevents
    unbounded chain merging (positions 1mm apart chaining across large spans).
    The representative position is the one with the highest vertex count.
    """
    if not sorted_positions:
        return []

    merged: list[tuple[float, dict]] = []
    current_pos = sorted_positions[0]
    current_data = {
        "z_set": set(groups[current_pos]["z_set"]),
        "count": groups[current_pos]["count"],
    }
    best_pos = current_pos
    best_count = current_data["count"]

    for pos in sorted_positions[1:]:
        if pos - current_pos <= cluster_radius:
            # Merge into current group
            current_data["z_set"].update(groups[pos]["z_set"])
            current_data["count"] += groups[pos]["count"]
            if groups[pos]["count"] > best_count:
                best_pos = pos
                best_count = groups[pos]["count"]
        else:
            # Emit current group
            merged.append((best_pos, current_data))
            # Start new group
            current_pos = pos
            current_data = {
                "z_set": set(groups[pos]["z_set"]),
                "count": groups[pos]["count"],
            }
            best_pos = pos
            best_count = current_data["count"]

    # Emit last group
    merged.append((best_pos, current_data))
    return merged


def _precision_ndigits(precision: float) -> int:
    """Convert precision to number of decimal digits."""
    return max(0, math.ceil(-math.log10(precision)))
