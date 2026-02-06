import click
import logging
from pathlib import Path

from structure_aligner.config import AlignmentConfig
from structure_aligner.utils.logger import setup_logging


@click.group()
def cli():
    """Structure Aligner - Geometric alignment for building structures."""
    pass


@cli.command()
@click.option("--input-3dm", required=True, type=click.Path(exists=True), help="Path to .3dm Rhino file")
@click.option("--input-db", required=True, type=click.Path(exists=True), help="Path to source .db file")
@click.option("--output", required=True, type=click.Path(), help="Path to output .db file")
@click.option("--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def etl(input_3dm: str, input_db: str, output: str, log_level: str):
    """Extract vertices from .3dm, link to .db metadata, produce PRD-compliant database."""
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    input_3dm_path = Path(input_3dm)
    input_db_path = Path(input_db)
    output_path = Path(output)

    from structure_aligner.etl.extractor import extract_vertices
    from structure_aligner.etl.transformer import transform
    from structure_aligner.etl.loader import load

    logger.info("Starting ETL pipeline")
    logger.info("  Input 3DM: %s", input_3dm_path)
    logger.info("  Input DB:  %s", input_db_path)
    logger.info("  Output:    %s", output_path)

    # Extract
    logger.info("Phase 1/3: Extracting vertices from .3dm")
    raw_vertices = extract_vertices(input_3dm_path)
    logger.info("  Extracted %d raw vertices from %d objects", raw_vertices.total_vertices, raw_vertices.total_objects)

    # Transform
    logger.info("Phase 2/3: Transforming and linking to database")
    result = transform(raw_vertices, input_db_path)
    logger.info("  Matched %d/%d elements", result.matched_count, result.total_count)
    logger.info("  Total vertices: %d", len(result.vertices))
    for name, count in result.unmatched:
        logger.warning("  Unmatched: %s (skipped)", name)

    # Load
    logger.info("Phase 3/3: Loading into output database")
    report = load(result, input_db_path, output_path)
    logger.info("  Output written to: %s", output_path)
    logger.info("  Validation report: %s", report.report_path)
    logger.info("ETL complete")


@cli.command()
@click.option("--input", "input_db", required=True, type=click.Path(exists=True),
              help="Path to PRD-compliant input database")
@click.option("--output", type=click.Path(), default=None,
              help="Path for output database (auto-generated if omitted)")
@click.option("--alpha", type=float, default=0.05,
              help="Tolerance in meters (default: 0.05)")
@click.option("--min-cluster-size", type=int, default=3,
              help="Minimum vertices per thread (default: 3)")
@click.option("--report", type=click.Path(), default=None,
              help="Path for JSON report (auto-generated if omitted)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Simulation mode: produce report only, no output DB")
@click.option("--log-level", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def align(input_db, output, alpha, min_cluster_size, report, dry_run, log_level):
    """Align vertices to detected threads within tolerance."""
    import time
    import numpy as np
    from datetime import datetime

    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    input_path = Path(input_db)
    config = AlignmentConfig(alpha=alpha, min_cluster_size=min_cluster_size)

    # Auto-generate output path if not provided
    if output is None and not dry_run:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = input_path.with_name(
            f"{input_path.stem}_aligned_{timestamp}.db"
        )
    elif output:
        output_path = Path(output)
    else:
        output_path = None

    # Auto-generate report path
    if report is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = input_path.with_name(f"alignment_report_{timestamp}.json")
    else:
        report_path = Path(report)

    start_time = time.time()

    logger.info("Starting alignment pipeline")
    logger.info("  Input:  %s", input_path)
    logger.info("  Output: %s", output_path or "(dry-run)")
    logger.info("  Alpha:  %.3fm", config.alpha)
    logger.info("  Mode:   %s", "dry-run" if dry_run else "full")

    # Step 1: Load vertices
    from structure_aligner.db.reader import load_vertices
    vertices = load_vertices(input_path)
    logger.info("Loaded %d vertices", len(vertices))

    # Step 2: Compute statistics
    from structure_aligner.analysis.statistics import compute_axis_statistics
    xs = np.array([v.x for v in vertices])
    ys = np.array([v.y for v in vertices])
    zs = np.array([v.z for v in vertices])

    stats = [
        compute_axis_statistics(xs, "X"),
        compute_axis_statistics(ys, "Y"),
        compute_axis_statistics(zs, "Z"),
    ]
    for s in stats:
        logger.info("  Axis %s: %d unique values, std=%.4f", s.axis, s.unique_count, s.std)

    # Step 3: Detect threads
    from structure_aligner.alignment.thread_detector import detect_threads
    threads_x = detect_threads(xs, "X", config)
    threads_y = detect_threads(ys, "Y", config)
    threads_z = detect_threads(zs, "Z", config)
    all_threads = threads_x + threads_y + threads_z
    logger.info("Detected %d threads (X:%d, Y:%d, Z:%d)",
                len(all_threads), len(threads_x), len(threads_y), len(threads_z))

    # Step 4: Align vertices
    from structure_aligner.alignment.processor import align_vertices
    aligned = align_vertices(vertices, threads_x, threads_y, threads_z, config)

    # Step 5: Validate
    from structure_aligner.output.validator import validate_alignment
    validation = validate_alignment(aligned, len(vertices), config)

    # Step 6: Build result
    from structure_aligner.config import AlignmentResult
    alignment_result = AlignmentResult(
        threads=all_threads,
        aligned_vertices=aligned,
        statistics=stats,
        config=config,
    )

    # Step 7: Write output DB (unless dry-run)
    if not dry_run and output_path:
        from structure_aligner.db.writer import write_aligned_db
        write_aligned_db(input_path, output_path, aligned)
        logger.info("Output database: %s", output_path)

    # Step 8: Generate report
    execution_time = time.time() - start_time
    from structure_aligner.output.report_generator import generate_report
    generate_report(
        alignment_result, validation,
        input_path, output_path if not dry_run else None,
        execution_time, report_path,
    )
    logger.info("Report: %s", report_path)

    # Summary
    aligned_count = sum(1 for v in aligned if v.aligned_axis != "none")
    rate = aligned_count / len(aligned) * 100 if aligned else 0
    max_disp = max((v.displacement_total for v in aligned), default=0)

    logger.info("Alignment complete in %.1fs", execution_time)
    logger.info("  %d/%d vertices aligned (%.1f%%)", aligned_count, len(aligned), rate)
    logger.info("  Max displacement: %.4fm (3D Euclidean, for reporting)", max_disp)
    logger.info("  Validation: %s", "PASSED" if validation.passed else "FAILED")


@cli.command("export-3dm")
@click.option("--input-db", required=True, type=click.Path(exists=True),
              help="Path to aligned or PRD-compliant database")
@click.option("--template-3dm", required=True, type=click.Path(exists=True),
              help="Path to original .3dm file used in forward ETL")
@click.option("--output", type=click.Path(), default=None,
              help="Path for output .3dm (auto-generated if omitted)")
@click.option("--report", type=click.Path(), default=None,
              help="Path for JSON validation report")
@click.option("--log-level", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def export_3dm(input_db, template_3dm, output, report, log_level):
    """Export aligned database back to a .3dm Rhino file."""
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    input_db_path = Path(input_db)
    template_path = Path(template_3dm)

    # Auto-generate output path if not provided
    if output is None:
        output_path = input_db_path.with_suffix(".3dm")
    else:
        output_path = Path(output)

    from structure_aligner.etl.reverse_reader import read_aligned_elements
    from structure_aligner.etl.reverse_writer import write_aligned_3dm

    logger.info("Starting reverse ETL (export-3dm)")
    logger.info("  Input DB:     %s", input_db_path)
    logger.info("  Template 3DM: %s", template_path)
    logger.info("  Output 3DM:   %s", output_path)

    # Read aligned elements from DB
    aligned_elements = read_aligned_elements(input_db_path)
    logger.info("  Read %d elements from database", len(aligned_elements))

    # Write aligned .3dm
    result = write_aligned_3dm(template_path, aligned_elements, output_path)

    logger.info("Reverse ETL complete")
    logger.info("  Updated %d/%d objects (%d vertices)", result.updated_objects, result.total_objects, result.updated_vertices)
    logger.info("  Skipped: %d not in DB, %d unsupported, %d mismatched",
                len(result.skipped_objects), len(result.skipped_unsupported), len(result.mismatched_objects))
    if result.brep_residual_warnings:
        logger.info("  Brep edge desync warnings: %d", len(result.brep_residual_warnings))
    logger.info("  Output: %s", output_path)
    logger.info("  Report: %s", result.report_path)


@cli.command()
@click.option("--input-3dm", required=True, type=click.Path(exists=True), help="Path to .3dm Rhino file")
@click.option("--input-db", required=True, type=click.Path(exists=True), help="Path to source .db file")
@click.option("--output", type=click.Path(), default=None,
              help="Path for final aligned database (auto-generated if omitted)")
@click.option("--alpha", type=float, default=0.05,
              help="Tolerance in meters (default: 0.05)")
@click.option("--min-cluster-size", type=int, default=3,
              help="Minimum vertices per thread (default: 3)")
@click.option("--report", type=click.Path(), default=None,
              help="Path for JSON report (auto-generated if omitted)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Simulation mode: produce report only, no aligned DB")
@click.option("--export-3dm", "do_export_3dm", is_flag=True, default=False,
              help="Also export aligned .3dm file")
@click.option("--log-level", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def pipeline(input_3dm, input_db, output, alpha, min_cluster_size, report, dry_run, do_export_3dm, log_level):
    """Run ETL then alignment in one go."""
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    input_3dm_path = Path(input_3dm)
    input_db_path = Path(input_db)

    # Intermediate PRD-compliant DB produced by ETL
    etl_output = input_db_path.with_name(f"{input_db_path.stem}_prd.db")

    logger.info("=== PIPELINE: ETL + ALIGN ===")

    # --- ETL ---
    ctx = click.Context(etl)
    ctx.invoke(etl, input_3dm=input_3dm, input_db=input_db,
               output=str(etl_output), log_level=log_level)

    # --- ALIGN (reuse the ETL output as input) ---
    ctx = click.Context(align)
    ctx.invoke(align, input_db=str(etl_output), output=output,
               alpha=alpha, min_cluster_size=min_cluster_size,
               report=report, dry_run=dry_run, log_level=log_level)

    logger.info("=== PIPELINE COMPLETE ===")

    if do_export_3dm:
        # Find the aligned DB that was just created
        aligned_dbs = sorted(etl_output.parent.glob(f"{etl_output.stem}_aligned_*.db"))
        if aligned_dbs:
            aligned_db = aligned_dbs[-1]  # most recent
        elif output:
            aligned_db = Path(output)
        else:
            logger.error("Cannot find aligned DB for export. Specify --output explicitly.")
            return

        logger.info("=== EXPORT 3DM ===")
        ctx = click.Context(export_3dm)
        ctx.invoke(export_3dm, input_db=str(aligned_db), template_3dm=input_3dm,
                   output=None, report=None, log_level=log_level)


if __name__ == "__main__":
    cli()
