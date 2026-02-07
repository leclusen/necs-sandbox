"""Validate discovered axis lines against a reference 3dm file."""

from __future__ import annotations

import bisect
import logging
import math
from collections import defaultdict
from pathlib import Path

import rhino3dm

from structure_aligner.config import AxisLine

logger = logging.getLogger(__name__)


def validate_against_reference(
    discovered: list[AxisLine],
    reference_3dm_path: Path,
    axis: str,
    tolerance: float = 0.005,
    min_vertex_count: int = 5,
) -> dict:
    """Compare discovered axis lines against reference after.3dm.

    Extracts axis-line positions from named objects in the reference file
    (positions shared by many vertices, indicating structural axis lines)
    and compares against the discovered axis lines.

    Args:
        discovered: List of discovered AxisLine objects.
        reference_3dm_path: Path to the reference .3dm file.
        axis: "X" or "Y" - which axis to compare.
        tolerance: Match tolerance in meters.
        min_vertex_count: Minimum vertices at a position for it to count
            as an axis line in the reference.

    Returns:
        Dict with comparison metrics.
    """
    reference_positions = _extract_axis_positions(
        reference_3dm_path, axis, tolerance, min_vertex_count,
    )
    discovered_positions = sorted(a.position for a in discovered)

    matched_ref = 0
    unmatched_reference = []
    for ref_pos in reference_positions:
        if _has_match(ref_pos, discovered_positions, tolerance):
            matched_ref += 1
        else:
            unmatched_reference.append(ref_pos)

    matched_disc = 0
    unmatched_discovered = []
    ref_sorted = sorted(reference_positions)
    for disc_pos in discovered_positions:
        if _has_match(disc_pos, ref_sorted, tolerance):
            matched_disc += 1
        else:
            unmatched_discovered.append(disc_pos)

    ref_count = len(reference_positions)
    disc_count = len(discovered_positions)

    recall = matched_ref / ref_count if ref_count > 0 else 0.0
    precision = matched_disc / disc_count if disc_count > 0 else 0.0

    result = {
        "axis": axis,
        "discovered_count": disc_count,
        "reference_count": ref_count,
        "matched": matched_ref,
        "recall": recall,
        "precision": precision,
        "unmatched_reference": unmatched_reference,
        "unmatched_discovered": unmatched_discovered,
    }

    logger.info(
        "%s axis: %d discovered, %d reference, %d matched (recall=%.1f%%, precision=%.1f%%)",
        axis, disc_count, ref_count, matched_ref, recall * 100, precision * 100,
    )

    return result


def _extract_axis_positions(
    path_3dm: Path,
    axis: str,
    dedup_tolerance: float = 0.005,
    min_vertex_count: int = 5,
) -> list[float]:
    """Extract axis-line positions from named objects in a 3dm file.

    An axis-line position is one where many vertices sit (>= min_vertex_count).
    Positions with few vertices are typically from added geometry (consolidated
    dalles, simplified voiles) and not structural axis lines.
    """
    model = rhino3dm.File3dm.Read(str(path_3dm))
    if model is None:
        raise RuntimeError(f"Failed to read 3dm file: {path_3dm}")

    # Count vertices at each position
    ndigits = max(0, math.ceil(-math.log10(dedup_tolerance)))
    position_counts: dict[float, int] = defaultdict(int)

    for obj in model.Objects:
        name = obj.Attributes.Name
        if not name:
            continue
        geom = obj.Geometry
        coords = _extract_coords(geom, axis)
        for c in coords:
            rounded = round(c, ndigits)
            position_counts[rounded] += 1

    # Filter by minimum vertex count
    axis_positions = sorted(
        pos for pos, count in position_counts.items()
        if count >= min_vertex_count
    )

    # Merge nearby positions
    return _dedup_positions(axis_positions, dedup_tolerance)


def _extract_coords(geom, axis: str) -> list[float]:
    """Extract X or Y coordinates from a geometry object."""
    points = []

    if isinstance(geom, rhino3dm.Brep):
        for vi in range(len(geom.Vertices)):
            v = geom.Vertices[vi]
            loc = v.Location
            points.append(loc.X if axis == "X" else loc.Y)

    elif isinstance(geom, rhino3dm.LineCurve):
        for p in [geom.PointAtStart, geom.PointAtEnd]:
            points.append(p.X if axis == "X" else p.Y)

    elif isinstance(geom, rhino3dm.PolylineCurve):
        for pi in range(geom.PointCount):
            p = geom.Point(pi)
            points.append(p.X if axis == "X" else p.Y)

    elif isinstance(geom, rhino3dm.NurbsCurve):
        for pi in range(len(geom.Points)):
            p = geom.Points[pi]
            points.append(p.X if axis == "X" else p.Y)

    elif isinstance(geom, rhino3dm.Point):
        loc = geom.Location
        points.append(loc.X if axis == "X" else loc.Y)

    return points


def _dedup_positions(sorted_positions: list[float], tolerance: float) -> list[float]:
    """Remove duplicate positions within tolerance, keeping the first."""
    if not sorted_positions:
        return []

    result = [sorted_positions[0]]
    for pos in sorted_positions[1:]:
        if pos - result[-1] > tolerance:
            result.append(pos)
    return result


def _has_match(value: float, sorted_list: list[float], tolerance: float) -> bool:
    """Check if value has a match in sorted_list within tolerance."""
    if not sorted_list:
        return False
    idx = bisect.bisect_left(sorted_list, value - tolerance)
    if idx < len(sorted_list) and abs(sorted_list[idx] - value) <= tolerance:
        return True
    if idx > 0 and abs(sorted_list[idx - 1] - value) <= tolerance:
        return True
    return False
