"""Filaire (column/beam centerline) generation at support positions.

Phase 5.4 - Creates vertical LineCurve/PolylineCurve/NurbsCurve
objects at support point positions, spanning floor-to-floor heights.
"""

from __future__ import annotations

import logging

import rhino3dm

logger = logging.getLogger(__name__)


def generate_filaire(
    model: rhino3dm.File3dm,
    support_positions: list[tuple[float, float, float]],
    floor_z_levels: tuple[float, ...],
    layer_index: int = 0,
    start_id: int | None = None,
) -> int:
    """Add Filaire centerlines at support positions.

    For each support position, creates a vertical line spanning from
    the support's Z to the next floor Z-level above it.

    The geometry type is chosen based on floor level:
    - NurbsCurve for Z=2.12 (lower floors)
    - PolylineCurve for higher floors
    - LineCurve for beams at Z=-4.44

    Args:
        model: The rhino3dm model to add objects to.
        support_positions: List of (x, y, z) from support placement.
        floor_z_levels: Known floor Z-levels.
        layer_index: Layer index for new objects.
        start_id: Starting ID for naming.

    Returns:
        Number of Filaire objects added.
    """
    if start_id is None:
        start_id = _get_max_filaire_id(model) + 1

    sorted_z = sorted(floor_z_levels)
    next_id = start_id
    added = 0

    for x, y, z in support_positions:
        # Find the next floor Z above this support's Z
        z_top = _next_floor_above(z, sorted_z)
        if z_top is None or z_top <= z:
            continue

        name = f"Filaire_{next_id}"
        next_id += 1

        attr = rhino3dm.ObjectAttributes()
        attr.Name = name
        attr.LayerIndex = layer_index

        geom = _create_vertical_geom(x, y, z, z_top)
        if isinstance(geom, rhino3dm.LineCurve):
            model.Objects.AddCurve(geom, attr)
        elif isinstance(geom, rhino3dm.NurbsCurve):
            model.Objects.AddCurve(geom, attr)
        elif isinstance(geom, rhino3dm.PolylineCurve):
            model.Objects.AddCurve(geom, attr)
        else:
            continue

        added += 1

    logger.info("Filaire generation: %d centerlines added", added)
    return added


def _next_floor_above(z: float, sorted_z: list[float], tol: float = 0.01) -> float | None:
    """Find the next floor level above z."""
    for fz in sorted_z:
        if fz > z + tol:
            return fz
    return None


def _create_vertical_geom(
    x: float, y: float, z_bot: float, z_top: float,
) -> rhino3dm.LineCurve | rhino3dm.PolylineCurve | rhino3dm.NurbsCurve:
    """Create vertical geometry based on floor level conventions.

    Research patterns:
    - NurbsCurve at Z=2.12->5.48 (40 objects)
    - PolylineCurve for most higher floors
    - LineCurve for beams at Z=-4.44
    """
    p_bot = rhino3dm.Point3d(x, y, z_bot)
    p_top = rhino3dm.Point3d(x, y, z_top)
    height = z_top - z_bot

    # Beams (horizontal or short spans at basement level)
    if abs(z_bot - (-4.44)) < 0.1 and height < 3.0:
        return rhino3dm.LineCurve(p_bot, p_top)

    # NurbsCurve for lower floors (Z=2.12)
    if abs(z_bot - 2.12) < 0.1:
        return rhino3dm.NurbsCurve.Create(False, 1, [p_bot, p_top])

    # PolylineCurve for everything else
    return rhino3dm.PolylineCurve([p_bot, p_top])


def _get_max_filaire_id(model: rhino3dm.File3dm) -> int:
    """Find the highest Filaire_NNNN id in the model."""
    max_id = 0
    for obj in model.Objects:
        name = obj.Attributes.Name
        if name and name.startswith("Filaire_"):
            try:
                num = int(name.split("_")[1])
                if num > max_id:
                    max_id = num
            except (ValueError, IndexError):
                pass
    return max_id
