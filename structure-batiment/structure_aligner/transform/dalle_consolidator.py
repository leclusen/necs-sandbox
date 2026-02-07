"""Dalle (slab) consolidation: create large planar Breps per floor.

Phase 5.1 - Replaces removed individual dalle panels with 1-3 large
consolidated slab surfaces per floor level.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

import rhino3dm

logger = logging.getLogger(__name__)


@dataclass
class RemovedDalleInfo:
    """Footprint info from a removed dalle for consolidation."""
    name: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z: float


def extract_dalle_info(
    model: rhino3dm.File3dm,
    dalle_names: set[str],
) -> list[RemovedDalleInfo]:
    """Extract footprint info from dalle objects before removal.

    Call this BEFORE removing dalles to capture their extents.
    """
    info: list[RemovedDalleInfo] = []
    for obj in model.Objects:
        name = obj.Attributes.Name
        if name not in dalle_names:
            continue
        geom = obj.Geometry
        if not isinstance(geom, rhino3dm.Brep) or len(geom.Vertices) == 0:
            continue
        xs = [geom.Vertices[i].Location.X for i in range(len(geom.Vertices))]
        ys = [geom.Vertices[i].Location.Y for i in range(len(geom.Vertices))]
        zs = [geom.Vertices[i].Location.Z for i in range(len(geom.Vertices))]
        z_avg = sum(zs) / len(zs)
        info.append(RemovedDalleInfo(
            name=name,
            x_min=min(xs), x_max=max(xs),
            y_min=min(ys), y_max=max(ys),
            z=round(z_avg, 2),
        ))
    return info


def consolidate_dalles(
    model: rhino3dm.File3dm,
    removed_dalles: list[RemovedDalleInfo],
    floor_z_levels: tuple[float, ...],
    layer_index: int = 0,
) -> int:
    """Create consolidated slab Breps per floor level.

    Groups removed dalle footprints by Z-level, computes bounding
    rectangles per structural zone, and creates single-face planar
    Breps at each floor.

    Args:
        model: The rhino3dm model to add objects to.
        removed_dalles: Footprint info from removed dalles.
        floor_z_levels: Known floor Z-levels.
        layer_index: Layer index for new objects.

    Returns:
        Number of consolidated dalle objects added.
    """
    if not removed_dalles:
        return 0

    # Group by Z-level (match to nearest floor)
    by_z: dict[float, list[RemovedDalleInfo]] = defaultdict(list)
    for info in removed_dalles:
        matched_z = _match_z(info.z, floor_z_levels)
        by_z[matched_z].append(info)

    added = 0
    next_id = _get_max_coque_id(model) + 1

    for z_level, dalles in sorted(by_z.items()):
        # Compute overall bounding box
        x_min = min(d.x_min for d in dalles)
        x_max = max(d.x_max for d in dalles)
        y_min = min(d.y_min for d in dalles)
        y_max = max(d.y_max for d in dalles)

        # Split into structural zones if the footprint is large
        zones = _split_zones(dalles, x_min, x_max, y_min, y_max)

        for zone_x_min, zone_x_max, zone_y_min, zone_y_max in zones:
            brep = _create_planar_brep(
                zone_x_min, zone_x_max, zone_y_min, zone_y_max, z_level
            )
            if brep is None:
                continue

            name = f"Coque_{next_id}"
            next_id += 1

            attr = rhino3dm.ObjectAttributes()
            attr.Name = name
            attr.LayerIndex = layer_index
            model.Objects.AddBrep(brep, attr)
            added += 1

    logger.info("Dalle consolidation: %d consolidated slabs added", added)
    return added


def _match_z(z: float, floor_z_levels: tuple[float, ...], tol: float = 0.5) -> float:
    """Match Z to nearest floor level."""
    if not floor_z_levels:
        return round(z, 2)
    best = min(floor_z_levels, key=lambda fz: abs(z - fz))
    if abs(z - best) <= tol:
        return best
    return round(z, 2)


def _split_zones(
    dalles: list[RemovedDalleInfo],
    x_min: float, x_max: float,
    y_min: float, y_max: float,
) -> list[tuple[float, float, float, float]]:
    """Split into structural zones based on dalle distribution.

    Uses a simple approach: if the Y extent is large (>50m),
    split at the largest Y-gap between dalle groups.
    """
    x_range = x_max - x_min
    y_range = y_max - y_min

    if y_range < 50.0 and x_range < 100.0:
        return [(x_min, x_max, y_min, y_max)]

    # Find Y-gap to split
    y_centers = sorted(set(round((d.y_min + d.y_max) / 2, 1) for d in dalles))
    if len(y_centers) < 2:
        return [(x_min, x_max, y_min, y_max)]

    # Find largest gap
    max_gap = 0.0
    split_y = None
    for i in range(len(y_centers) - 1):
        gap = y_centers[i + 1] - y_centers[i]
        if gap > max_gap:
            max_gap = gap
            split_y = (y_centers[i] + y_centers[i + 1]) / 2

    if max_gap > 10.0 and split_y is not None:
        zone_a = [d for d in dalles if (d.y_min + d.y_max) / 2 < split_y]
        zone_b = [d for d in dalles if (d.y_min + d.y_max) / 2 >= split_y]
        zones = []
        if zone_a:
            zones.append((
                min(d.x_min for d in zone_a),
                max(d.x_max for d in zone_a),
                min(d.y_min for d in zone_a),
                max(d.y_max for d in zone_a),
            ))
        if zone_b:
            zones.append((
                min(d.x_min for d in zone_b),
                max(d.x_max for d in zone_b),
                min(d.y_min for d in zone_b),
                max(d.y_max for d in zone_b),
            ))
        return zones

    return [(x_min, x_max, y_min, y_max)]


def _create_planar_brep(
    x_min: float, x_max: float,
    y_min: float, y_max: float,
    z: float,
) -> rhino3dm.Brep | None:
    """Create a single-face horizontal planar Brep at the given Z."""
    plane = rhino3dm.Plane(
        rhino3dm.Point3d(0, 0, z),
        rhino3dm.Vector3d(0, 0, 1),
    )
    srf = rhino3dm.PlaneSurface(
        plane,
        rhino3dm.Interval(x_min, x_max),
        rhino3dm.Interval(y_min, y_max),
    )
    return rhino3dm.Brep.CreateFromSurface(srf)


def _get_max_coque_id(model: rhino3dm.File3dm) -> int:
    """Find the highest Coque_NNNN id in the model."""
    max_id = 0
    for obj in model.Objects:
        name = obj.Attributes.Name
        if name and name.startswith("Coque_"):
            try:
                num = int(name.split("_")[1])
                if num > max_id:
                    max_id = num
            except (ValueError, IndexError):
                pass
    return max_id
