# PRD v2 - Structure-Batiment Alignment Pipeline

**Version**: 2.0
**Date**: 2026-02-07
**Status**: Draft - Pending Review
**Supersedes**: PRD v1 (`prd/PRD.md`)
**Based on**: Research findings from 2026-02-06 and 2026-02-07

---

## 1. Overview

Complete redesign of the alignment pipeline. The V1 pipeline used DBSCAN clustering to discover alignment positions and per-vertex snapping. This is fundamentally wrong. The V2 pipeline uses:

1. **Multi-floor position filtering** to select canonical axis lines from existing before data
2. **Per-element-endpoint snapping** for 100% accurate vertex alignment
3. **7 codifiable object-level transformation rules** for the complete before→after transformation

### 1.1 What Changed from V1

| Aspect | V1 (Wrong) | V2 (Correct) |
|--------|-----------|--------------|
| Axis discovery | DBSCAN clustering → cluster centroids | Multi-floor filtering → canonical position selection |
| Snap method | Per-vertex nearest thread | Per-element-endpoint nearest axis line |
| Z treatment | Modified (snapped to Z threads) | **Never modified** |
| Max tolerance | alpha=0.05m (50mm) | max_snap_distance=0.75m, outlier up to 4.0m |
| Rounding | 0.01m (1cm) | 0.005m (5mm) |
| Object changes | None | 7 transformation rules (removal + addition) |
| Thread refs | Cluster centroid (mean) | Canonical axis position (selection) |

### 1.2 Why V1 Is Wrong

1. Only 21% of V1 pipeline X threads match true axis positions (within 5mm)
2. Cluster centroids have a median 60mm offset from correct positions
3. alpha=0.05m makes it impossible to handle real displacements (up to 3.7m)
4. Z coordinates should never change but V1 modifies them
5. V1 ignores 320 object removals and 476+ object additions

---

## 2. The 7 Transformation Rules

### Rule 1: Axis Line Selection

**Purpose**: Select canonical X/Y positions from the before data that define the structural grid.

**Input**: All vertex positions from before.3dm
**Output**: List of canonical X axis lines, list of canonical Y axis lines

**Algorithm**:
```
1. Extract all unique X positions from all named objects in before.3dm
2. Pre-process: round X/Y to rounding_precision (5mm) before deduplication
   to handle floating-point noise (observed ~0.044mm micro-offsets)
3. For each unique X position (deduplicated within cluster_radius=2mm):
   a. Find all Z-levels (floors) where this X position appears
   b. Z-level matching uses a tolerance of 0.02m (20mm) to handle Z noise
   c. Count distinct Z-levels
4. Keep positions appearing on >= min_floors (default: 3) Z-levels
5. These are the canonical X axis lines
6. Repeat steps 1-5 for Y positions
```

**Noise handling**: The before data has observed XY noise of ~0.044mm (floating-point artifacts from Rhino coordinate system origin). Rounding to 5mm before floor counting prevents position splitting. Z-levels are well-separated (min gap 2.72m) so 20mm tolerance is safe.

**Expected results on test data**:
- Input: 720 unique before X values → Output: ~188 X axis lines (98% recall)
- Input: 786 unique before Y values → Output: ~273 Y axis lines (96% recall)
- Precision: ~99-100% (almost no false positives)

**Key insight**: 100% of after axis positions exist in the before data. This is a selection problem, not a generation problem. Multi-floor presence is the strongest signal: structurally important positions have elements on 3+ floors.

**Remaining 2-4% (fallback)**: Floor-specific positions on fewer than 3 floors. When recall falls below target threshold (96% X, 94% Y), the algorithm automatically includes positions on 2+ floors as a fallback. These can also be recovered by checking if positions are element endpoints of structural members (poteaux/voiles).

### Rule 2: Vertex Snapping (Per-Element-Endpoint)

**Purpose**: Snap each vertex to the nearest canonical axis line, respecting element topology.

**Input**: Vertices grouped by element, axis lines from Rule 1
**Output**: Aligned vertex positions

**Algorithm**:
```
For each element:
  1. Group vertices by element_id
  2. Identify distinct X/Y endpoint positions (cluster within cluster_radius=2mm):
     - Poteaux (columns): 1 X endpoint, 1 Y endpoint (all vertices same position)
     - Voiles (walls): 1-2 X endpoints, 1-2 Y endpoints
       * Orientation detection: if X range > Y range, wall is X-aligned (2 X endpoints, 1 Y)
       * Otherwise Y-aligned (1 X endpoint, 2 Y endpoints)
       * L-shaped walls: treated as having 2 endpoints per axis
     - Dalles: skip (being removed) or keep as-is (roof)
     - Appuis: 1 endpoint per axis
  3. For each endpoint position, find nearest axis line:
     a. First try within max_snap_distance (0.75m)
     b. If no match, try within outlier_snap_distance (4.0m)
     c. If still no match, keep original position (unsnapped)
     d. Tie-break: when two axis lines are equidistant, prefer the one with
        higher floor_count (more structurally significant)
  4. For each vertex in the element:
     a. Determine which endpoint it's closest to (Euclidean distance on the snap axis)
     b. Apply that endpoint's displacement (delta = target - endpoint_position)
  5. NEVER modify Z coordinates
```

**Outlier escalation**: The two-tier tolerance ensures most vertices snap within 0.75m (covers P99), while the 4.0m fallback handles the ~30 extreme Y corrections without accidentally snapping well-placed vertices to distant axes.

**Expected results**:
- 100% accuracy on test dataset (per-element-endpoint snap matches actual after positions)
- 6994 vertices processed
- Displacement distribution: P95 ~175-192mm, P99 ~235-260mm, max ~3.7m

**Why per-element matters**: Per-vertex nearest-axis fails for spanning voiles. A wall connecting two axis lines has vertices at both ends - each end must snap to a different axis line based on element topology, not global proximity.

### Rule 3: Dalle Removal

**Purpose**: Remove all floor slab panels (type=DALLE) except the roof.

**Input**: 3dm model + structural database
**Output**: Modified 3dm with dalles removed

**Algorithm**:
```
1. Query DB: SELECT name FROM shell WHERE type='DALLE'
2. For each dalle name, find matching Brep object in 3dm
3. Check Z position: if max_z > roof_z_threshold (30.0m), keep it (roof)
4. Otherwise, remove from model
```

**Expected**: 207 of 208 dalles removed, 1 roof dalle kept (at Z=32.36)

### Rule 4: Dalle Consolidation

**Purpose**: Replace fragmented per-panel floor slabs with 1-3 large consolidated slabs per floor.

**Input**: Floor Z-levels, building footprint from removed dalle geometry
**Output**: New consolidated dalle Breps added to model

**Algorithm**:
```
1. Group removed dalle footprints by floor Z-level
2. For each floor:
   a. Compute bounding rectangle per structural zone from removed panel extents
   b. Create single-face planar Brep at that Z
   c. Add to model on appropriate layer with dalle naming
3. Structural zones: typically 1-3 per floor based on building geometry
   (zones are derived from spatial clustering of removed panel positions)
```

**Note on voids**: Consolidated slabs are simple bounding rectangles, not detailed geometry with holes for stairs/shafts. The reference file uses this same simplification. Expansion joints are handled by the zone splitting (separate rectangles per structural zone).

**Expected**: 22 new dalle objects across all floor levels

### Rule 5: Voile Simplification

**Purpose**: Replace complex multi-face wall Breps with single-face per-floor segments.

**Input**: Multi-face voile Breps, floor Z-levels
**Output**: Per-floor single-face wall segments

**Algorithm**:
```
1. Identify voiles with >1 Brep face (complex walls)
2. For each complex voile:
   a. Extract planar extent (wall position on X or Y axis, width)
   b. Split into per-floor segments using Z-level boundaries
   c. Create single-face planar Brep for each floor segment
   d. Height = floor-to-floor distance at that level
3. Add simplified segments to model with appropriate naming
```

**Floor-to-floor heights** (from Z-levels):
```
Z-levels:  -4.44  -1.56   2.12   5.48   8.20  13.32  17.96  22.12  26.28  29.64  32.36
Heights:    2.88   3.68   3.36   2.72   5.12   4.64   4.16   4.16   3.36   2.72
```

**Expected**: 106 voiles removed, 82 new single-face segments added

### Rule 6: Support Point Placement

**Purpose**: Add structural support points (Appuis) at grid intersections.

**Input**: Axis lines (X and Y), floor Z-levels, existing column positions
**Output**: Point and LineCurve objects at structural intersections

**Algorithm**:
```
1. For each support floor Z-level (primarily Z=2.12 and Z=-4.44):
   a. For each axis_X × axis_Y intersection:
      - Check if a column element exists within proximity_tolerance (0.5m)
        of this intersection in the aligned (post-snap) data
      - If yes, add Point object (Appuis) at (axis_X, axis_Y, floor_Z)
      - Dedup: skip if a support already exists within 0.1m of this position
2. Add LineCurve supports along edges where needed (20 line supports)
3. Remove 7 obsolete supports at axis lines no longer in the structural system
   (all at X=-10.830, Z=-4.440)
```

**Support Z-levels**: Only Z=2.12 and Z=-4.44 get support points in the test dataset. Other Z-levels may receive supports in future buildings but are not required for this implementation.

**Expected**:
- 217 Point supports + 20 LineCurve supports = 237 Appuis total
- 181 at Z=2.12, 56 at Z=-4.44
- 7 obsolete supports removed

### Rule 7: Column/Beam Centerlines (Filaire)

**Purpose**: Add vertical centerline geometry at support positions.

**Input**: Support point positions, floor Z-levels
**Output**: Filaire (centerline) curves at support locations

**Algorithm**:
```
1. For each support position:
   a. Create vertical line spanning single floor height
   b. Geometry type depends on floor level:
      - PolylineCurve for Z=[17.96, 22.12] floors (84 objects)
      - NurbsCurve for Z=[2.12, 5.48] floors (40 objects)
      - LineCurve for beams at Z=-4.44 and Z=2.12 (11 objects)
2. Add to model on Filaire layer
```

**Expected**: 135 Filaire objects

### Additional: Structural Grid Lines

**Purpose**: Add visual grid line geometry at axis positions.

**Input**: Y axis line positions, building X extent
**Output**: Unnamed PolylineCurve objects representing the structural grid

**Algorithm**:
```
1. For each Y axis line position:
   a. Create horizontal PolylineCurve spanning full X extent (~205m)
   b. Add on "Defaut" layer (unnamed)
2. Add additional curves on "Files" layer (33 curves)
```

**Expected**: ~166 on "Defaut" layer + ~33 on "Files" layer = ~199 unnamed curves

---

## 3. Configuration Parameters

### 3.1 PipelineConfig

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `min_floors` | int | 3 | 2-11 | Min Z-levels for axis line candidacy |
| `cluster_radius` | float | 0.002 | 0.001-0.01 | Dedup tolerance for nearby positions (m) |
| `max_snap_distance` | float | 0.75 | 0.1-2.0 | Max snap distance for normal vertices (m) |
| `outlier_snap_distance` | float | 4.0 | 1.0-10.0 | Max snap for extreme corrections (m) |
| `z_enabled` | bool | False | - | Whether to modify Z coordinates (always False) |
| `rounding_precision` | float | 0.005 | 0.001-0.01 | Coordinate rounding precision (m) |
| `remove_dalles` | bool | True | - | Remove DALLE objects except roof |
| `roof_z_threshold` | float | 30.0 | 20.0-50.0 | Z above which dalles are kept (m) |
| `consolidate_dalles` | bool | True | - | Generate consolidated slab Breps |
| `simplify_voiles` | bool | True | - | Replace multi-face voiles |
| `add_support_points` | bool | True | - | Add Appuis at grid intersections |
| `add_filaire` | bool | True | - | Add column/beam centerlines |
| `add_grid_lines` | bool | True | - | Add structural grid lines |
| `reference_3dm` | str\|None | None | - | Optional reference for validation |

### 3.2 Floor Z-Levels (Invariant)

These 11 Z-levels define the building's floor structure. They are invariant (never modified):

```
-4.44, -1.56, 2.12, 5.48, 8.20, 13.32, 17.96, 22.12, 26.28, 29.64, 32.36
```

Floor-to-floor heights:
```
Level    Z-bottom  Z-top   Height
SS-2     -4.44    -1.56    2.88m
SS-1     -1.56     2.12    3.68m
RDC       2.12     5.48    3.36m
R+1       5.48     8.20    2.72m
R+2       8.20    13.32    5.12m
R+3      13.32    17.96    4.64m
R+4      17.96    22.12    4.16m
R+5      22.12    26.28    4.16m
R+6      26.28    29.64    3.36m
Roof     29.64    32.36    2.72m
```

### 3.3 Changes from V1 Config

| Parameter | V1 Value | V2 Value | Reason |
|-----------|----------|----------|--------|
| `alpha` | 0.05m | Removed | Replaced by max_snap_distance |
| `min_cluster_size` | 3 | Removed | DBSCAN removed |
| `rounding_precision` | 0.01m | 0.005m | 5mm resolution matches data |
| `max_snap_distance` | N/A | 0.75m | Covers P99 of displacements |
| `outlier_snap_distance` | N/A | 4.0m | For extreme Y corrections |
| `min_floors` | N/A | 3 | Multi-floor axis threshold |
| `z_enabled` | implicit yes | False | Z never modified |

---

## 4. Pipeline Flow

```
Input: before.3dm + geometrie_2.db
                    |
                    v
    +-------------------------------+
    | 1. ETL: Extract vertices      |  (reuse existing extractor.py)
    |    + link to DB elements      |  (reuse existing transformer.py)
    +-------------------------------+
                    |
                    v
    +-------------------------------+
    | 2. Discover axis lines        |  (NEW - Rule 1)
    |    Multi-floor filtering      |
    +-------------------------------+
                    |
                    v
    +-------------------------------+
    | 3. Per-element snap alignment |  (NEW - Rule 2)
    |    Never modify Z             |
    +-------------------------------+
                    |
                    v
    +-------------------------------+
    | 4. Object removal rules       |  (NEW - Rules 3, 5 removal, obsolete support removal)
    |    Dalles, voiles, supports   |
    +-------------------------------+
                    |
                    v
    +-------------------------------+
    | 5. Object addition rules      |  (NEW - Rules 4, 5 addition, 6 addition, 7, grid)
    |    Consolidated geometry      |
    +-------------------------------+
                    |
                    v
    +-------------------------------+
    | 6. Write output .3dm          |  (update reverse_writer.py)
    +-------------------------------+
                    |
                    v
    +-------------------------------+
    | 7. Validate against reference |  (NEW - if reference provided)
    +-------------------------------+
                    |
                    v
    Output: aligned.3dm + report.json
```

---

## 5. CLI Interface

```bash
python -m structure_aligner pipeline-v2 \
  --input-3dm data/input/before.3dm \
  --input-db data/input/geometrie_2.db \
  --output output/v2/ \
  --reference-3dm data/input/after.3dm \
  --max-snap-distance 0.75 \
  --min-floors 3 \
  --log-level INFO
```

### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--input-3dm` | Yes | - | Input .3dm file (before) |
| `--input-db` | Yes | - | Structural database (.db) |
| `--output` | Yes | - | Output directory |
| `--reference-3dm` | No | None | Reference for validation |
| `--max-snap-distance` | No | 0.75 | Max snap distance (m) |
| `--outlier-snap-distance` | No | 4.0 | Outlier snap distance (m) |
| `--min-floors` | No | 3 | Min Z-levels for axis lines |
| `--log-level` | No | INFO | Logging level |
| `--skip-object-rules` | No | False | Skip object transformations |

---

## 6. Validation & Success Criteria

### 6.1 Automated Checks

| Check | Threshold | Type |
|-------|-----------|------|
| Vertex position match vs reference | >= 95% within 5mm | CRITICAL |
| Z coordinates unchanged | 0 changes | CRITICAL |
| Per-element displacement consistency | 100% | CRITICAL |
| Axis line recall (X) | >= 96% | WARNING |
| Axis line recall (Y) | >= 94% | WARNING |
| Object count difference vs reference | < 10% per type | WARNING |
| Alignment rate (vertices snapped) | >= 85% | WARNING |

### 6.2 Comparison Metrics

When a reference file is provided, generate:
- Per-object vertex position match rate
- Object presence comparison (added/removed/common)
- Displacement distribution analysis
- Per-element-type breakdown
- Summary report

---

## 7. Data Models

### 7.1 AxisLine
```python
@dataclass
class AxisLine:
    axis: str           # "X" or "Y"
    position: float     # Canonical coordinate value
    floor_count: int    # Number of Z-levels this position appears on
    vertex_count: int   # Total vertices at this position in before data
```

### 7.2 ElementInfo
```python
@dataclass
class ElementInfo:
    id: int
    name: str
    type: str           # poteau, voile, dalle, appui, poutre
    geometry_type: str | None = None
```

### 7.3 ElementAlignment
```python
@dataclass
class ElementAlignment:
    element_id: int
    element_name: str
    element_type: str
    snap_x: list[tuple[float, float]]  # [(before, after), ...] per endpoint
    snap_y: list[tuple[float, float]]
    vertices_moved: int
    max_displacement: float
```

---

## 8. Performance Requirements

| Operation | Expected Time | Complexity |
|-----------|--------------|------------|
| Axis line discovery | < 1s | O(V * Z) |
| Per-element snap | < 5s | O(E * A) with binary search |
| Object rules | < 10s | O(N) geometry generation |
| **Total pipeline** | **< 30s** | Full building dataset |

---

## 9. What's NOT in Scope

1. GUI/visualization
2. Multi-database support (PostgreSQL, MySQL)
3. Cloud/API deployment
4. ML-based optimization
5. Interactive axis line editing
6. Multi-building support

---

## 10. References

- Research 1: `docs/research/2026-02-06-pipeline-discrepancies-and-corrective-prd.md`
- Research 2: `docs/research/2026-02-07-before-after-pattern-analysis.md`
- Original PRD: `prd/PRD.md`
- Test data: `data/input/before.3dm`, `data/input/after.3dm`, `data/input/geometrie_2.db`
