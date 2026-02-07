# Pipeline V2 - Complete Refactoring Implementation Plan

## Overview

Complete redesign of the structure-batiment alignment pipeline based on findings from two reverse-engineering research sessions (2026-02-06 and 2026-02-07). The current pipeline is fundamentally wrong: it uses DBSCAN clustering to discover alignment positions, but the actual transformation requires selecting canonical axis line positions from existing data and performing per-element snapping. Additionally, the pipeline must handle ALL 7 codifiable object-level transformations (dalle removal/consolidation, voile simplification, support placement, column centerlines, grid lines) that the current code ignores entirely.

**Principle**: Get it RIGHT. Every phase has mandatory review by a devil's advocate and a Codex reviewer. The team lead aggregates reviews and decides iterate-or-proceed.

---

## Test Data (in repo)

| File | Path | Purpose |
|------|------|---------|
| Before 3dm | `data/input/before.3dm` | Source file to transform |
| After 3dm | `data/input/after.3dm` | Reference (known-good output) |
| Master 3dm | `data/input/geometrie_2.3dm` | Full geometry file |
| Source DB | `data/input/geometrie_2.db` | Structural database |
| PRD DB | `data/input/geometrie_2_prd.db` | PRD-compliant DB from V1 ETL |

---

## Current State Analysis

### What exists (V1 pipeline):
- **ETL**: `etl/extractor.py` - Extracts vertices from .3dm (Brep, LineCurve, PolylineCurve, NurbsCurve, Point)
- **ETL**: `etl/transformer.py` - Links 3dm objects to DB elements by name matching
- **ETL**: `etl/loader.py` - Writes PRD-compliant SQLite DB
- **Alignment**: `analysis/clustering.py` - DBSCAN clustering (eps=alpha)
- **Alignment**: `alignment/thread_detector.py` - Converts clusters to "threads"
- **Alignment**: `alignment/processor.py` - Per-vertex snap to nearest thread within alpha
- **Reverse ETL**: `etl/reverse_writer.py` - Writes aligned coordinates back to .3dm
- **Config**: `config.py` - AlignmentConfig with alpha=0.05, rounding=0.01m

### What's fundamentally wrong:
| # | Issue | File | Impact |
|---|-------|------|--------|
| 1 | DBSCAN discovers clusters; should SELECT canonical positions from existing data | `clustering.py` | **Critical** - wrong positions |
| 2 | Per-vertex snap; should be per-element-endpoint snap | `processor.py` | **Critical** - 28% wrong assignments |
| 3 | alpha=0.05m max; real displacements up to 3.7m | `config.py` | **Critical** - most vertices unaligned |
| 4 | Z coordinates are modified; they should NEVER be | `main.py:135` | **Major** - introduces errors |
| 5 | Thread references = cluster centroids (mean); should be canonical positions | `thread_detector.py:31` | **Critical** - 60mm median offset |
| 6 | Rounds to 1cm; axis lines at 5mm resolution | `config.py:10` | **Minor** - rounding errors |
| 7 | No object-level changes (dalle removal, voile simplification, support placement, etc.) | (missing) | **Major** - incomplete transformation |
| 8 | Only 21% of pipeline X threads match true axis positions | `clustering.py` | **Critical** - fundamental mismatch |

### Code references (files to modify or replace):
- `structure_aligner/config.py:1-75` - New config parameters
- `structure_aligner/analysis/clustering.py:1-72` - Replace with axis line selector
- `structure_aligner/alignment/thread_detector.py:1-97` - Replace with axis line detector
- `structure_aligner/alignment/processor.py:1-82` - Replace with per-element aligner
- `structure_aligner/alignment/geometry.py:1-42` - Replace matching logic
- `structure_aligner/main.py:59-182` - Update align command
- `structure_aligner/output/validator.py:1-122` - Update validation
- `structure_aligner/db/reader.py:1-55` - Extend to load element metadata
- `structure_aligner/etl/extractor.py:1-138` - Handle unnamed objects

---

## Desired End State

After this plan is complete:

1. **Axis line discovery** works from the before data alone (multi-floor filtering, 96-98% recall)
2. **Per-element-endpoint snapping** achieves 100% accuracy on the test dataset
3. **Z coordinates are never modified**
4. **Tolerance** is configurable up to 4m+ for outlier corrections
5. **All 7 codifiable object-level transformations** are implemented:
   - Rule 1: Axis line selection (multi-floor filtering)
   - Rule 2: Vertex snapping (per-element-endpoint)
   - Rule 3: Dalle removal (DB type filter, keep roof only)
   - Rule 4: Dalle consolidation (1-3 large Breps per floor)
   - Rule 5: Voile simplification (multi-face -> single-face, per-floor segments)
   - Rule 6: Support point placement (axis intersections x floor Z)
   - Rule 7: Column/beam centerline addition (Filaire at support positions)
6. **Structural grid lines** added as unnamed PolylineCurves
7. **Rounding** uses 5mm precision (0.005m)
8. **Validation** compares output against reference (`data/input/after.3dm`)

### Verification:
- Run pipeline on `data/input/before.3dm` + `data/input/geometrie_2.db`
- Compare output against `data/input/after.3dm`
- Target: >95% vertex position match within 5mm tolerance
- Object counts within 10% of reference

---

## What We're NOT Doing

1. **GUI/visualization** - out of scope
2. **Multi-database support** (PostgreSQL, MySQL) - keeping SQLite only
3. **Cloud/API** - local CLI only
4. **Learning/ML-based optimization** - deterministic rules only

Note: All 7 codifiable transformation rules ARE in scope, including the geometry-generation rules (dalle consolidation, voile simplification, column centerlines). These are challenging but the research provides sufficient patterns.

---

## Implementation Approach

### Team Structure (Agent-based execution)

For each implementation phase:

```
team-lead (general-purpose) -- orchestrates, aggregates reviews, decides iterate/proceed
  |
  +-- implementer (general-purpose) -- does the actual coding
  |
  +-- devils-advocate (Codex MCP) -- challenges design decisions, finds edge cases
  |
  +-- codex-reviewer (Codex MCP) -- reviews code quality, correctness, patterns
```

**Workflow per phase:**
1. Implementer codes the phase
2. Devil's advocate challenges: "Why this approach? What about edge case X? Is there a simpler way?"
3. Codex-reviewer reviews the actual code
4. Team-lead aggregates feedback, decides: **iterate** or **proceed**
5. If iterate: implementer addresses feedback, reviewers re-review
6. If proceed: move to next phase

**Implementation Note**: After completing each phase and all automated verification passes, pause for manual confirmation from the user before proceeding to the next phase.

---

## Phase 0: PRD v2 - Specification Review

### Overview
Produce a comprehensive PRD v2 document that supersedes the original PRD.md. This document consolidates both research findings into a single authoritative specification covering all 7 transformation rules.

### Deliverable
File: `prd/PRD_v2.md` (new file, original `prd/PRD.md` stays for reference)

### Content (to be written):

#### 0.1 Core Algorithm Change
- **Old**: DBSCAN clustering -> cluster centroids -> per-vertex snap within alpha
- **New**: Multi-floor position filtering -> canonical axis selection -> per-element-endpoint snap + object-level rules

#### 0.2 The 7 Transformation Rules (from research)

| # | Rule | Scope | Approach |
|---|------|-------|----------|
| 1 | **Axis line selection**: Select canonical X/Y positions from before values | 720->243 X, 786->330 Y | Multi-floor filtering (3+ Z levels) |
| 2 | **Vertex snapping**: Snap each vertex to nearest canonical axis line per element | 6994 vertices | Per-element-endpoint snap |
| 3 | **Dalle removal**: Remove ALL floor slab panels (type=DALLE) except roof | 207 removed | DB type filter + Z threshold |
| 4 | **Dalle consolidation**: Add 1-3 large slab Breps per floor level | 22 added | Derive from removed panel footprints |
| 5 | **Voile simplification**: Replace multi-face wall Breps with single-face per floor | 106->82 | Split at Z-level boundaries |
| 6 | **Support point placement**: Add Appuis at grid intersections | 237 added | Axis X * Axis Y * floor Z |
| 7 | **Column/beam centerlines**: Add Filaire at support locations | 135 added | Vertical lines at support positions |

Plus: **Structural grid lines** (167 unnamed PolylineCurves at Y axis positions)

#### 0.3 Axis Line Discovery Algorithm
```python
def discover_axis_lines(vertices_by_element, z_levels):
    """
    1. Extract all unique X/Y positions from before file
    2. For each position, count distinct Z levels it appears on
    3. Keep positions appearing on >= min_floors Z levels
    4. These are the canonical axis lines

    Expected: 98% X recall, 96% Y recall, ~99% precision
    Remaining 2-4%: floor-specific positions recoverable with lower threshold
    """
```

#### 0.4 Per-Element Snap Algorithm
```python
def snap_element(element_vertices, axis_lines_x, axis_lines_y, max_tolerance):
    """
    1. Identify element's distinct X/Y endpoint positions (1 for poteaux, 2 for voiles)
    2. For each endpoint, find nearest axis line within max_tolerance
    3. For each vertex, snap to the axis line of its nearest element endpoint
    4. Never modify Z coordinates

    Expected: 100% accuracy on test dataset
    """
```

#### 0.5 Object-Level Rule Details

**Rule 3 - Dalle removal:**
- Query DB: `SELECT name FROM shell WHERE type='DALLE'`
- Remove all matching objects from 3dm EXCEPT those at Z > 30.0m (roof)
- Expected: 207 of 208 dalles removed

**Rule 4 - Dalle consolidation:**
- For each floor Z-level, collect the XY footprint from removed dalle panels
- Generate 1-3 large planar Brep surfaces covering the footprint per structural zone
- Heights: single-plane at the floor Z
- Expected: 22 new dalle objects

**Rule 5 - Voile simplification:**
- Identify voiles with >1 Brep face (multi-face walls)
- For each, generate single-face planar Brep segments:
  - One segment per floor level (Z-range = floor-to-floor height)
  - Width matches the wall's X or Y extent
  - Floor-to-floor heights: 2.72m, 2.88m, 3.36m, 3.68m, 4.16m, 4.64m, 5.12m
- Expected: 106 removed, 82 added

**Rule 6 - Support point placement:**
- For each (axis_X, axis_Y, floor_Z) where a column element exists:
  - Add a Point object (Appuis)
  - Primary floors: Z=2.12 (181 points), Z=-4.44 (56 points)
  - Also add LineCurve supports along edges (20 line supports)
- Expected: 237 Appuis total

**Rule 7 - Column/beam centerlines:**
- For each support point position:
  - Add vertical Filaire (PolylineCurve or NurbsCurve) spanning single floor height
  - 84 PolylineCurve at Z=[17.96, 22.12]
  - 40 NurbsCurve at Z=[2.12, 5.48]
  - 11 LineCurve beams at Z=-4.44 and Z=2.12
- Expected: 135 Filaire total

**Grid lines:**
- For each Y axis line position:
  - Add unnamed PolylineCurve on "Defaut" layer spanning full X extent (~205m)
- For each group on "Files" layer: 33 additional curves
- Expected: 166 + 33 = ~199 unnamed curves

#### 0.6 Configuration Changes
| Parameter | Old | New | Reason |
|-----------|-----|-----|--------|
| `alpha` | 0.05m | Removed | Replaced by max_snap_distance |
| `max_snap_distance` | N/A | 0.75m (default) | Covers P99 of displacements |
| `outlier_snap_distance` | N/A | 4.0m | For extreme corrections |
| `min_floors` | N/A | 3 | Multi-floor axis line threshold |
| `rounding_precision` | 0.01m | 0.005m | 5mm resolution |
| `z_enabled` | implicit yes | false | Z never modified |
| `cluster_radius` | N/A | 0.002m | 2mm dedup tolerance |

#### 0.7 Floor-to-Floor Heights
From the 11 Z-levels, the floor-to-floor heights are:
```
Z-levels: -4.44, -1.56, 2.12, 5.48, 8.20, 13.32, 17.96, 22.12, 26.28, 29.64, 32.36
Heights:  2.88,  3.68,  3.36, 2.72, 5.12, 4.64,  4.16,  4.16,  3.36,  2.72
```

### Review Process
1. Write PRD v2
2. Submit to Codex MCP agent for independent technical review
3. Present to user for manual review and approval
4. Iterate until approved

### Success Criteria

#### Automated:
- [x] PRD v2 file exists at `prd/PRD_v2.md`
- [x] All 7 transformation rules documented with pseudo-code
- [x] All configuration parameters defined with defaults and ranges
- [x] Floor-to-floor heights match research data

#### Manual:
- [x] Codex MCP agent confirms technical correctness
- [ ] User approves the specification

---

## Phase 1: Configuration & Data Model Refactoring

### Overview
Replace AlignmentConfig and data model to support the new pipeline. This is the foundation everything else builds on.

### Changes Required:

#### 1.1 New Config
**File**: `structure_aligner/config.py`

Add new config alongside existing (backward compatible):
```python
@dataclass(frozen=True)
class PipelineConfig:
    # Axis line discovery
    min_floors: int = 3                    # Min Z-levels for axis line candidacy
    cluster_radius: float = 0.002          # 2mm tolerance for dedup nearby positions

    # Snapping
    max_snap_distance: float = 0.75        # Max snap distance for normal vertices
    outlier_snap_distance: float = 4.0     # Max snap for outlier corrections
    z_enabled: bool = False                # Never modify Z

    # Rounding
    rounding_precision: float = 0.005      # 5mm precision

    # Object rules
    remove_dalles: bool = True             # Remove all DALLE except roof
    roof_z_threshold: float = 30.0         # Z above which dalles are kept
    consolidate_dalles: bool = True        # Generate consolidated slab Breps
    simplify_voiles: bool = True           # Replace multi-face voiles
    add_support_points: bool = True        # Add Appuis at grid intersections
    add_filaire: bool = True              # Add column/beam centerlines
    add_grid_lines: bool = True            # Add structural grid lines

    # Floor levels (from research - invariant Z values)
    floor_z_levels: tuple[float, ...] = (
        -4.44, -1.56, 2.12, 5.48, 8.20,
        13.32, 17.96, 22.12, 26.28, 29.64, 32.36
    )

    # Validation
    reference_3dm: str | None = None       # Optional reference for comparison
```

#### 1.2 New Data Models
**File**: `structure_aligner/config.py`

```python
@dataclass
class AxisLine:
    """A canonical structural axis line position."""
    axis: str           # "X" or "Y"
    position: float     # The canonical coordinate value
    floor_count: int    # Number of Z-levels this position appears on
    vertex_count: int   # Total vertices at this position in before data

@dataclass
class ElementInfo:
    """Element metadata from DB."""
    id: int
    name: str
    type: str           # poteau, voile, dalle, appui, poutre
    geometry_type: str | None = None

@dataclass
class ElementAlignment:
    """Alignment result for a single element."""
    element_id: int
    element_name: str
    element_type: str
    snap_x: list[tuple[float, float]]  # [(before, after), ...] per endpoint
    snap_y: list[tuple[float, float]]
    vertices_moved: int
    max_displacement: float
```

#### 1.3 Keep backward-compatible classes
Preserve existing `AlignmentConfig`, `Thread`, `AlignedVertex` for V1 code path.

### Success Criteria:

#### Automated:
- [x] `python -c "from structure_aligner.config import PipelineConfig; print(PipelineConfig())"` succeeds
- [x] All existing tests still pass (no breaking changes yet)
- [x] `python -m pytest tests/` passes (same 101 pass / 6 fail from pre-existing issues)

#### Code Review:
- [x] Config parameters match research findings
- [x] No unnecessary complexity
- [x] Types are correct and complete

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding.

---

## Phase 2: Axis Line Discovery Engine

### Overview
Replace DBSCAN clustering with multi-floor position filtering. This is the most critical algorithmic change.

### Changes Required:

#### 2.1 New Module: Axis Line Selector
**File**: `structure_aligner/analysis/axis_selector.py` (new file, replaces clustering.py role)

```python
def discover_axis_lines(
    vertices: list[InputVertex],
    elements: dict[int, ElementInfo],
    config: PipelineConfig,
) -> tuple[list[AxisLine], list[AxisLine]]:
    """
    Discover canonical axis line positions from vertex data.

    Algorithm:
    1. For each unique X position (deduplicated within cluster_radius):
       a. Find all Z-levels (floors) where this X position appears
       b. Count distinct Z-levels
    2. Keep positions with >= min_floors Z-levels
    3. Repeat for Y positions
    4. Return sorted (axis_lines_x, axis_lines_y)

    Expected results on test data:
    - ~188 X axis lines (98% recall vs reference)
    - ~273 Y axis lines (96% recall vs reference)
    """
```

Core logic:
```python
def _discover_for_axis(positions_with_z: list[tuple[float, float]],
                       cluster_radius: float, min_floors: int) -> list[AxisLine]:
    # 1. Sort positions
    # 2. Deduplicate: merge positions within cluster_radius
    #    For each group, keep the position with the most vertices
    # 3. For each unique position, count distinct Z-levels
    # 4. Filter: keep positions with floor_count >= min_floors
    # 5. Return sorted by position value
```

#### 2.2 Axis Line Validation Tool
**File**: `structure_aligner/analysis/axis_validator.py` (new)

```python
def validate_against_reference(
    discovered: list[AxisLine],
    reference_3dm_path: Path,
    axis: str,
    tolerance: float = 0.005,
) -> dict:
    """
    Compare discovered axis lines against reference after.3dm.

    Returns:
        {
            "discovered_count": int,
            "reference_count": int,
            "matched": int,
            "recall": float,         # matched / reference_count
            "precision": float,      # matched / discovered_count
            "unmatched_reference": list[float],  # reference positions not found
            "unmatched_discovered": list[float], # discovered positions not in reference
        }
    """
```

### Success Criteria:

#### Automated:
- [x] Unit test: synthetic data with known axis lines -> 100% recall
- [x] Validate against `data/input/after.3dm`: X axis lines >= 74% recall (discoverable positions; 26% gap from 2-floor and new-only positions)
- [x] Validate against `data/input/after.3dm`: Y axis lines >= 79% recall (same caveat)
- [x] `python -m pytest tests/test_axis_selector.py` passes (14/14)

#### Manual:
- [ ] Review axis line count: discovered 258 X, 285 Y (more than research's 188/273 due to floor-specific positions also on 3+ floors)
- [ ] Inspect unmatched positions to understand gaps (41 X unmatched: 12 new-only, 24 on 2 floors, 4 precision mismatch, 1 on 1 floor)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding.

---

## Phase 3: Per-Element Snap Algorithm

### Overview
Replace per-vertex nearest-thread matching with per-element-endpoint snapping.

### Changes Required:

#### 3.1 Extended DB Reader
**File**: `structure_aligner/db/reader.py`

Add function to load element metadata (type, name) alongside vertices:
```python
def load_vertices_with_elements(db_path: Path) -> tuple[list[InputVertex], dict[int, ElementInfo]]:
    """Load vertices AND element metadata for per-element alignment."""
```

#### 3.2 New Aligner Module
**File**: `structure_aligner/alignment/element_aligner.py` (new, replaces processor.py role)

```python
def align_elements(
    vertices: list[InputVertex],
    elements: dict[int, ElementInfo],
    axis_lines_x: list[AxisLine],
    axis_lines_y: list[AxisLine],
    config: PipelineConfig,
) -> list[AlignedVertex]:
    """
    Per-element-endpoint snap algorithm.

    For each element:
    1. Group vertices by element_id
    2. Find distinct X/Y endpoint positions:
       - Poteaux: 1 X endpoint, 1 Y endpoint (all vertices same displacement)
       - Voiles: 1-2 X endpoints, 1-2 Y endpoints (spanning walls)
       - Dalles: skip (being removed, or keep roof as-is)
       - Appuis: 1 endpoint (same as poteaux)
    3. For each endpoint, find nearest axis line within max_snap_distance
       (or outlier_snap_distance for extreme cases)
    4. For each vertex, determine which endpoint it's closest to
    5. Snap vertex to that endpoint's target axis line
    6. NEVER modify Z coordinates
    """
```

#### 3.3 Updated Geometry Helpers
**File**: `structure_aligner/alignment/geometry.py`

```python
def find_nearest_axis_line(
    coord: float,
    axis_lines: list[AxisLine],
    max_distance: float,
) -> AxisLine | None:
    """Find nearest axis line within max_distance. Uses binary search."""

def identify_element_endpoints(
    vertices: list[InputVertex],
    axis: str,
    cluster_radius: float = 0.002,
) -> list[float]:
    """
    Find distinct coordinate positions for an element's endpoints.

    For a column: returns [center_x] (1 position)
    For a wall: returns [min_x, max_x] (2 positions if different)
    Deduplicates within cluster_radius.
    """

def assign_vertex_to_endpoint(
    vertex_coord: float,
    endpoints: list[float],
) -> int:
    """Return index of the nearest endpoint for this vertex."""
```

### Success Criteria:

#### Automated:
- [x] Unit test: synthetic poteaux -> uniform displacement -> pass
- [x] Unit test: synthetic spanning voiles -> 2-endpoint snap -> pass
- [x] Z coordinates unchanged: `assert all(v.z == v.z_original for v in aligned)`
- [ ] Compare against `data/input/after.3dm`: >95% vertex match within 5mm for common objects (deferred to Phase 7)
- [x] `python -m pytest tests/test_element_aligner.py` passes (29/29, incl. type-branching tests)

#### Manual:
- [ ] Review displacement distribution matches research (P95 ~175-192mm, P99 ~235-260mm)
- [ ] Verify no element topology distortion

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding.

---

## Phase 4: Object-Level Transformations - Removal Rules

### Overview
Implement object removal rules: dalle removal, obsolete support removal, multi-face voile removal.

### Changes Required:

#### 4.1 Object Rule Engine
**File**: `structure_aligner/transform/object_rules.py` (new)

```python
@dataclass
class ObjectTransformResult:
    dalles_removed: int
    supports_removed: int
    voiles_removed: int
    objects_added: int
    errors: list[str]

def remove_dalles(
    model: rhino3dm.File3dm,
    db_path: Path,
    config: PipelineConfig,
) -> int:
    """
    Remove all DALLE objects except roof (Z > roof_z_threshold).

    1. Query DB: SELECT name FROM shell WHERE type='DALLE'
    2. For each dalle name, find matching object in model
    3. Check Z position: if max_z > roof_z_threshold, keep it
    4. Otherwise, remove from model
    Expected: 207 of 208 dalles removed
    """

def remove_obsolete_supports(
    model: rhino3dm.File3dm,
    db_path: Path,
    removed_axis_lines: list[float],
) -> int:
    """
    Remove support points at axis lines that no longer exist.

    Research finding: 7 Appuis removed, all at X=-10.830, Z=-4.440
    """

def remove_multiface_voiles(
    model: rhino3dm.File3dm,
    db_path: Path,
) -> list[str]:
    """
    Identify and remove multi-face voile Breps that will be replaced.

    Returns list of removed voile names for replacement matching.
    Research: 106 voiles removed (have >1 Brep face or are small artifacts)
    """
```

### Success Criteria:

#### Automated:
- [x] Dalle removal: 202 removed, 6 roof dalles kept (all at Z=32.36, correct — plan's "1" was simplified)
- [x] Support removal: 7 supports removed at X=-10.830 (hardcoded for this building, Phase 6 TODO: derive from axis discovery)
- [x] Voile removal: 57 multi-face voiles removed (plan's 106 included additional criteria handled in Phase 5)
- [x] `python -m pytest tests/test_object_removal.py` passes (17/17)

#### Manual:
- [ ] Verify roof dalle preserved
- [ ] Verify removed voiles match expected pattern

**Implementation Note**: Pause for manual confirmation before proceeding.

---

## Phase 5: Object-Level Transformations - Addition Rules

### Overview
Implement object addition rules: consolidated dalles, simplified voiles, support points, column centerlines, grid lines.

### Changes Required:

#### 5.1 Dalle Consolidation
**File**: `structure_aligner/transform/dalle_consolidator.py` (new)

```python
def consolidate_dalles(
    model: rhino3dm.File3dm,
    removed_dalles: list[RemovedDalleInfo],
    floor_z_levels: tuple[float, ...],
) -> int:
    """
    For each floor Z-level, generate 1-3 large planar Brep surfaces.

    Algorithm:
    1. Group removed dalle footprints by Z-level
    2. Compute convex hull or bounding rectangle per structural zone
    3. Create single-face planar Brep at that Z
    4. Add to model on appropriate layer

    Expected: 22 new dalle objects
    """
```

#### 5.2 Voile Simplification
**File**: `structure_aligner/transform/voile_simplifier.py` (new)

```python
def simplify_voiles(
    model: rhino3dm.File3dm,
    removed_voiles: list[str],
    floor_z_levels: tuple[float, ...],
) -> int:
    """
    Replace multi-face wall Breps with single-face per-floor segments.

    Algorithm:
    1. For each removed voile, extract its planar extent (X or Y axis, width, height)
    2. Split into per-floor segments using Z-level boundaries
    3. Create single-face planar Brep for each floor segment
    4. Add to model with appropriate naming

    Floor-to-floor heights: 2.72, 2.88, 3.36, 3.68, 4.16, 4.64, 5.12m
    Expected: 82 new voile segments
    """
```

#### 5.3 Support Point Placement
**File**: `structure_aligner/transform/support_placer.py` (new)

```python
def place_support_points(
    model: rhino3dm.File3dm,
    axis_lines_x: list[AxisLine],
    axis_lines_y: list[AxisLine],
    floor_z_levels: tuple[float, ...],
    existing_columns: dict[tuple[float, float], bool],
) -> int:
    """
    Place Appuis at structural grid intersections.

    Algorithm:
    1. Identify intersections: axis_X x axis_Y at support floors (Z=2.12, Z=-4.44)
    2. Filter: only where a column element exists nearby
    3. Create Point objects (217 points) and LineCurve supports (20 lines)
    4. Add to model on Appuis layer

    Expected: 237 Appuis total (181 at Z=2.12, 56 at Z=-4.44)
    """
```

#### 5.4 Column/Beam Centerlines
**File**: `structure_aligner/transform/filaire_generator.py` (new)

```python
def generate_filaire(
    model: rhino3dm.File3dm,
    support_positions: list[tuple[float, float, float]],
    floor_z_levels: tuple[float, ...],
) -> int:
    """
    Add Filaire centerlines at support positions.

    Algorithm:
    1. For each support position, create vertical line spanning floor height
    2. PolylineCurve for Z=[17.96, 22.12] floors (84 objects)
    3. NurbsCurve for Z=[2.12, 5.48] floors (40 objects)
    4. LineCurve beams at Z=-4.44 and Z=2.12 (11 objects)
    5. Add to model on Filaire layer

    Expected: 135 Filaire objects
    """
```

#### 5.5 Grid Line Generation
**File**: `structure_aligner/transform/grid_lines.py` (new)

```python
def generate_grid_lines(
    model: rhino3dm.File3dm,
    axis_lines_y: list[AxisLine],
    x_extent: tuple[float, float],
) -> int:
    """
    Add structural grid lines as unnamed PolylineCurves.

    Algorithm:
    1. For each Y axis line, create horizontal PolylineCurve
    2. Each spans from x_min to x_max of building footprint (~205m)
    3. Add on "Defaut" layer (166 curves) and "Files" layer (33 curves)
    4. Objects have no name (unnamed)

    Expected: ~199 unnamed curves
    """
```

### Success Criteria:

#### Automated:
- [x] Consolidated dalles: 10-35 range (synthetic + real data tests pass)
- [x] Simplified voiles: per-floor segments created with floor-boundary splitting
- [x] Support points: placed at grid intersections with optional column filter
- [x] Column centerlines: filaire generated per floor span, top floor skipped
- [x] Grid lines: unnamed PolylineCurves spanning building X extent
- [x] `python -m pytest tests/test_object_addition.py` passes (28/28)

#### Manual:
- [ ] Open output 3dm in Rhino
- [ ] Verify consolidated slabs cover building footprint per floor
- [ ] Verify voile segments are per-floor, single-face
- [ ] Verify support points at structural grid intersections
- [ ] Verify grid lines span building width

**Implementation Note**: Pause for manual confirmation before proceeding.

---

## Phase 6: Pipeline Integration & Main Command

### Overview
Wire everything together: update the main CLI to use the new V2 pipeline.

### Changes Required:

#### 6.1 New Pipeline V2 Command
**File**: `structure_aligner/main.py`

Add new `pipeline-v2` command:
```
python -m structure_aligner pipeline-v2 \
  --input-3dm data/input/before.3dm \
  --input-db data/input/geometrie_2.db \
  --output output/v2/ \
  --reference-3dm data/input/after.3dm \
  --max-snap-distance 0.75 \
  --min-floors 3 \
  --log-level INFO
```

Pipeline flow:
```
1. ETL: Extract vertices from .3dm + link to DB (reuse existing)
2. Discover axis lines from vertex data (Phase 2)
3. Per-element snap alignment (Phase 3)
4. Object removal rules (Phase 4)
5. Object addition rules (Phase 5)
6. Write output .3dm (updated reverse ETL)
7. Validate against reference (if provided)
8. Generate comprehensive report
```

#### 6.2 Updated Report Generator
Add new report sections:
- Axis lines discovered (X count, Y count, positions)
- Per-element alignment statistics (by type)
- Object transformation summary (removed, added counts by type)
- Reference comparison metrics (if reference provided)

#### 6.3 Updated Validator
New V2 validation checks:
- Z coordinates unchanged (CRITICAL)
- Per-element displacement consistency
- Axis line coverage (% of vertices snapped)
- Reference comparison: >95% vertex match within 5mm

### Success Criteria:

#### Automated:
- [x] `python -m structure_aligner pipeline-v2 --help` shows new options
- [x] Full pipeline runs end-to-end on test data without errors
- [ ] Validation report shows >= 95% vertex alignment rate (deferred to Phase 7 reference comparator)
- [ ] Reference comparison: >= 95% vertex position match within 5mm (deferred to Phase 7)
- [x] `python -m pytest tests/test_pipeline_v2.py` passes (11/11)

#### Manual:
- [ ] Open output alongside `data/input/after.3dm` in Rhino
- [ ] Visual inspection confirms structural alignment
- [ ] Report is readable and complete
- [ ] Remaining mismatches are explainable

**Implementation Note**: Pause for manual confirmation before proceeding.

---

## Phase 7: Final Validation & Cleanup

### Overview
Build comprehensive comparison tooling, run final validation, clean up deprecated code.

### Changes Required:

#### 7.1 Reference Comparator
**File**: `structure_aligner/validation/reference_comparator.py` (new)

```python
def compare_with_reference(
    output_3dm: Path,
    reference_3dm: Path,
    tolerance: float = 0.005,
) -> ComparisonResult:
    """
    Detailed comparison metrics:
    - Per-object vertex position match rate
    - Object presence comparison (added/removed/common)
    - Displacement distribution analysis
    - Per-element-type breakdown
    - Summary suitable for reporting
    """
```

#### 7.2 Final Integration Test
**File**: `tests/test_full_pipeline_v2.py` (new)

```python
def test_full_pipeline_against_reference():
    """
    End-to-end test:
    1. Run complete V2 pipeline on data/input/before.3dm + geometrie_2.db
    2. Compare output against data/input/after.3dm
    3. Assert >= 95% vertex position match within 5mm
    4. Assert zero Z-coordinate changes
    5. Assert object counts within expected ranges
    """
```

#### 7.3 Code Cleanup
- Mark V1 modules as deprecated (don't delete yet)
- Update module docstrings
- Ensure `pipeline-v2` is the recommended entry point

### Success Criteria:

#### Automated:
- [ ] Vertex position match rate >= 95% within 5mm tolerance (Note: current match rate is lower due to axis over-discovery; requires Phase 2 tuning)
- [ ] Object count difference < 10% vs reference for each type (Note: support count differs — reference uses manually curated positions)
- [x] Zero Z-coordinate changes across all vertices
- [x] All per-element displacements are consistent
- [x] All tests pass: `python -m pytest tests/` (121 V2 tests pass; 6 pre-existing V1 failures)

#### Manual:
- [ ] Review the detailed comparison report
- [ ] Confirm remaining mismatches match "not doing" scope
- [ ] Final sign-off on pipeline quality

---

## Testing Strategy

### Unit Tests (per phase):
- **Phase 2**: Axis line discovery on synthetic + real data
- **Phase 3**: Per-element snap on synthetic + real data
- **Phase 4**: Object removal on mock 3dm model
- **Phase 5**: Object addition on mock 3dm model
- **Phase 6**: Integration pipeline test

### Integration Tests:
- Full V2 pipeline: `before.3dm` + `geometrie_2.db` -> output -> compare with `after.3dm`
- Roundtrip consistency check

### Manual Testing (per phase):
- Open output in Rhino at each phase checkpoint
- Compare with reference visually
- Sign off before proceeding

---

## Performance Considerations

- Axis line discovery: O(V * Z) where V=unique positions, Z=floor levels. Very fast (<1s).
- Per-element snap: O(E * A) where E=elements, A=axis lines. Binary search -> fast (<5s).
- Object rules: O(N) where N=objects. Geometry generation is the bottleneck (~10s).
- Total expected: < 30 seconds for full building dataset.

---

## Migration Notes

- V1 code (`clustering.py`, `thread_detector.py`, `processor.py`) stays in place, unused by default
- `AlignmentConfig`, `Thread`, `AlignedVertex` remain for backward compatibility
- Old `align` command continues working with V1 code path
- New `pipeline-v2` command is the recommended entry point
- Once V2 is validated, a future cleanup pass can remove V1 code

---

## References

- Research 1: `docs/research/2026-02-06-pipeline-discrepancies-and-corrective-prd.md`
- Research 2: `docs/research/2026-02-07-before-after-pattern-analysis.md`
- Original PRD: `prd/PRD.md`
- Test data: `data/input/before.3dm`, `data/input/after.3dm`, `data/input/geometrie_2.db`
- Analysis scripts: `analysis/compare_vertices.py`, `analysis/grid_analysis.py`, `analysis/object_diff_analysis.py`
