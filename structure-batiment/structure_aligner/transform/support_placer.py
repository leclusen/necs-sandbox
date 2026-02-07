"""Support point placement at structural grid intersections.

Phase 5.3 - Places Appuis (Point and LineCurve) at axis line
intersections where column elements exist.
"""

from __future__ import annotations

import logging
from collections import defaultdict

import rhino3dm

from structure_aligner.config import AxisLine

logger = logging.getLogger(__name__)

# Default support floor levels (from research)
SUPPORT_Z_LEVELS = (2.12, -4.44)


def place_support_points(
    model: rhino3dm.File3dm,
    axis_lines_x: list[AxisLine],
    axis_lines_y: list[AxisLine],
    support_z_levels: tuple[float, ...] = SUPPORT_Z_LEVELS,
    existing_columns: dict[tuple[float, float], bool] | None = None,
    column_tolerance: float = 0.5,
    layer_index: int = 0,
    start_id: int | None = None,
) -> tuple[int, list[tuple[float, float, float]]]:
    """Place Appuis at grid intersections where columns exist.

    Args:
        model: The rhino3dm model to add objects to.
        axis_lines_x: Sorted X axis lines.
        axis_lines_y: Sorted Y axis lines.
        support_z_levels: Floor Z-levels where supports are placed.
        existing_columns: Optional dict mapping (x, y) -> bool for column
            positions. If None, places supports at ALL intersections.
        column_tolerance: Tolerance for matching column positions.
        layer_index: Layer index for new objects.
        start_id: Starting ID for Appuis naming. If None, auto-detect.

    Returns:
        Tuple of (count_added, positions_list) where positions_list
        contains (x, y, z) for each support placed.
    """
    if start_id is None:
        start_id = _get_max_appui_id(model) + 1

    if existing_columns is None:
        logger.warning(
            "No column filter provided — supports placed at ALL %d grid "
            "intersections. Provide existing_columns to filter.",
            len(axis_lines_x) * len(axis_lines_y) * len(support_z_levels),
        )

    # Build spatial index for O(1) column lookup
    bucket_size = max(column_tolerance, 0.01)
    column_index: set[tuple[int, int]] | None = None
    if existing_columns is not None:
        column_index = _build_column_index(existing_columns, column_tolerance)

    next_id = start_id
    added = 0
    positions: list[tuple[float, float, float]] = []

    for z in support_z_levels:
        for ax in axis_lines_x:
            for ay in axis_lines_y:
                x, y = ax.position, ay.position

                # Filter by column positions if provided
                if column_index is not None:
                    if not _has_nearby_column_indexed(
                        x, y, column_index, bucket_size
                    ):
                        continue

                name = f"Appuis_{next_id}"
                next_id += 1

                attr = rhino3dm.ObjectAttributes()
                attr.Name = name
                attr.LayerIndex = layer_index

                model.Objects.AddPoint(
                    rhino3dm.Point3d(x, y, z), attr
                )
                positions.append((x, y, z))
                added += 1

    logger.info(
        "Support placement: %d Appuis added at %d Z-levels",
        added, len(support_z_levels),
    )
    return added, positions


def place_support_points_at_columns(
    model: rhino3dm.File3dm,
    column_positions: dict[tuple[float, float], bool],
    axis_lines_x: list[AxisLine],
    axis_lines_y: list[AxisLine],
    support_z_levels: tuple[float, ...] = SUPPORT_Z_LEVELS,
    snap_tolerance: float = 0.75,
    layer_index: int = 0,
    start_id: int | None = None,
) -> tuple[int, list[tuple[float, float, float]]]:
    """Place supports at column positions snapped to nearest axis intersection.

    Instead of scanning all grid intersections, this iterates column centers
    and snaps each to the nearest (axis_x, axis_y) intersection within
    snap_tolerance. This produces O(C) supports where C = number of columns.

    Args:
        model: The rhino3dm model.
        column_positions: Dict of (x, y) -> True for column centers.
        axis_lines_x: X axis lines.
        axis_lines_y: Y axis lines.
        support_z_levels: Z-levels for support placement.
        snap_tolerance: Max distance to snap a column to an axis intersection.
        layer_index: Layer index for new objects.
        start_id: Starting Appuis ID.

    Returns:
        Tuple of (count_added, positions_list).
    """
    if start_id is None:
        start_id = _get_max_appui_id(model) + 1

    # Sort axis positions for binary search
    import bisect
    x_positions = sorted(al.position for al in axis_lines_x)
    y_positions = sorted(al.position for al in axis_lines_y)

    next_id = start_id
    added = 0
    positions: list[tuple[float, float, float]] = []
    seen: set[tuple[float, float]] = set()

    for (cx, cy) in column_positions:
        # Find nearest X axis line
        snap_x = _find_nearest_sorted(cx, x_positions, snap_tolerance)
        snap_y = _find_nearest_sorted(cy, y_positions, snap_tolerance)
        if snap_x is None or snap_y is None:
            continue

        key = (round(snap_x, 4), round(snap_y, 4))
        if key in seen:
            continue
        seen.add(key)

        for z in support_z_levels:
            name = f"Appuis_{next_id}"
            next_id += 1
            attr = rhino3dm.ObjectAttributes()
            attr.Name = name
            attr.LayerIndex = layer_index
            model.Objects.AddPoint(rhino3dm.Point3d(snap_x, snap_y, z), attr)
            positions.append((snap_x, snap_y, z))
            added += 1

    logger.info(
        "Support placement (column-based): %d Appuis at %d unique positions, %d Z-levels",
        added, len(seen), len(support_z_levels),
    )
    return added, positions


def _find_nearest_sorted(
    value: float, sorted_positions: list[float], tolerance: float,
) -> float | None:
    """Find nearest position in sorted list within tolerance using binary search."""
    import bisect
    idx = bisect.bisect_left(sorted_positions, value)
    best = None
    best_dist = tolerance + 1
    for i in (idx - 1, idx):
        if 0 <= i < len(sorted_positions):
            d = abs(sorted_positions[i] - value)
            if d < best_dist:
                best_dist = d
                best = sorted_positions[i]
    return best if best_dist <= tolerance else None


def place_line_supports(
    model: rhino3dm.File3dm,
    axis_lines_x: list[AxisLine],
    edge_y_positions: list[float],
    z_level: float = -4.44,
    line_length: float = 1.0,
    layer_index: int = 0,
    start_id: int | None = None,
) -> int:
    """Place LineCurve supports along building edges.

    Args:
        model: The rhino3dm model to add objects to.
        axis_lines_x: X axis lines for positioning.
        edge_y_positions: Y positions at building edges.
        z_level: Z position for line supports.
        line_length: Length of each line support.
        layer_index: Layer index for new objects.
        start_id: Starting ID for naming.

    Returns:
        Number of line supports added.
    """
    if start_id is None:
        start_id = _get_max_appui_id(model) + 1

    next_id = start_id
    added = 0

    for ax in axis_lines_x:
        for y in edge_y_positions:
            p1 = rhino3dm.Point3d(ax.position, y, z_level)
            p2 = rhino3dm.Point3d(ax.position, y + line_length, z_level)
            line = rhino3dm.LineCurve(p1, p2)

            name = f"Appuis_{next_id}"
            next_id += 1

            attr = rhino3dm.ObjectAttributes()
            attr.Name = name
            attr.LayerIndex = layer_index
            model.Objects.AddCurve(line, attr)
            added += 1

    logger.info("Line support placement: %d LineCurve supports added", added)
    return added


def _build_column_index(
    existing_columns: dict[tuple[float, float], bool],
    tolerance: float,
) -> set[tuple[int, int]]:
    """Build spatial index with rounded keys for O(1) column lookup."""
    index: set[tuple[int, int]] = set()
    bucket_size = max(tolerance, 0.01)
    for (cx, cy) in existing_columns:
        # Add to all neighboring buckets for tolerance matching
        bx = int(cx / bucket_size)
        by = int(cy / bucket_size)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                index.add((bx + dx, by + dy))
    return index


def _has_nearby_column_indexed(
    x: float,
    y: float,
    column_index: set[tuple[int, int]],
    bucket_size: float,
) -> bool:
    """O(1) column proximity check using spatial index."""
    bx = int(x / bucket_size)
    by = int(y / bucket_size)
    return (bx, by) in column_index


def _get_max_appui_id(model: rhino3dm.File3dm) -> int:
    """Find the highest Appuis_NNNN id in the model."""
    max_id = 0
    for obj in model.Objects:
        name = obj.Attributes.Name
        if name and name.startswith("Appuis_"):
            try:
                num = int(name.split("_")[1])
                if num > max_id:
                    max_id = num
            except (ValueError, IndexError):
                pass
    return max_id
