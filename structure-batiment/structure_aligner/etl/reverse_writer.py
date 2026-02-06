from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import rhino3dm

from structure_aligner.etl.reverse_reader import AlignedElement, AlignedVertexCoord

logger = logging.getLogger(__name__)


@dataclass
class ReverseETLReport:
    output_path: Path
    report_path: Path
    total_objects: int = 0
    updated_objects: int = 0
    updated_vertices: int = 0
    skipped_objects: list[str] = field(default_factory=list)
    skipped_unsupported: list[str] = field(default_factory=list)
    mismatched_objects: list[str] = field(default_factory=list)
    brep_residual_warnings: list[tuple[str, float]] = field(default_factory=list)
    max_displacement_m: float = 0.0
    total_displacement_sum: float = 0.0


def write_aligned_3dm(
    template_3dm: Path,
    aligned_elements: dict[str, AlignedElement],
    output_path: Path,
) -> ReverseETLReport:
    """Read template .3dm, update vertex coordinates in-place, write output."""
    if not template_3dm.exists():
        raise FileNotFoundError(f"Template .3dm not found: {template_3dm}")

    model = rhino3dm.File3dm.Read(str(template_3dm))
    if model is None:
        raise RuntimeError(f"Failed to read template .3dm: {template_3dm}")

    report_path = output_path.with_suffix(".reverse_etl_report.json")
    report = ReverseETLReport(output_path=output_path, report_path=report_path)
    report.total_objects = len(model.Objects)

    for obj in model.Objects:
        name = obj.Attributes.Name
        if not name:
            report.skipped_objects.append(f"unnamed-object-layer-{obj.Attributes.LayerIndex}")
            continue

        element = aligned_elements.get(name)
        if element is None:
            report.skipped_objects.append(name)
            continue

        geom = obj.Geometry
        vertices = element.vertices

        # Skip elements with no vertices (e.g., db_only elements)
        if not vertices:
            continue

        success, vertex_count, brep_warning = _update_geometry(geom, vertices, name)

        if success is None:
            # Unsupported geometry type
            report.skipped_unsupported.append(f"{name} ({type(geom).__name__})")
            logger.warning("Unsupported geometry type %s for element %s", type(geom).__name__, name)
            continue

        if not success:
            # Vertex count mismatch
            report.mismatched_objects.append(name)
            continue

        report.updated_objects += 1
        report.updated_vertices += vertex_count

        if brep_warning:
            report.brep_residual_warnings.append(brep_warning)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.Write(str(output_path), 0)
    logger.info("Written aligned .3dm to %s", output_path)

    # Generate report
    _write_report(report, template_3dm, aligned_elements)

    return report


def _update_geometry(
    geom: rhino3dm.GeometryBase,
    vertices: list[AlignedVertexCoord],
    name: str,
) -> tuple[bool | None, int, tuple[str, float] | None]:
    """Dispatch to geometry-specific update. Returns (success, vertex_count, brep_warning).

    success=None means unsupported geometry type.
    success=False means vertex count mismatch.
    success=True means update succeeded.
    """
    if isinstance(geom, rhino3dm.Point):
        return _update_point(geom, vertices, name)
    elif isinstance(geom, rhino3dm.LineCurve):
        return _update_line_curve(geom, vertices, name)
    elif isinstance(geom, rhino3dm.PolylineCurve):
        return _update_polyline_curve(geom, vertices, name)
    elif isinstance(geom, rhino3dm.NurbsCurve):
        return _update_nurbs_curve(geom, vertices, name)
    elif isinstance(geom, rhino3dm.Brep):
        return _update_brep(geom, vertices, name)
    else:
        return (None, 0, None)


def _update_point(
    geom: rhino3dm.Point,
    vertices: list[AlignedVertexCoord],
    name: str,
) -> tuple[bool, int, None]:
    if len(vertices) != 1:
        logger.warning("Point %s: expected 1 vertex, got %d", name, len(vertices))
        return (False, 0, None)
    v = vertices[0]
    geom.Location = rhino3dm.Point3d(v.x, v.y, v.z)
    return (True, 1, None)


def _update_line_curve(
    geom: rhino3dm.LineCurve,
    vertices: list[AlignedVertexCoord],
    name: str,
) -> tuple[bool, int, None]:
    if len(vertices) != 2:
        logger.warning("LineCurve %s: expected 2 vertices, got %d", name, len(vertices))
        return (False, 0, None)
    # Sort by vertex_index to ensure correct order
    sorted_verts = sorted(vertices, key=lambda v: v.vertex_index)
    geom.SetStartPoint(rhino3dm.Point3d(sorted_verts[0].x, sorted_verts[0].y, sorted_verts[0].z))
    geom.SetEndPoint(rhino3dm.Point3d(sorted_verts[1].x, sorted_verts[1].y, sorted_verts[1].z))
    return (True, 2, None)


def _update_polyline_curve(
    geom: rhino3dm.PolylineCurve,
    vertices: list[AlignedVertexCoord],
    name: str,
) -> tuple[bool, int, None]:
    if len(vertices) != geom.PointCount:
        logger.warning("PolylineCurve %s: expected %d vertices, got %d", name, geom.PointCount, len(vertices))
        return (False, 0, None)
    sorted_verts = sorted(vertices, key=lambda v: v.vertex_index)
    for v in sorted_verts:
        geom.SetPoint(v.vertex_index, rhino3dm.Point3d(v.x, v.y, v.z))
    return (True, len(vertices), None)


def _update_nurbs_curve(
    geom: rhino3dm.NurbsCurve,
    vertices: list[AlignedVertexCoord],
    name: str,
) -> tuple[bool, int, None]:
    if len(vertices) != len(geom.Points):
        logger.warning("NurbsCurve %s: expected %d control points, got %d", name, len(geom.Points), len(vertices))
        return (False, 0, None)
    sorted_verts = sorted(vertices, key=lambda v: v.vertex_index)
    for v in sorted_verts:
        # Preserve existing W weight
        existing_point = geom.Points[v.vertex_index]
        w = existing_point.W
        geom.Points[v.vertex_index] = rhino3dm.Point4d(v.x, v.y, v.z, w)
    return (True, len(vertices), None)


def _update_brep(
    geom: rhino3dm.Brep,
    vertices: list[AlignedVertexCoord],
    name: str,
) -> tuple[bool, int, tuple[str, float] | None]:
    """Hybrid Transform + per-vertex fixup strategy."""
    brep_vertex_count = len(geom.Vertices)
    if len(vertices) != brep_vertex_count:
        logger.warning("Brep %s: expected %d vertices, got %d", name, brep_vertex_count, len(vertices))
        return (False, 0, None)

    sorted_verts = sorted(vertices, key=lambda v: v.vertex_index)

    # Step 1: Compute mean displacement
    mean_dx = 0.0
    mean_dy = 0.0
    mean_dz = 0.0
    for v in sorted_verts:
        orig = geom.Vertices[v.vertex_index].Location
        mean_dx += v.x - orig.X
        mean_dy += v.y - orig.Y
        mean_dz += v.z - orig.Z
    n = len(sorted_verts)
    mean_dx /= n
    mean_dy /= n
    mean_dz /= n

    # Step 2: Apply bulk translation (moves vertices, edges, surfaces)
    xform = rhino3dm.Transform.Translation(mean_dx, mean_dy, mean_dz)
    geom.Transform(xform)

    # Step 3: Per-vertex fixup for residuals
    max_residual = 0.0
    for v in sorted_verts:
        current = geom.Vertices[v.vertex_index].Location
        residual = math.sqrt(
            (v.x - current.X) ** 2 + (v.y - current.Y) ** 2 + (v.z - current.Z) ** 2
        )
        if residual > 1e-9:
            geom.Vertices[v.vertex_index].Location = rhino3dm.Point3d(v.x, v.y, v.z)
        max_residual = max(max_residual, residual)

    brep_warning = None
    if max_residual > 0.001:  # > 1mm
        brep_warning = (name, max_residual)
        logger.debug("Brep %s edge desync residual: %.6fm", name, max_residual)

    return (True, len(vertices), brep_warning)


def _write_report(
    report: ReverseETLReport,
    template_3dm: Path,
    aligned_elements: dict[str, AlignedElement],
) -> None:
    """Write JSON validation report."""
    # Compute brep residual stats
    residuals_mm = [residual * 1000 for _name, residual in report.brep_residual_warnings]

    report_data = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "template_3dm": str(template_3dm),
            "output_3dm": str(report.output_path),
            "software_version": "0.1.0",
        },
        "statistics": {
            "total_objects": report.total_objects,
            "updated_objects": report.updated_objects,
            "updated_vertices": report.updated_vertices,
            "skipped_not_in_db": len(report.skipped_objects),
            "skipped_unsupported_geometry": len(report.skipped_unsupported),
            "vertex_count_mismatches": len(report.mismatched_objects),
        },
        "brep_edge_desync": {
            "breps_with_residual": len(report.brep_residual_warnings),
            "max_residual_mm": max(residuals_mm) if residuals_mm else 0.0,
            "mean_residual_mm": sum(residuals_mm) / len(residuals_mm) if residuals_mm else 0.0,
            "details": [
                f"{name}: max_residual={residual:.6f}m"
                for name, residual in report.brep_residual_warnings[:50]
            ],
        },
        "warnings": report.skipped_unsupported,
        "skipped_objects": report.skipped_objects[:50],
        "mismatched_objects": report.mismatched_objects,
    }

    report.report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
    logger.info("Reverse ETL report written to %s", report.report_path)
