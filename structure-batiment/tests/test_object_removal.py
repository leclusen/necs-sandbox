"""Tests for object-level removal rules (Phase 4)."""

from pathlib import Path

import pytest
import rhino3dm

from structure_aligner.config import PipelineConfig
from structure_aligner.transform.object_rules import (
    ObjectTransformResult,
    remove_dalles,
    remove_multiface_voiles,
    remove_obsolete_supports,
)


BEFORE_3DM = Path("data/input/before.3dm")
STRUCT_DB = Path("data/input/geometrie_2.db")


# =========================================================================
# Synthetic helper
# =========================================================================


def _make_model_with_points(names_and_positions: list[tuple[str, float, float, float]]) -> rhino3dm.File3dm:
    """Create a minimal 3dm model with named Point objects."""
    model = rhino3dm.File3dm()
    for name, x, y, z in names_and_positions:
        pt = rhino3dm.Point(rhino3dm.Point3d(x, y, z))
        attr = rhino3dm.ObjectAttributes()
        attr.Name = name
        model.Objects.AddPoint(rhino3dm.Point3d(x, y, z), attr)
    return model


def _make_model_with_breps(
    names_and_z: list[tuple[str, float, int]],
) -> rhino3dm.File3dm:
    """Create a minimal 3dm model with named Brep objects at given Z.

    Uses small spheres to generate single-face Breps centered at each Z.
    """
    model = rhino3dm.File3dm()
    for name, z, _ in names_and_z:
        sphere = rhino3dm.Sphere(rhino3dm.Point3d(0, 0, z), 0.1)
        brep = sphere.ToBrep()
        if brep is not None:
            attr = rhino3dm.ObjectAttributes()
            attr.Name = name
            model.Objects.AddBrep(brep, attr)
    return model


def _count_named(model: rhino3dm.File3dm, name: str) -> int:
    """Count objects with the given name in the model."""
    return sum(1 for obj in model.Objects if obj.Attributes.Name == name)


def _get_all_names(model: rhino3dm.File3dm) -> set[str]:
    """Get all object names from the model."""
    return {obj.Attributes.Name for obj in model.Objects if obj.Attributes.Name}


# =========================================================================
# Dalle removal tests
# =========================================================================


class TestRemoveDallesSynthetic:
    """Synthetic tests for dalle removal logic."""

    def test_removes_low_z_dalles(self, tmp_path):
        """Dalles below roof threshold should be removed."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE shell (id INTEGER PRIMARY KEY, name TEXT, type TEXT)"
        )
        conn.execute("INSERT INTO shell VALUES (1, 'Dalle_1', 'DALLE')")
        conn.execute("INSERT INTO shell VALUES (2, 'Dalle_2', 'DALLE')")
        conn.execute("INSERT INTO shell VALUES (3, 'Voile_1', 'VOILE')")
        conn.commit()
        conn.close()

        model = _make_model_with_breps([
            ("Dalle_1", 5.0, 1),
            ("Dalle_2", 2.0, 1),
            ("Voile_1", 5.0, 1),
        ])

        config = PipelineConfig(roof_z_threshold=30.0)
        removed, kept = remove_dalles(model, db_path, config)

        assert removed == 2
        assert kept == 0
        # Voile should still be there
        assert _count_named(model, "Voile_1") == 1

    def test_keeps_roof_dalles(self, tmp_path):
        """Dalles above roof threshold should be kept."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE shell (id INTEGER PRIMARY KEY, name TEXT, type TEXT)"
        )
        conn.execute("INSERT INTO shell VALUES (1, 'Dalle_Low', 'DALLE')")
        conn.execute("INSERT INTO shell VALUES (2, 'Dalle_Roof', 'DALLE')")
        conn.commit()
        conn.close()

        model = _make_model_with_breps([
            ("Dalle_Low", 5.0, 1),
            ("Dalle_Roof", 32.36, 1),
        ])

        config = PipelineConfig(roof_z_threshold=30.0)
        removed, kept = remove_dalles(model, db_path, config)

        assert removed == 1
        assert kept == 1
        assert _count_named(model, "Dalle_Roof") == 1
        assert _count_named(model, "Dalle_Low") == 0

    def test_empty_db(self, tmp_path):
        """No dalles in DB should result in 0 removals."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE shell (id INTEGER PRIMARY KEY, name TEXT, type TEXT)"
        )
        conn.commit()
        conn.close()

        model = rhino3dm.File3dm()
        config = PipelineConfig()
        removed, kept = remove_dalles(model, db_path, config)

        assert removed == 0
        assert kept == 0


# =========================================================================
# Support removal tests
# =========================================================================


class TestRemoveObsoleteSupportsSynthetic:
    """Synthetic tests for support removal logic."""

    def test_removes_at_matching_x(self, tmp_path):
        """Supports at removed axis X positions should be removed."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE support (id INTEGER PRIMARY KEY, name TEXT)"
        )
        conn.execute("INSERT INTO support VALUES (1, 'Appuis_1')")
        conn.execute("INSERT INTO support VALUES (2, 'Appuis_2')")
        conn.execute("INSERT INTO support VALUES (3, 'Appuis_3')")
        conn.commit()
        conn.close()

        model = _make_model_with_points([
            ("Appuis_1", -10.830, 5.0, -4.44),
            ("Appuis_2", -10.830, 10.0, -4.44),
            ("Appuis_3", 20.0, 5.0, -4.44),  # Different X, should be kept
        ])

        removed = remove_obsolete_supports(
            model, db_path, removed_axis_x=[-10.830]
        )

        assert removed == 2
        assert _count_named(model, "Appuis_3") == 1

    def test_keeps_all_when_no_removed_axes(self, tmp_path):
        """No removed axis lines means no supports removed."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE support (id INTEGER PRIMARY KEY, name TEXT)"
        )
        conn.execute("INSERT INTO support VALUES (1, 'Appuis_1')")
        conn.commit()
        conn.close()

        model = _make_model_with_points([
            ("Appuis_1", 10.0, 5.0, 2.12),
        ])

        removed = remove_obsolete_supports(
            model, db_path, removed_axis_x=[]
        )

        assert removed == 0

    def test_tolerance_matching(self, tmp_path):
        """Support slightly off should still match within tolerance."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE support (id INTEGER PRIMARY KEY, name TEXT)"
        )
        conn.execute("INSERT INTO support VALUES (1, 'Appuis_1')")
        conn.commit()
        conn.close()

        model = _make_model_with_points([
            ("Appuis_1", -10.835, 5.0, -4.44),  # 5mm off
        ])

        removed = remove_obsolete_supports(
            model, db_path, removed_axis_x=[-10.830], tolerance=0.01
        )

        assert removed == 1

    def test_outside_tolerance(self, tmp_path):
        """Support far from removed axis should not be removed."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE support (id INTEGER PRIMARY KEY, name TEXT)"
        )
        conn.execute("INSERT INTO support VALUES (1, 'Appuis_1')")
        conn.commit()
        conn.close()

        model = _make_model_with_points([
            ("Appuis_1", -10.0, 5.0, -4.44),  # 0.83m off
        ])

        removed = remove_obsolete_supports(
            model, db_path, removed_axis_x=[-10.830], tolerance=0.01
        )

        assert removed == 0


# =========================================================================
# Multi-face voile removal tests
# =========================================================================


class TestRemoveMultifaceVoilesSynthetic:
    """Synthetic tests for multi-face voile removal."""

    def test_single_face_kept(self, tmp_path):
        """Single-face voiles should not be removed."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE shell (id INTEGER PRIMARY KEY, name TEXT, type TEXT)"
        )
        conn.execute("INSERT INTO shell VALUES (1, 'Voile_1', 'VOILE')")
        conn.commit()
        conn.close()

        # Create model with single-face brep
        model = _make_model_with_breps([("Voile_1", 5.0, 1)])

        removed = remove_multiface_voiles(model, db_path, min_faces=2)

        assert len(removed) == 0
        assert _count_named(model, "Voile_1") == 1

    def test_non_voile_not_affected(self, tmp_path):
        """Non-voile objects should never be removed even if multi-face."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE shell (id INTEGER PRIMARY KEY, name TEXT, type TEXT)"
        )
        conn.execute("INSERT INTO shell VALUES (1, 'Dalle_1', 'DALLE')")
        conn.commit()
        conn.close()

        model = _make_model_with_breps([("Dalle_1", 5.0, 1)])

        removed = remove_multiface_voiles(model, db_path, min_faces=1)

        assert len(removed) == 0

    def test_empty_db(self, tmp_path):
        """No voiles in DB should return empty list."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE shell (id INTEGER PRIMARY KEY, name TEXT, type TEXT)"
        )
        conn.commit()
        conn.close()

        model = rhino3dm.File3dm()
        removed = remove_multiface_voiles(model, db_path)

        assert removed == []


# =========================================================================
# ObjectTransformResult tests
# =========================================================================


class TestObjectTransformResult:
    """Test the result dataclass."""

    def test_default_values(self):
        result = ObjectTransformResult()
        assert result.dalles_removed == 0
        assert result.dalles_kept == 0
        assert result.supports_removed == 0
        assert result.voiles_removed == 0
        assert result.removed_voile_names == []
        assert result.errors == []


# =========================================================================
# Integration tests with real data
# =========================================================================


@pytest.mark.skipif(
    not BEFORE_3DM.exists() or not STRUCT_DB.exists(),
    reason="Real data files not available",
)
class TestRemoveDallesRealData:
    """Integration tests using real before.3dm and geometrie_2.db."""

    def test_dalle_removal_count(self):
        """Should remove ~202 of 208 dalles, keeping ~6 roof dalles."""
        model = rhino3dm.File3dm.Read(str(BEFORE_3DM))
        config = PipelineConfig(roof_z_threshold=30.0)
        initial = len(model.Objects)

        removed, kept = remove_dalles(model, STRUCT_DB, config)

        assert removed >= 200, f"Expected ~202 removed, got {removed}"
        assert removed <= 208, f"Expected <=208 removed, got {removed}"
        assert kept >= 1, f"Expected at least 1 roof dalle kept, got {kept}"
        assert len(model.Objects) == initial - removed

    def test_roof_dalles_preserved(self):
        """Dalles at Z>30 (roof level) should be preserved."""
        import sqlite3

        model = rhino3dm.File3dm.Read(str(BEFORE_3DM))
        config = PipelineConfig(roof_z_threshold=30.0)

        conn = sqlite3.connect(str(STRUCT_DB))
        c = conn.cursor()
        c.execute("SELECT name FROM shell WHERE type='DALLE'")
        dalle_names = {r[0] for r in c.fetchall()}
        conn.close()

        remove_dalles(model, STRUCT_DB, config)

        # Check remaining dalles are all at high Z
        remaining_names = _get_all_names(model)
        remaining_dalles = remaining_names & dalle_names
        for obj in model.Objects:
            name = obj.Attributes.Name
            if name in remaining_dalles:
                geom = obj.Geometry
                if isinstance(geom, rhino3dm.Brep):
                    max_z = max(
                        geom.Vertices[i].Location.Z
                        for i in range(len(geom.Vertices))
                    )
                    assert max_z > 30.0, (
                        f"Remaining dalle {name} has max_z={max_z:.2f}, "
                        f"expected >30.0"
                    )


@pytest.mark.skipif(
    not BEFORE_3DM.exists() or not STRUCT_DB.exists(),
    reason="Real data files not available",
)
class TestRemoveObsoleteSupportsRealData:
    """Integration tests for support removal on real data."""

    def test_support_removal_count(self):
        """Should remove 7 supports at X=-10.830."""
        model = rhino3dm.File3dm.Read(str(BEFORE_3DM))
        initial = len(model.Objects)

        removed = remove_obsolete_supports(model, STRUCT_DB)

        assert removed == 7, f"Expected 7 removed, got {removed}"
        assert len(model.Objects) == initial - 7

    def test_removed_supports_at_correct_position(self):
        """All removed supports should be at X=-10.830, Z=-4.440."""
        import sqlite3

        model = rhino3dm.File3dm.Read(str(BEFORE_3DM))

        conn = sqlite3.connect(str(STRUCT_DB))
        c = conn.cursor()
        c.execute("SELECT name FROM support")
        support_names = {r[0] for r in c.fetchall()}
        conn.close()

        # Collect positions before removal
        support_positions = {}
        for obj in model.Objects:
            name = obj.Attributes.Name
            if name in support_names:
                geom = obj.Geometry
                if isinstance(geom, rhino3dm.Point):
                    support_positions[name] = (
                        geom.Location.X,
                        geom.Location.Y,
                        geom.Location.Z,
                    )

        remove_obsolete_supports(model, STRUCT_DB)

        remaining = _get_all_names(model) & support_names
        removed_names = set(support_positions.keys()) - remaining

        for name in removed_names:
            x, y, z = support_positions[name]
            assert abs(x - (-10.830)) < 0.01, f"{name}: X={x}"
            assert abs(z - (-4.440)) < 0.01, f"{name}: Z={z}"


@pytest.mark.skipif(
    not BEFORE_3DM.exists() or not STRUCT_DB.exists(),
    reason="Real data files not available",
)
class TestRemoveMultifaceVoilesRealData:
    """Integration tests for multi-face voile removal on real data."""

    def test_multiface_voile_removal_count(self):
        """Should remove ~57 multi-face voiles (2+ faces)."""
        model = rhino3dm.File3dm.Read(str(BEFORE_3DM))
        initial = len(model.Objects)

        removed = remove_multiface_voiles(model, STRUCT_DB)

        assert len(removed) >= 40, f"Expected ~57 removed, got {len(removed)}"
        assert len(removed) <= 120, f"Expected ~57 removed, got {len(removed)}"
        assert len(model.Objects) == initial - len(removed)

    def test_returns_correct_names(self):
        """Returned names should be valid voile names from DB."""
        import sqlite3

        model = rhino3dm.File3dm.Read(str(BEFORE_3DM))

        conn = sqlite3.connect(str(STRUCT_DB))
        c = conn.cursor()
        c.execute("SELECT name FROM shell WHERE type='VOILE'")
        voile_names = {r[0] for r in c.fetchall()}
        conn.close()

        removed = remove_multiface_voiles(model, STRUCT_DB)

        for name in removed:
            assert name in voile_names, f"{name} not a valid voile"
