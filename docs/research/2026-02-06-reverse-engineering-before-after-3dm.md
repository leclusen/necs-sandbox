---
date: 2026-02-06T20:30:14Z
researcher: Claude Code
git_commit: HEAD (initial commit pending)
branch: main
repository: necs
topic: "Reverse-Engineering Transformation Rules from before.3dm/after.3dm Reference Files"
tags: [research, codebase, reverse-engineering, 3dm, alignment, transformation-rules, pipeline-bugs]
status: complete
last_updated: 2026-02-06
last_updated_by: Claude Code
---

# Research: Reverse-Engineering Transformation Rules from before.3dm/after.3dm

**Date**: 2026-02-06T20:30:14Z
**Researcher**: Claude Code
**Git Commit**: HEAD (initial commit pending)
**Branch**: main
**Repository**: necs

## Research Question

Reverse-engineer the transformation rules applied between `data/input/before.3dm` (unaligned input) and `data/input/after.3dm` (correctly aligned output) to identify what the current pipeline implements incorrectly or is missing from the PRD.

## Summary

The before/after 3dm comparison reveals **fundamental discrepancies** between what the PRD specifies, what the pipeline implements, and what the reference output actually does. The pipeline produces wrong results because it follows the PRD too literally in some areas while the reference output uses significantly different rules. Below is a comprehensive list of **14 identified issues**.

---

## Detailed Findings

### 1. File Relationships

| File | Objects (named) | Vertices | Relationship |
|------|----------------|----------|-------------|
| `geometrie_2.3dm` | 5,825 | 20,994 | Full model (superset) |
| `before.3dm` | 2,527 | 10,348 | **Subset** of geometrie_2.3dm (identical vertices for all 2,527 common objects) |
| `after.3dm` | 2,683 (named) / 2,850 (total) | 9,058 | Aligned version with structural changes |

**Critical finding**: `before.3dm` is NOT the same as `geometrie_2.3dm`. It is a filtered subset containing only 2,527 of the 5,825 objects. The pipeline currently runs on geometrie_2.3dm (full set), producing alignment for objects that don't exist in the reference before/after pair. **The pipeline input must be before.3dm, not geometrie_2.3dm.**

### 2. Object Set Changes (Not Just Vertex Moves)

| Metric | Count |
|--------|-------|
| Common objects (before ∩ after) | 2,207 |
| Only in before (removed) | 320 (313 Coque, 7 Appuis) |
| Only in after (added) | 476 (104 Coque, 135 Filaire, 237 Appuis) |

**Rule not in PRD**: The alignment process **adds and removes objects**. This is not a simple vertex-snapping operation. The reference output:
- Removes 320 objects (mostly Coque/shell elements and some supports)
- Adds 476 new objects (with new naming/numbering: Appuis_8032-8289, Coque_8xxx, Filaire_8xxx)
- The 167 unnamed objects in after.3dm are also new additions

### 3. Geometry Type Conversions and Layer Changes

**All 2,207 common Filaire objects changed from `LineCurve` to `PolylineCurve`** in the after file (919 in before, only 38 LineCurve remain in after vs 1,162 PolylineCurve).

Additionally:
- **1,728 new layers** were added (Appuis_8032-8289, Coque_6553-8222, Filaire_7429-8233, plus structural layers `Files`, `Keep_files`, `Volume`)
- **2 layers removed** (`Calque 01`, `Calque 02`)
- **All common objects received new color attributes** — Coque elements went from uniform gray `(169,169,169)` to categorized colors (blue, teal, green, purple, brown), suggesting a classification scheme was applied
- **40 NurbsCurve** and **1 Surface** objects appeared in after (0 in before)
- **All 1,288 common Brep objects have identical topology** (same faces, edges, vertices, trims) — only vertex positions changed, not the Brep structure

**Rule not in PRD**: The PRD never mentions geometry type conversion, layer addition/removal, or color classification. The current pipeline preserves geometry types.

### 4. Z Axis is NEVER Modified

| Axis | Vertices changed | Max displacement |
|------|-----------------|-----------------|
| X | 6,186/6,994 (88.4%) | 0.7289m |
| Y | 4,502/6,994 (64.4%) | 3.6866m |
| Z | 0/6,994 (0.0%) | 0.0000m |

**Rule not in PRD**: Z is completely untouched. The PRD specifies alignment on all three axes (X, Y, Z), and the pipeline detects and aligns Z threads. The reference output preserves Z exactly.

**Pipeline bug**: The pipeline aligns Z vertices (the report shows 13 unique Z values clustered into threads). This introduces unintended Z modifications.

### 5. Tolerance (Alpha) is MUCH Larger Than PRD Default

The PRD default alpha is 0.05m. The reference output has:

| Percentile | X displacement | Y displacement |
|------------|---------------|----------------|
| p50 | 0.0400m | 0.0250m |
| p90 | 0.1750m | 0.1600m |
| p95 | 0.2000m | 0.1938m |
| p99 | 0.2489m | 0.3000m |
| max | 0.7289m | 3.6866m |

**Rule deviation from PRD**: The effective tolerance is approximately **0.20-0.30m** for 95% of vertices, with outliers up to 0.73m (X) and 3.69m (Y). The PRD's alpha=0.05m would reject most of these alignments.

**Pipeline bug**: With alpha=0.05, the pipeline only aligns vertices within 5cm, missing the vast majority of intended alignments.

### 6. Thread Detection Rules Differ from PRD

The PRD specifies `DBSCAN(eps=alpha, min_samples=3)`. The reference output shows:

| Metric | After X | After Y |
|--------|---------|---------|
| Unique positions (threads) | 439 | 589 |
| Thread with 1 vertex | 37 | ? |
| Thread with 2 vertices | 193 | ? |
| Thread with 3+ vertices | 209 | ? |

**Rules not matching PRD**:
- **min_cluster_size=3 is wrong**: 230 X threads (52%) have fewer than 3 vertices. The reference allows threads with just 1-2 vertices.
- **Thread merge at 2*alpha is too aggressive**: After X values have 265 gaps < 0.1m between adjacent unique positions. With alpha=0.05, merge threshold=0.10m would incorrectly merge many distinct threads.
- **Thread references are NOT rounded to centimeter**: The after X values have sub-millimeter precision (e.g., -71.874957, -69.499455, -66.799955). PRD says `round(mean, 2)` (centimeter). The reference keeps 3-6 decimal places.

### 7. Non-Uniform Brep Displacements (Per-Vertex Alignment)

| Category | Count |
|----------|-------|
| Uniformly translated objects | 1,076 |
| Non-uniformly displaced objects | 1,100 (ALL Breps) |
| Unchanged objects | 31 |

**All 1,100 non-uniform objects are Breps** (Coque elements). Different vertices within the same Brep snap to different threads. Example:

```
Coque_3143 (Brep, 4 vertices):
  v0: (-61.831, 30.900) -> (-61.400, 30.850)  dx=+0.431, dy=-0.050
  v1: (-61.831, 30.900) -> (-61.400, 30.850)  dx=+0.431, dy=-0.050
  v2: (-60.725, 30.900) -> (-60.725, 30.850)  dx= 0.000, dy=-0.050
  v3: (-60.725, 30.900) -> (-60.725, 30.850)  dx= 0.000, dy=-0.050
```

This means vertices v0-v1 snapped to a different X thread than v2-v3. **The pipeline correctly does per-vertex alignment**, but its tolerance is too tight to replicate this behavior.

### 8. Top Displacement Patterns

The most common displacement vectors (dx, dy, dz) reveal alignment to grid-like reference values:

| Displacement (dx, dy, dz) | Count | Interpretation |
|---------------------------|-------|----------------|
| (0, 0, 0) | 1,640 | Already aligned |
| (0, 0.025, 0) | 268 | Y snap to 2.5cm grid |
| (0.025, 0, 0) | 230 | X snap to 2.5cm grid |
| (0.075, 0, 0) | 220 | X snap to 7.5cm |
| (0.05, 0, 0) | 194 | X snap to 5cm grid |
| (0, -0.025, 0) | 178 | Y snap to -2.5cm |
| (0.2, 0, 0) | 128 | X snap to 20cm |
| (0.16, 0, 0) | 118 | X snap to 16cm |
| (-0.175, 0, 0) | 100 | X snap to -17.5cm |

**Pattern**: Displacements are often multiples of 0.025m (2.5cm), suggesting the reference values may be on a finer grid than the 1cm precision specified in the PRD.

### 9. Displacement Precision Analysis

Checking if displacements are quantized:

| Multiple of | X match rate | Y match rate |
|-------------|-------------|-------------|
| 0.001m | 46.8% | 60.1% |
| 0.005m | 46.7% | 60.0% |
| 0.010m | 30.6% | 31.3% |
| 0.025m | 42.9% | 50.6% |
| 0.050m | 28.0% | 25.8% |

The displacements are NOT purely quantized to any single grid. This suggests thread references are derived from actual vertex clusters, not from a predefined grid.

### 10. LineCurve Uniform Translation

All 913 LineCurve (Filaire) objects have uniform displacement — both endpoints move by the same (dx, dy, 0) vector. This is consistent with snapping both endpoints to the same pair of threads. However, 912 of these are converted to PolylineCurve in the output, which is an unexplained structural change.

### 11. Reference Values Analysis

After X values are NOT at any standard grid precision:
- 0% are multiples of 0.025m
- 0% are multiples of 0.001m
- Values like -71.874957, -69.499455, -66.799955 have sub-millimeter fractional parts

This means thread reference values retain the full precision of the cluster centroid rather than being rounded.

### 12. Y-Axis Outliers

Y displacements have extreme outliers (max 3.69m) while X max is 0.73m. This suggests:
- Some elements have large Y corrections (possibly modeling errors)
- The tolerance for Y alignment may be higher, or these outliers represent a different operation (e.g., object repositioning rather than vertex snapping)

### 13. PRD Validation Rule Failures

The PRD's F-09 validation states: "Déplacement max ≤ alpha → ERREUR CRITIQUE - Rollback"

With any reasonable alpha (0.05, 0.13, 0.5), the reference output would FAIL this validation:
- alpha=0.05: Max displacement 3.69m >> 0.05m
- alpha=0.50: Max displacement 3.69m >> 0.50m

**This means either**: (a) the PRD validation rule is wrong/incomplete, (b) the alpha parameter has a different meaning in practice, or (c) outlier vertices should be handled differently.

### 14. Object Addition/Removal Rules

The reference adds 476 objects and removes 320. Patterns:
- **Removed**: Mostly Coque (shell) objects with IDs in the original range
- **Added**: New Appuis (supports) with IDs 8032-8289, new Filaire with IDs in 8xxx range, new Coque objects

This suggests the alignment tool may also perform structural operations like:
- Splitting or merging elements
- Renumbering supports
- Creating new structural elements at aligned positions

---

## Gap Analysis: PRD vs. Reference Output vs. Pipeline

| # | Rule/Behavior | PRD Says | Reference Output Shows | Pipeline Does | Status |
|---|--------------|----------|----------------------|---------------|--------|
| 1 | Input file | geometrie_2.3dm | before.3dm (subset) | geometrie_2.3dm | **WRONG INPUT** |
| 2 | Z alignment | Align all axes | Z never modified | Aligns Z | **BUG** |
| 3 | Alpha tolerance | 0.05m default | Effective ~0.20-0.30m, max 3.69m | Strictly enforces 0.05m | **TOO STRICT** |
| 4 | Min cluster size | 3 | Threads with 1-2 vertices exist | 3 | **TOO STRICT** |
| 5 | Thread rounding | Round to 0.01m | Full precision (6dp) | Rounds to 0.01m | **WRONG PRECISION** |
| 6 | Thread merge | Merge if < 2*alpha | Many close threads preserved | Merges at 2*alpha | **TOO AGGRESSIVE** |
| 7 | Object add/remove | Not mentioned | 476 added, 320 removed | No add/remove | **MISSING** |
| 8 | Geometry conversion | Not mentioned | LineCurve→PolylineCurve, +40 NurbsCurve, +1 Surface | Preserves types | **MISSING** |
| 9 | Validation threshold | Reject if displacement > alpha | Displacements up to 3.69m | Rejects > alpha | **NEEDS UPDATE** |
| 10 | DBSCAN eps | eps=alpha | Unknown (much larger effective range) | eps=alpha | **LIKELY WRONG** |
| 11 | Displacement quantization | Not specified | Often multiples of 0.025m | N/A | **NOT IN PRD** |
| 12 | Per-vertex vs uniform | Per-vertex | Both (Brep=per-vertex, Line=uniform) | Per-vertex | Correct |
| 13 | Object naming | Preserve | New IDs for added objects (8xxx range) | Preserve | **MISSING** |
| 14 | Brep residual handling | Not mentioned | N/A (reference is final) | Transform+fixup | Unknown |

---

## Recommendations Priority

### P0 - Critical (Pipeline produces wrong results)

1. **Disable Z alignment**: Add `align_z=False` parameter or hard-code Z preservation
2. **Increase alpha**: Default to 0.25-0.30m, or make configurable with higher default
3. **Remove centimeter rounding**: Keep thread references at full precision (or at least 4-6dp)
4. **Lower min_cluster_size to 1**: Allow single-vertex and 2-vertex threads
5. **Use before.3dm as input**: The pipeline currently operates on the full geometrie_2.3dm

### P1 - Important (Pipeline behavior differs from reference)

6. **Relax or remove thread merge**: Either increase merge threshold significantly or remove merging entirely
7. **Update DBSCAN eps**: Use a larger eps value (0.25-0.30m) or switch to a different clustering approach
8. **Update validation thresholds**: Allow larger displacements or add per-axis configurable limits

### P2 - Missing Features (Not in pipeline at all)

9. **Object add/remove logic**: The reference adds/removes objects — this may be a separate manual/tool step
10. **LineCurve→PolylineCurve conversion**: May be a Rhino export artifact rather than intentional
11. **Structural element creation**: The 476 new objects may come from a different tool

---

## Follow-up Finding: 25mm Grid Snapping (from Pipeline Comparison Agent)

A parallel analysis comparing the pipeline output against after.3dm revealed an additional critical insight:

### RC-5: The Reference Uses a Predefined 25mm Structural Grid

The reference displacements are **clean multiples of 0.025m (25mm)**: 0.025, 0.05, 0.075, 0.1, 0.125, 0.15, 0.175, 0.2, etc. This strongly suggests the reference alignment snaps vertices to a **predefined 25mm structural grid** rather than to DBSCAN-discovered cluster centroids.

| Metric | Pipeline (DBSCAN) | Reference (after.3dm) |
|--------|-------------------|----------------------|
| Snap targets | Cluster mean values, rounded to 1cm | 25mm grid positions |
| X delta pattern | ~0.005m multiples (rounding artifact) | ~0.025m multiples (grid) |
| Input objects | 5,825 (geometrie_2.3dm) | 2,527 (before.3dm) |
| Alignment rate | 100% (over-aligns) | 95.2% (leaves some alone) |

### Pipeline Comparison: 0% Exact Match

When comparing the pipeline output (aligned.3dm) to the reference after.3dm for the 2,207 common objects:
- **0 vertices match exactly** — every pipeline vertex is in the wrong position
- **100% over-alignment** — pipeline snaps all vertices while reference leaves 4.8% unchanged
- The pipeline produces thread refs like `-23.76` while the reference has `-23.599954`

### Implication

The alignment algorithm may need to be fundamentally restructured: instead of DBSCAN clustering to discover threads from data, it should snap to the **nearest point on a 25mm grid**. This would be a simpler algorithm:
```
aligned_coord = round(original_coord / 0.025) * 0.025
```
However, this needs validation against the full dataset, as some reference coordinates don't appear to be exact 25mm multiples.

---

## Code References

- `structure_aligner/config.py:8-11` — AlignmentConfig defaults (alpha=0.05, min_cluster_size=3, rounding=0.01)
- `structure_aligner/alignment/geometry.py:36-37` — find_matching_thread uses alpha as hard cutoff
- `structure_aligner/analysis/clustering.py:33` — DBSCAN eps=alpha, min_samples=min_cluster_size
- `structure_aligner/alignment/thread_detector.py:31` — Thread reference rounded to rounding_ndigits (2dp)
- `structure_aligner/alignment/thread_detector.py:47` — Merge threshold = alpha * 2
- `structure_aligner/alignment/processor.py:43-44` — Aligns all 3 axes (X, Y, Z)
- `structure_aligner/output/validator.py:60` — Rejects displacement > alpha

## Architecture Documentation

The pipeline has 3 main phases:
1. **ETL**: Extract vertices from .3dm → Transform/link to .db → Load into PRD-compliant DB
2. **Align**: Load vertices → Cluster → Detect threads → Snap vertices → Validate → Write aligned DB
3. **Reverse ETL**: Read aligned DB → Update .3dm template → Write output .3dm

The core issue is that Phase 2 (Align) parameters don't match the reference output behavior.

## Related Research

- `docs/research/2026-02-03-prd-analysis-geometric-alignment-software.md` — PRD analysis
- `docs/research/2026-02-05-geometrie2-database-prd-alignment.md` — DB alignment research
- `docs/research/2026-02-06-alignment-plan-review.md` — Plan review

## Open Questions

1. **Is after.3dm produced by a completely different tool** (e.g., native Rhino plugin) rather than the Python pipeline? The object additions/removals and geometry type changes suggest it may be.
2. **What alpha value should be used?** The data suggests 0.25-0.30m covers 95% of vertices, but outliers go to 3.69m.
3. **Should the 476 added objects be handled?** They may come from a separate modeling step.
4. **Is the LineCurve→PolylineCurve change intentional?** It may be a Rhino file format artifact.
5. **How should Y outliers (>1m displacement) be handled?** Are they modeling corrections or alignment bugs?
6. **Is before.3dm the correct input, or should the pipeline handle the full geometrie_2.3dm and produce partial output?**

---

*Research completed on 2026-02-06 using multi-angle analysis: direct vertex extraction with rhino3dm, Codex MCP independent analysis, and statistical pattern analysis.*
