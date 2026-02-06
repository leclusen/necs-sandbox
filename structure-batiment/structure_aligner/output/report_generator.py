import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from structure_aligner.config import AlignmentResult
from structure_aligner.output.validator import ValidationResult

logger = logging.getLogger(__name__)


def generate_report(
    result: AlignmentResult,
    validation: ValidationResult,
    input_db: Path,
    output_db: Path | None,
    execution_time_seconds: float,
    report_path: Path,
) -> Path:
    """
    Generate a comprehensive JSON report per PRD F-10.

    Args:
        result: Complete alignment result.
        validation: Post-alignment validation result.
        input_db: Path to the input database.
        output_db: Path to the output database (None for dry-run).
        execution_time_seconds: Total pipeline execution time.
        report_path: Where to write the JSON report.

    Returns:
        Path to the generated report file.
    """
    aligned = result.aligned_vertices
    threads = result.threads

    # Compute displacement statistics
    displacements = [v.displacement_total for v in aligned]
    aligned_count = sum(1 for v in aligned if v.aligned_axis != "none")
    isolated_count = len(aligned) - aligned_count

    # Group threads by axis
    threads_by_axis = {"X": [], "Y": [], "Z": []}
    for t in threads:
        threads_by_axis[t.axis].append({
            "fil_id": t.fil_id,
            "reference": t.reference,
            "delta": t.delta,
            "vertex_count": t.vertex_count,
        })

    # Isolated vertices detail
    isolated_details = []
    for v in aligned:
        if v.aligned_axis == "none":
            isolated_details.append({
                "vertex_id": v.id,
                "element_id": v.element_id,
                "coordinates": [v.x_original, v.y_original, v.z_original],
                "reason": "no_nearby_cluster",
            })

    import numpy as np
    disp_array = np.array(displacements) if displacements else np.array([0.0])

    report_data = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_database": str(input_db),
            "output_database": str(output_db) if output_db else None,
            "execution_time_seconds": round(execution_time_seconds, 2),
            "software_version": "0.1.0",
            "dry_run": output_db is None,
        },
        "parameters": {
            "alpha": result.config.alpha,
            "clustering_method": "dbscan",
            "min_cluster_size": result.config.min_cluster_size,
            "rounding_precision": result.config.rounding_precision,
        },
        "statistics": {
            "total_vertices": len(aligned),
            "aligned_vertices": aligned_count,
            "isolated_vertices": isolated_count,
            "alignment_rate_percent": round(
                aligned_count / len(aligned) * 100, 1
            ) if aligned else 0,
        },
        "axis_statistics": {
            stat.axis: {
                "mean": stat.mean,
                "median": stat.median,
                "std": stat.std,
                "min": stat.min,
                "max": stat.max,
                "q1": stat.q1,
                "q3": stat.q3,
                "unique_count": stat.unique_count,
                "total_count": stat.total_count,
            }
            for stat in result.statistics
        },
        "threads_detected": threads_by_axis,
        "displacement_statistics": {
            "mean_meters": round(float(np.mean(disp_array)), 6),
            "median_meters": round(float(np.median(disp_array)), 6),
            "max_meters": round(float(np.max(disp_array)), 6),
            "std_meters": round(float(np.std(disp_array)), 6),
            "note": "3D Euclidean displacement (for reporting). Per-axis constraint enforced separately.",
        },
        "isolated_vertices": isolated_details[:100],  # Cap at 100 for readability
        "isolated_vertices_total": len(isolated_details),
        "validation": {
            "passed": validation.passed,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail}
                for c in validation.checks
            ],
        },
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
    logger.info("Alignment report written to %s", report_path)

    return report_path
