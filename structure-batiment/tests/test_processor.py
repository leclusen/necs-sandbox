"""Tests for structure_aligner.alignment.processor."""
import math

import pytest

from structure_aligner.alignment.processor import align_vertices
from structure_aligner.config import AlignmentConfig, Thread, AlignedVertex
from structure_aligner.db.reader import InputVertex


def _make_thread(reference: float, axis: str, fil_id: str,
                 delta: float = 0.01, vertex_count: int = 10) -> Thread:
    return Thread(
        fil_id=fil_id, axis=axis, reference=reference, delta=delta,
        vertex_count=vertex_count, range_min=reference - 0.05, range_max=reference + 0.05,
    )


def _make_vertex(id: int, x: float, y: float, z: float,
                 element_id: int = 1, vertex_index: int = 0) -> InputVertex:
    return InputVertex(id=id, element_id=element_id, x=x, y=y, z=z, vertex_index=vertex_index)


class TestAlignVertices:

    def test_simple_all_align(self):
        config = AlignmentConfig(alpha=0.05)
        vertices = [
            _make_vertex(1, 10.02, 20.01, 30.03),
            _make_vertex(2, 10.04, 20.03, 30.01),
        ]
        tx = [_make_thread(10.0, "X", "X_001")]
        ty = [_make_thread(20.0, "Y", "Y_001")]
        tz = [_make_thread(30.0, "Z", "Z_001")]

        result = align_vertices(vertices, tx, ty, tz, config)

        assert len(result) == 2
        assert result[0].x == 10.0
        assert result[0].y == 20.0
        assert result[0].z == 30.0
        assert result[0].aligned_axis == "XYZ"
        assert result[0].fil_x_id == "X_001"
        assert result[0].fil_y_id == "Y_001"
        assert result[0].fil_z_id == "Z_001"

    def test_mixed_some_align_some_not(self):
        config = AlignmentConfig(alpha=0.05)
        vertices = [
            _make_vertex(1, 10.02, 20.01, 30.03),  # All axes align
            _make_vertex(2, 99.0, 20.03, 99.0),     # Only Y aligns
        ]
        tx = [_make_thread(10.0, "X", "X_001")]
        ty = [_make_thread(20.0, "Y", "Y_001")]
        tz = [_make_thread(30.0, "Z", "Z_001")]

        result = align_vertices(vertices, tx, ty, tz, config)

        assert result[0].aligned_axis == "XYZ"
        assert result[1].aligned_axis == "Y"
        assert result[1].x == 99.0  # Original preserved
        assert result[1].y == 20.0  # Aligned
        assert result[1].z == 99.0  # Original preserved
        assert result[1].fil_x_id is None
        assert result[1].fil_y_id == "Y_001"
        assert result[1].fil_z_id is None

    def test_no_match_gives_none_axis(self):
        config = AlignmentConfig(alpha=0.05)
        vertices = [_make_vertex(1, 99.0, 99.0, 99.0)]
        tx = [_make_thread(10.0, "X", "X_001")]

        result = align_vertices(vertices, tx, [], [], config)

        assert result[0].aligned_axis == "none"
        assert result[0].x == 99.0
        assert result[0].fil_x_id is None

    def test_per_axis_at_alpha_boundary(self):
        """Displacement exactly at alpha should align (using exact floats)."""
        config = AlignmentConfig(alpha=0.5)
        vertices = [_make_vertex(1, 10.5, 20.0, 30.0)]
        tx = [_make_thread(10.0, "X", "X_001")]

        result = align_vertices(vertices, tx, [], [], config)

        assert result[0].aligned_axis == "X"
        assert result[0].x == 10.0

    def test_multi_axis_3d_displacement_exceeds_alpha(self):
        """Per-axis is the constraint. 3D displacement can exceed alpha."""
        config = AlignmentConfig(alpha=0.05)
        # Each axis displaced by 0.04 -> 3D = sqrt(3*0.04^2) = 0.0693 > 0.05
        vertices = [_make_vertex(1, 10.04, 20.04, 30.04)]
        tx = [_make_thread(10.0, "X", "X_001")]
        ty = [_make_thread(20.0, "Y", "Y_001")]
        tz = [_make_thread(30.0, "Z", "Z_001")]

        result = align_vertices(vertices, tx, ty, tz, config)

        assert result[0].aligned_axis == "XYZ"
        assert result[0].displacement_total == pytest.approx(
            math.sqrt(3 * 0.04**2), abs=1e-6
        )
        # 3D displacement > alpha is OK (per-axis constraint, not 3D)
        assert result[0].displacement_total > config.alpha

    def test_empty_input(self):
        config = AlignmentConfig(alpha=0.05)
        result = align_vertices([], [], [], [], config)
        assert result == []

    def test_aligned_axis_strings(self):
        config = AlignmentConfig(alpha=0.05)
        tx = [_make_thread(10.0, "X", "X_001")]
        ty = [_make_thread(20.0, "Y", "Y_001")]
        tz = [_make_thread(30.0, "Z", "Z_001")]

        cases = [
            (_make_vertex(1, 10.01, 99.0, 99.0), "X"),
            (_make_vertex(2, 99.0, 20.01, 99.0), "Y"),
            (_make_vertex(3, 99.0, 99.0, 30.01), "Z"),
            (_make_vertex(4, 10.01, 20.01, 99.0), "XY"),
            (_make_vertex(5, 10.01, 99.0, 30.01), "XZ"),
            (_make_vertex(6, 99.0, 20.01, 30.01), "YZ"),
            (_make_vertex(7, 10.01, 20.01, 30.01), "XYZ"),
            (_make_vertex(8, 99.0, 99.0, 99.0), "none"),
        ]

        for vertex, expected_axis in cases:
            result = align_vertices([vertex], tx, ty, tz, config)
            assert result[0].aligned_axis == expected_axis, (
                f"Vertex {vertex.id}: expected '{expected_axis}', got '{result[0].aligned_axis}'"
            )

    def test_rounding_uses_config_ndigits(self):
        config = AlignmentConfig(alpha=0.05, rounding_precision=0.001)
        assert config.rounding_ndigits == 3

        vertices = [_make_vertex(1, 10.0234, 20.0, 30.0)]
        tx = [_make_thread(10.0, "X", "X_001")]

        result = align_vertices(vertices, tx, [], [], config)

        # Thread reference is 10.0, rounded to 3 digits = 10.0
        assert result[0].x == 10.0

    def test_originals_preserved(self):
        config = AlignmentConfig(alpha=0.05)
        vertices = [_make_vertex(1, 10.03, 20.02, 30.01)]
        tx = [_make_thread(10.0, "X", "X_001")]
        ty = [_make_thread(20.0, "Y", "Y_001")]
        tz = [_make_thread(30.0, "Z", "Z_001")]

        result = align_vertices(vertices, tx, ty, tz, config)

        assert result[0].x_original == 10.03
        assert result[0].y_original == 20.02
        assert result[0].z_original == 30.01
