import math

from structure_aligner.config import AlignmentConfig, AlignedVertex
from structure_aligner.output.validator import (
    ValidationCheck,
    ValidationResult,
    validate_alignment,
)


def _make_vertex(
    id=1, element_id=1, x=0.0, y=0.0, z=0.0, vertex_index=0,
    x_original=0.0, y_original=0.0, z_original=0.0,
    aligned_axis="X", fil_x_id="X_001", fil_y_id=None, fil_z_id=None,
    displacement_total=0.0,
):
    return AlignedVertex(
        id=id, element_id=element_id, x=x, y=y, z=z,
        vertex_index=vertex_index,
        x_original=x_original, y_original=y_original, z_original=z_original,
        aligned_axis=aligned_axis,
        fil_x_id=fil_x_id, fil_y_id=fil_y_id, fil_z_id=fil_z_id,
        displacement_total=displacement_total,
    )


class TestValidateAlignment:
    """Tests for validate_alignment."""

    def test_all_checks_pass(self):
        """Normal case: all vertices aligned within alpha."""
        config = AlignmentConfig(alpha=0.05)
        vertices = [
            _make_vertex(id=1, x=1.00, x_original=1.02, aligned_axis="X",
                         fil_x_id="X_001", displacement_total=0.02),
            _make_vertex(id=2, x=2.00, x_original=2.01, aligned_axis="X",
                         fil_x_id="X_002", displacement_total=0.01),
        ]
        result = validate_alignment(vertices, original_count=2, config=config)
        assert result.passed is True
        assert len(result.checks) == 4
        assert all(c.status in ("PASS",) for c in result.checks)

    def test_per_axis_displacement_exceeds_alpha_fails(self):
        """Per-axis displacement > alpha should FAIL."""
        config = AlignmentConfig(alpha=0.05)
        vertices = [
            _make_vertex(id=1, x=1.00, x_original=1.10, aligned_axis="X",
                         fil_x_id="X_001", displacement_total=0.10),
        ]
        result = validate_alignment(vertices, original_count=1, config=config)
        assert result.passed is False
        disp_check = next(c for c in result.checks if c.name == "max_per_axis_displacement")
        assert disp_check.status == "FAIL"

    def test_multi_axis_3d_exceeds_alpha_but_per_axis_within_passes(self):
        """3D Euclidean > alpha but each per-axis <= alpha -> PASS.

        If dx=0.04, dy=0.04, dz=0.04 then 3D = sqrt(0.04^2*3) ~ 0.069 > 0.05
        but each per-axis = 0.04 <= 0.05 -> PASS.
        """
        config = AlignmentConfig(alpha=0.05)
        vertices = [
            _make_vertex(
                id=1,
                x=1.04, y=2.04, z=3.04,
                x_original=1.0, y_original=2.0, z_original=3.0,
                aligned_axis="XYZ",
                fil_x_id="X_001", fil_y_id="Y_001", fil_z_id="Z_001",
                displacement_total=math.sqrt(3 * 0.04**2),  # ~0.069
            ),
        ]
        result = validate_alignment(vertices, original_count=1, config=config)
        assert result.passed is True
        disp_check = next(c for c in result.checks if c.name == "max_per_axis_displacement")
        assert disp_check.status == "PASS"

    def test_null_coordinates_fails(self):
        """NULL coordinate introduced -> FAIL."""
        config = AlignmentConfig(alpha=0.05)
        vertices = [
            _make_vertex(id=1, x=None, x_original=1.0, aligned_axis="none",
                         fil_x_id=None, displacement_total=0.0),
        ]
        result = validate_alignment(vertices, original_count=1, config=config)
        assert result.passed is False
        null_check = next(c for c in result.checks if c.name == "no_null_coordinates")
        assert null_check.status == "FAIL"

    def test_vertex_count_mismatch_fails(self):
        """Vertex count changed -> FAIL."""
        config = AlignmentConfig(alpha=0.05)
        vertices = [
            _make_vertex(id=1, aligned_axis="X"),
        ]
        result = validate_alignment(vertices, original_count=5, config=config)
        assert result.passed is False
        count_check = next(c for c in result.checks if c.name == "vertex_count_preserved")
        assert count_check.status == "FAIL"

    def test_low_alignment_rate_is_warning_not_fail(self):
        """Alignment rate < 80% -> WARNING (not FAIL). Result still passes."""
        config = AlignmentConfig(alpha=0.05)
        # 1 aligned, 9 isolated -> 10% rate
        vertices = [_make_vertex(id=1, aligned_axis="X")]
        vertices += [
            _make_vertex(id=i, aligned_axis="none", fil_x_id=None)
            for i in range(2, 11)
        ]
        result = validate_alignment(vertices, original_count=10, config=config)
        # Should still pass (WARNING is not FAIL)
        assert result.passed is True
        rate_check = next(c for c in result.checks if c.name == "alignment_rate")
        assert rate_check.status == "WARNING"

    def test_empty_input(self):
        """Empty vertex list should pass all checks."""
        config = AlignmentConfig(alpha=0.05)
        result = validate_alignment([], original_count=0, config=config)
        assert result.passed is True
        # Should have displacement, null, and count checks (no alignment_rate for empty)
        assert len(result.checks) == 3

    def test_float_epsilon_boundary(self):
        """Displacement exactly at alpha should PASS (within epsilon)."""
        config = AlignmentConfig(alpha=0.05)
        vertices = [
            _make_vertex(id=1, x=1.05, x_original=1.0, aligned_axis="X",
                         fil_x_id="X_001", displacement_total=0.05),
        ]
        result = validate_alignment(vertices, original_count=1, config=config)
        disp_check = next(c for c in result.checks if c.name == "max_per_axis_displacement")
        assert disp_check.status == "PASS"

    def test_unaligned_axis_not_counted_in_displacement(self):
        """Only axes with a fil_id should contribute to displacement check."""
        config = AlignmentConfig(alpha=0.05)
        # fil_x_id is set but fil_y_id is None, so y displacement ignored
        vertices = [
            _make_vertex(
                id=1,
                x=1.03, y=2.50, z=3.0,
                x_original=1.0, y_original=2.0, z_original=3.0,
                aligned_axis="X",
                fil_x_id="X_001", fil_y_id=None, fil_z_id=None,
                displacement_total=0.5,
            ),
        ]
        result = validate_alignment(vertices, original_count=1, config=config)
        disp_check = next(c for c in result.checks if c.name == "max_per_axis_displacement")
        # Only x displacement (0.03) counted, y (0.50) ignored
        assert disp_check.status == "PASS"
