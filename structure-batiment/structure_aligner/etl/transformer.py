from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import logging
import sqlite3

from structure_aligner.etl.extractor import ExtractionResult, RawVertex

logger = logging.getLogger(__name__)


@dataclass
class Element:
    """A PRD-compliant element record."""
    id: int
    type: str   # "poteau", "poutre", "voile", "dalle", "appui"
    nom: str
    geometry_type: str | None = None


@dataclass
class Vertex:
    """A PRD-compliant vertex record."""
    element_id: int
    x: float
    y: float
    z: float
    vertex_index: int


@dataclass
class TransformResult:
    """Result of the transform step."""
    elements: list[Element] = field(default_factory=list)
    vertices: list[Vertex] = field(default_factory=list)
    matched_count: int = 0
    total_count: int = 0
    unmatched: list[tuple[str, str]] = field(default_factory=list)  # (name, source)
    template_object_count: int = 0
    template_names_hash: str = ""


def transform(extraction: ExtractionResult, db_path: Path) -> TransformResult:
    """
    Link extracted vertices to database elements by name matching.

    Reads element names and IDs from the source database (filaire, shell,
    support tables), then matches them to the 3dm extraction results.
    Unmatched items are logged and skipped.

    Args:
        extraction: Result from extract_vertices().
        db_path: Path to the source .db file.

    Returns:
        TransformResult with PRD-compliant elements and vertices.
    """
    result = TransformResult()

    # Load name->id mapping from database
    db_elements = _load_db_elements(db_path)
    db_name_to_element = {e.nom: e for e in db_elements}
    db_names = set(db_name_to_element.keys())

    # Get unique 3dm element names
    threedm_names = set()
    vertices_by_name: dict[str, list[RawVertex]] = {}
    for v in extraction.vertices:
        threedm_names.add(v.element_name)
        vertices_by_name.setdefault(v.element_name, []).append(v)

    result.total_count = len(threedm_names | db_names)

    # Find matches and mismatches
    matched_names = threedm_names & db_names
    only_3dm = threedm_names - db_names
    only_db = db_names - threedm_names

    result.matched_count = len(matched_names)

    for name in sorted(only_3dm):
        result.unmatched.append((name, "3dm_only"))
        logger.warning("Element '%s' exists in .3dm but not in .db — skipping vertices", name)

    for name in sorted(only_db):
        result.unmatched.append((name, "db_only"))
        logger.warning("Element '%s' exists in .db but not in .3dm — included without vertices", name)

    # Build elements list: all DB elements (even those without 3dm geometry)
    for element in db_elements:
        result.elements.append(element)

    # Build vertices list: only for matched names
    for name in sorted(matched_names):
        element = db_name_to_element[name]
        raw_verts = vertices_by_name[name]
        if raw_verts:
            element.geometry_type = raw_verts[0].geometry_type
        for rv in raw_verts:
            result.vertices.append(Vertex(
                element_id=element.id,
                x=rv.x,
                y=rv.y,
                z=rv.z,
                vertex_index=rv.vertex_index,
            ))

    # Validate: no NULL coordinates
    invalid_count = 0
    valid_vertices = []
    for v in result.vertices:
        if v.x is None or v.y is None or v.z is None:
            invalid_count += 1
            logger.warning("Vertex with NULL coordinate for element_id=%d — skipped", v.element_id)
            continue
        if abs(v.x) > 10000 or abs(v.y) > 10000 or abs(v.z) > 10000:
            logger.warning("Vertex with out-of-range coordinate (%.2f, %.2f, %.2f) for element_id=%d",
                          v.x, v.y, v.z, v.element_id)
        valid_vertices.append(v)

    if invalid_count > 0:
        logger.warning("Rejected %d vertices with NULL coordinates", invalid_count)
    result.vertices = valid_vertices

    result.template_object_count = extraction.total_objects
    names_str = "\n".join(sorted(threedm_names))
    result.template_names_hash = hashlib.sha256(names_str.encode()).hexdigest()

    return result


def _load_db_elements(db_path: Path) -> list[Element]:
    """Load all elements from filaire, shell, and support tables."""
    elements = []
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # Filaire: POTEAU, POUTRE
        cursor.execute("SELECT id, type, name FROM filaire")
        for row in cursor.fetchall():
            elements.append(Element(id=row[0], type=row[1].lower(), nom=row[2]))

        # Shell: VOILE, DALLE
        cursor.execute("SELECT id, type, name FROM shell")
        for row in cursor.fetchall():
            elements.append(Element(id=row[0], type=row[1].lower(), nom=row[2]))

        # Support
        cursor.execute("SELECT id, name FROM support")
        for row in cursor.fetchall():
            elements.append(Element(id=row[0], type="appui", nom=row[1]))

    finally:
        conn.close()

    return elements
