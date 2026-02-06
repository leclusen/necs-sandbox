#!/usr/bin/env python3
"""Compare vertices between two Rhino .3dm files.

Loads both files with rhino3dm (via structure_aligner.etl.extractor),
matches vertices by object name + vertex_index, and prints displacement
statistics to help understand the transformation from one file to another.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np

from structure_aligner.etl.extractor import ExtractionResult, RawVertex, extract_vertices


@dataclass(frozen=True)
class VertexKey:
    """Key used for matching vertices across files."""
    name: str
    vertex_index: int


def load_vertices(path: Path) -> ExtractionResult:
    result = extract_vertices(path)
    print(
        f"[load] {path.name}: {len(result.vertices)} vertices, "
        f"{len({v.element_name for v in result.vertices})} named objects, "
        f"{result.total_objects} total objects"
    )
    if result.skipped_objects:
        print(f"[load]   skipped {len(result.skipped_objects)} unsupported/unnamed objects")
    return result


def build_index(vertices: Iterable[RawVertex]) -> tuple[dict[VertexKey, RawVertex], dict[VertexKey, list[RawVertex]]]:
    index: dict[VertexKey, RawVertex] = {}
    collisions: defaultdict[VertexKey, list[RawVertex]] = defaultdict(list)
    for v in vertices:
        key = VertexKey(v.element_name, v.vertex_index)
        if key in index:
            collisions[key].append(v)
        else:
            index[key] = v
    return index, collisions


def displacement_summary(deltas: np.ndarray) -> str:
    """Return a compact multi-line summary for displacement vectors."""
    if deltas.size == 0:
        return "no matching vertices"

    summary = []
    axes = ["X", "Y", "Z"]
    abs_deltas = np.abs(deltas)
    for i, axis in enumerate(axes):
        axis_vals = deltas[:, i]
        abs_vals = abs_deltas[:, i]
        changed = np.count_nonzero(abs_vals > 1e-9)
        summary.append(
            f"  {axis}: changed {changed}/{len(axis_vals)}; "
            f"median {np.median(axis_vals):.4f}, mean {np.mean(axis_vals):.4f}, "
            f"min {np.min(axis_vals):.4f}, max {np.max(axis_vals):.4f}; "
            f"abs max {np.max(abs_vals):.4f}"
        )
    return "\n".join(summary)


def top_patterns(deltas: np.ndarray, round_to: int = 4, limit: int = 10) -> list[tuple[Tuple[float, float, float], int]]:
    """Most common displacement vectors, rounded for grouping."""
    if deltas.size == 0:
        return []
    rounded = [tuple(np.round(vec, round_to)) for vec in deltas]
    counts = Counter(rounded)
    return counts.most_common(limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare vertices between two .3dm files.")
    parser.add_argument("--before", type=Path, default=Path("data/input/before.3dm"))
    parser.add_argument("--after", type=Path, default=Path("data/input/after.3dm"))
    parser.add_argument("--round", type=int, default=4, help="Decimal places for grouping displacement patterns")
    args = parser.parse_args()

    before = load_vertices(args.before)
    after = load_vertices(args.after)

    idx_before, collisions_before = build_index(before.vertices)
    idx_after, collisions_after = build_index(after.vertices)

    if collisions_before:
        print(f"[warn] {len(collisions_before)} duplicate keys in BEFORE (name + vertex_index)")
    if collisions_after:
        print(f"[warn] {len(collisions_after)} duplicate keys in AFTER (name + vertex_index)")

    keys_before = set(idx_before.keys())
    keys_after = set(idx_after.keys())

    common = sorted(keys_before & keys_after, key=lambda k: (k.name, k.vertex_index))
    only_before = sorted(keys_before - keys_after, key=lambda k: (k.name, k.vertex_index))
    only_after = sorted(keys_after - keys_before, key=lambda k: (k.name, k.vertex_index))

    print(f"[match] common vertices: {len(common)}")
    print(f"[match] only in BEFORE: {len(only_before)}")
    print(f"[match] only in AFTER:  {len(only_after)}")

    if only_before:
        sample = ", ".join(f"{k.name}[{k.vertex_index}]" for k in only_before[:10])
        print(f"        sample BEFORE-only: {sample}")
    if only_after:
        sample = ", ".join(f"{k.name}[{k.vertex_index}]" for k in only_after[:10])
        print(f"        sample AFTER-only:  {sample}")

    deltas = []
    for key in common:
        b = idx_before[key]
        a = idx_after[key]
        deltas.append([a.x - b.x, a.y - b.y, a.z - b.z])
    deltas_np = np.array(deltas)

    print("[delta] displacement statistics (signed, meters):")
    print(displacement_summary(deltas_np))

    patterns = top_patterns(deltas_np, round_to=args.round, limit=15)
    if patterns:
        print(f"[delta] top displacement patterns (rounded to {args.round} dp):")
        for vec, count in patterns:
            print(f"  {vec}: {count}")

    for axis, idx in (("X", 0), ("Y", 1), ("Z", 2)):
        axis_vals = deltas_np[:, idx] if deltas_np.size else np.array([])
        changed = axis_vals[np.abs(axis_vals) > 1e-9]
        unique_changes = np.unique(np.round(changed, args.round)) if changed.size else []
        print(
            f"[delta] axis {axis}: {len(changed)} changed; "
            f"{len(unique_changes)} unique displacements (rounded) -> {unique_changes[:15]}"
        )


if __name__ == "__main__":
    main()
