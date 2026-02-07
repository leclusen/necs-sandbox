"""Tests for object-level addition rules (Phase 5)."""

from pathlib import Path

import pytest
import rhino3dm

from structure_aligner.config import AxisLine, PipelineConfig
from structure_aligner.transform.dalle_consolidator import (
    RemovedDalleInfo,
    consolidate_dalles,
    extract_dalle_info,
)
from structure_aligner.transform.voile_simplifier import (
    VoileExtent,
    simplify_voiles,
)
from structure_aligner.transform.support_placer import (
    place_support_points,
    place_line_supports,
)
from structure_aligner.transform.filaire_generator import generate_filaire
from structure_aligner.transform.grid_lines import generate_grid_lines


FLOOR_Z = (-4.44, -1.56, 2.12, 5.48, 8.20, 13.32, 17.96, 22.12, 26.28, 29.64, 32.36)


def _make_axis_lines(axis, positions):
    return [AxisLine(axis=axis, position=p, floor_count=5, vertex_count=10)
            for p in sorted(positions)]


def _count_objects(model):
    return len(model.Objects)


def _count_named(model, prefix):
    return sum(
        1 for obj in model.Objects
        if obj.Attributes.Name and obj.Attributes.Name.startswith(prefix)
    )


def _count_unnamed(model):
    return sum(1 for obj in model.Objects if not obj.Attributes.Name)


# =========================================================================
# Dalle consolidation tests
# =========================================================================


class TestDalleConsolidation:
    """Tests for dalle consolidation."""

    def test_basic_consolidation(self):
        """Creates planar Breps per Z-level."""
        model = rhino3dm.File3dm()
        dalles = [
            RemovedDalleInfo("D1", -50, -20, -80, -40, 5.48),
            RemovedDalleInfo("D2", -60, -30, -60, -30, 5.48),
            RemovedDalleInfo("D3", -40, -10, -50, 0, 2.12),
        ]

        added = consolidate_dalles(model, dalles, FLOOR_Z)

        assert added >= 2  # at least 2 Z-levels
        assert _count_objects(model) == added

    def test_empty_input(self):
        model = rhino3dm.File3dm()
        added = consolidate_dalles(model, [], FLOOR_Z)
        assert added == 0

    def test_breps_are_planar(self):
        """All created Breps should be planar (single face)."""
        model = rhino3dm.File3dm()
        dalles = [
            RemovedDalleInfo("D1", -50, -20, -80, -40, 8.20),
        ]

        consolidate_dalles(model, dalles, FLOOR_Z)

        for obj in model.Objects:
            geom = obj.Geometry
            assert isinstance(geom, rhino3dm.Brep)
            assert len(geom.Faces) == 1

    def test_z_level_matching(self):
        """Dalles at similar Z should be grouped to the same floor."""
        model = rhino3dm.File3dm()
        dalles = [
            RemovedDalleInfo("D1", -50, -20, -80, -40, 2.10),
            RemovedDalleInfo("D2", -50, -20, -80, -40, 2.14),
        ]

        added = consolidate_dalles(model, dalles, FLOOR_Z)
        assert added == 1  # Both should merge to Z=2.12

    def test_zone_splitting(self):
        """Large Y-gap should cause zone splitting."""
        model = rhino3dm.File3dm()
        dalles = [
            RemovedDalleInfo("D1", -50, -20, -80, -50, 5.48),
            RemovedDalleInfo("D2", -50, -20, 10, 30, 5.48),
        ]

        added = consolidate_dalles(model, dalles, FLOOR_Z)
        assert added == 2  # Two zones due to Y-gap > 10m


# =========================================================================
# Voile simplification tests
# =========================================================================


class TestVoileSimplification:
    """Tests for voile simplification."""

    def test_basic_simplification(self):
        """Creates per-floor segments."""
        model = rhino3dm.File3dm()
        extents = [
            VoileExtent(
                name="Coque_100",
                orientation="X",
                coord_min=-50,
                coord_max=-20,
                cross_coord=-40,
                z_min=2.12,
                z_max=8.20,
                thickness=0.2,
                layer_index=0,
            ),
        ]

        added = simplify_voiles(model, extents, FLOOR_Z)

        # Z range 2.12->8.20 spans floors: 2.12, 5.48, 8.20
        # Segments: 2.12->5.48, 5.48->8.20 = 2 segments
        assert added == 2

    def test_single_floor_segment(self):
        """Voile within one floor creates one segment."""
        model = rhino3dm.File3dm()
        extents = [
            VoileExtent(
                name="Coque_200",
                orientation="Y",
                coord_min=-80,
                coord_max=-40,
                cross_coord=-30,
                z_min=2.12,
                z_max=5.48,
                thickness=0.2,
                layer_index=0,
            ),
        ]

        added = simplify_voiles(model, extents, FLOOR_Z)
        assert added == 1

    def test_empty_input(self):
        model = rhino3dm.File3dm()
        added = simplify_voiles(model, [], FLOOR_Z)
        assert added == 0

    def test_segments_are_breps(self):
        """All created segments should be Breps."""
        model = rhino3dm.File3dm()
        extents = [
            VoileExtent(
                name="Coque_300",
                orientation="X",
                coord_min=-50,
                coord_max=-20,
                cross_coord=-40,
                z_min=2.12,
                z_max=5.48,
                thickness=0.2,
                layer_index=0,
            ),
        ]

        simplify_voiles(model, extents, FLOOR_Z)

        for obj in model.Objects:
            assert isinstance(obj.Geometry, rhino3dm.Brep)

    def test_preserves_name(self):
        """Segments should have the original voile name (possibly suffixed)."""
        model = rhino3dm.File3dm()
        extents = [
            VoileExtent(
                name="Coque_400",
                orientation="X",
                coord_min=-50,
                coord_max=-20,
                cross_coord=-40,
                z_min=2.12,
                z_max=8.20,
                thickness=0.2,
                layer_index=0,
            ),
        ]

        simplify_voiles(model, extents, FLOOR_Z)

        for obj in model.Objects:
            assert obj.Attributes.Name.startswith("Coque_400")


# =========================================================================
# Support placement tests
# =========================================================================


class TestSupportPlacement:
    """Tests for support point placement."""

    def test_basic_placement(self):
        """Places points at grid intersections."""
        model = rhino3dm.File3dm()
        ax = _make_axis_lines("X", [-40.0, -30.0])
        ay = _make_axis_lines("Y", [-80.0, -60.0])

        added, positions = place_support_points(
            model, ax, ay,
            support_z_levels=(2.12,),
            start_id=1,
        )

        assert added == 4  # 2 X * 2 Y * 1 Z
        assert len(positions) == 4
        assert _count_named(model, "Appuis_") == 4

    def test_multiple_z_levels(self):
        """Places at multiple Z levels."""
        model = rhino3dm.File3dm()
        ax = _make_axis_lines("X", [-40.0])
        ay = _make_axis_lines("Y", [-80.0])

        added, positions = place_support_points(
            model, ax, ay,
            support_z_levels=(2.12, -4.44),
            start_id=1,
        )

        assert added == 2  # 1 X * 1 Y * 2 Z

    def test_with_column_filter(self):
        """Only places where columns exist."""
        model = rhino3dm.File3dm()
        ax = _make_axis_lines("X", [-40.0, -30.0])
        ay = _make_axis_lines("Y", [-80.0, -60.0])
        columns = {(-40.0, -80.0): True}  # Only 1 column

        added, _ = place_support_points(
            model, ax, ay,
            support_z_levels=(2.12,),
            existing_columns=columns,
            start_id=1,
        )

        assert added == 1

    def test_empty_axes(self):
        model = rhino3dm.File3dm()
        added, _ = place_support_points(model, [], [], start_id=1)
        assert added == 0

    def test_point_geometry(self):
        """All support objects should be Point geometry."""
        model = rhino3dm.File3dm()
        ax = _make_axis_lines("X", [-40.0])
        ay = _make_axis_lines("Y", [-80.0])

        place_support_points(
            model, ax, ay,
            support_z_levels=(2.12,),
            start_id=1,
        )

        for obj in model.Objects:
            # AddPoint creates Point geometry
            geom = obj.Geometry
            assert isinstance(geom, rhino3dm.Point)


class TestLineSupportPlacement:
    """Tests for line support placement."""

    def test_basic_line_supports(self):
        model = rhino3dm.File3dm()
        ax = _make_axis_lines("X", [-40.0, -30.0])

        added = place_line_supports(
            model, ax,
            edge_y_positions=[-80.0],
            start_id=1,
        )

        assert added == 2  # 2 X * 1 edge


# =========================================================================
# Filaire generation tests
# =========================================================================


class TestFilaireGeneration:
    """Tests for filaire centerline generation."""

    def test_basic_generation(self):
        """Creates vertical lines at support positions."""
        model = rhino3dm.File3dm()
        positions = [
            (-40.0, -80.0, 2.12),
            (-30.0, -60.0, 2.12),
        ]

        added = generate_filaire(model, positions, FLOOR_Z, start_id=1)

        assert added == 2
        assert _count_named(model, "Filaire_") == 2

    def test_z_spanning(self):
        """Filaire should span from support Z to next floor above."""
        model = rhino3dm.File3dm()
        positions = [(-40.0, -80.0, 2.12)]

        generate_filaire(model, positions, FLOOR_Z, start_id=1)

        obj = model.Objects[0]
        geom = obj.Geometry
        # Should span from 2.12 to 5.48
        if isinstance(geom, rhino3dm.NurbsCurve):
            z_start = geom.Points[0].Z
            z_end = geom.Points[len(geom.Points) - 1].Z
        elif isinstance(geom, rhino3dm.PolylineCurve):
            z_start = geom.Point(0).Z
            z_end = geom.Point(geom.PointCount - 1).Z
        elif isinstance(geom, rhino3dm.LineCurve):
            z_start = geom.PointAtStart.Z
            z_end = geom.PointAtEnd.Z
        else:
            pytest.fail(f"Unexpected geometry type: {type(geom)}")

        assert abs(z_start - 2.12) < 0.01
        assert abs(z_end - 5.48) < 0.01

    def test_top_floor_no_filaire(self):
        """No filaire at the topmost floor (no Z above)."""
        model = rhino3dm.File3dm()
        positions = [(-40.0, -80.0, 32.36)]  # Top floor

        added = generate_filaire(model, positions, FLOOR_Z, start_id=1)
        assert added == 0

    def test_empty_positions(self):
        model = rhino3dm.File3dm()
        added = generate_filaire(model, [], FLOOR_Z, start_id=1)
        assert added == 0

    def test_multiple_floors(self):
        """Multiple support positions at different floors."""
        model = rhino3dm.File3dm()
        positions = [
            (-40.0, -80.0, -4.44),
            (-40.0, -80.0, 2.12),
            (-40.0, -80.0, 17.96),
        ]

        added = generate_filaire(model, positions, FLOOR_Z, start_id=1)
        assert added == 3


# =========================================================================
# Grid line generation tests
# =========================================================================


class TestGridLineGeneration:
    """Tests for structural grid line generation."""

    def test_basic_generation(self):
        """Creates one PolylineCurve per Y axis line."""
        model = rhino3dm.File3dm()
        ay = _make_axis_lines("Y", [-80.0, -60.0, -40.0])

        added = generate_grid_lines(
            model, ay, x_extent=(-70.0, 0.0)
        )

        assert added == 3
        assert _count_unnamed(model) == 3

    def test_curves_are_unnamed(self):
        """Grid lines should have no name."""
        model = rhino3dm.File3dm()
        ay = _make_axis_lines("Y", [-80.0])

        generate_grid_lines(model, ay, x_extent=(-70.0, 0.0))

        for obj in model.Objects:
            assert obj.Attributes.Name == ""

    def test_curves_span_x_extent(self):
        """Each curve should span the full X extent."""
        model = rhino3dm.File3dm()
        ay = _make_axis_lines("Y", [-80.0])

        generate_grid_lines(model, ay, x_extent=(-70.0, 0.0))

        geom = model.Objects[0].Geometry
        assert isinstance(geom, rhino3dm.PolylineCurve)
        p1 = geom.Point(0)
        p2 = geom.Point(geom.PointCount - 1)
        assert abs(p1.X - (-70.0)) < 0.01
        assert abs(p2.X - 0.0) < 0.01
        assert abs(p1.Y - (-80.0)) < 0.01
        assert abs(p2.Y - (-80.0)) < 0.01

    def test_empty_axes(self):
        model = rhino3dm.File3dm()
        added = generate_grid_lines(model, [], x_extent=(-70.0, 0.0))
        assert added == 0

    def test_files_layer_routing(self):
        """Y positions in files_y_positions should use files layer."""
        model = rhino3dm.File3dm()
        # Must add layers so rhino3dm recognizes the indices
        default_layer = rhino3dm.Layer()
        default_layer.Name = "Defaut"
        model.Layers.Add(default_layer)
        files_layer = rhino3dm.Layer()
        files_layer.Name = "Files"
        model.Layers.Add(files_layer)

        ay = _make_axis_lines("Y", [-80.0, -60.0, -40.0])

        added = generate_grid_lines(
            model, ay,
            x_extent=(-70.0, 0.0),
            default_layer_index=0,
            files_layer_index=1,
            files_y_positions=[-60.0],
        )

        assert added == 3
        layer_indices = [obj.Attributes.LayerIndex for obj in model.Objects]
        assert 1 in layer_indices  # files layer used


# =========================================================================
# Integration tests with real data
# =========================================================================


BEFORE_3DM = Path("data/input/before.3dm")
STRUCT_DB = Path("data/input/geometrie_2.db")
AFTER_3DM = Path("data/input/after.3dm")


@pytest.mark.skipif(
    not BEFORE_3DM.exists() or not AFTER_3DM.exists(),
    reason="Real data files not available",
)
class TestObjectAdditionRealDataCounts:
    """Verify object counts match expected ranges from after.3dm analysis."""

    def test_after_3dm_counts(self):
        """Reference check: after.3dm has expected object counts."""
        model = rhino3dm.File3dm.Read(str(AFTER_3DM))

        # Count by category
        named = sum(1 for obj in model.Objects if obj.Attributes.Name)
        unnamed = sum(1 for obj in model.Objects if not obj.Attributes.Name)

        # From our analysis: 237 Appuis, 24 Dalles, 1042 Poteaux,
        # 12 Poutres, 1368 Voiles, 134+33 unnamed
        assert 2700 <= len(model.Objects) <= 3000
        assert unnamed >= 150  # grid lines

    def test_consolidation_on_real_data(self):
        """Dalle consolidation produces objects in expected range."""
        import sqlite3

        model = rhino3dm.File3dm.Read(str(BEFORE_3DM))
        conn = sqlite3.connect(str(STRUCT_DB))
        c = conn.cursor()
        c.execute("SELECT name FROM shell WHERE type='DALLE'")
        dalle_names = {r[0] for r in c.fetchall()}
        conn.close()

        config = PipelineConfig()
        infos = extract_dalle_info(model, dalle_names)

        # Filter out roof dalles
        non_roof = [d for d in infos if d.z < config.roof_z_threshold]

        out_model = rhino3dm.File3dm()
        added = consolidate_dalles(out_model, non_roof, config.floor_z_levels)

        # Expected: ~22 (18-26 range)
        assert 10 <= added <= 35, f"Expected 18-26, got {added}"
