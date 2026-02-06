import logging
from structure_aligner.config import AlignmentConfig, Thread, AlignedVertex
from structure_aligner.db.reader import InputVertex
from structure_aligner.alignment.geometry import euclidean_displacement, find_matching_thread

logger = logging.getLogger(__name__)


def align_vertices(
    vertices: list[InputVertex],
    threads_x: list[Thread],
    threads_y: list[Thread],
    threads_z: list[Thread],
    config: AlignmentConfig,
) -> list[AlignedVertex]:
    """
    Align all vertices to their nearest threads.

    For each vertex, tries to match each axis coordinate (X, Y, Z)
    to a thread. If matched, the coordinate is snapped to the thread's
    reference value. If not matched, the original coordinate is preserved.

    Displacement is enforced PER-AXIS (PRD CF-02, lines 272-273):
      abs(vertex.coord - thread.reference) <= alpha
    This is guaranteed by find_matching_thread which only returns threads
    within alpha. The 3D Euclidean displacement is computed for reporting only.

    Args:
        vertices: Input vertices to align.
        threads_x: Detected threads for X axis.
        threads_y: Detected threads for Y axis.
        threads_z: Detected threads for Z axis.
        config: Alignment configuration.

    Returns:
        List of AlignedVertex with original and aligned coordinates.
    """
    ndigits = config.rounding_ndigits
    aligned = []
    for v in vertices:
        # Try matching each axis (per-axis displacement guaranteed <= alpha)
        tx = find_matching_thread(v.x, threads_x, config.alpha)
        ty = find_matching_thread(v.y, threads_y, config.alpha)
        tz = find_matching_thread(v.z, threads_z, config.alpha)

        new_x = tx.reference if tx else v.x
        new_y = ty.reference if ty else v.y
        new_z = tz.reference if tz else v.z

        # Build aligned_axis string
        axes = []
        if tx: axes.append("X")
        if ty: axes.append("Y")
        if tz: axes.append("Z")
        aligned_axis = "".join(axes) if axes else "none"

        # Calculate total 3D displacement (for REPORTING only, not for constraint)
        displacement = euclidean_displacement(v.x, v.y, v.z, new_x, new_y, new_z)

        aligned.append(AlignedVertex(
            id=v.id,
            element_id=v.element_id,
            x=round(new_x, ndigits),
            y=round(new_y, ndigits),
            z=round(new_z, ndigits),
            vertex_index=v.vertex_index,
            x_original=v.x,
            y_original=v.y,
            z_original=v.z,
            aligned_axis=aligned_axis,
            fil_x_id=tx.fil_id if tx else None,
            fil_y_id=ty.fil_id if ty else None,
            fil_z_id=tz.fil_id if tz else None,
            displacement_total=round(displacement, 6),
        ))

    aligned_count = sum(1 for av in aligned if av.aligned_axis != "none")
    logger.info("Aligned %d/%d vertices (%.1f%%)", aligned_count, len(aligned),
                aligned_count / len(aligned) * 100 if aligned else 0)

    return aligned
