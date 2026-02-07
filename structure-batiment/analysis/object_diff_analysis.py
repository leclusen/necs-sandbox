#!/usr/bin/env python3
"""Analyze removed/added objects and line->polyline conversions between before/after 3dm."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import sqlite3

import numpy as np
import rhino3dm

BEFORE = Path("data/input/before.3dm")
AFTER = Path("data/input/after.3dm")
DB = Path("data/input/geometrie_2.db")


@dataclass
class ObjInfo:
    name: str
    geom_type: str
    bbox: tuple[float, float, float, float, float, float]
    center: tuple[float, float, float]
    layer: str


def load_model(path: Path):
    model = rhino3dm.File3dm.Read(str(path))
    if model is None:
        raise RuntimeError(f"Failed to read {path}")
    # Map layer id -> layer
    layer_by_id = {str(l.Id): l for l in model.Layers}

    def resolve_category(layer: rhino3dm.Layer):
        current = layer
        null_id = "00000000-0000-0000-0000-000000000000"
        while str(current.ParentLayerId) != null_id and str(current.ParentLayerId) in layer_by_id:
            current = layer_by_id[str(current.ParentLayerId)]
        return current.Name

    objs = {}
    for obj in model.Objects:
        nm = obj.Attributes.Name
        if not nm:
            continue
        geom = obj.Geometry
        gtype = type(geom).__name__
        bbox = geom.GetBoundingBox()
        bb_tuple = (bbox.Min.X, bbox.Min.Y, bbox.Min.Z, bbox.Max.X, bbox.Max.Y, bbox.Max.Z)
        center = ((bbox.Min.X + bbox.Max.X) / 2, (bbox.Min.Y + bbox.Max.Y) / 2, (bbox.Min.Z + bbox.Max.Z) / 2)
        layer = resolve_category(model.Layers[obj.Attributes.LayerIndex])
        objs[nm] = ObjInfo(nm, gtype, bb_tuple, center, layer)
    return objs


def load_shell_props(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("select name, type, thickness, cover_top, cover_bottom, material_id, modeling from shell")
    props = {row[0]: row[1:] for row in cur.fetchall()}
    conn.close()
    return props


def summarize_bbox(objs):
    dx = []
    dy = []
    dz = []
    zmin = []
    zmax = []
    centers_z = []
    for o in objs:
        xmin, ymin, z0, xmax, ymax, z1 = o.bbox
        dx.append(xmax - xmin)
        dy.append(ymax - ymin)
        dz.append(z1 - z0)
        zmin.append(z0)
        zmax.append(z1)
        centers_z.append(o.center[2])
    def stats(arr):
        return (float(np.min(arr)), float(np.max(arr)), float(np.median(arr)), float(np.mean(arr))) if arr else (0,0,0,0)
    return {
        'dx': stats(dx),
        'dy': stats(dy),
        'dz': stats(dz),
        'zmin': stats(zmin),
        'zmax': stats(zmax),
        'cz': stats(centers_z),
    }


def histogram_levels(values, round_mm=1.0, top=12):
    vals_mm = np.round(np.array(values) * 1000 / round_mm) * round_mm
    cnt = Counter(vals_mm)
    return cnt.most_common(top)


def analyze():
    before = load_model(BEFORE)
    after = load_model(AFTER)
    shell_props = load_shell_props(DB)

    before_names = set(before)
    after_names = set(after)

    removed_names = sorted(before_names - after_names)
    added_names = sorted(after_names - before_names)
    common = before_names & after_names

    removed = [before[n] for n in removed_names]
    added = [after[n] for n in added_names]

    print(f"Removed objects: {len(removed)} (expected ~320)")
    print(f"Added objects:   {len(added)} (expected ~476)")

    # Removed summary
    print("\n=== Removed ===")
    print("By layer:", Counter(o.layer for o in removed).most_common())
    print("By geom type:", Counter(o.geom_type for o in removed).most_common())
    stats = summarize_bbox(removed)
    print("BBox stats (min, max, median, mean):")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    zmins = [o.bbox[2] for o in removed]
    print("Top Z-min levels (mm):", histogram_levels(zmins))
    zmids = [o.center[2] for o in removed]
    print("Top center Z levels (mm):", histogram_levels(zmids))

    # Shell property join
    matched = [o for o in removed if o.name.split('[')[0] in shell_props or o.name in shell_props]
    matched_names = []
    for o in removed:
        key = o.name.split('[')[0]
        if key in shell_props:
            matched_names.append(key)
    print(f"Shell-table matches: {len(set(matched_names))}/{len(removed)}")
    shell_types = Counter()
    thicknesses = []
    modeling = Counter()
    for n in set(matched_names):
        t, thick, cover_t, cover_b, mat, mod = shell_props[n]
        shell_types[t] += 1
        thicknesses.append(thick)
        modeling[mod] += 1
    print("Shell types:", shell_types.most_common())
    if thicknesses:
        print(f"Thickness min/med/max: {min(thicknesses):.4f}/{np.median(thicknesses):.4f}/{max(thicknesses):.4f} m")
    print("Modeling modes:", modeling.most_common())

    # Added summary
    print("\n=== Added ===")
    print("By layer:", Counter(o.layer for o in added).most_common())
    print("By geom type:", Counter(o.geom_type for o in added).most_common())
    stats_a = summarize_bbox(added)
    print("BBox stats (min, max, median, mean):")
    for k, v in stats_a.items():
        print(f"  {k}: {v}")
    zmins_a = [o.bbox[2] for o in added]
    print("Top Z-min levels (mm):", histogram_levels(zmins_a))
    zmids_a = [o.center[2] for o in added]
    print("Top center Z levels (mm):", histogram_levels(zmids_a))

    # Placement heuristic: XY positions rounded to 1mm
    xy_round = lambda o: (round(o.center[0], 3), round(o.center[1], 3))
    xy_counts = Counter(xy_round(o) for o in added)
    duplicates = [item for item, c in xy_counts.items() if c > 1]
    print(f"Repeated XY centers (rounded 1mm): {len(duplicates)} occurrences with >1 objects")

    # Added supports vs columns: nearest XY distance to any Poteau center in AFTER
    poteaux_after = [o for o in after.values() if o.layer == "Poteau"]
    poteau_xy = np.array([[p.center[0], p.center[1]] for p in poteaux_after]) if poteaux_after else np.empty((0, 2))
    appuis_added = [o for o in added if o.layer == "Appuis"]
    if len(poteau_xy) > 0 and appuis_added:
        dists = []
        for a in appuis_added:
            diff = poteau_xy - np.array([[a.center[0], a.center[1]]])
            norm = np.sqrt(np.sum(diff**2, axis=1))
            dists.append(float(np.min(norm)))
        print("Nearest XY distance from added Appuis to any Poteau (m):")
        print(f"  min/med/max/mean = {min(dists):.4f}/{np.median(dists):.4f}/{max(dists):.4f}/{np.mean(dists):.4f}")
        for thr in [0.05, 0.10, 0.20, 0.50]:
            pct = sum(d <= thr for d in dists) / len(dists) * 100
            print(f"  within {thr:.2f} m: {pct:5.1f}% ({sum(d <= thr for d in dists)}/{len(dists)})")

    # Removed vs added shells: XY displacement between centers of nearest shell replacement
    removed_shells = [o for o in removed if o.layer in ("Dalle", "Voile")]
    added_shells = [o for o in added if o.layer in ("Dalle", "Voile")]
    if removed_shells and added_shells:
        added_xy = np.array([[s.center[0], s.center[1]] for s in added_shells])
        disps = []
        for r in removed_shells:
            diff = added_xy - np.array([[r.center[0], r.center[1]]])
            norm = np.sqrt(np.sum(diff**2, axis=1))
            disps.append(float(np.min(norm)))
        print("Nearest XY distance from removed shells to any added shell (m):")
        print(f"  min/med/max/mean = {min(disps):.4f}/{np.median(disps):.4f}/{max(disps):.4f}/{np.mean(disps):.4f}")
        for thr in [0.05, 0.10, 0.25, 0.50]:
            pct = sum(d <= thr for d in disps) / len(disps) * 100
            print(f"  within {thr:.2f} m: {pct:5.1f}% ({sum(d <= thr for d in disps)}/{len(disps)})")

    # Line->polyline conversions among common names
    print("\n=== LineCurve -> PolylineCurve conversions ===")
    conversions = []
    for n in common:
        gt_b = before[n].geom_type
        gt_a = after[n].geom_type
        if gt_b == "LineCurve" and gt_a == "PolylineCurve":
            # count points in polyline
            # reopen geometries for counts
            conversions.append(n)
    print(f"Found {len(conversions)} conversions (expected 912)")

    if conversions:
        # Need fresh access to geometry to count points
        model_before = rhino3dm.File3dm.Read(str(BEFORE))
        model_after = rhino3dm.File3dm.Read(str(AFTER))
        obj_map_before = {obj.Attributes.Name: obj.Geometry for obj in model_before.Objects if obj.Attributes.Name}
        obj_map_after = {obj.Attributes.Name: obj.Geometry for obj in model_after.Objects if obj.Attributes.Name}

        more_than_two = 0
        point_counts = []
        for n in conversions:
            poly = obj_map_after[n]
            pc = poly.PointCount
            point_counts.append(pc)
            if pc > 2:
                more_than_two += 1
        pc_counter = Counter(point_counts)
        print("Polyline point counts (after):", pc_counter.most_common())
        print(f"With >2 points: {more_than_two}/{len(conversions)}")


if __name__ == "__main__":
    analyze()
