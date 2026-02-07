"""Object-level transformation rules: removal operations.

Implements Phase 4 of the V2 pipeline:
- Dalle (slab) removal: remove all floor slabs except roof
- Obsolete support removal: remove supports at removed axis positions
- Multi-face voile removal: identify and remove multi-face wall Breps
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import rhino3dm

from structure_aligner.config import PipelineConfig

logger = logging.getLogger(__name__)


@dataclass
class ObjectTransformResult:
    """Tracks object removal/addition counts."""
    dalles_removed: int = 0
    dalles_kept: int = 0
    supports_removed: int = 0
    voiles_removed: int = 0
    removed_voile_names: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def remove_dalles(
    model: rhino3dm.File3dm,
    db_path: Path,
    config: PipelineConfig,
) -> tuple[int, int]:
    """Remove all DALLE objects except roof (Z > roof_z_threshold).

    Queries the structural DB for element names with type='DALLE', then
    removes matching objects from the 3dm model unless their maximum Z
    coordinate exceeds the roof threshold.

    Args:
        model: The rhino3dm model (modified in place).
        db_path: Path to the structural database (geometrie_2.db).
        config: Pipeline configuration with roof_z_threshold.

    Returns:
        Tuple of (removed_count, kept_count).
    """
    dalle_names = _load_names_by_type(db_path, "DALLE")
    if not dalle_names:
        logger.warning("No DALLE entries found in database %s", db_path)
        return 0, 0

    # Build index: name -> list of (object_index, max_z)
    to_remove: list[int] = []
    kept = 0

    for i in range(len(model.Objects)):
        obj = model.Objects[i]
        name = obj.Attributes.Name
        if name not in dalle_names:
            continue

        geom = obj.Geometry
        max_z = _get_max_z(geom)

        if max_z is None:
            logger.warning("Dalle %s has unrecognized geometry; removing", name)
            to_remove.append(i)
        elif max_z > config.roof_z_threshold:
            kept += 1
            logger.debug("Keeping roof dalle %s (max_z=%.2f)", name, max_z)
        else:
            to_remove.append(i)

    # Remove in reverse order to preserve indices
    removed = _remove_objects_by_indices(model, to_remove)

    logger.info(
        "Dalle removal: %d removed, %d kept (roof)",
        removed, kept,
    )
    return removed, kept


def remove_obsolete_supports(
    model: rhino3dm.File3dm,
    db_path: Path,
    removed_axis_x: list[float] | None = None,
    tolerance: float = 0.01,
) -> int:
    """Remove support points at axis lines that no longer exist.

    Research finding: 7 Appuis removed, all at X=-10.830, Z=-4.440.
    This function removes support Point objects whose X coordinate matches
    a removed axis line position.

    Args:
        model: The rhino3dm model (modified in place).
        db_path: Path to the structural database.
        removed_axis_x: List of removed X axis line positions. If None,
            defaults to [-10.830] based on research findings.
        tolerance: Position matching tolerance in meters.

    Returns:
        Number of supports removed.
    """
    if removed_axis_x is None:
        removed_axis_x = [-10.830]

    support_names = _load_support_names(db_path)
    if not support_names:
        logger.warning("No support entries found in database %s", db_path)
        return 0

    to_remove: list[int] = []

    for i in range(len(model.Objects)):
        obj = model.Objects[i]
        name = obj.Attributes.Name
        if name not in support_names:
            continue

        geom = obj.Geometry
        if not isinstance(geom, rhino3dm.Point):
            continue

        x = geom.Location.X
        for removed_x in removed_axis_x:
            if abs(x - removed_x) <= tolerance:
                to_remove.append(i)
                logger.debug(
                    "Removing obsolete support %s at X=%.3f",
                    name, x,
                )
                break

    removed = _remove_objects_by_indices(model, to_remove)
    logger.info("Obsolete support removal: %d removed", removed)
    return removed


def remove_multiface_voiles(
    model: rhino3dm.File3dm,
    db_path: Path,
    min_faces: int = 2,
) -> list[str]:
    """Identify and remove multi-face voile Breps.

    Multi-face voiles (walls with >1 Brep face) are geometric artifacts
    that should be replaced with simplified single-face per-floor segments
    (done in Phase 5).

    Args:
        model: The rhino3dm model (modified in place).
        db_path: Path to the structural database.
        min_faces: Minimum face count to consider as multi-face (default 2).

    Returns:
        List of removed voile names (for Phase 5 replacement).
    """
    voile_names = _load_names_by_type(db_path, "VOILE")
    if not voile_names:
        logger.warning("No VOILE entries found in database %s", db_path)
        return []

    to_remove: list[int] = []
    removed_names: list[str] = []

    for i in range(len(model.Objects)):
        obj = model.Objects[i]
        name = obj.Attributes.Name
        if name not in voile_names:
            continue

        geom = obj.Geometry
        if not isinstance(geom, rhino3dm.Brep):
            continue

        face_count = len(geom.Faces)
        if face_count >= min_faces:
            to_remove.append(i)
            removed_names.append(name)
            logger.debug(
                "Removing multi-face voile %s (%d faces)",
                name, face_count,
            )

    _remove_objects_by_indices(model, to_remove)
    logger.info(
        "Multi-face voile removal: %d removed (min_faces=%d)",
        len(removed_names), min_faces,
    )
    return removed_names


# =========================================================================
# Internal helpers
# =========================================================================


def _load_names_by_type(db_path: Path, element_type: str) -> set[str]:
    """Load element names of a given type from the shell table."""
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM shell WHERE type = ?",
            (element_type,),
        )
        return {row[0] for row in cursor.fetchall()}
    except sqlite3.OperationalError as e:
        logger.warning("Could not query shell table: %s", e)
        return set()
    finally:
        conn.close()


def _load_support_names(db_path: Path) -> set[str]:
    """Load all support names from the support table."""
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM support")
        return {row[0] for row in cursor.fetchall()}
    except sqlite3.OperationalError as e:
        logger.warning("Could not query support table: %s", e)
        return set()
    finally:
        conn.close()


def _get_max_z(geom: rhino3dm.GeometryBase) -> float | None:
    """Get the maximum Z coordinate from a geometry object."""
    if isinstance(geom, rhino3dm.Brep):
        if len(geom.Vertices) == 0:
            return None
        return max(geom.Vertices[i].Location.Z for i in range(len(geom.Vertices)))
    elif isinstance(geom, rhino3dm.Point):
        return geom.Location.Z
    elif isinstance(geom, rhino3dm.LineCurve):
        return max(geom.PointAtStart.Z, geom.PointAtEnd.Z)
    elif isinstance(geom, rhino3dm.PolylineCurve):
        if geom.PointCount == 0:
            return None
        return max(geom.Point(i).Z for i in range(geom.PointCount))
    return None


def _remove_objects_by_indices(model: rhino3dm.File3dm, indices: list[int]) -> int:
    """Remove objects from model by their indices (handles reverse ordering).

    The rhino3dm library uses GUID-based deletion, not index-based.

    Returns:
        Number of objects actually removed.
    """
    if not indices:
        return 0

    # Collect GUIDs for objects to remove
    guids = []
    for i in indices:
        obj = model.Objects[i]
        guids.append(obj.Attributes.Id)

    count_before = len(model.Objects)
    for guid in guids:
        model.Objects.Delete(guid)

    removed = count_before - len(model.Objects)
    if removed != len(guids):
        logger.warning(
            "Expected to delete %d objects but removed %d",
            len(guids), removed,
        )

    return removed
