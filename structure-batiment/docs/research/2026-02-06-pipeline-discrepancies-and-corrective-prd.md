---
date: "2026-02-06T20:57:57Z"
researcher: Claude Opus 4.6
research_method: agent-team
git_commit: 2c63e740b6d84d5b3ca5dc34f6a8d747e5f8c382
branch: main
repository: structure-batiment
topic: "Before/After 3dm Reverse Engineering - Pipeline Discrepancies and Corrective PRD"
tags: [research, codebase, pipeline, alignment, 3dm, reverse-engineering, PRD]
status: complete
last_updated: "2026-02-06"
last_updated_by: Claude Opus 4.6
team_members: [code-analyst, pattern-finder, codebase-scout, codex-manager, coordinator]
codex_verified: confirmed
---

# Research: Before/After 3DM Reverse Engineering - Pipeline Discrepancies and Corrective PRD

**Date**: 2026-02-06T20:57:57Z
**Researcher**: Claude Opus 4.6
**Method**: Agent Team (coordinated parallel research)
**Git Commit**: 2c63e740b6d84d5b3ca5dc34f6a8d747e5f8c382
**Branch**: main
**Repository**: structure-batiment

## Research Question

Aggregate findings from reverse engineering the before/after 3dm files. Identify all discrepancies between what the current pipeline produces and what the expected output (after.3dm) contains. Draft a corrective PRD to fix the pipeline.

## Executive Summary

The current pipeline fundamentally misunderstands the transformation. It uses **DBSCAN clustering to discover alignment threads from the data itself**, then snaps vertices to cluster centroids. The actual transformation applied by the human operator is radically different: vertices are snapped to **predefined structural axis line positions** that are specific to the building's structural grid. These axis lines are NOT discoverable from the data alone using generic clustering - they are external knowledge.

Additionally, the human operator made significant **object-level changes** (320 objects removed, 476 objects added/renamed) that the pipeline doesn't address at all.

---

## Detailed Findings

### 1. The Transformation is NOT Clustering-Based

**Current pipeline approach:**
- Runs DBSCAN on all X/Y/Z coordinates
- Discovers clusters automatically
- Snaps to cluster centroids (mean of cluster)
- Uses alpha as DBSCAN eps parameter

**Actual transformation:**
- Vertices are snapped to **predefined structural axis line positions**
- These positions are specific to the building (not computed from vertex positions)
- The axis lines do NOT follow a regular grid (25mm, 50mm, or otherwise)
- 188 unique X axis positions, 273 unique Y axis positions
- Z values are completely unchanged (stay at 11 predefined floor levels)

**Evidence:**
- Pipeline detected 202 X threads; the true answer has 188 unique X positions
- **Only 43/202 (21%) pipeline threads match a true axis line within 5mm**
- The largest true axis line (X=-39.700, 716 vertices) has **no matching pipeline thread**
- Pipeline thread references have a **median 60mm offset** from the nearest true axis line

### 2. Axis Line Positions Are Not On Any Regular Grid

Initial hypothesis was that coordinates snap to a 25mm grid. This is **incorrect**.

**Evidence:**
- 0% of after X values are exact multiples of any grid (1mm, 5mm, 25mm)
- After X values have a consistent micro-offset of ~0.000044m (from Rhino coordinate system origin)
- The unique after X values are at positions like -71.875, -55.850, -43.250, -39.700, -23.600 - these are structural axis positions, not grid multiples
- After Y values similarly are NOT on a regular grid

**However, the displacements ARE frequently multiples of 5mm:**
- 80.2% of X displacements are multiples of 5mm
- 80.6% of Y displacements are multiples of 5mm
- 63% of X displacements are multiples of 25mm

This means the axis lines themselves are probably defined at 5mm resolution, but their positions are determined by structural engineering requirements, not a regular grid.

### 3. The Transformation is Per-Element, Not Per-Vertex

**Finding:** For 1748/2207 (79.2%) elements, all vertices receive the same X displacement. For 1830/2207 (82.9%), all vertices receive the same Y displacement.

The remaining 459 elements with non-uniform X displacement are elements (primarily voiles/walls) that span between two different axis lines. Their vertices at one end snap to one axis line, and vertices at the other end snap to a different axis line.

**Key implication:** The transformation preserves element topology - it never changes the number of unique positions within an element, only shifts them.

### 4. Z Coordinates Are Never Modified

**Finding:** Zero Z coordinates changed between before and after. The Z axis has exactly 11 unique values representing floor levels:

```
-4.44, -1.56, 2.12, 5.48, 8.20, 13.32, 17.96, 22.12, 26.28, 29.64, 32.36
```

These are already at the correct positions in the before file. The pipeline incorrectly detects Z threads and may modify Z values.

### 5. Large Displacements Occur (Far Beyond Current Alpha)

The current pipeline uses alpha=0.05m (50mm) as maximum tolerance. The actual transformation has:

**X axis:**
- Max displacement: 0.729m (729mm)
- P99 displacement: 0.235m (235mm)
- P95 displacement: 0.192m (192mm)
- 4 vertices moved > 0.5m

**Y axis:**
- Max displacement: 3.687m (3687mm!)
- P99 displacement: 0.260m (260mm)
- P95 displacement: 0.175m (175mm)
- 30 vertices moved > 0.5m
- 16 vertices moved > 1.0m
- 8 vertices moved > 2.0m

**Implication:** The alpha=0.05 constraint in the current pipeline makes it structurally impossible to reproduce the correct output. Many elements are reassigned to axis lines much further than 50mm away.

### 6. Significant Object-Level Changes

The human operator didn't just move vertices - they also restructured the model:

- **320 object names present in before.3dm are absent in after.3dm** (objects removed or renamed)
  - Includes Coque_ (voiles/dalles) and Appuis_ (supports)
  - Examples: Coque_1534, Coque_1540, Coque_1554, Appuis_6463, etc.

- **476 object names present in after.3dm are absent in before.3dm** (objects added or renamed)
  - Primarily new Appuis_ (supports) with higher ID numbers
  - Examples: Appuis_8032-8052, etc.

- **167 objects in after.3dm have no name** (skipped by extractor)

The pipeline currently handles NONE of these object-level changes.

### 7. Brep Topology May Change

The compare_3dm analysis showed that some Brep objects have different topology between before and after (different number of faces, edges, vertices). The current pipeline only modifies vertex positions and doesn't handle topology changes.

### 8. Pipeline Thread Reference Values Are Wrong

Even where the pipeline detects threads in roughly the right area, the reference values (cluster centroids) are wrong:

**Example - X=-39.700m axis line (716 vertices):**
- True target: -39.700m
- Pipeline would compute centroid from nearby before values (mean ≈ -39.764m)
- Pipeline reference: ~-39.76m (60mm off from the true target)

The pipeline computes references as `mean(cluster_points)` rounded to centimeter. The true references are predefined positions that are NOT the mean of nearby vertices.

---

## Corrective PRD: Structural Axis Line Alignment

### Overview

The alignment pipeline must be redesigned to snap vertices to **predefined structural axis lines** rather than discovering alignment positions from clustering. The current DBSCAN-based approach is fundamentally wrong for this use case.

### CR-01: Axis Line Definition (Replaces F-04, F-05)

**The pipeline must accept predefined axis line positions as input, not discover them.**

**Option A - External axis line definition file:**
```yaml
axis_lines:
  X:
    - -71.875
    - -55.850
    - -49.300
    - -43.250
    - -39.700
    - -31.700
    - -29.001
    - -23.600
    # ... all axis positions
  Y:
    - -87.825
    - -82.325
    - -79.550
    - -71.375
    - -55.425
    - -52.250
    # ... all axis positions
  Z: []  # Z is never modified
```

**Option B - Extract axis lines from a reference 3dm file (after.3dm):**
The pipeline could extract unique coordinate positions from a known-good reference file and use those as axis lines.

**Option C - Extract axis lines from the geometre_2.3dm master file:**
The full geometry file may contain guide curves, dimension lines, or other objects that define the structural grid.

**Acceptance criteria:**
- Axis lines are explicitly defined, not computed from vertex clustering
- Z axis has no axis lines (coordinates are never modified)
- Axis line positions can be at any value (not restricted to grid multiples)

### CR-02: Snap Algorithm (Replaces F-07)

**For each vertex coordinate (X, Y only, never Z):**
1. Find the closest axis line position for that axis
2. If the distance to the nearest axis line is within max_tolerance, snap to it
3. If no axis line is within max_tolerance, keep the original coordinate
4. The max_tolerance must be configurable and should default to at least 0.5m (much larger than the current 0.05m alpha)

**Per-element consistency rule:**
- When an element has multiple vertices at the same approximate X position, they must ALL snap to the SAME axis line
- This preserves element geometry (a wall's width doesn't change arbitrarily)

**Pseudo-code:**
```python
def align_vertex_to_axis_lines(coord, axis_lines, max_tolerance):
    if not axis_lines:
        return coord  # No axis lines defined (e.g., Z axis)

    nearest_line = min(axis_lines, key=lambda line: abs(coord - line))
    distance = abs(coord - nearest_line)

    if distance <= max_tolerance:
        return nearest_line
    else:
        return coord  # Keep original
```

### CR-03: Remove DBSCAN Clustering (Deprecate F-04)

The DBSCAN clustering module (`analysis/clustering.py`, `alignment/thread_detector.py`) should be removed or made optional. It produces incorrect results for this use case because:

1. It discovers clusters from data rather than using predefined positions
2. Cluster centroids ≠ structural axis line positions
3. DBSCAN eps=alpha limits the clustering radius, but the true snap distances can be much larger
4. The "chaining effect" workaround is unnecessary when using predefined positions

### CR-04: Z-Axis Treatment (New)

**Z coordinates must NEVER be modified.** The current pipeline detects Z threads and snaps Z values, which is incorrect. Z values represent floor levels that are already correct in the input file.

### CR-05: Tolerance Configuration (Replaces alpha)

**Replace the single `alpha` parameter with:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_snap_distance_x` | 0.5m | Maximum snap distance for X axis |
| `max_snap_distance_y` | 0.5m | Maximum snap distance for Y axis |
| `outlier_snap_distance` | 4.0m | Maximum snap for outlier corrections |
| `z_axis_enabled` | false | Whether to modify Z coordinates |

Note: The actual transformation has some Y displacements up to 3.7m. These appear to be corrections of significantly misplaced elements. The pipeline should either:
- Support a large outlier tolerance, OR
- Flag these as requiring manual review

### CR-06: Object-Level Changes (New, Out of Scope for V1)

The human operator added/removed/renamed 796 objects. This is likely out of scope for the alignment pipeline but should be documented:

- 320 objects removed (including voiles and supports)
- 476 objects added (primarily new supports with higher IDs)
- These changes may represent structural redesign, not alignment

### CR-07: Displacement Rounding (Refinement)

**Observation:** 80%+ of displacements are multiples of 5mm. Axis line positions appear to be defined at 5mm resolution.

**Recommendation:** After snapping, round the final coordinates to 5mm precision (0.005m), not 1cm (0.01m) as the current pipeline does. This better matches the observed data.

However, the exact rounding should be configurable and validated against the reference file.

### CR-08: Axis Line Discovery Tool (New, Optional)

Since the axis lines must be predefined, add a utility to help users define them:

```bash
# Extract axis lines from a reference file
python -m structure_aligner discover-axes --reference after.3dm --output axis_lines.yaml

# Extract from the full geometry file
python -m structure_aligner discover-axes --reference geometrie_2.3dm --output axis_lines.yaml
```

This tool would:
1. Extract all unique coordinate positions from named objects
2. Cluster nearby positions (within 1mm) to account for floating-point noise
3. Rank by vertex count (most-used positions first)
4. Output a YAML file for use with the alignment pipeline

---

## Key Discrepancies Summary

| # | Current Pipeline | Correct Behavior | Impact |
|---|-----------------|-------------------|--------|
| 1 | Discovers axis positions via DBSCAN | Must use predefined axis line positions | **Critical** - Wrong reference values |
| 2 | Snaps to cluster centroid (mean) | Snaps to nearest predefined axis line | **Critical** - Positions off by 10-100mm |
| 3 | Alpha = 0.05m max tolerance | Need 0.5m+ tolerance (up to 3.7m for outliers) | **Critical** - Most vertices won't snap |
| 4 | Modifies Z coordinates | Z must NEVER be modified | **Major** - Introduces errors |
| 5 | 202 X threads, 323 Y threads detected | 188 X axis lines, 273 Y axis lines needed | **Major** - Wrong count and positions |
| 6 | Only 21% of pipeline X threads match true positions | 100% of axis lines must match | **Critical** - Fundamental mismatch |
| 7 | Per-vertex independent snapping | Per-element consistent snapping | **Moderate** - Can distort elements |
| 8 | Rounds to 1cm (0.01m) | Axis lines at 5mm resolution | **Minor** - Small rounding errors |
| 9 | No object add/remove/rename | 796 object-level changes | **Out of scope** but documented |
| 10 | Handles all 3 axes symmetrically | X/Y only; Z is exempt | **Major** |

---

## Code References

- `structure_aligner/analysis/clustering.py:9-71` - DBSCAN clustering (to be replaced)
- `structure_aligner/alignment/thread_detector.py:9-96` - Thread detection (to be replaced)
- `structure_aligner/alignment/processor.py:9-81` - Vertex alignment (to be modified)
- `structure_aligner/alignment/geometry.py:16-41` - find_matching_thread (to be modified)
- `structure_aligner/config.py:1-75` - Configuration (needs new parameters)
- `structure_aligner/main.py:59-182` - Align command (needs axis line input)
- `prd/PRD.md` - Original PRD (to be superseded by corrective PRD)

## Analysis Scripts

- `analysis/compare_vertices.py` - Vertex displacement comparison tool
- `analysis/grid_analysis.py` - Grid alignment and pattern analysis
- `scripts/compare_3dm.py` - Full 3dm file structural comparison

## Codex Independent Review - Cross-Reference

An independent review was conducted using the Codex MCP tool (OpenAI o3) to validate the team's findings and check for discrepancies.

### Confirmations (Codex agrees with team findings)

1. **DBSCAN is wrong** - Codex confirms the fundamental issue: clustering from input data cannot produce the correct output. An external grid is required.
2. **Z is unchanged** - Codex confirms zero Z displacements for common vertices.
3. **Alpha too small** - Codex confirms the 50mm cap is far too restrictive (need 75-200mm typical, up to meters for outliers).
4. **Displacement quantization** - Codex confirms ~70% X and ~55% Y displacements are 25mm multiples, consistent with our 80%/80% finding (difference likely due to rounding methodology).
5. **After coordinate consolidation** - Codex reports X unique values drop from 1002→418, Y from 1157→557. Our finding of 188 X and 273 Y positions refers to the vertex positions of common (matched) objects only, while Codex counted all unique coordinate values including added objects. Both confirm massive consolidation.
6. **Rounding precision wrong** - Codex confirms 0.01m (1cm) is too coarse; axis lines exist at 1mm or 5mm precision.

### Additional Insights from Codex

1. **42 X grid lines in after.3dm are NOT present in before.3dm** - This definitively proves the grid is externally defined. The pipeline cannot discover all target positions from the input alone, because some target positions don't exist in the input at all.
2. **Two mezzanine Z levels** (~3.8291m, ~5.1807m) appear only in after-only objects. Our analysis found 11 Z levels for common vertices; Codex found 2 additional levels used by the 476 newly-added objects.
3. **Codex recommends histogram peak detection** as an optional augmentation to the master grid. This could help validate the grid but should not be the primary source.

### Discrepancies Between Codex and Team Findings

1. **Grid precision**: Codex says "1mm precision with 5mm/25mm quantization". Our analysis found the axis lines have a micro-offset of ~0.000044m suggesting they aren't exactly on any standard grid. Both agree that 5mm is the practical resolution for displacements.
2. **Z-level treatment**: Codex recommends "snap Z to nearest level from fixed list". Our analysis says Z should NEVER be modified because it's already correct. For common vertices both approaches produce the same result, but Codex's approach would also handle newly-added objects. Our recommendation (CR-04) is more conservative: don't touch Z.
3. **Distance limit**: Codex says "snap regardless of distance" (no max tolerance). Our CR-05 recommends a configurable max_snap_distance with a large outlier tolerance. The Codex approach is simpler but riskier for incorrectly-placed elements.

### Verdict

The Codex independent review **strongly confirms** all critical findings. The most valuable new insight is that **42 X axis lines exist in after.3dm that have no corresponding position in before.3dm**, providing definitive proof that the grid must be externally defined.

---

## Open Questions

1. **Where do the axis line positions come from?** Are they defined in the geometre_2.3dm master file? In an external document? In Revit/ArchiCAD? The pipeline needs a way to import them.

2. **Why are some displacements > 1m?** The 8 vertices with Y displacement > 2m suggest either major corrections or model restructuring. Should the pipeline handle these automatically or flag for review?

3. **Object-level changes:** Are the 796 added/removed objects part of the alignment process or separate structural design changes? This determines scope.

4. **Brep topology changes:** Some objects changed topology (different number of faces/edges). Is this expected from vertex position changes, or does it indicate geometry reconstruction?

5. **Per-element axis line assignment:** When an element spans two axis lines, how should the pipeline determine which vertices snap to which line? Currently the "closest" rule works for most cases but fails for ~28% of X vertex assignments.
