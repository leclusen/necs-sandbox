#!/usr/bin/env python3
"""Deep grid analysis of displacement patterns between before.3dm and after.3dm.

Loads both files, matches vertices by (name, vertex_index), then analyzes:
- Grid snapping of after values at multiple granularities
- Displacement quantization patterns
- Before vs after value distributions
- Rounding rule detection
- Z-axis level detection
- Per-element-type breakdown
- Sign/direction analysis
- Unchanged vertex inventory
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from structure_aligner.etl.extractor import ExtractionResult, RawVertex, extract_vertices

BEFORE_PATH = Path("data/input/before.3dm")
AFTER_PATH = Path("data/input/after.3dm")

GRID_SIZES_MM = [1, 5, 10, 25, 50, 100, 250, 500, 1000]
AXES = ["X", "Y", "Z"]


def load_and_index(path: Path):
    result = extract_vertices(path)
    print(f"[load] {path.name}: {len(result.vertices)} vertices, "
          f"{len({v.element_name for v in result.vertices})} named objects, "
          f"{result.total_objects} total objects")
    index = {}
    for v in result.vertices:
        key = (v.element_name, v.vertex_index)
        index[key] = v
    return result, index


def coord(v: RawVertex, axis: int) -> float:
    return [v.x, v.y, v.z][axis]


def is_multiple(value_m: float, grid_mm: float, tol_mm: float = 0.01) -> bool:
    grid_m = grid_mm / 1000.0
    if grid_m == 0:
        return True
    remainder = abs(value_m) % grid_m
    return min(remainder, grid_m - remainder) < (tol_mm / 1000.0)


def pct(n: int, total: int) -> str:
    if total == 0:
        return "N/A"
    return f"{100.0 * n / total:.1f}%"


def section(title: str):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


def main():
    print("=" * 80)
    print("  DEEP GRID ANALYSIS: before.3dm vs after.3dm")
    print("=" * 80)

    before_result, before_idx = load_and_index(BEFORE_PATH)
    after_result, after_idx = load_and_index(AFTER_PATH)

    keys_before = set(before_idx.keys())
    keys_after = set(after_idx.keys())
    common_keys = sorted(keys_before & keys_after)
    only_before = keys_before - keys_after
    only_after = keys_after - keys_before

    print(f"\n[match] Common vertices: {len(common_keys)}")
    print(f"[match] Only in before: {len(only_before)}")
    print(f"[match] Only in after:  {len(only_after)}")

    # Build matched arrays
    before_coords = np.array([[coord(before_idx[k], a) for a in range(3)] for k in common_keys])
    after_coords = np.array([[coord(after_idx[k], a) for a in range(3)] for k in common_keys])
    deltas = after_coords - before_coords

    categories = [before_idx[k].category for k in common_keys]
    geom_types = [before_idx[k].geometry_type for k in common_keys]
    names = [k[0] for k in common_keys]

    n = len(common_keys)

    # =====================================================================
    # 1. GRID SNAPPING ANALYSIS (after values)
    # =====================================================================
    section("1. GRID SNAPPING OF AFTER VALUES")
    print("For each axis and grid size, what % of 'after' coordinates are exact multiples.\n")

    for ai, axis in enumerate(AXES):
        print(f"--- Axis {axis} ---")
        vals = after_coords[:, ai]
        for gs in GRID_SIZES_MM:
            count = sum(1 for v in vals if is_multiple(v, gs))
            print(f"  Grid {gs:>5d} mm: {count:>6d}/{n} = {pct(count, n)}")
        print()

    # =====================================================================
    # 2. DISPLACEMENT PATTERNS
    # =====================================================================
    section("2. DISPLACEMENT PATTERNS")

    for ai, axis in enumerate(AXES):
        print(f"\n--- Axis {axis} displacements ---")
        axis_d = deltas[:, ai]
        moved = axis_d[np.abs(axis_d) > 1e-9]
        print(f"  Moved: {len(moved)}/{n} vertices")
        if len(moved) == 0:
            continue

        print(f"  Range: [{np.min(moved):.6f}, {np.max(moved):.6f}] m")
        print(f"  Mean:  {np.mean(moved):.6f} m")
        print(f"  Median: {np.median(moved):.6f} m")
        print(f"  Std:   {np.std(moved):.6f} m")

        # Convert to mm for quantization analysis
        moved_mm = moved * 1000.0
        rounded_1mm = np.round(moved_mm).astype(int)
        counts_1mm = Counter(rounded_1mm)
        print(f"\n  Top 20 displacements (rounded to 1mm):")
        for val, cnt in counts_1mm.most_common(20):
            print(f"    {val:>8d} mm  ({val/1000:.3f} m): {cnt} vertices")

        # Check quantization: are displacements multiples of common grid sizes?
        print(f"\n  Displacement quantization (% of moved vertices on grid):")
        for gs in [1, 5, 10, 25, 50, 100]:
            on_grid = sum(1 for d in moved_mm if abs(round(d / gs) * gs - d) < 0.01)
            print(f"    {gs:>5d} mm grid: {on_grid}/{len(moved)} = {pct(on_grid, len(moved))}")

    # =====================================================================
    # 3. AFTER VALUE FREQUENCY ANALYSIS
    # =====================================================================
    section("3. MOST FREQUENT AFTER COORDINATE VALUES")

    for ai, axis in enumerate(AXES):
        print(f"\n--- Axis {axis} ---")
        vals_mm = np.round(after_coords[:, ai] * 1000, 1)
        counts = Counter(vals_mm)
        print(f"  Unique values: {len(counts)}")
        print(f"  Top 20 most frequent:")
        for val, cnt in counts.most_common(20):
            print(f"    {val:>12.1f} mm  ({val/1000:.4f} m): {cnt} vertices")

    # =====================================================================
    # 4. BEFORE VALUE ANALYSIS
    # =====================================================================
    section("4. BEFORE VALUE GRID ANALYSIS")
    print("Are 'before' values already on some grid?\n")

    for ai, axis in enumerate(AXES):
        print(f"--- Axis {axis} ---")
        vals = before_coords[:, ai]
        for gs in GRID_SIZES_MM:
            count = sum(1 for v in vals if is_multiple(v, gs))
            print(f"  Grid {gs:>5d} mm: {count:>6d}/{n} = {pct(count, n)}")
        print()

    # =====================================================================
    # 5. ROUNDING RULE DETECTION
    # =====================================================================
    section("5. ROUNDING RULE DETECTION")
    print("For each vertex that moved, test: after == round(before / grid) * grid\n")

    for ai, axis in enumerate(AXES):
        print(f"--- Axis {axis} ---")
        moved_mask = np.abs(deltas[:, ai]) > 1e-9
        n_moved = np.sum(moved_mask)
        if n_moved == 0:
            print("  No moved vertices.")
            continue

        b_vals = before_coords[moved_mask, ai]
        a_vals = after_coords[moved_mask, ai]

        for gs in GRID_SIZES_MM:
            grid_m = gs / 1000.0
            predicted = np.round(b_vals / grid_m) * grid_m
            matches = np.sum(np.abs(predicted - a_vals) < 1e-6)
            print(f"  round(before/{gs}mm)*{gs}mm: {matches}/{n_moved} = {pct(matches, int(n_moved))}")

        # Also test floor and ceil
        print(f"\n  Floor/Ceil tests (best grid candidates):")
        for gs in [5, 10, 25, 50, 100]:
            grid_m = gs / 1000.0
            pred_floor = np.floor(b_vals / grid_m) * grid_m
            pred_ceil = np.ceil(b_vals / grid_m) * grid_m
            pred_round = np.round(b_vals / grid_m) * grid_m
            m_floor = int(np.sum(np.abs(pred_floor - a_vals) < 1e-6))
            m_ceil = int(np.sum(np.abs(pred_ceil - a_vals) < 1e-6))
            m_round = int(np.sum(np.abs(pred_round - a_vals) < 1e-6))
            print(f"    {gs:>4d}mm - floor: {m_floor}, ceil: {m_ceil}, round: {m_round} / {n_moved}")
        print()

    # =====================================================================
    # 6. Z-AXIS LEVEL DETECTION
    # =====================================================================
    section("6. Z-AXIS LEVEL DETECTION")
    print("Z values often represent floor levels. Checking for level clustering.\n")

    z_after = after_coords[:, 2]
    z_before = before_coords[:, 2]

    z_after_mm = np.round(z_after * 1000, 1)
    z_after_unique = sorted(set(z_after_mm))
    print(f"Unique Z values in 'after' (rounded to 0.1mm): {len(z_after_unique)}")

    z_counts = Counter(z_after_mm)
    print(f"\nTop 30 Z levels in 'after':")
    for val, cnt in z_counts.most_common(30):
        print(f"  Z = {val:>10.1f} mm  ({val/1000:.4f} m): {cnt} vertices")

    # Check if Z after values are on regular spacing
    if len(z_after_unique) > 1:
        spacings = np.diff(z_after_unique)
        spacing_counts = Counter(np.round(spacings, 1))
        print(f"\nZ level spacings (mm):")
        for sp, cnt in spacing_counts.most_common(20):
            print(f"  {sp:>10.1f} mm: {cnt} occurrences")

    # Z before values
    z_before_mm = np.round(z_before * 1000, 1)
    z_before_counts = Counter(z_before_mm)
    print(f"\nTop 20 Z levels in 'before':")
    for val, cnt in z_before_counts.most_common(20):
        print(f"  Z = {val:>10.1f} mm  ({val/1000:.4f} m): {cnt} vertices")

    # =====================================================================
    # 7. PER-ELEMENT-TYPE ANALYSIS
    # =====================================================================
    section("7. PER-ELEMENT-TYPE ANALYSIS")

    cat_set = sorted(set(categories))
    print(f"Categories found: {cat_set}\n")

    for cat in cat_set:
        mask = np.array([c == cat for c in categories])
        n_cat = np.sum(mask)
        if n_cat == 0:
            continue

        cat_deltas = deltas[mask]
        cat_after = after_coords[mask]
        cat_before = before_coords[mask]

        print(f"--- {cat.upper()} ({n_cat} vertices) ---")
        for ai, axis in enumerate(AXES):
            d = cat_deltas[:, ai]
            moved = np.abs(d) > 1e-9
            n_moved = np.sum(moved)
            print(f"  {axis}: {n_moved}/{n_cat} moved", end="")
            if n_moved > 0:
                print(f", mean delta={np.mean(d[moved]):.4f}m, "
                      f"range=[{np.min(d[moved]):.4f}, {np.max(d[moved]):.4f}]", end="")
            print()

        # Grid snapping per category (after values)
        print(f"  After-value grid snapping:")
        for gs in [10, 50, 100]:
            for ai, axis in enumerate(AXES):
                vals = cat_after[:, ai]
                count = sum(1 for v in vals if is_multiple(v, gs))
                print(f"    {axis} @ {gs}mm: {count}/{n_cat} = {pct(count, int(n_cat))}", end="  ")
            print()

        # Rounding rule per category
        print(f"  Rounding rule match (round(before/grid)*grid == after):")
        for gs in [10, 50, 100]:
            grid_m = gs / 1000.0
            for ai, axis in enumerate(AXES):
                moved_mask_cat = np.abs(cat_deltas[:, ai]) > 1e-9
                n_m = int(np.sum(moved_mask_cat))
                if n_m == 0:
                    print(f"    {axis} @ {gs}mm: 0/0", end="  ")
                    continue
                b = cat_before[moved_mask_cat, ai]
                a = cat_after[moved_mask_cat, ai]
                pred = np.round(b / grid_m) * grid_m
                matches = int(np.sum(np.abs(pred - a) < 1e-6))
                print(f"    {axis} @ {gs}mm: {matches}/{n_m} = {pct(matches, n_m)}", end="  ")
            print()
        print()

    # =====================================================================
    # 8. SIGN/DIRECTION ANALYSIS
    # =====================================================================
    section("8. SIGN AND DIRECTION ANALYSIS")

    for ai, axis in enumerate(AXES):
        print(f"\n--- Axis {axis} ---")
        d = deltas[:, ai]
        moved = np.abs(d) > 1e-9
        positive = np.sum(d[moved] > 0)
        negative = np.sum(d[moved] < 0)
        print(f"  Positive displacements: {positive}")
        print(f"  Negative displacements: {negative}")

        # Sign changes: before and after have different signs
        b = before_coords[:, ai]
        a = after_coords[:, ai]
        sign_change = np.sum((b > 1e-9) & (a < -1e-9) | (b < -1e-9) & (a > 1e-9))
        print(f"  Sign changes (before>0 -> after<0 or vice versa): {sign_change}")

        # Reflections: after == -before?
        reflections = np.sum(np.abs(a + b) < 1e-6)
        print(f"  Exact reflections (after == -before): {reflections}")

    # Check for any coordinate swaps
    print(f"\n--- Coordinate swap detection ---")
    for ai, bi in [(0, 1), (0, 2), (1, 2)]:
        swap_count = np.sum(
            (np.abs(after_coords[:, ai] - before_coords[:, bi]) < 1e-6) &
            (np.abs(after_coords[:, bi] - before_coords[:, ai]) < 1e-6) &
            (np.abs(deltas[:, ai]) > 1e-9)
        )
        print(f"  {AXES[ai]}<->{AXES[bi]} swap: {swap_count} vertices")

    # =====================================================================
    # 9. UNCHANGED VERTICES
    # =====================================================================
    section("9. UNCHANGED VERTICES")

    dist = np.sqrt(np.sum(deltas ** 2, axis=1))
    unchanged = dist < 1e-9
    n_unchanged = np.sum(unchanged)
    n_changed = n - n_unchanged

    print(f"Total matched vertices: {n}")
    print(f"Unchanged (distance < 1e-9): {n_unchanged} ({pct(n_unchanged, n)})")
    print(f"Changed:                     {n_changed} ({pct(n_changed, n)})")

    if n_unchanged > 0:
        unchanged_cats = Counter(np.array(categories)[unchanged])
        print(f"\nUnchanged by category:")
        for cat, cnt in unchanged_cats.most_common():
            total_cat = sum(1 for c in categories if c == cat)
            print(f"  {cat}: {cnt}/{total_cat} = {pct(cnt, total_cat)}")

    if n_changed > 0:
        changed_cats = Counter(np.array(categories)[~unchanged])
        print(f"\nChanged by category:")
        for cat, cnt in changed_cats.most_common():
            total_cat = sum(1 for c in categories if c == cat)
            print(f"  {cat}: {cnt}/{total_cat} = {pct(cnt, total_cat)}")

    # Distance distribution for changed vertices
    changed_dist = dist[~unchanged]
    print(f"\nDisplacement magnitude for changed vertices:")
    print(f"  Min:    {np.min(changed_dist):.6f} m ({np.min(changed_dist)*1000:.3f} mm)")
    print(f"  Max:    {np.max(changed_dist):.6f} m ({np.max(changed_dist)*1000:.3f} mm)")
    print(f"  Mean:   {np.mean(changed_dist):.6f} m ({np.mean(changed_dist)*1000:.3f} mm)")
    print(f"  Median: {np.median(changed_dist):.6f} m ({np.median(changed_dist)*1000:.3f} mm)")

    # Histogram of displacement magnitudes
    print(f"\nDisplacement magnitude histogram:")
    thresholds = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0]
    for t in thresholds:
        count = np.sum(changed_dist <= t)
        print(f"  <= {t*1000:>7.1f} mm: {count}/{len(changed_dist)} = {pct(count, len(changed_dist))}")

    # =====================================================================
    # 10. SUMMARY / KEY FINDINGS
    # =====================================================================
    section("10. RAW DATA SAMPLE (first 20 moved vertices)")

    moved_indices = np.where(~unchanged)[0][:20]
    print(f"{'Name':<30} {'VIdx':>4} {'Cat':<10} "
          f"{'BX':>10} {'BY':>10} {'BZ':>10} "
          f"{'AX':>10} {'AY':>10} {'AZ':>10} "
          f"{'dX':>10} {'dY':>10} {'dZ':>10}")
    print("-" * 160)
    for idx in moved_indices:
        k = common_keys[idx]
        b = before_idx[k]
        a = after_idx[k]
        d = deltas[idx]
        print(f"{k[0]:<30} {k[1]:>4} {b.category:<10} "
              f"{b.x:>10.4f} {b.y:>10.4f} {b.z:>10.4f} "
              f"{a.x:>10.4f} {a.y:>10.4f} {a.z:>10.4f} "
              f"{d[0]:>10.4f} {d[1]:>10.4f} {d[2]:>10.4f}")

    print("\n" + "=" * 80)
    print("  END OF ANALYSIS")
    print("=" * 80)


if __name__ == "__main__":
    main()
