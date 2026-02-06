# ETL Pipeline: Rhino 3DM to PRD-Compliant Database

## Overview

Build an ETL pipeline that extracts vertex geometry from `geometrie_2.3dm` (Rhino file) using `rhino3dm`, links it to structural metadata in `geometrie_2.db`, and produces a PRD-compliant output database with `elements` + `vertices` tables. This is the prerequisite data preparation step before the alignment algorithm (DBSCAN clustering) can run.

## Current State Analysis

### What Exists
- **`structure-batiment/data/geometrie_2.3dm`** (49.4 MB): Rhino 3D model with 5,825 geometry objects
- **`structure-batiment/data/geometrie_2.db`** (952 KB): SQLite database with 5,825 structural elements across 17 tables
- **`.venv/`**: Python venv with `rhino3dm` 8.17.0 already installed
- **No Python source code**: Project is in planning phase

### What's Missing
- No `elements` table in PRD format (data split across `filaire`, `shell`, `support`)
- No `vertices` table at all (coordinates only in `.3dm` file)
- No project packaging (`pyproject.toml`, package structure)
- No CLI entry point

### Key Discoveries (from research)
- **1:1 name mapping**: 5,824/5,825 object names match between `.3dm` and `.db` (99.98%)
- **Single mismatch**: `Filaire_7415` (3dm only) vs `Filaire_7416` (db only)
- **20,996 total vertices** extractable from 5 geometry types:
  - `Brep` (voiles/dalles): access via `geom.Vertices[i].Location`
  - `LineCurve` (poteaux/poutres): access via `geom.PointAtStart` / `geom.PointAtEnd`
  - `PolylineCurve` (157 multi-segment beams): access via `geom.Point(i)`
  - `NurbsCurve` (3 curved beams): access via `geom.Points[i]`
  - `Point` (supports): access via `geom.Location`
- **Coordinates in meters**: X range [-72.18, 46.80], Y range [-88.15, 31.25], Z range [-4.44, 37.21]
- **13 floor levels** on Z-axis (already naturally clustered)
- **Layer hierarchy** maps to element categories: `Poteau`, `Poutre`, `Voile`, `Dalle`, `Appuis`
- **Element type mapping**: `POTEAU`→`poteau`, `POUTRE`→`poutre`, `VOILE`→`voile`, `DALLE`→`dalle`

## Desired End State

After this plan is complete:

1. A Python package `structure_aligner` exists with a working ETL pipeline
2. Running `python -m structure_aligner etl --input-3dm data/geometrie_2.3dm --input-db data/geometrie_2.db --output data/output.db` produces a new SQLite database containing:
   - All 17 original tables from `geometrie_2.db` (copied)
   - A new `elements` table with 5,825 rows matching PRD schema (id, type, nom)
   - A new `vertices` table with ~20,996 rows matching PRD schema (id, element_id, x, y, z, vertex_index)
3. A JSON validation report is written alongside the output DB
4. Unit tests verify extraction, transformation, and loading

### Verification
```bash
# Run the ETL
python -m structure_aligner etl \
  --input-3dm structure-batiment/data/geometrie_2.3dm \
  --input-db structure-batiment/data/geometrie_2.db \
  --output structure-batiment/data/geometrie_2_prd.db

# Verify output
sqlite3 structure-batiment/data/geometrie_2_prd.db "SELECT COUNT(*) FROM elements;"
# Expected: 5825

sqlite3 structure-batiment/data/geometrie_2_prd.db "SELECT COUNT(*) FROM vertices;"
# Expected: ~20996

sqlite3 structure-batiment/data/geometrie_2_prd.db "SELECT type, COUNT(*) FROM elements GROUP BY type;"
# Expected: poteau|1527, poutre|1192, voile|2669, dalle|284, appui|153

# Run tests
python -m pytest tests/ -v
```

## What We're NOT Doing

- **Alignment algorithm**: No DBSCAN clustering, thread detection, or vertex alignment (that's the next plan)
- **Multi-DB support**: Only SQLite for now (PostgreSQL/MySQL are PRD V1 scope but not needed for ETL)
- **CLI for alignment**: Only the `etl` subcommand, not the full `--alpha` alignment CLI
- **Performance optimization**: 20,996 vertices is small; no batch processing or parallelism needed
- **Config file support**: No `config.yaml` — CLI flags are sufficient for ETL
- **Documentation**: No Sphinx docs, no README beyond minimal usage in this plan
- **CI/CD**: No GitHub Actions or CI pipeline

## Implementation Approach

Follow the PRD module structure (`structure_aligner/`) but only build what's needed for ETL. Use `click` for CLI, `rhino3dm` for .3dm reading, plain `sqlite3` for database operations (no SQLAlchemy — overkill for SQLite-only ETL). Keep it simple.

---

## Phase 1: Project Scaffolding

### Overview
Set up the Python package structure, dependencies, and CLI entry point.

### Changes Required:

#### 1. Project configuration
**File**: `structure-batiment/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "structure-aligner"
version = "0.1.0"
description = "Geometric alignment software for building structures"
requires-python = ">=3.10"
dependencies = [
    "rhino3dm>=8.0.0",
    "click>=8.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=3.0.0",
]

[project.scripts]
structure-aligner = "structure_aligner.main:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

#### 2. Package structure
Create the following directory tree:

```
structure-batiment/
├── pyproject.toml
├── structure_aligner/
│   ├── __init__.py
│   ├── main.py              # Click CLI entry point
│   ├── etl/
│   │   ├── __init__.py
│   │   ├── extractor.py     # Phase 2: Read .3dm
│   │   ├── transformer.py   # Phase 3: Link & normalize
│   │   └── loader.py        # Phase 4: Write output DB
│   └── utils/
│       ├── __init__.py
│       └── logger.py        # Logging setup
└── tests/
    ├── __init__.py
    ├── conftest.py           # Shared fixtures
    ├── test_extractor.py
    ├── test_transformer.py
    └── test_loader.py
```

#### 3. CLI entry point
**File**: `structure-batiment/structure_aligner/main.py`

```python
import click
import logging
from pathlib import Path

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

if __name__ == "__main__":
    cli()
```

#### 4. Logger utility
**File**: `structure-batiment/structure_aligner/utils/logger.py`

```python
import logging
import sys

def setup_logging(level: str = "INFO") -> None:
    """Configure logging with the PRD-specified format."""
    fmt = "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s"
    logging.basicConfig(
        level=getattr(logging, level),
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )
```

#### 5. Empty init files
**Files**: All `__init__.py` files are empty (just `# noqa`).

### Success Criteria:

#### Automated Verification:
- [x] Install in dev mode: `cd structure-batiment && pip install -e ".[dev]"`
- [x] CLI help works: `python -m structure_aligner --help`
- [x] ETL subcommand shows options: `python -m structure_aligner etl --help`
- [x] Import works: `python -c "from structure_aligner.main import cli"`

#### Manual Verification:
- [ ] Directory structure matches the tree above
- [ ] `pyproject.toml` installs without errors

#### Code Review:
- [ ] Minimal dependencies (only rhino3dm and click for runtime)
- [ ] No unnecessary abstractions
- [ ] Logger format matches PRD NFR-08

**Implementation Note**: After completing this phase, verify the automated criteria pass before proceeding to Phase 2.

---

## Phase 2: Extract — Read .3dm Geometry

### Overview
Read the `.3dm` file using `rhino3dm` and extract all vertex coordinates, organized by element name and category.

### Changes Required:

#### 1. Data classes for extraction results
**File**: `structure-batiment/structure_aligner/etl/extractor.py`

```python
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
            vertices.append(RawVertex(name, v.Location.X, v.Location.Y, v.Location.Z, vi, category))

    elif isinstance(geom, rhino3dm.LineCurve):
        vertices.append(RawVertex(name, geom.PointAtStart.X, geom.PointAtStart.Y, geom.PointAtStart.Z, 0, category))
        vertices.append(RawVertex(name, geom.PointAtEnd.X, geom.PointAtEnd.Y, geom.PointAtEnd.Z, 1, category))

    elif isinstance(geom, rhino3dm.PolylineCurve):
        for pi in range(geom.PointCount):
            p = geom.Point(pi)
            vertices.append(RawVertex(name, p.X, p.Y, p.Z, pi, category))

    elif isinstance(geom, rhino3dm.NurbsCurve):
        for pi in range(len(geom.Points)):
            p = geom.Points[pi]
            vertices.append(RawVertex(name, p.X, p.Y, p.Z, pi, category))

    elif isinstance(geom, rhino3dm.Point):
        vertices.append(RawVertex(name, geom.Location.X, geom.Location.Y, geom.Location.Z, 0, category))

    else:
        return None

    return vertices
```

#### 2. Unit tests for extractor
**File**: `structure-batiment/tests/test_extractor.py`

```python
from pathlib import Path
import pytest
from structure_aligner.etl.extractor import extract_vertices

DATA_DIR = Path(__file__).parent.parent / "data"
DM_FILE = DATA_DIR / "geometrie_2.3dm"

@pytest.mark.skipif(not DM_FILE.exists(), reason="Test data not available")
class TestExtractor:

    def test_extracts_correct_total_objects(self):
        result = extract_vertices(DM_FILE)
        assert result.total_objects == 5825

    def test_extracts_correct_total_vertices(self):
        result = extract_vertices(DM_FILE)
        assert result.total_vertices == 20996

    def test_all_vertices_have_names(self):
        result = extract_vertices(DM_FILE)
        for v in result.vertices:
            assert v.element_name, f"Vertex has empty name"

    def test_all_vertices_have_valid_category(self):
        result = extract_vertices(DM_FILE)
        valid = {"poteau", "poutre", "voile", "dalle", "appui"}
        for v in result.vertices:
            assert v.category in valid, f"Invalid category: {v.category} for {v.element_name}"

    def test_category_counts(self):
        result = extract_vertices(DM_FILE)
        counts = {}
        # Count unique element names per category
        elements_by_cat = {}
        for v in result.vertices:
            elements_by_cat.setdefault(v.category, set()).add(v.element_name)
        counts = {cat: len(names) for cat, names in elements_by_cat.items()}
        assert counts["poteau"] == 1527
        assert counts["poutre"] == 1192
        assert counts["voile"] == 2669
        assert counts["dalle"] == 284
        assert counts["appui"] == 153

    def test_coordinate_ranges(self):
        result = extract_vertices(DM_FILE)
        xs = [v.x for v in result.vertices]
        ys = [v.y for v in result.vertices]
        zs = [v.z for v in result.vertices]
        assert min(xs) == pytest.approx(-72.1752, abs=0.01)
        assert max(xs) == pytest.approx(46.80, abs=0.01)
        assert min(zs) == pytest.approx(-4.44, abs=0.01)
        assert max(zs) == pytest.approx(37.21, abs=0.01)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            extract_vertices(Path("/nonexistent/file.3dm"))

    def test_no_skipped_objects(self):
        result = extract_vertices(DM_FILE)
        assert len(result.skipped_objects) == 0, f"Skipped: {result.skipped_objects[:5]}"
```

### Success Criteria:

#### Automated Verification:
- [x] Extractor tests pass: `cd structure-batiment && python -m pytest tests/test_extractor.py -v`
- [x] Import works: `python -c "from structure_aligner.etl.extractor import extract_vertices"`

#### Manual Verification:
- [x] Run extraction standalone and verify output counts match research (20,996 vertices, 5,825 objects)

#### Code Review:
- [ ] All 5 geometry types handled (Brep, LineCurve, PolylineCurve, NurbsCurve, Point)
- [ ] Category resolution uses layer hierarchy, not name parsing
- [ ] No unnecessary dependencies

**Implementation Note**: After completing this phase, run tests and verify all 8 tests pass before proceeding to Phase 3.

---

## Phase 3: Transform — Link & Normalize

### Overview
Match extracted 3dm element names to database element IDs. Build PRD-compliant `elements` and `vertices` lists. Log and skip unmatched names.

### Changes Required:

#### 1. Transformer module
**File**: `structure-batiment/structure_aligner/etl/transformer.py`

```python
from dataclasses import dataclass, field
from pathlib import Path
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
```

#### 2. Unit tests for transformer
**File**: `structure-batiment/tests/test_transformer.py`

```python
from pathlib import Path
import pytest
from structure_aligner.etl.extractor import extract_vertices, ExtractionResult, RawVertex
from structure_aligner.etl.transformer import transform, _load_db_elements

DATA_DIR = Path(__file__).parent.parent / "data"
DM_FILE = DATA_DIR / "geometrie_2.3dm"
DB_FILE = DATA_DIR / "geometrie_2.db"

@pytest.mark.skipif(not (DM_FILE.exists() and DB_FILE.exists()), reason="Test data not available")
class TestTransformer:

    @pytest.fixture(scope="class")
    def extraction(self):
        return extract_vertices(DM_FILE)

    @pytest.fixture(scope="class")
    def result(self, extraction):
        return transform(extraction, DB_FILE)

    def test_all_db_elements_included(self, result):
        assert len(result.elements) == 5825

    def test_element_types_normalized(self, result):
        types = {e.type for e in result.elements}
        assert types == {"poteau", "poutre", "voile", "dalle", "appui"}

    def test_element_type_counts(self, result):
        from collections import Counter
        counts = Counter(e.type for e in result.elements)
        assert counts["poteau"] == 1527
        assert counts["poutre"] == 1192
        assert counts["voile"] == 2669
        assert counts["dalle"] == 284
        assert counts["appui"] == 153

    def test_matched_count(self, result):
        assert result.matched_count == 5824

    def test_unmatched_count(self, result):
        # 1 in 3dm only + 1 in db only
        assert len(result.unmatched) == 2

    def test_unmatched_names(self, result):
        names = {name for name, _ in result.unmatched}
        assert "Filaire_7415" in names
        assert "Filaire_7416" in names

    def test_vertex_count(self, result):
        # 20996 total minus vertices belonging to Filaire_7415 (2 vertices for a LineCurve)
        assert len(result.vertices) == 20994

    def test_no_null_coordinates(self, result):
        for v in result.vertices:
            assert v.x is not None
            assert v.y is not None
            assert v.z is not None

    def test_all_vertex_element_ids_exist(self, result):
        element_ids = {e.id for e in result.elements}
        for v in result.vertices:
            assert v.element_id in element_ids, f"Orphan vertex: element_id={v.element_id}"


class TestLoadDbElements:

    @pytest.mark.skipif(not DB_FILE.exists(), reason="Test data not available")
    def test_loads_correct_count(self):
        elements = _load_db_elements(DB_FILE)
        assert len(elements) == 5825

    @pytest.mark.skipif(not DB_FILE.exists(), reason="Test data not available")
    def test_no_duplicate_ids(self):
        elements = _load_db_elements(DB_FILE)
        ids = [e.id for e in elements]
        assert len(ids) == len(set(ids)), "Duplicate element IDs found"
```

### Success Criteria:

#### Automated Verification:
- [x] Transformer tests pass: `cd structure-batiment && python -m pytest tests/test_transformer.py -v`
- [x] All 11 tests pass

#### Manual Verification:
- [x] Warnings logged for `Filaire_7415` and `Filaire_7416`
- [x] Vertex count is 20994 (20996 minus 2 for the unmatched LineCurve)

#### Code Review:
- [ ] Name matching is case-sensitive exact match (correct for this dataset)
- [ ] All DB elements included even without 3dm geometry (db_only elements get 0 vertices)
- [ ] NULL coordinate validation per PRD F-02
- [ ] Out-of-range warning (>10000m) per PRD F-02

**Implementation Note**: After completing this phase, run tests and verify all pass before proceeding to Phase 4.

---

## Phase 4: Load — Write PRD-Compliant Database

### Overview
Copy the source database, create `elements` and `vertices` tables, insert all data in a single atomic transaction, generate a JSON validation report.

### Changes Required:

#### 1. Loader module
**File**: `structure-batiment/structure_aligner/etl/loader.py`

```python
from dataclasses import dataclass
from pathlib import Path
import json
import logging
import shutil
import sqlite3
from datetime import datetime, timezone

from structure_aligner.etl.transformer import TransformResult

logger = logging.getLogger(__name__)

@dataclass
class LoadReport:
    """Report generated after loading data."""
    report_path: Path
    elements_inserted: int
    vertices_inserted: int
    validation_passed: bool

# SQL for PRD-compliant tables
CREATE_ELEMENTS_SQL = """
CREATE TABLE IF NOT EXISTS elements (
    id INTEGER PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    nom VARCHAR(100) NOT NULL
);
"""

CREATE_VERTICES_SQL = """
CREATE TABLE IF NOT EXISTS vertices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    element_id INTEGER NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL NOT NULL,
    vertex_index INTEGER NOT NULL,
    FOREIGN KEY (element_id) REFERENCES elements(id)
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_vertices_element_id ON vertices(element_id);",
    "CREATE INDEX IF NOT EXISTS idx_vertices_x ON vertices(x);",
    "CREATE INDEX IF NOT EXISTS idx_vertices_y ON vertices(y);",
    "CREATE INDEX IF NOT EXISTS idx_vertices_z ON vertices(z);",
]


def load(result: TransformResult, source_db: Path, output_path: Path) -> LoadReport:
    """
    Copy source database and add PRD-compliant elements + vertices tables.

    The source database is copied to output_path first (preserving all
    original tables), then elements and vertices tables are created and
    populated in a single atomic transaction.

    Args:
        result: TransformResult from the transform step.
        source_db: Path to the original .db file.
        output_path: Path for the output .db file.

    Returns:
        LoadReport with insertion counts and validation status.

    Raises:
        FileExistsError: If output_path already exists.
        sqlite3.Error: If database operations fail (transaction is rolled back).
    """
    if output_path.exists():
        raise FileExistsError(f"Output file already exists: {output_path}. Remove it first or choose a different path.")

    # Step 1: Copy source database
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source_db), str(output_path))
    logger.info("Copied source database to %s", output_path)

    # Step 2: Create tables and insert data in a single transaction
    conn = sqlite3.connect(str(output_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        cursor = conn.cursor()

        # Create tables
        cursor.execute(CREATE_ELEMENTS_SQL)
        cursor.execute(CREATE_VERTICES_SQL)

        # Insert elements
        cursor.executemany(
            "INSERT INTO elements (id, type, nom) VALUES (?, ?, ?)",
            [(e.id, e.type, e.nom) for e in result.elements],
        )
        elements_inserted = len(result.elements)

        # Insert vertices
        cursor.executemany(
            "INSERT INTO vertices (element_id, x, y, z, vertex_index) VALUES (?, ?, ?, ?, ?)",
            [(v.element_id, v.x, v.y, v.z, v.vertex_index) for v in result.vertices],
        )
        vertices_inserted = len(result.vertices)

        # Create indexes
        for sql in CREATE_INDEXES_SQL:
            cursor.execute(sql)

        conn.commit()
        logger.info("Inserted %d elements, %d vertices", elements_inserted, vertices_inserted)

    except Exception:
        conn.rollback()
        # Clean up the copied file on failure
        output_path.unlink(missing_ok=True)
        raise
    finally:
        conn.close()

    # Step 3: Validate
    validation_passed = _validate_output(output_path, result)

    # Step 4: Generate report
    report_path = output_path.with_suffix(".etl_report.json")
    report = _generate_report(
        report_path, output_path, result,
        elements_inserted, vertices_inserted, validation_passed,
    )

    return report


def _validate_output(output_path: Path, result: TransformResult) -> bool:
    """Run post-load validation checks."""
    conn = sqlite3.connect(str(output_path))
    passed = True
    try:
        cursor = conn.cursor()

        # Check element count
        cursor.execute("SELECT COUNT(*) FROM elements")
        db_count = cursor.fetchone()[0]
        if db_count != len(result.elements):
            logger.error("Element count mismatch: expected %d, got %d", len(result.elements), db_count)
            passed = False

        # Check vertex count
        cursor.execute("SELECT COUNT(*) FROM vertices")
        db_count = cursor.fetchone()[0]
        if db_count != len(result.vertices):
            logger.error("Vertex count mismatch: expected %d, got %d", len(result.vertices), db_count)
            passed = False

        # Check no NULL coordinates
        cursor.execute("SELECT COUNT(*) FROM vertices WHERE x IS NULL OR y IS NULL OR z IS NULL")
        null_count = cursor.fetchone()[0]
        if null_count > 0:
            logger.error("%d vertices with NULL coordinates in output", null_count)
            passed = False

        # Check FK integrity
        cursor.execute("""
            SELECT COUNT(*) FROM vertices v
            LEFT JOIN elements e ON v.element_id = e.id
            WHERE e.id IS NULL
        """)
        orphan_count = cursor.fetchone()[0]
        if orphan_count > 0:
            logger.error("%d vertices with invalid element_id references", orphan_count)
            passed = False

        # Check element types
        cursor.execute("SELECT DISTINCT type FROM elements")
        types = {row[0] for row in cursor.fetchall()}
        expected_types = {"poteau", "poutre", "voile", "dalle", "appui"}
        if types != expected_types:
            logger.error("Unexpected element types: %s (expected %s)", types, expected_types)
            passed = False

    finally:
        conn.close()

    if passed:
        logger.info("All post-load validation checks passed")
    else:
        logger.error("Post-load validation FAILED")

    return passed


def _generate_report(
    report_path: Path,
    output_path: Path,
    result: TransformResult,
    elements_inserted: int,
    vertices_inserted: int,
    validation_passed: bool,
) -> LoadReport:
    """Write a JSON validation report."""
    from collections import Counter

    type_counts = Counter(e.type for e in result.elements)
    xs = [v.x for v in result.vertices]
    ys = [v.y for v in result.vertices]
    zs = [v.z for v in result.vertices]

    report_data = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output_database": str(output_path),
            "pipeline": "etl",
            "software_version": "0.1.0",
        },
        "statistics": {
            "elements_total": elements_inserted,
            "elements_by_type": dict(type_counts),
            "vertices_total": vertices_inserted,
            "matched_elements": result.matched_count,
            "unmatched_elements": len(result.unmatched),
            "unmatched_details": [
                {"name": name, "source": source}
                for name, source in result.unmatched
            ],
        },
        "coordinate_ranges": {
            "x": {"min": min(xs), "max": max(xs)} if xs else None,
            "y": {"min": min(ys), "max": max(ys)} if ys else None,
            "z": {"min": min(zs), "max": max(zs)} if zs else None,
        },
        "validation": {
            "passed": validation_passed,
            "checks": [
                "element_count",
                "vertex_count",
                "no_null_coordinates",
                "fk_integrity",
                "element_types",
            ],
        },
    }

    report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
    logger.info("Validation report written to %s", report_path)

    return LoadReport(
        report_path=report_path,
        elements_inserted=elements_inserted,
        vertices_inserted=vertices_inserted,
        validation_passed=validation_passed,
    )
```

#### 2. Unit tests for loader
**File**: `structure-batiment/tests/test_loader.py`

```python
from pathlib import Path
import json
import sqlite3
import pytest
from structure_aligner.etl.extractor import extract_vertices
from structure_aligner.etl.transformer import transform
from structure_aligner.etl.loader import load

DATA_DIR = Path(__file__).parent.parent / "data"
DM_FILE = DATA_DIR / "geometrie_2.3dm"
DB_FILE = DATA_DIR / "geometrie_2.db"

@pytest.mark.skipif(not (DM_FILE.exists() and DB_FILE.exists()), reason="Test data not available")
class TestLoader:

    @pytest.fixture(scope="class")
    def etl_result(self, tmp_path_factory):
        """Run full ETL pipeline once for all tests in this class."""
        tmp = tmp_path_factory.mktemp("loader")
        output_path = tmp / "output.db"

        extraction = extract_vertices(DM_FILE)
        result = transform(extraction, DB_FILE)
        report = load(result, DB_FILE, output_path)

        return output_path, report

    def test_output_file_created(self, etl_result):
        output_path, _ = etl_result
        assert output_path.exists()

    def test_elements_count(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        count = conn.execute("SELECT COUNT(*) FROM elements").fetchone()[0]
        conn.close()
        assert count == 5825

    def test_vertices_count(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        count = conn.execute("SELECT COUNT(*) FROM vertices").fetchone()[0]
        conn.close()
        assert count == 20994

    def test_original_tables_preserved(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        # Original tables still present
        assert "filaire" in tables
        assert "shell" in tables
        assert "support" in tables
        assert "material" in tables
        # New tables added
        assert "elements" in tables
        assert "vertices" in tables

    def test_element_types(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        types = {row[0] for row in conn.execute("SELECT DISTINCT type FROM elements").fetchall()}
        conn.close()
        assert types == {"poteau", "poutre", "voile", "dalle", "appui"}

    def test_no_null_vertices(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        count = conn.execute("SELECT COUNT(*) FROM vertices WHERE x IS NULL OR y IS NULL OR z IS NULL").fetchone()[0]
        conn.close()
        assert count == 0

    def test_fk_integrity(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        orphans = conn.execute("""
            SELECT COUNT(*) FROM vertices v
            LEFT JOIN elements e ON v.element_id = e.id
            WHERE e.id IS NULL
        """).fetchone()[0]
        conn.close()
        assert orphans == 0

    def test_validation_passed(self, etl_result):
        _, report = etl_result
        assert report.validation_passed is True

    def test_report_file_created(self, etl_result):
        _, report = etl_result
        assert report.report_path.exists()

    def test_report_is_valid_json(self, etl_result):
        _, report = etl_result
        data = json.loads(report.report_path.read_text())
        assert data["validation"]["passed"] is True
        assert data["statistics"]["elements_total"] == 5825
        assert data["statistics"]["vertices_total"] == 20994

    def test_output_exists_error(self, etl_result):
        output_path, _ = etl_result
        extraction = extract_vertices(DM_FILE)
        result = transform(extraction, DB_FILE)
        with pytest.raises(FileExistsError):
            load(result, DB_FILE, output_path)

    def test_indexes_created(self, etl_result):
        output_path, _ = etl_result
        conn = sqlite3.connect(str(output_path))
        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='vertices'"
        ).fetchall()}
        conn.close()
        assert "idx_vertices_element_id" in indexes
        assert "idx_vertices_x" in indexes
        assert "idx_vertices_y" in indexes
        assert "idx_vertices_z" in indexes
```

#### 3. Test fixtures
**File**: `structure-batiment/tests/conftest.py`

```python
# Shared pytest fixtures for structure_aligner tests.
# Currently empty — fixtures are defined per-test-module.
```

### Success Criteria:

#### Automated Verification:
- [x] Loader tests pass: `cd structure-batiment && python -m pytest tests/test_loader.py -v`
- [x] Full test suite passes: `cd structure-batiment && python -m pytest tests/ -v`
- [x] End-to-end CLI works:
  ```bash
  cd structure-batiment
  python -m structure_aligner etl \
    --input-3dm data/geometrie_2.3dm \
    --input-db data/geometrie_2.db \
    --output data/geometrie_2_prd.db
  ```
- [x] Output DB has correct counts:
  ```bash
  sqlite3 data/geometrie_2_prd.db "SELECT COUNT(*) FROM elements;"  # 5825
  sqlite3 data/geometrie_2_prd.db "SELECT COUNT(*) FROM vertices;"  # 20994
  sqlite3 data/geometrie_2_prd.db "SELECT type, COUNT(*) FROM elements GROUP BY type ORDER BY type;"
  ```

#### Manual Verification:
- [x] ETL report JSON is human-readable and contains expected statistics
- [x] Original tables (filaire, shell, support, material, section, etc.) all still present and unchanged in output
- [x] Log output shows clean 3-phase progression with no unexpected errors

#### Code Review:
- [ ] Atomic transaction: single COMMIT, rollback on any error
- [ ] Output file cleaned up on failure (no corrupt partial DB left behind)
- [ ] FileExistsError prevents accidental overwrites
- [ ] JSON report follows structure compatible with PRD F-10
- [ ] Indexes created for query performance on vertices table

**Implementation Note**: After completing this phase, run the full test suite and the end-to-end CLI command. Verify the output database manually with sqlite3 queries before considering the plan complete.

---

## Testing Strategy

### Unit Tests (per-phase):
- **test_extractor.py** (8 tests): Geometry extraction, vertex counts, categories, coordinate ranges, error handling
- **test_transformer.py** (11 tests): Name matching, type normalization, unmatched handling, FK integrity, NULL rejection
- **test_loader.py** (12 tests): DB creation, data integrity, validation, report generation, error cases, indexes

### Integration Test:
The loader tests effectively serve as integration tests by running the full ETL pipeline (extract → transform → load) and validating the output.

### Key Edge Cases Covered:
- Unmatched element names (Filaire_7415 / Filaire_7416)
- NULL coordinate rejection
- Out-of-range coordinate warnings (>10000m)
- Output file already exists
- Missing input files
- All 5 geometry types extracted
- FK integrity between elements and vertices

### What's NOT Tested (out of scope):
- PostgreSQL/MySQL connections
- Corrupted .3dm files
- Performance benchmarks
- Concurrent access

## Performance Considerations

With 20,996 vertices and 5,825 elements, this dataset is small. No optimization is needed:
- Extraction: reads .3dm file once sequentially
- Transform: in-memory name matching with dict lookup
- Load: single bulk INSERT with `executemany`
- Expected runtime: under 10 seconds total

## References

- Related research: `docs/research/2026-02-05-geometrie2-database-prd-alignment.md`
- PRD schema definition: `structure-batiment/prd/PRD.md:92-110`
- PRD module structure: `structure-batiment/prd/PRD.md:439-477`
- PRD validation rules: `structure-batiment/prd/PRD.md:119-135`
- PRD enriched output schema: `structure-batiment/prd/PRD.md:297-321`
