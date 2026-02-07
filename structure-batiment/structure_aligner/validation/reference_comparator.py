"""Reference comparator for V2 pipeline output validation.

Phase 7.1 - Compares output .3dm against a reference .3dm to validate
that the V2 pipeline produces results within acceptable tolerances.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import rhino3dm

logger = logging.getLogger(__name__)


@dataclass
class ObjectComparison:
    """Comparison result for a single named object."""
    name: str
    element_type: str = ""
    output_vertex_count: int = 0
    reference_vertex_count: int = 0
    matched_vertices: int = 0
    total_compared: int = 0
    match_rate: float = 0.0
    displacements: list[float] = field(default_factory=list)
    max_displacement: float = 0.0
    mean_displacement: float = 0.0


@dataclass
class ComparisonResult:
    """Comprehensive comparison between output and reference 3dm files."""
    output_3dm: str = ""
    reference_3dm: str = ""
    tolerance: float = 0.005

    # Object-level counts
    output_object_count: int = 0
    reference_object_count: int = 0
    common_objects: int = 0
    output_only_objects: int = 0
    reference_only_objects: int = 0

    # Vertex matching
    total_vertices_compared: int = 0
    vertices_matched: int = 0
    overall_match_rate: float = 0.0

    # Displacement distribution
    mean_displacement: float = 0.0
    median_displacement: float = 0.0
    p95_displacement: float = 0.0
    max_displacement: float = 0.0

    # Per-type breakdown
    type_breakdown: dict[str, dict] = field(default_factory=dict)

    # Lists
    output_only_names: list[str] = field(default_factory=list)
    reference_only_names: list[str] = field(default_factory=list)

    # Per-object details (optional, can be large)
    object_comparisons: list[dict] = field(default_factory=list)

    errors: list[str] = field(default_factory=list)


def compare_with_reference(
    output_3dm: Path,
    reference_3dm: Path,
    tolerance: float = 0.005,
    include_object_details: bool = False,
) -> ComparisonResult:
    """Compare output 3dm against a reference 3dm file.

    Args:
        output_3dm: Path to the pipeline output .3dm file.
        reference_3dm: Path to the reference .3dm file.
        tolerance: Position matching tolerance in meters (default: 5mm).
        include_object_details: If True, include per-object comparison details.

    Returns:
        ComparisonResult with all metrics.
    """
    result = ComparisonResult(
        output_3dm=str(output_3dm),
        reference_3dm=str(reference_3dm),
        tolerance=tolerance,
    )

    # Load models
    out_model = rhino3dm.File3dm.Read(str(output_3dm))
    if out_model is None:
        result.errors.append(f"Failed to read output 3dm: {output_3dm}")
        return result

    ref_model = rhino3dm.File3dm.Read(str(reference_3dm))
    if ref_model is None:
        result.errors.append(f"Failed to read reference 3dm: {reference_3dm}")
        return result

    # Index objects by name
    out_objects = _index_objects_by_name(out_model)
    ref_objects = _index_objects_by_name(ref_model)

    result.output_object_count = len(out_objects)
    result.reference_object_count = len(ref_objects)

    out_names = set(out_objects.keys())
    ref_names = set(ref_objects.keys())

    common_names = out_names & ref_names
    result.common_objects = len(common_names)
    result.output_only_objects = len(out_names - ref_names)
    result.reference_only_objects = len(ref_names - out_names)
    result.output_only_names = sorted(out_names - ref_names)
    result.reference_only_names = sorted(ref_names - out_names)

    # Compare common objects
    all_displacements: list[float] = []
    type_stats: dict[str, dict] = defaultdict(
        lambda: {"compared": 0, "matched": 0, "objects": 0}
    )

    for name in sorted(common_names):
        out_obj = out_objects[name]
        ref_obj = ref_objects[name]

        out_verts = _extract_vertices(out_obj.Geometry)
        ref_verts = _extract_vertices(ref_obj.Geometry)

        elem_type = _infer_element_type(name)
        type_stats[elem_type]["objects"] += 1

        obj_comp = ObjectComparison(
            name=name,
            element_type=elem_type,
            output_vertex_count=len(out_verts),
            reference_vertex_count=len(ref_verts),
        )

        # Compare vertex by vertex (index-based matching)
        n = min(len(out_verts), len(ref_verts))
        obj_comp.total_compared = n
        matched = 0

        for i in range(n):
            d = _distance_3d(out_verts[i], ref_verts[i])
            obj_comp.displacements.append(round(d, 6))
            all_displacements.append(d)

            type_stats[elem_type]["compared"] += 1
            if d <= tolerance:
                matched += 1
                type_stats[elem_type]["matched"] += 1

        obj_comp.matched_vertices = matched
        obj_comp.match_rate = (
            round(matched / n * 100, 1) if n > 0 else 100.0
        )
        if obj_comp.displacements:
            obj_comp.max_displacement = round(max(obj_comp.displacements), 6)
            obj_comp.mean_displacement = round(
                sum(obj_comp.displacements) / len(obj_comp.displacements), 6
            )

        if include_object_details:
            result.object_comparisons.append(asdict(obj_comp))

    # Overall stats
    result.total_vertices_compared = len(all_displacements)
    result.vertices_matched = sum(1 for d in all_displacements if d <= tolerance)
    result.overall_match_rate = (
        round(result.vertices_matched / len(all_displacements) * 100, 1)
        if all_displacements
        else 0.0
    )

    # Displacement distribution
    if all_displacements:
        sorted_d = sorted(all_displacements)
        result.mean_displacement = round(
            sum(sorted_d) / len(sorted_d), 6
        )
        n = len(sorted_d)
        result.median_displacement = round(
            sorted_d[n // 2] if n % 2 == 1
            else (sorted_d[n // 2 - 1] + sorted_d[n // 2]) / 2,
            6,
        )
        p95_idx = min(int(n * 0.95), n - 1)
        result.p95_displacement = round(sorted_d[p95_idx], 6)
        result.max_displacement = round(sorted_d[-1], 6)

    # Type breakdown
    result.type_breakdown = {
        t: {
            "objects": s["objects"],
            "vertices_compared": s["compared"],
            "vertices_matched": s["matched"],
            "match_rate": round(s["matched"] / s["compared"] * 100, 1)
            if s["compared"] > 0
            else 0.0,
        }
        for t, s in sorted(type_stats.items())
    }

    logger.info(
        "Comparison: %d common objects, %d/%d vertices matched (%.1f%%) within %.3fm",
        result.common_objects,
        result.vertices_matched,
        result.total_vertices_compared,
        result.overall_match_rate,
        tolerance,
    )

    return result


def _index_objects_by_name(
    model: rhino3dm.File3dm,
) -> dict[str, rhino3dm.File3dmObject]:
    """Index model objects by their Name attribute, skipping unnamed."""
    objects: dict[str, rhino3dm.File3dmObject] = {}
    for obj in model.Objects:
        name = obj.Attributes.Name
        if name:
            if name in objects:
                logger.warning("Duplicate object name '%s' — last instance used", name)
            objects[name] = obj
    return objects


def _extract_vertices(
    geom: rhino3dm.GeometryBase,
) -> list[tuple[float, float, float]]:
    """Extract vertex positions from a geometry object."""
    verts: list[tuple[float, float, float]] = []

    if isinstance(geom, rhino3dm.Brep):
        for i in range(len(geom.Vertices)):
            v = geom.Vertices[i]
            loc = v.Location
            verts.append((loc.X, loc.Y, loc.Z))
    elif isinstance(geom, rhino3dm.PolylineCurve):
        for i in range(geom.PointCount):
            p = geom.Point(i)
            verts.append((p.X, p.Y, p.Z))
    elif isinstance(geom, rhino3dm.LineCurve):
        p1 = geom.PointAtStart
        p2 = geom.PointAtEnd
        verts.append((p1.X, p1.Y, p1.Z))
        verts.append((p2.X, p2.Y, p2.Z))
    elif isinstance(geom, rhino3dm.NurbsCurve):
        for i in range(len(geom.Points)):
            cp = geom.Points[i]
            w = cp.W if cp.W != 0 else 1.0
            verts.append((cp.X / w, cp.Y / w, cp.Z / w))
    elif isinstance(geom, rhino3dm.Point):
        loc = geom.Location
        verts.append((loc.X, loc.Y, loc.Z))

    return verts


def _distance_3d(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    """Euclidean distance between two 3D points."""
    return math.sqrt(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    )


def _infer_element_type(name: str) -> str:
    """Infer element type from object name."""
    lower = name.lower()
    if lower.startswith("dalle"):
        return "dalle"
    if lower.startswith("voile"):
        return "voile"
    if lower.startswith("appuis") or lower.startswith("appui"):
        return "appui"
    if lower.startswith("poteau"):
        return "poteau"
    if lower.startswith("poutre"):
        return "poutre"
    if lower.startswith("filaire"):
        return "filaire"
    return "other"
