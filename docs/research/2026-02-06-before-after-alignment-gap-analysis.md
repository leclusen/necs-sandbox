---
date: 2026-02-06T20:19:30Z
researcher: Claude Code
git_commit: no-commit
branch: main
repository: necs
topic: "Leveraging before/after.3dm files to fix alignment pipeline"
tags: [research, codebase, alignment, before-after, gap-analysis, 3dm]
status: complete
last_updated: 2026-02-06
last_updated_by: Claude Code
---

# Research: Leveraging before/after.3dm Files to Fix the Alignment Pipeline

**Date**: 2026-02-06T20:19:30Z
**Researcher**: Claude Code
**Git Commit**: no-commit
**Branch**: main
**Repository**: necs

## Research Question

How to best leverage the before.3dm and after.3dm reference files to fix and improve the current alignment pipeline that produces wrong data, either because of bugs in the implementation or because the PRD lacks details, examples, or specific exhaustive alignment rules.

## Summary

The before/after.3dm files represent a **ground truth example** of expected alignment behavior. Comparing them reveals that the reference transformation involves displacements **far larger than any single alpha value** (up to 0.73m on X, 3.69m on Y), uses **different element sets** (the after file has different Appuis IDs), and **never modifies Z coordinates**. The current pipeline output diverges massively from the reference (displacements of 100m+), confirming fundamental mismatches between what the pipeline does and what the reference expects.

**Three root problems identified:**

1. **Different input files**: before.3dm (2,527 objects / 10,348 vertices) is a strict subset of geometrie_2.3dm (5,825 objects / 20,996 vertices). The pipeline runs on geometrie_2.3dm, not before.3dm. The after.3dm was made from before.3dm, not geometrie_2.3dm.
2. **Displacements exceed any alpha**: The reference transformation has displacements up to 3.69m (Y-axis), meaning the expected alignment is NOT a small tolerance-based snap. The PRD's alpha-tolerance model (0.05m default) cannot reproduce this behavior.
3. **Element set changes**: The after.3dm has 2,683 named objects with 156 more than the before (2,527). Some elements (Appuis_6463, 6465, etc.) are removed and new ones (Appuis_8032-8041+) are added. The pipeline has no concept of adding/removing elements.

## Detailed Findings

### 1. File Relationship: before.3dm vs geometrie_2.3dm

`before.3dm` is a **strict geometric subset** of `geometrie_2.3dm`:

| Property | before.3dm | geometrie_2.3dm |
|----------|-----------|-----------------|
| Total objects | 2,527 | 5,825 |
| Named objects | 2,527 | 5,825 |
| Total vertices | 10,348 | 20,996 |
| Common vertices | 10,348 (100% of before) | — |
| Displacement of common vertices | 0.0 on all axes | — |

**All 10,348 before.3dm vertices exist with identical coordinates in geometrie_2.3dm.** The additional 10,648 vertices in geometrie_2.3dm come from elements present in the database but absent from before.3dm.

### 2. Reference Transformation: before.3dm → after.3dm

The reference comparison reveals the "correct" alignment behavior:

| Property | Value |
|----------|-------|
| Common vertices (matched by name+index) | 6,994 |
| Only in before (removed) | 3,354 |
| Only in after (added) | 2,064 |

**Displacement statistics for the 6,994 common vertices:**

| Axis | Changed | Max (abs) | Median | Mean |
|------|---------|-----------|--------|------|
| X | 6,186/6,994 (88%) | 0.7289m | 0.0000 | 0.0306 |
| Y | 4,502/6,994 (64%) | 3.6866m | 0.0000 | 0.0066 |
| Z | 0/6,994 (0%) | 0.0000m | 0.0000 | 0.0000 |

**Top displacement patterns (rounded to 4dp):**

| Displacement (X, Y, Z) | Count |
|-------------------------|-------|
| (0.0, 0.0, 0.0) | 1,640 (23%) |
| (0.0, 0.025, 0.0) | 268 |
| (0.025, 0.0, 0.0) | 230 |
| (0.075, 0.0, 0.0) | 220 |
| (0.05, 0.0, 0.0) | 194 |
| (0.0, -0.025, 0.0) | 178 |
| (0.2, 0.0, 0.0) | 128 |
| (0.16, 0.0, 0.0) | 118 |
| (-0.175, 0.0, 0.0) | 100 |
| (0.1, 0.0, 0.0) | 92 |

**Key observations:**
- **Z is NEVER modified** — the reference alignment only affects X and Y
- **Displacements are multiples of 0.005m or 0.025m** — suggesting grid-based alignment, not just tolerance-snapping
- **Max displacement (3.69m on Y)** is 73x the default alpha (0.05m) — the PRD's alpha-based model cannot explain this
- **23% of common vertices unchanged** — many vertices don't need alignment
- **Displacement values: 0.025, 0.05, 0.075, 0.1, 0.125, 0.16, 0.175, 0.2** — these look like snapping to a regular grid (multiples of 5mm or 25mm)

### 3. Current Pipeline Output vs Reference (after.3dm)

Comparing the pipeline's output (aligned.3dm) with the reference after.3dm:

| Property | Value |
|----------|-------|
| Common vertices | 7,114 |
| Only in after.3dm (missing from output) | 1,944 |
| Only in pipeline output (extra) | 13,882 |

**Displacement statistics for common vertices:**

| Axis | Max (abs) | Median | Mean |
|------|-----------|--------|------|
| X | **118.68m** | -0.005 | 1.084 |
| Y | **110.33m** | 0.000 | 0.929 |
| Z | **23.68m** | 0.000 | -0.322 |

The pipeline output is **completely different** from the expected reference:
- Displacements of 100m+ indicate the pipeline and reference are operating on fundamentally different element sets
- 13,882 extra vertices in the pipeline output (from the full geometrie_2.3dm) don't exist in after.3dm
- Z-axis changes of 23m indicate some vertices are on entirely different floors

### 4. Element Set Differences

| Set | before.3dm | after.3dm |
|-----|-----------|-----------|
| Named objects | 2,527 | 2,683 (+156) |
| Total vertices | 10,348 | 9,058 (-1,290) |

Elements removed from before → after include `Appuis_6463`, `Appuis_6465`, `Appuis_6466`, `Coque_1534`, etc.
Elements added in after include `Appuis_8032`-`Appuis_8041`+.

This means the reference transformation **adds new elements and removes old ones**, which is not part of the current pipeline's capabilities at all.

### 5. Current Pipeline Architecture

The pipeline operates on `geometrie_2.3dm` (full model) + a source `.db`:

```
geometrie_2.3dm + source.db
    → ETL (extract, transform, load)
    → geometrie_2_prd.db (20,994 vertices)
    → Alignment (DBSCAN clustering, thread detection, vertex snapping)
    → aligned.db
    → Reverse ETL (write back to .3dm)
    → aligned.3dm
```

Key source files:
- `structure_aligner/alignment/processor.py` — vertex alignment
- `structure_aligner/alignment/thread_detector.py` — DBSCAN-based thread detection
- `structure_aligner/alignment/geometry.py` — matching logic
- `structure_aligner/analysis/clustering.py` — DBSCAN clustering
- `structure_aligner/etl/reverse_writer.py` — .3dm output (handles Brep, Line, Polyline, NurbsCurve, Point)

### 6. PRD Alignment Rules vs Reference Behavior

| PRD Rule | Reference Behavior | Match? |
|----------|-------------------|--------|
| Per-axis displacement ≤ alpha | Displacements up to 3.69m | **NO** |
| DBSCAN clustering with eps=alpha | Grid-like displacement patterns (multiples of 5mm) | **UNCLEAR** |
| All 3 axes aligned | Only X and Y modified; Z never touched | **NO** |
| Vertex count preserved | 10,348 → 9,058 (fewer) | **NO** |
| Element set unchanged | Elements added/removed | **NO** |

## How to Leverage the before/after Files

### Strategy 1: Build a Comparison Test Suite (Immediate Value)

Write a script that:
1. Runs the pipeline on `before.3dm` (not geometrie_2.3dm)
2. Compares the output against `after.3dm` vertex-by-vertex
3. Reports per-vertex displacement error (expected vs actual)
4. Scores the output (e.g., "52% of vertices within 1mm of reference")

This creates a **regression test** that quantitatively measures pipeline accuracy against the known-good output.

### Strategy 2: Reverse-Engineer Alignment Rules from the Data

The displacement patterns strongly suggest a **grid-snapping** or **structural grid alignment** mechanism:

1. **Extract the target coordinates from after.3dm** — these reveal the "grid lines"
2. **Compare target coordinates with thread references** — check if the pipeline detects the right threads
3. **Analyze displacement distribution** — the multiples of 0.005m/0.025m suggest a structural grid, not just DBSCAN-derived threads
4. **Z-axis invariance** — the pipeline should have an option to skip Z alignment (or Z is handled differently)

### Strategy 3: Create a Ground Truth Database

1. Extract vertices from both before.3dm and after.3dm
2. Match by element name + vertex_index
3. For each matched pair, record: original coords, expected aligned coords, displacement per axis
4. This becomes a **golden dataset** that can be used to:
   - Validate thread detection (do detected threads include the target coordinates?)
   - Validate alignment logic (does each vertex snap to the correct target?)
   - Identify missing alignment rules (what causes the large displacements?)

### Strategy 4: Investigate PRD Gaps

The reference data reveals several behaviors NOT described in the PRD:

1. **Z-axis immunity**: The reference never modifies Z coordinates. The PRD does not mention this.
2. **Large displacements**: Displacements up to 3.69m are not compatible with a small alpha tolerance. Either:
   - The alpha used was much larger (but then thread detection would be very coarse)
   - Multiple alignment passes were applied
   - A different alignment strategy was used (e.g., snap to known structural grid, not DBSCAN-derived threads)
3. **Element set mutation**: Elements are added/removed, suggesting a broader data cleanup process beyond coordinate alignment
4. **Grid-like patterns**: The 5mm/25mm displacement multiples suggest structural grid coordinates (e.g., architectural grid at 25mm resolution)

## Code References

- `structure-batiment/analysis/compare_vertices.py` — existing vertex comparison tool
- `structure-batiment/scripts/compare_3dm.py` — layer/object comparison tool
- `structure-batiment/structure_aligner/alignment/processor.py` — current alignment logic
- `structure-batiment/structure_aligner/alignment/thread_detector.py` — thread detection
- `structure-batiment/structure_aligner/alignment/geometry.py` — matching utilities
- `structure-batiment/structure_aligner/analysis/clustering.py` — DBSCAN clustering
- `structure-batiment/structure_aligner/etl/extractor.py` — .3dm vertex extraction
- `structure-batiment/structure_aligner/etl/reverse_writer.py` — .3dm output
- `structure-batiment/data/input/before.3dm` — input reference
- `structure-batiment/data/input/after.3dm` — expected output reference
- `structure-batiment/data/input/geometrie_2.3dm` — full model (superset of before.3dm)

## Architecture Documentation

### Current Pipeline Data Flow

```
Input: geometrie_2.3dm + source.db
  │
  ├─ ETL: extract_vertices() → transform() → load()
  │    └─ Produces: geometrie_2_prd.db (elements + vertices tables)
  │
  ├─ Alignment:
  │    ├─ load_vertices() from prd.db
  │    ├─ compute_axis_statistics() for X, Y, Z
  │    ├─ detect_threads() using DBSCAN(eps=alpha) + post-validation + merge
  │    ├─ align_vertices() snaps each vertex to nearest thread within alpha
  │    ├─ validate_alignment() checks per-axis displacement ≤ alpha
  │    └─ Produces: aligned.db + report.json
  │
  └─ Reverse ETL: read_aligned_elements() → write_aligned_3dm()
       └─ Produces: aligned.3dm
```

### Reference Transformation Characteristics

```
Input: before.3dm (2,527 objects, 10,348 vertices)
  │
  ├─ X/Y alignment (Z unchanged)
  ├─ Grid-like displacement patterns (multiples of 5mm)
  ├─ Max displacement: 3.69m (Y-axis)
  ├─ Elements added (156 new named objects)
  ├─ Elements removed (some vertices lost)
  │
Output: after.3dm (2,683 objects, 9,058 vertices)
```

## Related Research

- `docs/research/2026-02-03-prd-analysis-geometric-alignment-software.md` — PRD analysis
- `docs/research/2026-02-05-geometrie2-database-prd-alignment.md` — database analysis
- `docs/research/2026-02-06-alignment-plan-review.md` — plan review findings
- `docs/plans/2026-02-05-alignment-algorithm-implementation.md` — implementation plan

## Open Questions

1. **What tool/process generated the after.3dm?** — Was it a manual process in Rhino, a different software, or a previous version of this pipeline? Understanding the source would clarify the expected behavior.

2. **Is the Z-axis immunity intentional?** — Should the pipeline skip Z alignment entirely, or was Z already aligned in the before.3dm?

3. **What explains the large displacements (up to 3.69m)?** — Are these snapping to a known structural grid? Were multiple alpha passes used? Or does the alignment use externally-defined grid coordinates rather than DBSCAN-derived threads?

4. **Why do element sets differ?** — The added/removed elements suggest a data cleanup step not described in the PRD. Is this within scope for this pipeline?

5. **Should the pipeline take before.3dm as input instead of geometrie_2.3dm?** — Since before.3dm is a strict subset, the pipeline might need to operate only on this subset.

6. **What is the structural grid resolution?** — The displacement patterns (multiples of 5mm/25mm) suggest a known grid. Is this grid defined elsewhere (architectural drawings, BIM model)?

7. **Were the alignment rules applied manually by a structural engineer?** — If after.3dm was produced by manual adjustment in Rhino, extracting exact rules may require domain expert input to formalize.

---

*Research completed on 2026-02-06*
