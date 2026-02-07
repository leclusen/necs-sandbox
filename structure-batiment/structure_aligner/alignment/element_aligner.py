"""Per-element-endpoint snap algorithm (V2).

Replaces the V1 per-vertex processor with an element-aware snapping
approach: vertices belonging to the same element share the same
displacement per endpoint, preserving element topology.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from structure_aligner.config import (
    AlignedVertex,
    AxisLine,
    ElementInfo,
    PipelineConfig,
)
from structure_aligner.db.reader import InputVertex
from structure_aligner.alignment.geometry import (
    assign_vertex_to_endpoint,
    euclidean_displacement,
    find_nearest_axis_line,
    identify_element_endpoints,
)

logger = logging.getLogger(__name__)


def align_elements(
    vertices: list[InputVertex],
    elements: dict[int, ElementInfo],
    axis_lines_x: list[AxisLine],
    axis_lines_y: list[AxisLine],
    config: PipelineConfig,
) -> list[AlignedVertex]:
    """Per-element-endpoint snap algorithm.

    For each element:
    1. Group vertices by element_id
    2. Find distinct X/Y endpoint positions (cluster within cluster_radius)
    3. For each endpoint, find nearest axis line (max_snap_distance first,
       then outlier_snap_distance)
    4. For each vertex, snap to the axis line of its nearest element endpoint
    5. NEVER modify Z coordinates

    Args:
        vertices: All input vertices.
        elements: Element metadata keyed by element_id.
        axis_lines_x: Sorted X axis lines from discovery.
        axis_lines_y: Sorted Y axis lines from discovery.
        config: Pipeline configuration.

    Returns:
        List of AlignedVertex with original and aligned coordinates.
    """
    ndigits = config.rounding_ndigits

    # Group vertices by element_id
    by_element: dict[int, list[InputVertex]] = defaultdict(list)
    for v in vertices:
        by_element[v.element_id].append(v)

    aligned: list[AlignedVertex] = []
    aligned_count = 0

    # Element types that should be skipped (not snapped)
    skip_types = {"dalle"}

    for element_id, elem_verts in by_element.items():
        elem_info = elements.get(element_id)
        elem_type = elem_info.type if elem_info else None

        # Skip dalles – they are removed/consolidated in Phase 4
        if elem_type in skip_types:
            for v in elem_verts:
                aligned.append(AlignedVertex(
                    id=v.id, element_id=v.element_id,
                    x=v.x, y=v.y, z=v.z,
                    vertex_index=v.vertex_index,
                    x_original=v.x, y_original=v.y, z_original=v.z,
                    aligned_axis="none",
                    fil_x_id=None, fil_y_id=None, fil_z_id=None,
                    displacement_total=0.0,
                ))
            continue

        # Cap endpoints by element type:
        #   poteau/appui -> max 1 endpoint per axis (point-like)
        #   voile/poutre -> max 2 endpoints per axis (span)
        max_ep = 1 if elem_type in ("poteau", "appui") else 2

        # Compute endpoint snap targets for this element
        x_snap_map = _compute_endpoint_snaps(
            elem_verts, "X", axis_lines_x, config, max_endpoints=max_ep
        )
        y_snap_map = _compute_endpoint_snaps(
            elem_verts, "Y", axis_lines_y, config, max_endpoints=max_ep
        )

        for v in elem_verts:
            # Get snapped coordinates via endpoint mapping
            new_x, snapped_x = _snap_vertex_coord(v.x, x_snap_map, config.cluster_radius)
            new_y, snapped_y = _snap_vertex_coord(v.y, y_snap_map, config.cluster_radius)
            new_z = v.z  # NEVER modify Z

            # Round
            new_x = round(new_x, ndigits)
            new_y = round(new_y, ndigits)

            # Build aligned_axis string
            axes = []
            if snapped_x:
                axes.append("X")
            if snapped_y:
                axes.append("Y")
            aligned_axis = "".join(axes) if axes else "none"

            displacement = euclidean_displacement(
                v.x, v.y, v.z, new_x, new_y, new_z
            )

            if aligned_axis != "none":
                aligned_count += 1

            aligned.append(AlignedVertex(
                id=v.id,
                element_id=v.element_id,
                x=new_x,
                y=new_y,
                z=new_z,
                vertex_index=v.vertex_index,
                x_original=v.x,
                y_original=v.y,
                z_original=v.z,
                aligned_axis=aligned_axis,
                fil_x_id=None,
                fil_y_id=None,
                fil_z_id=None,
                displacement_total=round(displacement, 6),
            ))

    logger.info(
        "Aligned %d/%d vertices (%.1f%%)",
        aligned_count,
        len(aligned),
        aligned_count / len(aligned) * 100 if aligned else 0,
    )

    return aligned


def _compute_endpoint_snaps(
    elem_verts: list[InputVertex],
    axis: str,
    axis_lines: list[AxisLine],
    config: PipelineConfig,
    max_endpoints: int = 2,
) -> list[tuple[float, float | None]]:
    """Compute snap targets for each endpoint of an element on one axis.

    Returns a list of (endpoint_position, snap_target) tuples.
    snap_target is None if no axis line was found within tolerance.
    """
    if max_endpoints == 1:
        # Point-like element: force all coords into a single cluster
        # by using infinite cluster radius, then find best snap target.
        endpoints = identify_element_endpoints(
            elem_verts, axis, cluster_radius=float("inf")
        )
        # endpoints should be exactly [mean_of_all_coords]
    else:
        endpoints = identify_element_endpoints(
            elem_verts, axis, config.cluster_radius
        )
        # Cap to 2 endpoints (first/last) if more discovered
        if len(endpoints) > max_endpoints:
            endpoints = [endpoints[0], endpoints[-1]]

    result: list[tuple[float, float | None]] = []
    for ep in endpoints:
        # Try normal snap distance first
        target_line = find_nearest_axis_line(ep, axis_lines, config.max_snap_distance)
        if target_line is None:
            # Try outlier distance
            target_line = find_nearest_axis_line(
                ep, axis_lines, config.outlier_snap_distance
            )
        target = target_line.position if target_line else None
        result.append((ep, target))

    return result


def _snap_vertex_coord(
    coord: float,
    endpoint_snaps: list[tuple[float, float | None]],
    cluster_radius: float = 0.002,
) -> tuple[float, bool]:
    """Snap a single vertex coordinate using endpoint snap map.

    Args:
        coord: Original vertex coordinate.
        endpoint_snaps: List of (endpoint_pos, snap_target) from
            _compute_endpoint_snaps.
        cluster_radius: If vertex is within this distance of its
            assigned endpoint, snap directly to the target position
            (avoiding mean-based drift).

    Returns:
        (new_coord, was_snapped) tuple.
    """
    if not endpoint_snaps:
        return coord, False

    # Find which endpoint this vertex is closest to
    endpoints = [ep for ep, _ in endpoint_snaps]
    idx = assign_vertex_to_endpoint(coord, endpoints)

    ep_pos, snap_target = endpoint_snaps[idx]
    if snap_target is None:
        return coord, False

    # If vertex is close to its endpoint, snap directly to target
    # to avoid sub-mm drift from mean-based delta computation.
    if abs(coord - ep_pos) <= cluster_radius:
        return snap_target, True

    # Apply the endpoint's displacement (preserves section geometry)
    delta = snap_target - ep_pos
    return coord + delta, True
