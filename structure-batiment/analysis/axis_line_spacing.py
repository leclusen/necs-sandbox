#!/usr/bin/env python3
"""Axis-line spacing and recoverability study for before/after 3DM files.

Outputs:
- Unique X/Y positions in *after* and spacing histograms.
- Overlap of after axis lines with *before* positions at several tolerances.
- Attempts to recover after axis lines from *before* using:
  * DBSCAN (same alpha/min_samples as alignment config)
  * Histogram peak picking
  * Mode detection via grid-rounded values

This is meant to answer: can the after axis lines be derived from before data?
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

import numpy as np
from sklearn.cluster import DBSCAN

from structure_aligner.config import AlignmentConfig
from structure_aligner.etl.extractor import extract_vertices


BEFORE = Path("data/input/before.3dm")
AFTER = Path("data/input/after.3dm")

# Alpha/min_samples mirror the pipeline defaults
CFG = AlignmentConfig()


def unique_sorted(values: np.ndarray, round_to: int = 6) -> np.ndarray:
    """Return sorted unique values rounded to the requested decimals."""
    return np.sort(np.unique(np.round(values, round_to)))


def spacing_report(axis: str, axis_values: np.ndarray):
    uniq = unique_sorted(axis_values)
    spacings = np.diff(uniq)
    print(f"\n[axis {axis}] unique lines: {len(uniq)}")
    print(
        f"  spacing -> min {np.min(spacings):.4f} m, max {np.max(spacings):.4f} m, "
        f"median {np.median(spacings):.4f} m, mean {np.mean(spacings):.4f} m"
    )

    # Histogram of spacings (rounded to 1 mm)
    spacing_mm = np.round(spacings * 1000, 1)
    counts = Counter(spacing_mm)
    print("  top spacing frequencies (mm):")
    for val, cnt in counts.most_common(15):
        pct = 100 * cnt / len(spacing_mm)
        print(f"    {val:>8.1f} mm : {cnt:>4d} ({pct:5.1f}%)")


def overlap(after_lines: np.ndarray, before_lines: np.ndarray, tol: float) -> tuple[int, list[float]]:
    """Count after lines that have a before line within tol (abs diff)."""
    unmatched = []
    matched = 0
    for a in after_lines:
        if np.any(np.abs(before_lines - a) <= tol):
            matched += 1
        else:
            unmatched.append(float(a))
    return matched, unmatched


def dbscan_centers(values: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit(values.reshape(-1, 1)).labels_
    centers = []
    for lab in sorted(set(labels)):
        if lab == -1:
            continue
        cluster_vals = values[labels == lab]
        centers.append(np.mean(cluster_vals))
    return np.sort(np.array(centers))


def histogram_peaks(values: np.ndarray, bin_width: float, min_count: int = 5) -> np.ndarray:
    """Pick local maxima from a fixed-width histogram."""
    lo, hi = float(np.min(values)), float(np.max(values))
    bins = np.arange(lo - bin_width, hi + bin_width * 2, bin_width)
    hist, edges = np.histogram(values, bins=bins)
    peaks = []
    for i, count in enumerate(hist):
        if count < min_count:
            continue
        prev_c = hist[i - 1] if i > 0 else -1
        next_c = hist[i + 1] if i + 1 < len(hist) else -1
        if count >= prev_c and count >= next_c:
            center = (edges[i] + edges[i + 1]) / 2
            peaks.append(center)
    return np.sort(np.array(peaks))


def rounded_modes(values: np.ndarray, grid_sizes: Iterable[float], min_count: int = 3) -> dict[float, np.ndarray]:
    """Return mode positions for several grid sizes."""
    modes: dict[float, np.ndarray] = {}
    for g in grid_sizes:
        rounded = np.round(values / g) * g
        counts = Counter(np.round(rounded, 6))
        modes[g] = np.sort(np.array([k for k, v in counts.items() if v >= min_count], dtype=float))
    return modes


def coverage(label: str, after_lines: np.ndarray, predicted: np.ndarray, tol: float):
    matched = sum(1 for a in after_lines if np.any(np.abs(predicted - a) <= tol))
    print(f"  {label:<20} matched {matched}/{len(after_lines)} ({100*matched/len(after_lines):.1f}%) within ±{tol:.3f} m")


def main():
    before = extract_vertices(BEFORE).vertices
    after = extract_vertices(AFTER).vertices

    before_x = np.array([v.x for v in before])
    before_y = np.array([v.y for v in before])
    after_x = np.array([v.x for v in after])
    after_y = np.array([v.y for v in after])

    after_x_lines = unique_sorted(after_x)
    after_y_lines = unique_sorted(after_y)
    before_x_lines = unique_sorted(before_x)
    before_y_lines = unique_sorted(before_y)

    print("AFTER axis-line spacing analysis")
    spacing_report("X", after_x)
    spacing_report("Y", after_y)

    # Direct overlap checks
    print("\nOverlap of after lines with before positions")
    for tol in [0.0005, 0.001, 0.005, 0.01, 0.05]:
        mx, missing_x = overlap(after_x_lines, before_x_lines, tol)
        my, missing_y = overlap(after_y_lines, before_y_lines, tol)
        print(f"  tol={tol:.4f} m -> X matched {mx}/{len(after_x_lines)}, Y matched {my}/{len(after_y_lines)}")

    # DBSCAN-based recovery (pipeline default alpha)
    print("\nAttempted recovery of after lines from BEFORE data")
    centers_x = dbscan_centers(before_x, eps=CFG.alpha, min_samples=CFG.min_cluster_size)
    centers_y = dbscan_centers(before_y, eps=CFG.alpha, min_samples=CFG.min_cluster_size)
    coverage("DBSCAN (alpha=0.05)", after_x_lines, centers_x, tol=0.01)
    coverage("DBSCAN (alpha=0.05)", after_y_lines, centers_y, tol=0.01)

    # Histogram peak picking
    for bw in [0.02, 0.05, 0.10]:
        peaks_x = histogram_peaks(before_x, bin_width=bw)
        peaks_y = histogram_peaks(before_y, bin_width=bw)
        coverage(f"Hist peaks bw={bw:.02f}", after_x_lines, peaks_x, tol=0.01)
        coverage(f"Hist peaks bw={bw:.02f}", after_y_lines, peaks_y, tol=0.01)

    # Mode detection via rounded grids
    grids = [0.01, 0.025, 0.05, 0.10, 0.20]
    mode_map_x = rounded_modes(before_x, grids)
    mode_map_y = rounded_modes(before_y, grids)
    for g in grids:
        coverage(f"Round modes g={g:.3f}", after_x_lines, mode_map_x[g], tol=0.01)
        coverage(f"Round modes g={g:.3f}", after_y_lines, mode_map_y[g], tol=0.01)

    # Explicit list of after X lines that never show up in before (tight tol)
    missing_x = [a for a in after_x_lines if not np.any(np.abs(before_x_lines - a) <= 0.0005)]
    print(f"\nAfter X lines without any before match within 0.5mm: {len(missing_x)}")
    print("  sample:", np.round(missing_x[:30], 4))


if __name__ == "__main__":
    main()
