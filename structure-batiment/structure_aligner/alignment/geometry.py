from __future__ import annotations

import bisect
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from structure_aligner.config import AxisLine, Thread

from structure_aligner.db.reader import InputVertex


def euclidean_displacement(x1: float, y1: float, z1: float,
                           x2: float, y2: float, z2: float) -> float:
    """Calculate 3D Euclidean distance between two points (for reporting)."""
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2 + (z2 - z1)**2)


def find_matching_thread(coord: float, threads: list[Thread], alpha: float) -> Thread | None:
    """
    Find the closest thread whose reference is within alpha of the coordinate.

    Unlike the original plan, this:
    - Matches within alpha of the thread reference (not within delta)
    - Returns the CLOSEST thread when multiple threads match (deterministic)

    Args:
        coord: The coordinate value to match.
        threads: List of Thread objects for this axis.
        alpha: Maximum allowed per-axis displacement.

    Returns:
        The closest matching Thread, or None if no thread matches.
    """
    best_thread = None
    best_displacement = float("inf")

    for thread in threads:
        displacement = abs(coord - thread.reference)
        if displacement <= alpha and displacement < best_displacement:
            best_thread = thread
            best_displacement = displacement

    return best_thread


# =========================================================================
# V2 geometry helpers for per-element snap
# =========================================================================


def find_nearest_axis_line(
    coord: float,
    axis_lines: list[AxisLine],
    max_distance: float,
) -> AxisLine | None:
    """Find nearest axis line within max_distance using binary search.

    Args:
        coord: The coordinate value to match.
        axis_lines: Sorted list of AxisLine objects for this axis.
        max_distance: Maximum allowed distance.

    Returns:
        The nearest AxisLine, or None if none within max_distance.
    """
    if not axis_lines:
        return None

    positions = [al.position for al in axis_lines]
    idx = bisect.bisect_left(positions, coord)

    best: AxisLine | None = None
    best_dist = float("inf")

    for i in (idx - 1, idx):
        if 0 <= i < len(axis_lines):
            dist = abs(coord - axis_lines[i].position)
            if dist <= max_distance and dist < best_dist:
                best = axis_lines[i]
                best_dist = dist

    return best


def identify_element_endpoints(
    vertices: list[InputVertex],
    axis: str,
    cluster_radius: float = 0.002,
) -> list[float]:
    """Find distinct coordinate positions for an element's endpoints.

    For a column: returns [center_x] (1 position)
    For a wall: returns [min_x, max_x] (2 positions if sufficiently different)
    Deduplicates within cluster_radius.

    Args:
        vertices: All vertices belonging to a single element.
        axis: "X" or "Y" - which coordinate to extract.
        cluster_radius: Merge positions within this distance.

    Returns:
        Sorted list of distinct endpoint positions.
    """
    if not vertices:
        return []

    coords = sorted(getattr(v, axis.lower()) for v in vertices)

    # Cluster: merge nearby values
    clusters: list[list[float]] = [[coords[0]]]
    for c in coords[1:]:
        if c - clusters[-1][-1] <= cluster_radius:
            clusters[-1].append(c)
        else:
            clusters.append([c])

    # Representative = mean of each cluster
    endpoints = [sum(cl) / len(cl) for cl in clusters]
    return endpoints


def assign_vertex_to_endpoint(
    vertex_coord: float,
    endpoints: list[float],
) -> int:
    """Return index of the nearest endpoint for this vertex.

    Args:
        vertex_coord: The vertex coordinate value.
        endpoints: Sorted list of endpoint positions.

    Returns:
        Index into endpoints of the nearest one.
    """
    if len(endpoints) == 1:
        return 0

    best_idx = 0
    best_dist = abs(vertex_coord - endpoints[0])
    for i in range(1, len(endpoints)):
        dist = abs(vertex_coord - endpoints[i])
        if dist < best_dist:
            best_idx = i
            best_dist = dist
    return best_idx
