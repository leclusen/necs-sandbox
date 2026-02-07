"""Structural grid line generation.

Phase 5.5 - Creates unnamed horizontal PolylineCurves spanning
the building width for each Y axis line position.
"""

from __future__ import annotations

import logging

import rhino3dm

from structure_aligner.config import AxisLine

logger = logging.getLogger(__name__)


def generate_grid_lines(
    model: rhino3dm.File3dm,
    axis_lines_y: list[AxisLine],
    x_extent: tuple[float, float],
    z_level: float = 0.0,
    default_layer_index: int = 0,
    files_layer_index: int | None = None,
    files_y_positions: list[float] | None = None,
) -> int:
    """Add structural grid lines as unnamed PolylineCurves.

    For each Y axis line, creates a horizontal PolylineCurve spanning
    the full X extent of the building.

    Args:
        model: The rhino3dm model to add objects to.
        axis_lines_y: Y axis lines defining grid positions.
        x_extent: (x_min, x_max) building footprint extent.
        z_level: Z position for grid lines (typically 0).
        default_layer_index: Layer index for "Defaut" grid lines.
        files_layer_index: Layer index for "Files" grid lines.
        files_y_positions: Y positions that go on the "Files" layer
            instead of default. If None, all go on default layer.

    Returns:
        Number of grid line curves added.
    """
    x_min, x_max = x_extent
    added = 0

    files_set = set(files_y_positions) if files_y_positions else set()

    for ay in axis_lines_y:
        y = ay.position

        p1 = rhino3dm.Point3d(x_min, y, z_level)
        p2 = rhino3dm.Point3d(x_max, y, z_level)
        curve = rhino3dm.PolylineCurve([p1, p2])

        attr = rhino3dm.ObjectAttributes()
        # Grid lines are unnamed
        attr.Name = ""

        if y in files_set and files_layer_index is not None:
            attr.LayerIndex = files_layer_index
        else:
            attr.LayerIndex = default_layer_index

        model.Objects.AddCurve(curve, attr)
        added += 1

    logger.info("Grid line generation: %d unnamed curves added", added)
    return added
