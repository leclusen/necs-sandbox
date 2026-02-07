"""Voile (wall) simplification: replace multi-face Breps with single-face per-floor segments.

Phase 5.2 - For each removed multi-face voile, extract its planar extent
and create single-face segments split at floor Z-level boundaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import rhino3dm

logger = logging.getLogger(__name__)


@dataclass
class VoileExtent:
    """Geometric extent of a removed voile."""
    name: str
    # The wall's axis: "X" (varies in X, constant Y) or "Y" (varies in Y, constant X)
    orientation: str
    # Along-wall extent
    coord_min: float   # min X (or min Y)
    coord_max: float   # max X (or max Y)
    # Cross-wall position (the constant coordinate)
    cross_coord: float
    # Vertical extent
    z_min: float
    z_max: float
    # Thickness (for the narrow dimension)
    thickness: float
    # Layer index from the original object
    layer_index: int


def extract_voile_extents(
    model: rhino3dm.File3dm,
    voile_names: list[str],
) -> list[VoileExtent]:
    """Extract geometric extents from voile objects before removal.

    Call this BEFORE removing voiles to capture their geometry.
    """
    extents: list[VoileExtent] = []
    for obj in model.Objects:
        name = obj.Attributes.Name
        if name not in voile_names:
            continue
        geom = obj.Geometry
        if not isinstance(geom, rhino3dm.Brep) or len(geom.Vertices) == 0:
            continue

        xs = [geom.Vertices[i].Location.X for i in range(len(geom.Vertices))]
        ys = [geom.Vertices[i].Location.Y for i in range(len(geom.Vertices))]
        zs = [geom.Vertices[i].Location.Z for i in range(len(geom.Vertices))]

        x_range = max(xs) - min(xs)
        y_range = max(ys) - min(ys)

        # Known limitation: diagonal walls (>5° from axis) are approximated
        # as axis-aligned. This is acceptable for the structural model where
        # walls are predominantly axis-aligned.
        if x_range > y_range:
            orientation = "X"
            coord_min, coord_max = min(xs), max(xs)
            cross_coord = (min(ys) + max(ys)) / 2
            thickness = y_range
        else:
            orientation = "Y"
            coord_min, coord_max = min(ys), max(ys)
            cross_coord = (min(xs) + max(xs)) / 2
            thickness = x_range

        extents.append(VoileExtent(
            name=name,
            orientation=orientation,
            coord_min=coord_min,
            coord_max=coord_max,
            cross_coord=cross_coord,
            z_min=min(zs),
            z_max=max(zs),
            thickness=max(thickness, 0.15),  # minimum 15cm
            layer_index=obj.Attributes.LayerIndex,
        ))
    return extents


def simplify_voiles(
    model: rhino3dm.File3dm,
    voile_extents: list[VoileExtent],
    floor_z_levels: tuple[float, ...],
    layer_index: int = 0,
) -> int:
    """Create simplified single-face voile segments per floor.

    For each removed voile, splits its Z extent into floor-to-floor
    segments and creates a single-face planar Brep for each.

    Args:
        model: The rhino3dm model to add objects to.
        voile_extents: Geometric extents from removed voiles.
        floor_z_levels: Known floor Z-levels for splitting.
        layer_index: Default layer index for new objects.

    Returns:
        Number of simplified voile segments added.
    """
    if not voile_extents:
        return 0

    sorted_z = sorted(floor_z_levels)
    added = 0

    for extent in voile_extents:
        # Find floor boundaries within this voile's Z range
        z_boundaries = _get_floor_boundaries(
            extent.z_min, extent.z_max, sorted_z
        )

        if len(z_boundaries) < 2:
            # Single segment spanning the full height
            z_boundaries = [extent.z_min, extent.z_max]

        for i in range(len(z_boundaries) - 1):
            z_bot = z_boundaries[i]
            z_top = z_boundaries[i + 1]

            if z_top - z_bot < 0.1:  # skip very thin segments
                continue

            brep = _create_wall_brep(extent, z_bot, z_top)
            if brep is None:
                continue

            suffix = f"_{i}" if len(z_boundaries) > 2 else ""
            attr = rhino3dm.ObjectAttributes()
            attr.Name = f"{extent.name}{suffix}"
            attr.LayerIndex = extent.layer_index if extent.layer_index > 0 else layer_index
            model.Objects.AddBrep(brep, attr)
            added += 1

    logger.info("Voile simplification: %d segments added", added)
    return added


def _get_floor_boundaries(
    z_min: float, z_max: float, sorted_z: list[float], tol: float = 0.1,
) -> list[float]:
    """Get floor Z-levels that fall within the voile's Z range."""
    boundaries = [z_min]
    for z in sorted_z:
        if z_min + tol < z < z_max - tol:
            boundaries.append(z)
    boundaries.append(z_max)
    return sorted(set(boundaries))


def _create_wall_brep(
    extent: VoileExtent,
    z_bot: float,
    z_top: float,
) -> rhino3dm.Brep | None:
    """Create a single-face vertical planar Brep for a wall segment.

    Note: PlaneSurface parametric intervals map directly to world coordinates
    only when the plane is axis-aligned. This is valid here because walls are
    classified as X-oriented or Y-oriented (diagonal walls are approximated).
    """
    half_t = extent.thickness / 2

    if extent.orientation == "X":
        # Wall extends in X, thin in Y, vertical in Z
        # Plane normal = Y → parametric U maps to world X, V maps to world Z
        plane = rhino3dm.Plane(
            rhino3dm.Point3d(0, extent.cross_coord, 0),
            rhino3dm.Vector3d(0, 1, 0),
        )
        srf = rhino3dm.PlaneSurface(
            plane,
            rhino3dm.Interval(extent.coord_min, extent.coord_max),  # X extent
            rhino3dm.Interval(z_bot, z_top),                         # Z extent
        )
    else:
        # Wall extends in Y, thin in X, vertical in Z
        # Plane normal = X → parametric U maps to world Y, V maps to world Z
        plane = rhino3dm.Plane(
            rhino3dm.Point3d(extent.cross_coord, 0, 0),
            rhino3dm.Vector3d(1, 0, 0),
        )
        srf = rhino3dm.PlaneSurface(
            plane,
            rhino3dm.Interval(extent.coord_min, extent.coord_max),  # Y extent
            rhino3dm.Interval(z_bot, z_top),                         # Z extent
        )

    return rhino3dm.Brep.CreateFromSurface(srf)
