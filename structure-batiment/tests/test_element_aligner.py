"""Tests for the per-element-endpoint snap algorithm (Phase 3)."""

import math
from pathlib import Path

import pytest

from structure_aligner.config import (
    AlignedVertex,
    AxisLine,
    ElementInfo,
    PipelineConfig,
)
from structure_aligner.db.reader import InputVertex
from structure_aligner.alignment.element_aligner import align_elements
from structure_aligner.alignment.geometry import (
    assign_vertex_to_endpoint,
    find_nearest_axis_line,
    identify_element_endpoints,
)


# =========================================================================
# Geometry helper tests
# =========================================================================


class TestFindNearestAxisLine:
    """Tests for find_nearest_axis_line (binary search)."""

    def _make_lines(self, positions):
        return [AxisLine(axis="X", position=p, floor_count=5, vertex_count=10)
                for p in positions]

    def test_exact_match(self):
        lines = self._make_lines([1.0, 2.0, 3.0])
        result = find_nearest_axis_line(2.0, lines, 0.5)
        assert result is not None
        assert result.position == 2.0

    def test_within_distance(self):
        lines = self._make_lines([1.0, 2.0, 3.0])
        result = find_nearest_axis_line(2.03, lines, 0.05)
        assert result is not None
        assert result.position == 2.0

    def test_outside_distance(self):
        lines = self._make_lines([1.0, 2.0, 3.0])
        result = find_nearest_axis_line(2.5, lines, 0.1)
        assert result is None

    def test_empty_lines(self):
        result = find_nearest_axis_line(1.0, [], 1.0)
        assert result is None

    def test_picks_closest(self):
        lines = self._make_lines([1.0, 1.1, 1.2])
        result = find_nearest_axis_line(1.08, lines, 0.5)
        assert result is not None
        assert result.position == 1.1

    def test_edge_of_list(self):
        lines = self._make_lines([5.0, 10.0, 15.0])
        # Before first
        result = find_nearest_axis_line(4.9, lines, 0.2)
        assert result is not None
        assert result.position == 5.0
        # After last
        result = find_nearest_axis_line(15.05, lines, 0.1)
        assert result is not None
        assert result.position == 15.0


class TestIdentifyElementEndpoints:
    """Tests for identify_element_endpoints."""

    def _make_verts(self, coords_xy):
        """coords_xy: list of (x, y) pairs."""
        return [
            InputVertex(id=i, element_id=1, x=x, y=y, z=2.12, vertex_index=i)
            for i, (x, y) in enumerate(coords_xy)
        ]

    def test_single_point_column(self):
        verts = self._make_verts([(10.0, 5.0), (10.001, 5.0)])
        eps = identify_element_endpoints(verts, "X", cluster_radius=0.002)
        assert len(eps) == 1
        assert abs(eps[0] - 10.0005) < 0.01

    def test_two_endpoint_wall(self):
        verts = self._make_verts([
            (10.0, 5.0), (10.0, 5.0),
            (15.0, 5.0), (15.0, 5.0),
        ])
        eps = identify_element_endpoints(verts, "X", cluster_radius=0.002)
        assert len(eps) == 2
        assert abs(eps[0] - 10.0) < 0.01
        assert abs(eps[1] - 15.0) < 0.01

    def test_empty_vertices(self):
        eps = identify_element_endpoints([], "X")
        assert eps == []

    def test_y_axis(self):
        verts = self._make_verts([(1.0, 20.0), (1.0, 25.0)])
        eps = identify_element_endpoints(verts, "Y", cluster_radius=0.002)
        assert len(eps) == 2
        assert abs(eps[0] - 20.0) < 0.01
        assert abs(eps[1] - 25.0) < 0.01


class TestAssignVertexToEndpoint:
    """Tests for assign_vertex_to_endpoint."""

    def test_single_endpoint(self):
        assert assign_vertex_to_endpoint(10.0, [10.0]) == 0

    def test_two_endpoints_left(self):
        assert assign_vertex_to_endpoint(10.1, [10.0, 20.0]) == 0

    def test_two_endpoints_right(self):
        assert assign_vertex_to_endpoint(19.9, [10.0, 20.0]) == 1

    def test_midpoint(self):
        # At exact midpoint, should pick first (lower)
        idx = assign_vertex_to_endpoint(15.0, [10.0, 20.0])
        assert idx in (0, 1)  # either is acceptable


# =========================================================================
# Element aligner integration tests
# =========================================================================


def _make_axis_lines(axis, positions):
    return [AxisLine(axis=axis, position=p, floor_count=5, vertex_count=10)
            for p in sorted(positions)]


def _make_config(**overrides):
    return PipelineConfig(**overrides)


class TestAlignElementsPoteau:
    """Synthetic poteaux (columns): uniform displacement."""

    def test_column_uniform_snap(self):
        """A column at x=10.03 should snap all vertices to axis x=10.0."""
        verts = [
            InputVertex(id=1, element_id=100, x=10.03, y=5.02, z=2.12, vertex_index=0),
            InputVertex(id=2, element_id=100, x=10.03, y=5.02, z=5.48, vertex_index=1),
        ]
        elements = {100: ElementInfo(id=100, name="Poteau_1", type="poteau")}
        axis_x = _make_axis_lines("X", [10.0, 20.0])
        axis_y = _make_axis_lines("Y", [5.0, 15.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        assert len(result) == 2
        for av in result:
            assert av.x == 10.0
            assert av.y == 5.0
            assert av.aligned_axis == "XY"

    def test_column_preserves_z(self):
        """Z coordinates must never be modified."""
        verts = [
            InputVertex(id=1, element_id=100, x=10.03, y=5.02, z=2.12, vertex_index=0),
            InputVertex(id=2, element_id=100, x=10.03, y=5.02, z=5.48, vertex_index=1),
        ]
        elements = {100: ElementInfo(id=100, name="Poteau_1", type="poteau")}
        axis_x = _make_axis_lines("X", [10.0])
        axis_y = _make_axis_lines("Y", [5.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        assert result[0].z == 2.12
        assert result[0].z_original == 2.12
        assert result[1].z == 5.48
        assert result[1].z_original == 5.48


class TestAlignElementsVoile:
    """Synthetic spanning voiles (walls): 2-endpoint snap."""

    def test_wall_two_endpoint_snap(self):
        """A wall from x=10.03 to x=20.05 should snap endpoints independently."""
        verts = [
            # Left endpoint vertices
            InputVertex(id=1, element_id=200, x=10.03, y=5.0, z=2.12, vertex_index=0),
            InputVertex(id=2, element_id=200, x=10.03, y=5.0, z=5.48, vertex_index=1),
            # Right endpoint vertices
            InputVertex(id=3, element_id=200, x=20.05, y=5.0, z=2.12, vertex_index=2),
            InputVertex(id=4, element_id=200, x=20.05, y=5.0, z=5.48, vertex_index=3),
        ]
        elements = {200: ElementInfo(id=200, name="Voile_1", type="voile")}
        axis_x = _make_axis_lines("X", [10.0, 20.0, 30.0])
        axis_y = _make_axis_lines("Y", [5.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        assert len(result) == 4
        # Left vertices snap to x=10.0
        left = [av for av in result if av.id in (1, 2)]
        for av in left:
            assert av.x == 10.0, f"Expected 10.0, got {av.x}"
        # Right vertices snap to x=20.0
        right = [av for av in result if av.id in (3, 4)]
        for av in right:
            assert av.x == 20.0, f"Expected 20.0, got {av.x}"

    def test_wall_preserves_z(self):
        """Z must be unchanged for wall vertices."""
        verts = [
            InputVertex(id=1, element_id=200, x=10.03, y=5.0, z=2.12, vertex_index=0),
            InputVertex(id=2, element_id=200, x=20.05, y=5.0, z=5.48, vertex_index=1),
        ]
        elements = {200: ElementInfo(id=200, name="Voile_1", type="voile")}
        axis_x = _make_axis_lines("X", [10.0, 20.0])
        axis_y = _make_axis_lines("Y", [5.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        for av in result:
            assert av.z == av.z_original


class TestAlignElementsZUnchanged:
    """Z coordinates unchanged across all scenarios."""

    def test_z_never_modified(self):
        """Comprehensive test: Z must equal z_original for all aligned vertices."""
        z_values = [-4.44, -1.56, 2.12, 5.48, 8.20, 13.32, 17.96, 22.12]
        verts = [
            InputVertex(id=i, element_id=300, x=10.0 + i * 0.01,
                        y=5.0, z=z, vertex_index=i)
            for i, z in enumerate(z_values)
        ]
        elements = {300: ElementInfo(id=300, name="Poteau_2", type="poteau")}
        axis_x = _make_axis_lines("X", [10.0])
        axis_y = _make_axis_lines("Y", [5.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        for av in result:
            assert av.z == av.z_original, (
                f"Z was modified: {av.z_original} -> {av.z}"
            )


class TestAlignElementsOutlier:
    """Test outlier snap distance fallback."""

    def test_outlier_snap(self):
        """Vertex displaced >0.75m but <4.0m should still snap via outlier."""
        verts = [
            InputVertex(id=1, element_id=400, x=12.5, y=5.0, z=2.12, vertex_index=0),
        ]
        elements = {400: ElementInfo(id=400, name="Poteau_3", type="poteau")}
        axis_x = _make_axis_lines("X", [10.0, 20.0])
        axis_y = _make_axis_lines("Y", [5.0])
        config = _make_config(max_snap_distance=0.75, outlier_snap_distance=4.0)

        result = align_elements(verts, elements, axis_x, axis_y, config)

        assert len(result) == 1
        assert result[0].x == 10.0
        assert result[0].aligned_axis in ("X", "XY")

    def test_beyond_outlier_unsnapped(self):
        """Vertex displaced >4.0m should not snap."""
        verts = [
            InputVertex(id=1, element_id=500, x=50.0, y=5.0, z=2.12, vertex_index=0),
        ]
        elements = {500: ElementInfo(id=500, name="Poteau_4", type="poteau")}
        axis_x = _make_axis_lines("X", [10.0, 20.0])
        axis_y = _make_axis_lines("Y", [5.0])
        config = _make_config(max_snap_distance=0.75, outlier_snap_distance=4.0)

        result = align_elements(verts, elements, axis_x, axis_y, config)

        assert len(result) == 1
        assert result[0].x == 50.0  # unchanged


class TestAlignElementsTypeBranching:
    """Test element-type-aware snapping logic (C-1, C-2 fixes)."""

    def test_dalle_skipped(self):
        """Dalles should not be snapped – coordinates unchanged, aligned_axis='none'."""
        verts = [
            InputVertex(id=1, element_id=900, x=10.03, y=5.02, z=2.12, vertex_index=0),
            InputVertex(id=2, element_id=900, x=20.05, y=15.01, z=2.12, vertex_index=1),
        ]
        elements = {900: ElementInfo(id=900, name="Dalle_1", type="dalle")}
        axis_x = _make_axis_lines("X", [10.0, 20.0])
        axis_y = _make_axis_lines("Y", [5.0, 15.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        assert len(result) == 2
        for av in result:
            assert av.aligned_axis == "none"
            assert av.displacement_total == 0.0
            assert av.x == av.x_original
            assert av.y == av.y_original

    def test_poteau_single_endpoint(self):
        """Poteau with rectangular section should translate uniformly, preserving shape."""
        # A poteau with 60mm-wide rectangular section (9.97 to 10.03)
        verts = [
            InputVertex(id=1, element_id=910, x=9.97, y=5.0, z=2.12, vertex_index=0),
            InputVertex(id=2, element_id=910, x=10.03, y=5.0, z=2.12, vertex_index=1),
            InputVertex(id=3, element_id=910, x=9.97, y=5.3, z=2.12, vertex_index=2),
            InputVertex(id=4, element_id=910, x=10.03, y=5.3, z=2.12, vertex_index=3),
        ]
        elements = {910: ElementInfo(id=910, name="Poteau_T", type="poteau")}
        axis_x = _make_axis_lines("X", [10.0, 20.0])
        axis_y = _make_axis_lines("Y", [5.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        # Section shape must be preserved: vertices should NOT all collapse to same X
        xs = sorted(set(av.x for av in result))
        assert len(xs) == 2, f"Section collapsed: all X values are {xs}"
        # Section width (60mm) should be preserved
        assert abs(xs[1] - xs[0] - 0.06) < 0.001, f"Section width changed: {xs}"
        # Center should be at axis line 10.0 (mean of 9.97 and 10.03 = 10.0)
        center = (xs[0] + xs[1]) / 2
        assert abs(center - 10.0) < 0.001, f"Center not at axis: {center}"

    def test_voile_two_endpoints_preserved(self):
        """Voile should keep 2 endpoints and snap them independently."""
        verts = [
            InputVertex(id=1, element_id=920, x=10.03, y=5.0, z=2.12, vertex_index=0),
            InputVertex(id=2, element_id=920, x=20.05, y=5.0, z=2.12, vertex_index=1),
        ]
        elements = {920: ElementInfo(id=920, name="Voile_T", type="voile")}
        axis_x = _make_axis_lines("X", [10.0, 20.0])
        axis_y = _make_axis_lines("Y", [5.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        r1 = next(av for av in result if av.id == 1)
        r2 = next(av for av in result if av.id == 2)
        assert r1.x == 10.0
        assert r2.x == 20.0

    def test_mixed_types_independent(self):
        """Dalle, poteau, and voile in one batch should each follow their rules."""
        verts = [
            # Dalle - should NOT snap
            InputVertex(id=1, element_id=930, x=10.03, y=5.02, z=2.12, vertex_index=0),
            # Poteau - should snap
            InputVertex(id=2, element_id=931, x=10.03, y=5.02, z=2.12, vertex_index=0),
            # Voile - should snap
            InputVertex(id=3, element_id=932, x=10.03, y=5.02, z=2.12, vertex_index=0),
        ]
        elements = {
            930: ElementInfo(id=930, name="Dalle_M", type="dalle"),
            931: ElementInfo(id=931, name="Poteau_M", type="poteau"),
            932: ElementInfo(id=932, name="Voile_M", type="voile"),
        }
        axis_x = _make_axis_lines("X", [10.0])
        axis_y = _make_axis_lines("Y", [5.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        dalle_v = next(av for av in result if av.element_id == 930)
        poteau_v = next(av for av in result if av.element_id == 931)
        voile_v = next(av for av in result if av.element_id == 932)

        # Dalle: unchanged
        assert dalle_v.aligned_axis == "none"
        assert dalle_v.x == 10.03

        # Poteau: snapped
        assert poteau_v.x == 10.0
        assert poteau_v.y == 5.0

        # Voile: snapped
        assert voile_v.x == 10.0
        assert voile_v.y == 5.0


class TestAlignElementsNoMatch:
    """Test behavior when no axis line is nearby."""

    def test_no_snap_preserves_original(self):
        """Vertices far from any axis line should keep original coords."""
        verts = [
            InputVertex(id=1, element_id=600, x=99.0, y=99.0, z=2.12, vertex_index=0),
        ]
        elements = {600: ElementInfo(id=600, name="Poteau_5", type="poteau")}
        axis_x = _make_axis_lines("X", [10.0])
        axis_y = _make_axis_lines("Y", [5.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        assert result[0].x == 99.0
        assert result[0].y == 99.0
        assert result[0].aligned_axis == "none"


class TestAlignElementsMultipleElements:
    """Test multiple elements processed together."""

    def test_independent_elements(self):
        """Two elements should snap independently."""
        verts = [
            InputVertex(id=1, element_id=700, x=10.03, y=5.02, z=2.12, vertex_index=0),
            InputVertex(id=2, element_id=800, x=20.04, y=15.01, z=2.12, vertex_index=0),
        ]
        elements = {
            700: ElementInfo(id=700, name="Poteau_A", type="poteau"),
            800: ElementInfo(id=800, name="Poteau_B", type="poteau"),
        }
        axis_x = _make_axis_lines("X", [10.0, 20.0])
        axis_y = _make_axis_lines("Y", [5.0, 15.0])
        config = _make_config()

        result = align_elements(verts, elements, axis_x, axis_y, config)

        assert len(result) == 2
        r1 = next(av for av in result if av.element_id == 700)
        r2 = next(av for av in result if av.element_id == 800)
        assert r1.x == 10.0
        assert r1.y == 5.0
        assert r2.x == 20.0
        assert r2.y == 15.0


# =========================================================================
# Integration test with real data (if available)
# =========================================================================

PRD_DB = Path("data/input/geometrie_2_prd.db")


@pytest.mark.skipif(not PRD_DB.exists(), reason="PRD database not available")
class TestAlignElementsRealData:
    """Integration tests using real PRD database."""

    def test_real_data_alignment(self):
        """Run alignment on real data and verify basic properties."""
        from structure_aligner.db.reader import load_vertices_with_elements
        from structure_aligner.analysis.axis_selector import discover_axis_lines

        vertices, elements = load_vertices_with_elements(PRD_DB)
        config = PipelineConfig()
        axis_x, axis_y = discover_axis_lines(vertices, config)

        result = align_elements(vertices, elements, axis_x, axis_y, config)

        # Basic sanity checks
        assert len(result) == len(vertices)

        # Z coordinates must never change
        originals = {v.id: v for v in vertices}
        for av in result:
            assert av.z == originals[av.id].z, (
                f"Z changed for vertex {av.id}: {originals[av.id].z} -> {av.z}"
            )

        # Some vertices should be aligned
        aligned_count = sum(1 for av in result if av.aligned_axis != "none")
        pct = aligned_count / len(result) * 100
        assert pct > 50, f"Only {pct:.1f}% vertices aligned, expected >50%"

    def test_real_data_displacement_distribution(self):
        """Check displacement distribution matches research expectations."""
        from structure_aligner.db.reader import load_vertices_with_elements
        from structure_aligner.analysis.axis_selector import discover_axis_lines

        vertices, elements = load_vertices_with_elements(PRD_DB)
        config = PipelineConfig()
        axis_x, axis_y = discover_axis_lines(vertices, config)

        result = align_elements(vertices, elements, axis_x, axis_y, config)

        displacements = sorted(av.displacement_total for av in result
                               if av.displacement_total > 0)
        if displacements:
            p50 = displacements[len(displacements) // 2]
            p95 = displacements[int(len(displacements) * 0.95)]
            p99 = displacements[int(len(displacements) * 0.99)]

            # Research shows P95 ~175-192mm, P99 ~235-260mm
            # Allow generous bounds since our axis selection may differ
            assert p95 < 1.0, f"P95 displacement {p95:.3f}m seems too high"
            assert p99 < 4.5, f"P99 displacement {p99:.3f}m exceeds outlier limit"
