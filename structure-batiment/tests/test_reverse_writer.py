from pathlib import Path
import json
import pytest
import rhino3dm

from structure_aligner.etl.reverse_reader import AlignedElement, AlignedVertexCoord
from structure_aligner.etl.reverse_writer import write_aligned_3dm

DATA_DIR = Path(__file__).parent.parent / "data"
DM_FILE = DATA_DIR / "geometrie_2.3dm"


def _create_test_3dm(path, objects):
    """Helper: create a .3dm with given objects.
    objects: list of (name, geometry) tuples.
    """
    model = rhino3dm.File3dm()
    for name, geom in objects:
        attr = rhino3dm.ObjectAttributes()
        attr.Name = name
        model.Objects.Add(geom, attr)
    model.Write(str(path), 0)


def _make_point(x, y, z):
    """Create a Point geometry."""
    return rhino3dm.Point(rhino3dm.Point3d(x, y, z))


def _make_line_curve(x1, y1, z1, x2, y2, z2):
    """Create a LineCurve geometry."""
    return rhino3dm.LineCurve(
        rhino3dm.Point3d(x1, y1, z1),
        rhino3dm.Point3d(x2, y2, z2),
    )


def _make_polyline_curve(points):
    """Create a PolylineCurve from list of (x,y,z) tuples."""
    pts = rhino3dm.Point3dList(len(points))
    for x, y, z in points:
        pts.Add(x, y, z)
    return rhino3dm.PolylineCurve(pts)


class TestReverseWriterPoint:

    def test_updates_point_correctly(self, tmp_path):
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [("P1", _make_point(1, 2, 3))])

        elements = {
            "P1": AlignedElement(1, "P1", "point", [AlignedVertexCoord(0, 10, 20, 30)])
        }
        report = write_aligned_3dm(template, elements, output)

        assert report.updated_objects == 1
        assert report.updated_vertices == 1

        model = rhino3dm.File3dm.Read(str(output))
        geom = model.Objects[0].Geometry
        assert abs(geom.Location.X - 10) < 1e-6
        assert abs(geom.Location.Y - 20) < 1e-6
        assert abs(geom.Location.Z - 30) < 1e-6

    def test_point_wrong_vertex_count(self, tmp_path):
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [("P1", _make_point(1, 2, 3))])

        elements = {
            "P1": AlignedElement(1, "P1", "point", [
                AlignedVertexCoord(0, 10, 20, 30),
                AlignedVertexCoord(1, 40, 50, 60),
            ])
        }
        report = write_aligned_3dm(template, elements, output)
        assert "P1" in report.mismatched_objects
        assert report.updated_objects == 0


class TestReverseWriterLineCurve:

    def test_updates_line_curve_correctly(self, tmp_path):
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [("L1", _make_line_curve(0, 0, 0, 1, 1, 1))])

        elements = {
            "L1": AlignedElement(1, "L1", "line_curve", [
                AlignedVertexCoord(0, 10, 20, 30),
                AlignedVertexCoord(1, 40, 50, 60),
            ])
        }
        report = write_aligned_3dm(template, elements, output)
        assert report.updated_objects == 1
        assert report.updated_vertices == 2

        model = rhino3dm.File3dm.Read(str(output))
        geom = model.Objects[0].Geometry
        assert abs(geom.PointAtStart.X - 10) < 1e-6
        assert abs(geom.PointAtStart.Y - 20) < 1e-6
        assert abs(geom.PointAtStart.Z - 30) < 1e-6
        assert abs(geom.PointAtEnd.X - 40) < 1e-6
        assert abs(geom.PointAtEnd.Y - 50) < 1e-6
        assert abs(geom.PointAtEnd.Z - 60) < 1e-6


class TestReverseWriterPolylineCurve:

    def test_updates_polyline_correctly(self, tmp_path):
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [("PL1", _make_polyline_curve([(0, 0, 0), (1, 1, 1), (2, 2, 2)]))])

        elements = {
            "PL1": AlignedElement(1, "PL1", "polyline_curve", [
                AlignedVertexCoord(0, 10, 20, 30),
                AlignedVertexCoord(1, 40, 50, 60),
                AlignedVertexCoord(2, 70, 80, 90),
            ])
        }
        report = write_aligned_3dm(template, elements, output)
        assert report.updated_objects == 1
        assert report.updated_vertices == 3

        model = rhino3dm.File3dm.Read(str(output))
        geom = model.Objects[0].Geometry
        p0 = geom.Point(0)
        assert abs(p0.X - 10) < 1e-6
        assert abs(p0.Y - 20) < 1e-6
        assert abs(p0.Z - 30) < 1e-6
        p2 = geom.Point(2)
        assert abs(p2.X - 70) < 1e-6
        assert abs(p2.Y - 80) < 1e-6
        assert abs(p2.Z - 90) < 1e-6


class TestReverseWriterSkipsAndWarnings:

    def test_skips_unnamed_objects(self, tmp_path):
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        model = rhino3dm.File3dm()
        attr = rhino3dm.ObjectAttributes()
        attr.Name = ""
        model.Objects.Add(_make_point(1, 2, 3), attr)
        model.Write(str(template), 0)

        report = write_aligned_3dm(template, {}, output)
        assert len(report.skipped_objects) >= 1
        assert report.updated_objects == 0

    def test_skips_objects_not_in_db(self, tmp_path):
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [("P1", _make_point(1, 2, 3))])

        report = write_aligned_3dm(template, {}, output)
        assert "P1" in report.skipped_objects
        assert report.updated_objects == 0

    def test_reports_vertex_count_mismatch(self, tmp_path):
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [("L1", _make_line_curve(0, 0, 0, 1, 1, 1))])

        elements = {
            "L1": AlignedElement(1, "L1", "line_curve", [
                AlignedVertexCoord(0, 10, 20, 30),
            ])
        }
        report = write_aligned_3dm(template, elements, output)
        assert "L1" in report.mismatched_objects
        assert report.updated_objects == 0

    def test_generates_valid_json_report(self, tmp_path):
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [("P1", _make_point(1, 2, 3))])

        elements = {
            "P1": AlignedElement(1, "P1", "point", [AlignedVertexCoord(0, 10, 20, 30)])
        }
        report = write_aligned_3dm(template, elements, output)

        data = json.loads(report.report_path.read_text())
        assert data["statistics"]["updated_objects"] == 1
        assert data["statistics"]["updated_vertices"] == 1
        assert "brep_edge_desync" in data

    def test_template_not_found(self):
        with pytest.raises(FileNotFoundError):
            write_aligned_3dm(
                Path("/nonexistent.3dm"),
                {},
                Path("/output.3dm"),
            )

    def test_preserves_unmatched_objects(self, tmp_path):
        """Objects not in the DB should keep their original coordinates."""
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [
            ("P1", _make_point(1, 2, 3)),
            ("P2", _make_point(4, 5, 6)),
        ])

        elements = {
            "P1": AlignedElement(1, "P1", "point", [AlignedVertexCoord(0, 10, 20, 30)])
        }
        report = write_aligned_3dm(template, elements, output)

        model = rhino3dm.File3dm.Read(str(output))
        for obj in model.Objects:
            if obj.Attributes.Name == "P2":
                geom = obj.Geometry
                assert abs(geom.Location.X - 4) < 1e-6
                assert abs(geom.Location.Y - 5) < 1e-6
                assert abs(geom.Location.Z - 6) < 1e-6
                break

    def test_skips_elements_with_no_vertices(self, tmp_path):
        """Elements in DB but with empty vertex list should be silently skipped."""
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [("P1", _make_point(1, 2, 3))])

        elements = {
            "P1": AlignedElement(1, "P1", "point", [])
        }
        report = write_aligned_3dm(template, elements, output)
        assert report.updated_objects == 0


class TestReverseWriterMultipleTypes:

    def test_handles_mixed_geometry_types(self, tmp_path):
        """Test with Point + LineCurve in same file."""
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [
            ("P1", _make_point(1, 2, 3)),
            ("L1", _make_line_curve(0, 0, 0, 1, 1, 1)),
        ])

        elements = {
            "P1": AlignedElement(1, "P1", "point", [AlignedVertexCoord(0, 10, 20, 30)]),
            "L1": AlignedElement(2, "L1", "line_curve", [
                AlignedVertexCoord(0, 40, 50, 60),
                AlignedVertexCoord(1, 70, 80, 90),
            ]),
        }
        report = write_aligned_3dm(template, elements, output)
        assert report.updated_objects == 2
        assert report.updated_vertices == 3

    def test_handles_all_curve_types(self, tmp_path):
        """Test with Point + LineCurve + PolylineCurve in same file."""
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [
            ("P1", _make_point(1, 2, 3)),
            ("L1", _make_line_curve(0, 0, 0, 1, 1, 1)),
            ("PL1", _make_polyline_curve([(0, 0, 0), (1, 1, 1), (2, 2, 2)])),
        ])

        elements = {
            "P1": AlignedElement(1, "P1", "point", [AlignedVertexCoord(0, 10, 20, 30)]),
            "L1": AlignedElement(2, "L1", "line_curve", [
                AlignedVertexCoord(0, 40, 50, 60),
                AlignedVertexCoord(1, 70, 80, 90),
            ]),
            "PL1": AlignedElement(3, "PL1", "polyline_curve", [
                AlignedVertexCoord(0, 100, 110, 120),
                AlignedVertexCoord(1, 130, 140, 150),
                AlignedVertexCoord(2, 160, 170, 180),
            ]),
        }
        report = write_aligned_3dm(template, elements, output)
        assert report.updated_objects == 3
        assert report.updated_vertices == 6

    def test_report_counts_total_objects(self, tmp_path):
        template = tmp_path / "template.3dm"
        output = tmp_path / "output.3dm"
        _create_test_3dm(template, [
            ("P1", _make_point(1, 2, 3)),
            ("P2", _make_point(4, 5, 6)),
            ("P3", _make_point(7, 8, 9)),
        ])

        elements = {
            "P1": AlignedElement(1, "P1", "point", [AlignedVertexCoord(0, 10, 20, 30)])
        }
        report = write_aligned_3dm(template, elements, output)
        assert report.total_objects == 3
        assert report.updated_objects == 1
        assert len(report.skipped_objects) == 2
