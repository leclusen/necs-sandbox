from dataclasses import dataclass, field
from pathlib import Path
import logging
import rhino3dm

logger = logging.getLogger(__name__)


@dataclass
class RawVertex:
    """A single vertex extracted from the .3dm file."""
    element_name: str
    x: float
    y: float
    z: float
    vertex_index: int
    category: str  # "poteau", "poutre", "voile", "dalle", "appui"
    geometry_type: str  # "brep", "line_curve", "polyline_curve", "nurbs_curve", "point"


@dataclass
class ExtractionResult:
    """All vertices extracted from a .3dm file."""
    vertices: list[RawVertex] = field(default_factory=list)
    total_objects: int = 0
    total_vertices: int = 0
    skipped_objects: list[str] = field(default_factory=list)


def extract_vertices(path: Path) -> ExtractionResult:
    """
    Extract all vertices from a .3dm Rhino file.

    Handles 5 geometry types: Brep, LineCurve, PolylineCurve,
    NurbsCurve, and Point.

    Args:
        path: Path to the .3dm file.

    Returns:
        ExtractionResult with all raw vertices and metadata.

    Raises:
        FileNotFoundError: If the .3dm file does not exist.
        RuntimeError: If the .3dm file cannot be read.
    """
    if not path.exists():
        raise FileNotFoundError(f"3DM file not found: {path}")

    model = rhino3dm.File3dm.Read(str(path))
    if model is None:
        raise RuntimeError(f"Failed to read 3DM file: {path}")

    # Build layer lookup for category resolution
    layer_by_id = {}
    for layer in model.Layers:
        layer_by_id[str(layer.Id)] = layer

    result = ExtractionResult(total_objects=len(model.Objects))

    for obj in model.Objects:
        name = obj.Attributes.Name
        if not name:
            result.skipped_objects.append(f"unnamed-object-layer-{obj.Attributes.LayerIndex}")
            continue

        geom = obj.Geometry
        layer = model.Layers[obj.Attributes.LayerIndex]
        category = _resolve_category(layer, layer_by_id)

        extracted = _extract_from_geometry(name, geom, category)
        if extracted is None:
            result.skipped_objects.append(name)
            logger.debug("Skipped unsupported geometry type %s for %s", type(geom).__name__, name)
            continue

        result.vertices.extend(extracted)

    result.total_vertices = len(result.vertices)
    return result


def _resolve_category(layer: rhino3dm.Layer, layer_by_id: dict) -> str:
    """Walk up the layer hierarchy to find the top-level category name."""
    current = layer
    null_id = "00000000-0000-0000-0000-000000000000"

    while str(current.ParentLayerId) != null_id:
        parent_id = str(current.ParentLayerId)
        if parent_id in layer_by_id:
            current = layer_by_id[parent_id]
        else:
            break

    # Map Rhino layer names to PRD element types
    category_map = {
        "Poteau": "poteau",
        "Poutre": "poutre",
        "Voile": "voile",
        "Dalle": "dalle",
        "Appuis": "appui",
    }
    return category_map.get(current.Name, "unknown")


def _extract_from_geometry(
    name: str, geom: rhino3dm.GeometryBase, category: str
) -> list[RawVertex] | None:
    """Extract vertices from a single geometry object."""
    vertices = []

    if isinstance(geom, rhino3dm.Brep):
        for vi in range(len(geom.Vertices)):
            v = geom.Vertices[vi]
            vertices.append(RawVertex(name, v.Location.X, v.Location.Y, v.Location.Z, vi, category, "brep"))

    elif isinstance(geom, rhino3dm.LineCurve):
        vertices.append(RawVertex(name, geom.PointAtStart.X, geom.PointAtStart.Y, geom.PointAtStart.Z, 0, category, "line_curve"))
        vertices.append(RawVertex(name, geom.PointAtEnd.X, geom.PointAtEnd.Y, geom.PointAtEnd.Z, 1, category, "line_curve"))

    elif isinstance(geom, rhino3dm.PolylineCurve):
        for pi in range(geom.PointCount):
            p = geom.Point(pi)
            vertices.append(RawVertex(name, p.X, p.Y, p.Z, pi, category, "polyline_curve"))

    elif isinstance(geom, rhino3dm.NurbsCurve):
        for pi in range(len(geom.Points)):
            p = geom.Points[pi]
            vertices.append(RawVertex(name, p.X, p.Y, p.Z, pi, category, "nurbs_curve"))

    elif isinstance(geom, rhino3dm.Point):
        vertices.append(RawVertex(name, geom.Location.X, geom.Location.Y, geom.Location.Z, 0, category, "point"))

    else:
        return None

    return vertices
