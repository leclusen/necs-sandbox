# Reverse ETL: Aligned DB to .3dm Implementation Plan

## Overview

Implement a reverse ETL that takes an aligned database (or PRD-compliant database) and the **original .3dm file as a template**, modifies geometry vertex coordinates in-place with the aligned values from the DB, and writes a new `.3dm` file. The output should be semantically identical to the original except for the adjusted coordinates.

## Current State Analysis

### Forward Pipeline (existing)
```
original.3dm + source.db  →  ETL  →  _prd.db  →  Alignment  →  _aligned.db
```

### What we're adding (reverse)
```
_aligned.db + original.3dm  →  Reverse ETL  →  aligned.3dm
```

### Key Discoveries

- The forward ETL extracts vertices from 5 geometry types (Brep, LineCurve, PolylineCurve, NurbsCurve, Point) in `structure_aligner/etl/extractor.py:105-136`
- Vertex coordinates are stored in `vertices(element_id, x, y, z, vertex_index)` and element names in `elements(id, type, nom)` — see `structure_aligner/etl/loader.py:23-49`
- The mapping between .3dm objects and DB elements is via **name**: `obj.Attributes.Name` ↔ `elements.nom`
- The mapping between geometry vertices and DB rows is via **vertex_index**: same iteration order as extraction
- The aligned DB has `x, y, z` (aligned) and `x_original, y_original, z_original` (pre-alignment) — see `structure_aligner/db/writer.py:11-19`

### Empirically Validated rhino3dm Capabilities (tested on `geometrie_2.3dm`)

All 5 geometry types support **in-place coordinate modification** — no need to replace objects:

| Type | Modification API | Verified |
|------|-----------------|----------|
| **Point** | `geom.Location = Point3d(x, y, z)` | Works, persists through write/re-read |
| **LineCurve** | `geom.SetStartPoint(Point3d(...))` / `geom.SetEndPoint(Point3d(...))` | Works (note: `PointAtStart` property has no setter) |
| **PolylineCurve** | `geom.SetPoint(index, Point3d(x, y, z))` | Works for all point indices |
| **NurbsCurve** | `geom.Points[i] = Point4d(x, y, z, w)` | Works (note: `NurbsCurvePointList` has no `SetPoint` method; must use index assignment with `Point4d` preserving the W weight) |
| **Brep** | `geom.Vertices[i].Location = Point3d(x, y, z)` | **Vertices update, but edge curves do NOT follow** (see Brep Strategy below) |

Additional confirmed behaviors:
- `File3dmObject.Geometry` property has **no setter** — cannot replace geometry, must modify in-place
- `GeometryBase.Transform(xform)` properly updates vertices AND edges for Breps
- Vertex ordering is **deterministic** across reads and stable through write/re-read cycles (verified on all 5825 objects)
- `File3dm.Write(path, 0)` preserves all objects, layers, and attributes (version 0 = latest format)

### Brep Edge Desynchronization Problem

**The problem**: Setting `BrepVertex.Location` moves the topological vertex but does NOT update the 3D edge curves. After modification, edges still pass through original positions. The Brep reports `IsValid=True` but edge/vertex positions are inconsistent.

**Data from `geometrie_2_prd_aligned.db`**:
- Geometry distribution: Brep 2953, LineCurve 2580, PolylineCurve 158, Point 131, NurbsCurve 3
- Only **12.2%** of Breps have uniform per-vertex displacement (all vertices same delta)
- **87.8%** of Breps have non-uniform displacement (vertices snap to different threads)

**Chosen strategy — hybrid Transform + per-vertex fixup**:
1. Compute the **mean displacement vector** (mean_dx, mean_dy, mean_dz) across all vertices of the Brep
2. Apply `geom.Transform(Transform.Translation(mean_dx, mean_dy, mean_dz))` — this correctly moves vertices, edges, surfaces, and trim curves
3. For each vertex with a **residual** displacement (target - mean), set `BrepVertex.Location` to the exact target coordinate
4. The residual edge desynchronization is typically **< 1cm** (since nearby vertices snap to the same threads and the per-vertex residuals from the mean are small)
5. Log any Brep with residual edge desync > threshold in the report

**Why this is acceptable**: Displacements are ≤ alpha (5cm). The mean captures the bulk of the movement correctly. Residuals are typically a few mm. Rhino will render based on the underlying surface geometry, so the visual impact is negligible.

### Forward ETL Gap

The forward ETL does **not** store the geometry type per element. Adding it enables:
- Validation during reverse ETL (expected vertex count per geometry type)
- Better error messages when mismatches occur

**Decision**: Add a `geometry_type` column to the `elements` table in the forward ETL.

### Template Drift Detection

The reverse ETL requires the **exact same .3dm file** used in the forward ETL. If the file was modified between runs, vertex indices and element names may not match. To detect this:
- Store the .3dm object count and a hash of all element names in the forward ETL report
- Verify these match before applying reverse ETL

## Desired End State

After implementation:

1. A new CLI command `structure-aligner export-3dm` that produces a valid `.3dm` file from an aligned (or PRD) database + original .3dm template
2. The output .3dm is **semantically identical** to the original except for updated vertex coordinates (note: file headers, CRC, and timestamps will differ — byte-for-byte identity is not possible with `File3dm.Write`)
3. All object attributes (name, layer, color, material, user strings, etc.) are preserved — no objects are deleted/re-added
4. Geometry topology is preserved. For Breps, edges may have minor inconsistencies (< 1cm) due to per-vertex residual fixup
5. Objects not present in the DB keep their original coordinates untouched
6. Unsupported geometry types are skipped with a warning (not silently)
7. A JSON validation report confirms vertex counts, coordinate updates, and any warnings

### Verification:
- Open both original and aligned .3dm in Rhino — visually identical structure, only minor coordinate shifts visible on close inspection
- Run `structure-aligner etl` on the aligned .3dm → the re-extracted vertices should match the aligned DB coordinates within floating-point tolerance (1e-6)
- All existing tests continue to pass
- New tests validate the reverse ETL roundtrip

## What We're NOT Doing

- Reconstructing .3dm files without the original template (no "from scratch" generation)
- Modifying non-geometric properties (materials, render settings, user data, etc.)
- Supporting partial exports (all elements are included)
- Guaranteeing perfect Brep edge/vertex consistency for elements with non-uniform per-vertex displacement (we use the hybrid approach instead)

---

## Phase 1: Forward ETL Enhancement

### Overview
Add `geometry_type` column to the `elements` table and template fingerprint to the ETL report for traceability and validation in the reverse ETL.

### Changes Required:

#### 1.1 Update extractor to track geometry type
**File**: `structure_aligner/etl/extractor.py`

Add `geometry_type` field to `RawVertex`:
```python
@dataclass
class RawVertex:
    element_name: str
    x: float
    y: float
    z: float
    vertex_index: int
    category: str
    geometry_type: str  # "brep", "line_curve", "polyline_curve", "nurbs_curve", "point"
```

Update `_extract_from_geometry` to pass the geometry type string for each branch.

#### 1.2 Propagate geometry_type through transformer
**File**: `structure_aligner/etl/transformer.py`

Add `geometry_type` to `Element` dataclass. During transform, capture the geometry type from the first vertex of each matched element (all vertices of one element share the same geometry type).

#### 1.3 Update loader schema
**File**: `structure_aligner/etl/loader.py`

Add column to `elements` table:
```sql
CREATE TABLE IF NOT EXISTS elements (
    id INTEGER PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    nom VARCHAR(100) NOT NULL,
    geometry_type VARCHAR(30)
);
```

Update `INSERT INTO elements` to include geometry_type.

#### 1.4 Add template fingerprint to ETL report
**File**: `structure_aligner/etl/loader.py`

Add to the ETL report JSON:
```json
{
  "template_fingerprint": {
    "object_count": 5825,
    "element_names_hash": "sha256 hex digest of sorted element names"
  }
}
```

#### 1.5 Update existing tests
**Files**: `tests/test_extractor.py`, `tests/test_transformer.py`, `tests/test_loader.py`

Add assertions for the new `geometry_type` field.

### Success Criteria:

#### Automated Verification:
- [x] All existing tests pass with updated assertions: `pytest tests/`
- [x] ETL produces DB with `geometry_type` column populated
- [x] `geometry_type` values are one of: "brep", "line_curve", "polyline_curve", "nurbs_curve", "point"
- [x] ETL report includes `template_fingerprint`

---

## Phase 2: Reverse ETL Core Implementation

### Overview
Implement the reverse ETL module that reads an aligned DB + original .3dm template and produces a new .3dm with updated coordinates.

### Changes Required:

#### 2.1 Create DB reader for reverse ETL
**File**: `structure_aligner/etl/reverse_reader.py`

```python
@dataclass
class AlignedElement:
    element_id: int               # DB element ID (for uniqueness)
    nom: str                      # Element name
    geometry_type: str | None     # From elements table (may be NULL for old DBs)
    vertices: list[AlignedVertexCoord]  # sorted by vertex_index

@dataclass
class AlignedVertexCoord:
    vertex_index: int
    x: float
    y: float
    z: float

def read_aligned_elements(db_path: Path) -> dict[str, AlignedElement]:
    """Read aligned DB, return dict keyed by element name (nom).

    Works with both aligned DBs (has x_original columns) and
    PRD-compliant DBs (no alignment columns).

    Raises ValueError if duplicate element names are detected.
    """
```

Query groups by `element_id` (not just `nom`) and validates name uniqueness:
```sql
SELECT e.id, e.nom, e.geometry_type, v.vertex_index, v.x, v.y, v.z
FROM vertices v JOIN elements e ON v.element_id = e.id
ORDER BY e.id, v.vertex_index
```

**Duplicate name detection**: Before returning, verify no two element IDs map to the same name. If duplicates found, raise `ValueError` with the list of duplicate names.

#### 2.2 Create 3dm writer with in-place modification
**File**: `structure_aligner/etl/reverse_writer.py`

```python
@dataclass
class ReverseETLReport:
    output_path: Path
    report_path: Path
    total_objects: int
    updated_objects: int
    updated_vertices: int
    skipped_objects: list[str]       # objects not in DB (kept original)
    skipped_unsupported: list[str]   # unsupported geometry types (with warning)
    mismatched_objects: list[str]    # vertex count mismatch between .3dm and DB
    brep_residual_warnings: list[str]  # Breps with edge desync > threshold

def write_aligned_3dm(
    template_3dm: Path,
    aligned_elements: dict[str, AlignedElement],
    output_path: Path,
) -> ReverseETLReport:
    """Read template .3dm, update vertex coordinates in-place, write output.

    Does NOT delete or re-add objects (File3dmObject.Geometry has no setter).
    All modifications are in-place, preserving object UUIDs, attributes,
    layer assignments, user strings, and display settings.
    """
```

Core logic:
1. `rhino3dm.File3dm.Read(template_3dm)` — read template
2. For each `obj` in `model.Objects`:
   - Get `name = obj.Attributes.Name`
   - If no name: skip (keep original, log)
   - Look up `aligned_elements.get(name)`
   - If not found: skip (keep original, add to `skipped_objects`)
   - If found: validate vertex count matches
   - If count mismatch: log warning, add to `mismatched_objects`, skip
   - Call `_update_geometry(obj.Geometry, element.vertices)` — dispatches by geometry type
3. `model.Write(str(output_path), 0)` — write (version 0 = latest)

#### 2.3 Geometry update functions (all in-place, no object replacement)
**File**: `structure_aligner/etl/reverse_writer.py` (continued)

```python
def _update_point(geom: rhino3dm.Point, vertices: list[AlignedVertexCoord]) -> bool:
    """Set geom.Location = Point3d(v.x, v.y, v.z)"""

def _update_line_curve(geom: rhino3dm.LineCurve, vertices: list[AlignedVertexCoord]) -> bool:
    """Call geom.SetStartPoint(Point3d(...)) and geom.SetEndPoint(Point3d(...))
    Expects exactly 2 vertices (index 0 = start, index 1 = end)."""

def _update_polyline_curve(geom: rhino3dm.PolylineCurve, vertices: list[AlignedVertexCoord]) -> bool:
    """Call geom.SetPoint(i, Point3d(v.x, v.y, v.z)) for each vertex.
    Expects len(vertices) == geom.PointCount."""

def _update_nurbs_curve(geom: rhino3dm.NurbsCurve, vertices: list[AlignedVertexCoord]) -> bool:
    """Set geom.Points[i] = Point4d(v.x, v.y, v.z, existing_w) for each control point.
    MUST preserve the existing W (weight) value from the original control point.
    For rational curves (IsRational=True), incorrect weights would distort the curve.
    Expects len(vertices) == len(geom.Points)."""

def _update_brep(geom: rhino3dm.Brep, vertices: list[AlignedVertexCoord]) -> tuple[bool, float]:
    """Hybrid Transform + per-vertex fixup strategy.

    1. Compute mean displacement (mean_dx, mean_dy, mean_dz) across all vertices
    2. Apply geom.Transform(Transform.Translation(mean_dx, mean_dy, mean_dz))
       — this properly moves vertices, edges, surfaces, trim curves
    3. For each vertex, compute residual = (target - post-transform position)
    4. If residual != 0: set geom.Vertices[i].Location to exact target
       — edges won't update for this residual, but it's typically < 1cm
    5. Return (success, max_residual_displacement)

    Expects len(vertices) == len(geom.Vertices).
    """
```

#### 2.4 Generate reverse ETL validation report
**File**: `structure_aligner/etl/reverse_writer.py` (continued)

JSON report with:
```json
{
  "metadata": {
    "timestamp": "ISO 8601",
    "template_3dm": "path",
    "input_database": "path",
    "output_3dm": "path",
    "software_version": "0.1.0"
  },
  "statistics": {
    "total_objects": 5825,
    "updated_objects": 5824,
    "updated_vertices": 20994,
    "skipped_not_in_db": 0,
    "skipped_unsupported_geometry": 0,
    "vertex_count_mismatches": 0
  },
  "brep_edge_desync": {
    "breps_with_residual": 2593,
    "max_residual_mm": 8.2,
    "mean_residual_mm": 2.1,
    "details": ["Coque_1534: max_residual=0.0082m", "..."]
  },
  "coordinate_deltas": {
    "max_displacement_m": 0.047,
    "mean_displacement_m": 0.018
  },
  "warnings": ["..."],
  "skipped_objects": ["..."],
  "mismatched_objects": ["..."]
}
```

### Success Criteria:

#### Automated Verification:
- [x] Unit tests pass for `reverse_reader.py`: `pytest tests/test_reverse_reader.py`
- [x] Unit tests pass for `reverse_writer.py`: `pytest tests/test_reverse_writer.py`
- [x] Roundtrip test: ETL → Align → Reverse ETL → Re-extract → coordinates match aligned DB within 1e-6

---

## Phase 3: CLI Command & Integration

### Overview
Add the `export-3dm` CLI command and wire it into the existing pipeline.

### Changes Required:

#### 3.1 Add `export-3dm` command
**File**: `structure_aligner/main.py`

```python
@cli.command("export-3dm")
@click.option("--input-db", required=True, type=click.Path(exists=True),
              help="Path to aligned or PRD-compliant database")
@click.option("--template-3dm", required=True, type=click.Path(exists=True),
              help="Path to original .3dm file used in forward ETL")
@click.option("--output", type=click.Path(), default=None,
              help="Path for output .3dm (auto-generated if omitted)")
@click.option("--report", type=click.Path(), default=None,
              help="Path for JSON validation report")
@click.option("--log-level", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def export_3dm(input_db, template_3dm, output, report, log_level):
    """Export aligned database back to a .3dm Rhino file."""
```

Auto-generated output path: `{input_db_stem}.3dm`

#### 3.2 Extend `pipeline` command
**File**: `structure_aligner/main.py`

Add `--export-3dm` flag to the existing `pipeline` command so users can get the .3dm in one go:
```bash
structure-aligner pipeline --input-3dm geo.3dm --input-db geo.db --export-3dm
```

When `--export-3dm` is set, after the alignment step completes, automatically invoke the reverse ETL using the original `--input-3dm` as template and the aligned DB as input.

### Success Criteria:

#### Automated Verification:
- [x] `structure-aligner export-3dm --help` displays correct options
- [x] CLI runs end-to-end with sample data
- [ ] Pipeline with `--export-3dm` flag produces .3dm output

#### Manual Verification:
- [ ] Open output .3dm in Rhino 8 — all elements present, correct layer structure
- [ ] Compare original and aligned .3dm — only coordinate differences visible
- [ ] Rhino `Audit3dmFile` reports no critical issues

---

## Phase 4: Tests

### Unit Tests:

#### `tests/test_reverse_reader.py`
- Reads aligned DB correctly (vertices grouped by element, sorted by vertex_index)
- Reads PRD DB (no alignment columns) correctly
- Handles empty DB gracefully
- Handles DB with no elements table → clear error
- **Detects and rejects duplicate element names** → ValueError
- Handles elements with 0 vertices (e.g., Filaire_7416 in test data)

#### `tests/test_reverse_writer.py`
- Updates Point geometry correctly (1 vertex)
- Updates LineCurve geometry correctly (2 vertices via SetStartPoint/SetEndPoint)
- Updates PolylineCurve geometry correctly (N vertices via SetPoint)
- Updates NurbsCurve control points correctly (preserves W weight values)
- Updates Brep via hybrid strategy (Transform + per-vertex fixup)
- Brep edges move by mean displacement (verified via Edge.PointAtStart)
- Skips unnamed objects (keeps original coords, logged)
- Skips objects not in DB (keeps original coords, reported)
- **Reports unsupported geometry types** (not silently skipped)
- Reports vertex count mismatches without crashing
- Generates valid JSON report with brep_edge_desync section

#### `tests/test_reverse_etl_integration.py`
- Full roundtrip: `data/geometrie_2.3dm` + `data/geometrie_2.db` → ETL → Align → Reverse ETL → re-extract → compare
- Aligned coordinates in re-extracted data match aligned DB within tolerance (1e-6)
- Non-aligned vertices are unchanged
- Object count is preserved (5825 objects)
- Layer count is preserved (7753 layers)
- **NurbsCurve weights preserved** (verified IsRational and W values)
- **Vertex count per element preserved** (no vertices lost or added)

### Success Criteria:

#### Automated Verification:
- [x] All new tests pass: `pytest tests/test_reverse_*.py -v`
- [x] All existing tests still pass: `pytest tests/ -v`
- [ ] Coverage ≥ 90% for new modules

---

## Phase 5: Devil's Advocate Review

### Overview
A dedicated review phase where an agent challenges the implementation. Focus areas based on verified risks:

1. **Brep edge desync magnitude**: For the actual dataset, what is the maximum edge-vertex mismatch after the hybrid approach? Is it small enough for production use?
2. **NurbsCurve weight handling**: Verify that for rational NurbsCurves (only 3 in test data, all non-rational currently), the W value is correctly preserved. Test with a synthetic rational curve.
3. **Floating-point precision**: After write → re-read, do coordinates survive .3dm serialization without precision loss beyond 1e-6?
4. **Template fingerprint validation**: Test that reverse ETL detects a modified .3dm template and refuses to proceed.
5. **Edge case: elements with 0 vertices**: Filaire_7416 exists in DB but has 0 vertices. Reverse ETL should handle gracefully.
6. **Edge case: unnamed objects**: Forward ETL skips unnamed objects. Verify reverse ETL preserves them untouched.
7. **Performance profiling**: Time the full reverse ETL on `geometrie_2.3dm` (49 MB, 5825 objects). Target: < 30s.

### Adversarial Test Cases to Write:
- Synthetic .3dm with duplicate object names → verify error
- Synthetic .3dm with vertex count mismatch → verify warning + skip
- Synthetic .3dm with rational NurbsCurve → verify weight preservation
- Modified template .3dm (object added/removed) → verify fingerprint check fails
- Brep with maximally non-uniform displacement → verify max residual reported

### Checklist:
- [ ] Review all 5 `_update_*` functions for correctness
- [ ] Verify NurbsCurve weight preservation
- [ ] Verify .3dm output opens in Rhino without warnings
- [ ] Check that object UUIDs and attributes are preserved after in-place modification
- [ ] Profile execution time on full dataset
- [ ] Verify no data loss in coordinate serialization (compare to 6 decimal places)
- [ ] Review report JSON for completeness

---

## Agent Team Execution Strategy

### Team Structure

| Agent | Role | Phase | Dependencies |
|-------|------|-------|-------------|
| **forward-etl-agent** | Forward ETL enhancement | Phase 1 | None |
| **reverse-reader-agent** | DB reader + report generation | Phase 2.1, 2.4 | Phase 1 (needs geometry_type column) |
| **reverse-writer-agent** | 3dm writer + geometry update | Phase 2.2, 2.3 | Phase 1 (needs geometry_type for validation) |
| **cli-agent** | CLI command + pipeline integration | Phase 3 | Phase 2 (needs reader + writer) |
| **test-agent** | Unit + integration tests | Phase 4 | Phase 2 (can start unit tests in parallel with Phase 3) |
| **devils-advocate** | Adversarial review + edge case tests | Phase 5 | Phase 4 (needs implementation to review) |

Note: Phase 0 (spike) has been **eliminated** — all rhino3dm capabilities have been empirically validated during planning.

### Parallel Execution Windows

```
Time →
──────────────────────────────────────────────────────────────────────────
Phase 1:  [forward-etl-agent]
          ───────────────────
Phase 2:                      [reverse-reader-agent]──┐
                              [reverse-writer-agent]──┤ parallel
                                                      │
Phase 3:                                        [cli-agent]
Phase 4:                                [test-agent]────────
                                                      │
Phase 5:                                        [devils-advocate]
──────────────────────────────────────────────────────────────────────────
```

### Agent Instructions

**forward-etl-agent** (subagent_type: `general-purpose`):
- Add `geometry_type` field to `RawVertex` dataclass in extractor.py
- Update `_extract_from_geometry` to pass geometry type string ("brep", "line_curve", "polyline_curve", "nurbs_curve", "point")
- Add `geometry_type` to `Element` in transformer.py, capture from first vertex per element
- Update loader.py schema to include `geometry_type VARCHAR(30)` column
- Add template fingerprint (object_count + names hash) to ETL report
- Update all affected tests

**reverse-reader-agent** (subagent_type: `general-purpose`):
- Implement `structure_aligner/etl/reverse_reader.py` with duplicate name detection
- Group by element_id, not just nom, to avoid interleaving issues
- Handle both aligned DBs and plain PRD DBs (geometry_type may be NULL)
- Implement report generation logic
- Write unit tests for the reader

**reverse-writer-agent** (subagent_type: `general-purpose`):
- Implement `structure_aligner/etl/reverse_writer.py` with all 5 `_update_*` functions
- Use **in-place modification only** — never delete/re-add objects
- For NurbsCurve: preserve W weight via `Point4d(x, y, z, existing_point.W)`
- For Brep: implement hybrid Transform.Translation + per-vertex fixup
- Log unsupported geometry types explicitly (not silently skip)
- Write unit tests for the writer

**cli-agent** (subagent_type: `general-purpose`):
- Add `export-3dm` command to `main.py`
- Add `--export-3dm` flag to `pipeline` command
- Wire together reader + writer with proper logging

**test-agent** (subagent_type: `general-purpose`):
- Write `tests/test_reverse_etl_integration.py` with full roundtrip test
- Write edge case tests (0-vertex elements, unnamed objects, mismatched counts)
- Run full test suite, fix any regressions
- Verify coverage targets

**devils-advocate** (subagent_type: `general-purpose`, mode: `plan`):
- Review all new code against the edge cases listed in Phase 5
- Write adversarial test cases (duplicate names, rational NurbsCurve, template drift)
- Measure actual Brep edge desync magnitudes on test data
- Profile execution time
- Verify roundtrip data integrity to 6 decimal places

## Performance Considerations

- The sample file has 5825 objects / 20996 vertices — iteration should complete in seconds
- Building the name→element lookup dict is O(n) — no performance concern
- The .3dm write is handled by OpenNURBS internally — similar performance to read (~49 MB)
- Memory: the entire model fits in memory (49 MB file → ~200 MB in-memory estimate)
- The hybrid Brep strategy adds one `Transform` call per Brep — negligible overhead

## Migration Notes

- The `geometry_type` column addition to the forward ETL is **non-breaking**: existing databases without this column will still work (the reverse reader handles `NULL` geometry_type gracefully)
- The reverse ETL is a new command — no impact on existing workflows
- No changes to the alignment pipeline itself
- Existing aligned DBs (produced before this change) can still be used with the reverse ETL — they just won't have geometry_type for validation

## References

- Forward ETL extractor: `structure_aligner/etl/extractor.py:105-136`
- Aligned DB schema: `structure_aligner/db/writer.py:11-19`
- PRD DB schema: `structure_aligner/etl/loader.py:23-49`
- rhino3dm File3dm API: [mcneel.github.io](https://mcneel.github.io/rhino3dm/python/api/File3dm.html)
- rhino3dm ObjectTable API: [mcneel.github.io](https://mcneel.github.io/rhino3dm/python/api/File3dmObjectTable.html)
- rhino3dm ObjectAttributes API: [mcneel.github.io](https://mcneel.github.io/rhino3dm/python/api/ObjectAttributes.html)
- rhino3dm Transform API: [mcneel.github.io](https://mcneel.github.io/rhino3dm/python/api/Transform.html)
- Brep vertex/edge desync discussion: [McNeel Forum](https://discourse.mcneel.com/t/rebuild-update-brep-with-rhino-geometry-brepvertex-class/130646)
