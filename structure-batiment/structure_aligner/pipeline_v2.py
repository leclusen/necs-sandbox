"""V2 Pipeline: end-to-end structural alignment with object-level transformations.

Orchestrates all phases:
1. Load 3dm model + DB vertices/elements
2. Discover axis lines (Phase 2)
3. Per-element snap alignment (Phase 3)
4. Extract dalle/voile info before removal
5. Object removal (Phase 4)
6. Object addition (Phase 5)
7. Write output 3dm
8. Generate report
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import rhino3dm

from structure_aligner.config import AlignedVertex, AxisLine, ElementInfo, PipelineConfig

logger = logging.getLogger(__name__)


@dataclass
class PipelineV2Report:
    """Comprehensive report from a V2 pipeline run."""
    # Input
    input_3dm: str = ""
    input_db: str = ""
    output_3dm: str = ""
    timestamp: str = ""
    execution_time_s: float = 0.0

    # Axis lines
    axis_lines_x_count: int = 0
    axis_lines_y_count: int = 0

    # Alignment
    total_vertices: int = 0
    aligned_vertices: int = 0
    alignment_rate_pct: float = 0.0
    max_displacement_m: float = 0.0

    # Object removal
    dalles_removed: int = 0
    dalles_kept: int = 0
    supports_removed: int = 0
    voiles_removed: int = 0

    # Object addition
    dalles_consolidated: int = 0
    voiles_simplified: int = 0
    supports_added: int = 0
    filaire_added: int = 0
    grid_lines_added: int = 0

    # Final model
    final_object_count: int = 0

    errors: list[str] = field(default_factory=list)


def run_pipeline_v2(
    input_3dm: Path,
    input_db: Path,
    output_dir: Path,
    config: PipelineConfig | None = None,
    reference_3dm: Path | None = None,
) -> PipelineV2Report:
    """Run the complete V2 pipeline.

    Args:
        input_3dm: Path to the before .3dm file.
        input_db: Path to the structural database (.db).
        output_dir: Output directory for results.
        config: Pipeline configuration. Uses defaults if None.
        reference_3dm: Optional reference .3dm for comparison.

    Returns:
        PipelineV2Report with all metrics.
    """
    if config is None:
        config = PipelineConfig()

    start_time = time.time()
    report = PipelineV2Report(
        input_3dm=str(input_3dm),
        input_db=str(input_db),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Step 1: Load model and data ---
    logger.info("Step 1/8: Loading 3dm model and database")
    model = rhino3dm.File3dm.Read(str(input_3dm))
    if model is None:
        report.errors.append(f"Failed to read 3dm file: {input_3dm}")
        return report

    logger.info("  Model loaded: %d objects", len(model.Objects))

    # Load PRD database (need vertices + elements for alignment)
    prd_db = _find_prd_db(input_db, input_3dm)
    if prd_db is None:
        report.errors.append("No PRD database found. Run ETL first.")
        return report

    from structure_aligner.db.reader import load_vertices_with_elements
    vertices, elements = load_vertices_with_elements(prd_db)
    report.total_vertices = len(vertices)
    logger.info("  Loaded %d vertices, %d elements", len(vertices), len(elements))

    # --- Step 2: Discover axis lines ---
    logger.info("Step 2/8: Discovering axis lines")
    from structure_aligner.analysis.axis_selector import discover_axis_lines
    axis_x, axis_y = discover_axis_lines(vertices, config)
    report.axis_lines_x_count = len(axis_x)
    report.axis_lines_y_count = len(axis_y)
    logger.info("  Discovered %d X and %d Y axis lines", len(axis_x), len(axis_y))

    # --- Step 3: Per-element snap alignment ---
    logger.info("Step 3/8: Aligning elements")
    from structure_aligner.alignment.element_aligner import align_elements
    aligned = align_elements(vertices, elements, axis_x, axis_y, config)

    aligned_count = sum(1 for av in aligned if av.aligned_axis != "none")
    report.aligned_vertices = aligned_count
    report.alignment_rate_pct = round(
        aligned_count / len(aligned) * 100, 1
    ) if aligned else 0.0
    report.max_displacement_m = round(
        max((av.displacement_total for av in aligned), default=0.0), 4
    )
    logger.info(
        "  Aligned %d/%d vertices (%.1f%%)",
        aligned_count, len(aligned), report.alignment_rate_pct,
    )

    # --- Step 4: Extract info before removal ---
    logger.info("Step 4/8: Extracting info for object transformations")
    dalle_names = _load_names_by_type(input_db, "DALLE")
    voile_names_set = _load_names_by_type(input_db, "VOILE")

    from structure_aligner.transform.dalle_consolidator import extract_dalle_info
    dalle_infos = extract_dalle_info(model, dalle_names)
    non_roof_dalles = [d for d in dalle_infos if d.z < config.roof_z_threshold]

    from structure_aligner.transform.voile_simplifier import extract_voile_extents
    # We'll identify multi-face voiles first
    multiface_voile_names = _identify_multiface_voiles(model, voile_names_set)
    voile_extents = extract_voile_extents(model, multiface_voile_names)

    logger.info(
        "  Extracted %d dalle infos, %d voile extents",
        len(dalle_infos), len(voile_extents),
    )

    # --- Step 5: Object removal ---
    logger.info("Step 5/8: Removing objects")
    from structure_aligner.transform.object_rules import (
        remove_dalles,
        remove_multiface_voiles,
        remove_obsolete_supports,
    )

    dalles_removed, dalles_kept = remove_dalles(model, input_db, config)
    report.dalles_removed = dalles_removed
    report.dalles_kept = dalles_kept

    supports_removed = remove_obsolete_supports(model, input_db)
    report.supports_removed = supports_removed

    removed_voiles = remove_multiface_voiles(model, input_db)
    report.voiles_removed = len(removed_voiles)

    logger.info(
        "  Removed: %d dalles, %d supports, %d voiles",
        dalles_removed, supports_removed, len(removed_voiles),
    )

    # --- Step 6: Object addition ---
    logger.info("Step 6/8: Adding objects")
    from structure_aligner.transform.dalle_consolidator import consolidate_dalles
    dalles_consolidated = consolidate_dalles(
        model, non_roof_dalles, config.floor_z_levels
    )
    report.dalles_consolidated = dalles_consolidated

    from structure_aligner.transform.voile_simplifier import simplify_voiles
    voiles_simplified = simplify_voiles(model, voile_extents, config.floor_z_levels)
    report.voiles_simplified = voiles_simplified

    from structure_aligner.transform.support_placer import (
        place_support_points_at_columns,
    )
    # Place supports at column center positions snapped to nearest axis
    # intersection, avoiding the O(X*Y) grid scan with over-discovered axes.
    existing_columns = _build_column_positions(vertices, elements)
    logger.info("  Column centers: %d unique positions", len(existing_columns))
    supports_added, support_positions = place_support_points_at_columns(
        model, existing_columns, axis_x, axis_y,
        support_z_levels=(2.12, -4.44),
    )
    report.supports_added = supports_added

    from structure_aligner.transform.filaire_generator import generate_filaire
    filaire_added = generate_filaire(model, support_positions, config.floor_z_levels)
    report.filaire_added = filaire_added

    from structure_aligner.transform.grid_lines import generate_grid_lines

    # Compute X extent from axis lines
    if axis_x:
        x_min = min(al.position for al in axis_x)
        x_max = max(al.position for al in axis_x)
    else:
        x_min, x_max = -75.0, 5.0  # fallback

    grid_added = generate_grid_lines(model, axis_y, x_extent=(x_min, x_max))
    report.grid_lines_added = grid_added

    logger.info(
        "  Added: %d dalles, %d voiles, %d supports, %d filaire, %d grid lines",
        dalles_consolidated, voiles_simplified, supports_added,
        filaire_added, grid_added,
    )

    # --- Step 7: Apply vertex alignment to 3dm model ---
    # Safe ordering: Phase 4/5 only remove/add whole objects, never modify
    # surviving objects. So vertex indices from Phase 3 alignment remain valid.
    logger.info("Step 7/8: Applying vertex alignment to 3dm model")
    vertices_updated = _apply_alignment_to_model(model, aligned, elements)
    logger.info("  Updated %d vertices in 3dm model", vertices_updated)

    # --- Step 8: Write output ---
    logger.info("Step 8/8: Writing output")
    output_3dm = output_dir / "aligned_v2.3dm"
    model.Write(str(output_3dm), version=7)
    report.output_3dm = str(output_3dm)
    report.final_object_count = len(model.Objects)

    # Write report
    report.execution_time_s = round(time.time() - start_time, 2)
    report_path = output_dir / "pipeline_v2_report.json"
    _write_report(report, report_path)

    logger.info("Pipeline V2 complete in %.1fs", report.execution_time_s)
    logger.info("  Output: %s", output_3dm)
    logger.info("  Report: %s", report_path)
    logger.info("  Final model: %d objects", report.final_object_count)

    return report


# =========================================================================
# Internal helpers
# =========================================================================


def _build_column_positions(
    vertices: list,
    elements: dict[int, ElementInfo],
) -> dict[tuple[float, float], bool]:
    """Build column (x, y) center positions from poteau/appui elements.

    Computes the centroid of each column/appui element's vertices,
    returning one (x, y) position per element.
    """
    from collections import defaultdict

    column_types = {"poteau", "appui"}
    column_element_ids = {
        eid for eid, elem in elements.items() if elem.type in column_types
    }
    # Group vertices by element
    by_elem: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for v in vertices:
        if v.element_id in column_element_ids:
            by_elem[v.element_id].append((v.x, v.y))

    # Use centroid of each element
    positions: dict[tuple[float, float], bool] = {}
    for eid, coords in by_elem.items():
        cx = round(sum(c[0] for c in coords) / len(coords), 2)
        cy = round(sum(c[1] for c in coords) / len(coords), 2)
        positions[(cx, cy)] = True
    return positions


def _find_prd_db(input_db: Path, input_3dm: Path) -> Path | None:
    """Find the PRD database, either alongside input_db or generated by ETL."""
    # Check for *_prd.db alongside the structural DB
    prd_path = input_db.with_name(f"{input_db.stem}_prd.db")
    if prd_path.exists():
        return prd_path

    # Check in data/input/ — pick most recently modified if multiple exist
    data_dir = input_3dm.parent
    candidates = sorted(data_dir.glob("*_prd.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]

    return None


def _load_names_by_type(db_path: Path, element_type: str) -> set[str]:
    """Load element names from the shell table.

    Delegates to object_rules._load_names_by_type which includes
    OperationalError handling for missing tables.
    """
    from structure_aligner.transform.object_rules import (
        _load_names_by_type as _load_impl,
    )
    return _load_impl(db_path, element_type)


def _identify_multiface_voiles(
    model: rhino3dm.File3dm,
    voile_names: set[str],
    min_faces: int = 2,
) -> list[str]:
    """Find multi-face voile names without removing them."""
    result = []
    for obj in model.Objects:
        name = obj.Attributes.Name
        if name not in voile_names:
            continue
        geom = obj.Geometry
        if isinstance(geom, rhino3dm.Brep) and len(geom.Faces) >= min_faces:
            result.append(name)
    return result


def _apply_alignment_to_model(
    model: rhino3dm.File3dm,
    aligned_vertices: list[AlignedVertex],
    elements: dict[int, ElementInfo],
) -> int:
    """Apply aligned vertex coordinates back to the 3dm model objects.

    Maps aligned vertices back to named objects by element_id -> element name,
    then updates the Brep/curve/point vertex positions in-place.

    Note: For Breps, modifying Vertices[i].Location updates the control point
    but does not automatically recompute edges/faces/trims. This is acceptable
    for the small displacements typical of structural alignment (<1m). For
    large displacements, Brep topology may become invalid.
    """
    from collections import defaultdict
    by_name: dict[str, list] = defaultdict(list)
    for av in aligned_vertices:
        elem = elements.get(av.element_id)
        if elem:
            by_name[elem.name].append(av)

    updated = 0
    for obj in model.Objects:
        name = obj.Attributes.Name
        if not name or name not in by_name:
            continue

        verts = sorted(by_name[name], key=lambda v: v.vertex_index)
        geom = obj.Geometry

        if isinstance(geom, rhino3dm.Brep):
            for av in verts:
                if av.vertex_index < len(geom.Vertices):
                    geom.Vertices[av.vertex_index].Location = rhino3dm.Point3d(
                        av.x, av.y, av.z
                    )
                    updated += 1
        elif isinstance(geom, rhino3dm.LineCurve):
            for av in verts:
                if av.vertex_index == 0:
                    geom.SetStartPoint(rhino3dm.Point3d(av.x, av.y, av.z))
                    updated += 1
                elif av.vertex_index == 1:
                    geom.SetEndPoint(rhino3dm.Point3d(av.x, av.y, av.z))
                    updated += 1
        elif isinstance(geom, rhino3dm.PolylineCurve):
            for av in verts:
                if av.vertex_index < geom.PointCount:
                    geom.SetPoint(av.vertex_index, rhino3dm.Point3d(av.x, av.y, av.z))
                    updated += 1
        elif isinstance(geom, rhino3dm.NurbsCurve):
            for av in verts:
                if av.vertex_index < len(geom.Points):
                    geom.Points[av.vertex_index] = rhino3dm.Point4d(
                        av.x, av.y, av.z, 1.0
                    )
                    updated += 1
        elif isinstance(geom, rhino3dm.Point):
            for av in verts:
                if av.vertex_index == 0:
                    geom.Location = rhino3dm.Point3d(av.x, av.y, av.z)
                    updated += 1

    return updated


def _write_report(report: PipelineV2Report, path: Path) -> None:
    """Write pipeline report as JSON."""
    data = asdict(report)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
