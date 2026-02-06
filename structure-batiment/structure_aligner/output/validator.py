import logging
from dataclasses import dataclass, field

from structure_aligner.config import AlignmentConfig, AlignedVertex

logger = logging.getLogger(__name__)


@dataclass
class ValidationCheck:
    """Result of a single validation check."""
    name: str
    status: str  # "PASS", "FAIL", "WARNING"
    detail: str = ""


@dataclass
class ValidationResult:
    """Complete validation result."""
    passed: bool = True
    checks: list[ValidationCheck] = field(default_factory=list)


def validate_alignment(
    aligned_vertices: list[AlignedVertex],
    original_count: int,
    config: AlignmentConfig,
) -> ValidationResult:
    """
    Run PRD F-09 post-alignment validation checks.

    Checks:
    1. Max per-axis displacement <= alpha (CRITICAL, PRD CF-02)
    2. No NULL coordinates introduced (CRITICAL)
    3. Vertex count preserved (CRITICAL)
    4. Alignment rate >= 80% (WARNING per PRD F-09)

    Note: CQ-01 (85% alignment rate) is validated in integration tests,
    not here. This validator implements F-09's warning threshold of 80%.

    Args:
        aligned_vertices: The aligned vertices to validate.
        original_count: Number of vertices before alignment.
        config: Alignment configuration.

    Returns:
        ValidationResult with pass/fail status and individual check results.
    """
    result = ValidationResult()

    # Check 1: Max per-axis displacement <= alpha (PRD CF-02)
    if aligned_vertices:
        max_per_axis_disp = 0.0
        for v in aligned_vertices:
            dx = abs(v.x - v.x_original) if v.fil_x_id else 0.0
            dy = abs(v.y - v.y_original) if v.fil_y_id else 0.0
            dz = abs(v.z - v.z_original) if v.fil_z_id else 0.0
            max_per_axis_disp = max(max_per_axis_disp, dx, dy, dz)

        if max_per_axis_disp > config.alpha + 1e-9:  # Small epsilon for float comparison
            result.passed = False
            result.checks.append(ValidationCheck(
                "max_per_axis_displacement", "FAIL",
                f"Max per-axis displacement {max_per_axis_disp:.6f}m exceeds alpha {config.alpha}m"
            ))
            logger.error("CRITICAL: Max per-axis displacement %.6fm > alpha %.3fm",
                        max_per_axis_disp, config.alpha)
        else:
            result.checks.append(ValidationCheck(
                "max_per_axis_displacement", "PASS",
                f"Max per-axis displacement {max_per_axis_disp:.6f}m <= alpha {config.alpha}m"
            ))
    else:
        result.checks.append(ValidationCheck("max_per_axis_displacement", "PASS", "No vertices to check"))

    # Check 2: No NULL coordinates
    null_count = sum(1 for v in aligned_vertices if v.x is None or v.y is None or v.z is None)
    if null_count > 0:
        result.passed = False
        result.checks.append(ValidationCheck(
            "no_null_coordinates", "FAIL",
            f"{null_count} vertices with NULL coordinates"
        ))
    else:
        result.checks.append(ValidationCheck("no_null_coordinates", "PASS", "0 NULL coordinates"))

    # Check 3: Vertex count preserved
    if len(aligned_vertices) != original_count:
        result.passed = False
        result.checks.append(ValidationCheck(
            "vertex_count_preserved", "FAIL",
            f"Expected {original_count}, got {len(aligned_vertices)}"
        ))
    else:
        result.checks.append(ValidationCheck(
            "vertex_count_preserved", "PASS",
            f"Count preserved: {len(aligned_vertices)}"
        ))

    # Check 4: Alignment rate >= 80% (PRD F-09 WARNING threshold)
    if aligned_vertices:
        aligned_count = sum(1 for v in aligned_vertices if v.aligned_axis != "none")
        rate = aligned_count / len(aligned_vertices) * 100
        if rate < 80:
            result.checks.append(ValidationCheck(
                "alignment_rate", "WARNING",
                f"Alignment rate {rate:.1f}% < 80% threshold"
            ))
            logger.warning("Alignment rate %.1f%% below 80%% threshold", rate)
        else:
            result.checks.append(ValidationCheck(
                "alignment_rate", "PASS",
                f"Alignment rate {rate:.1f}%"
            ))

    if result.passed:
        logger.info("All validation checks passed")
    else:
        logger.error("Validation FAILED — see check details")

    return result
