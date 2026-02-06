---
date: 2026-02-05T00:24:07Z
researcher: Claude Code
git_commit: not-a-git-repo
branch: no-branch
repository: necs
topic: "Analysis of geometrie_2.db and geometrie_2.3dm - PRD Alignment"
tags: [research, database, sqlite, rhino3dm, geometric-alignment, building-structures, schema-analysis, vertex-extraction]
status: complete
last_updated: 2026-02-05
last_updated_by: Claude Code
last_updated_note: "Added rhino3dm exploration of .3dm file with full vertex extraction and cross-reference with .db"
---

# Research: geometrie_2.3dm + geometrie_2.db Analysis for PRD

**Date**: 2026-02-05T16:36:51Z
**Researcher**: Claude Code
**Git Commit**: not-a-git-repo
**Branch**: no-branch
**Repository**: necs

## Research Question

Using the `rhino3dm` Python library, explore the `geometrie_2.3dm` file and compare its contents with the `geometrie_2.db` database. Determine what can be done in relation to the PRD for the geometric alignment software.

## Summary

The `.3dm` file and `.db` database are **companion files with a near-perfect 1:1 mapping** (5,824/5,825 matching names). The `.3dm` file stores the actual 3D geometry (coordinates) while the `.db` stores structural metadata (materials, sections, boundary conditions). Together they contain **20,996 vertices** across 5,825 elements representing a multi-story building (~119m x 119m footprint, ~42m tall, 13 floor levels).

**Key findings:**
- The geometry types are simple: **LineCurves** (poteaux/poutres), **Breps** (voiles/dalles), **Points** (supports)
- Z-axis has only **13 unique values** (floor levels) - ideal for alignment threads
- X and Y have **1,439 and 1,592 unique values** respectively - the core alignment challenge
- **Linkage is by name**: `Filaire_1` in 3dm = `Filaire_1` in db, `Coque_1534` in 3dm = `Coque_1534` in db
- Coordinates are in **meters** (consistent with PRD expectations)

---

## Detailed Findings

### 1. File Pair Overview

| Property | geometrie_2.3dm | geometrie_2.db |
|----------|----------------|----------------|
| **Size** | 49.4 MB | 952 KB |
| **Format** | Rhino 3D Model | SQLite 3 |
| **Objects** | 5,825 | 5,825 elements |
| **Layers** | 7,753 | 17 tables |
| **Stores** | 3D geometry (coordinates) | Structural metadata (properties) |
| **Library** | `rhino3dm` 8.17.0 | `sqlite3` |

---

### 2. 3DM File Structure

#### Object Geometry Types

| Category | Object Count | Geometry Type | Vertices/Object |
|----------|-------------|---------------|-----------------|
| **Voile** (walls) | 2,669 | Brep | avg 4.1 (min 4, max 26) |
| **Poteau** (columns) | 1,527 | LineCurve | 2 (start + end) |
| **Poutre** (beams) | 1,192 | LineCurve (1,032) / PolylineCurve (157) / NurbsCurve (3) | avg 2.0 (min 2, max 7) |
| **Dalle** (slabs) | 284 | Brep | avg 15.5 (min 4, max 242) |
| **Appuis** (supports) | 153 | Point (131) / LineCurve (22) | avg 1.1 (min 1, max 2) |
| **Total** | **5,825** | - | **20,996 total vertices** |

#### Layer Hierarchy

The 3dm uses a 2-level hierarchy:

```
Top-Level Categories (parent layers)
├── Poteau      -> 1,531 child layers (one per element: Filaire_1, Filaire_2, ...)
├── Voile       -> 3,947 child layers (one per element: Coque_1530, Coque_1531, ...)
├── Poutre      -> 1,294 child layers (Filaire_6266, Filaire_6269, ...)
├── Dalle       ->   813 child layers (Coque_1529, Coque_1654, ...)
├── Appuis      ->   156 child layers (Appuis_6233, Appuis_6234, ...)
├── Défaut      ->     0 children
├── Calque 01-05 ->   0 children
└── 2D          ->     0 children
```

**Note**: Layer count > object count because some layers exist for organizational purposes without geometry.

---

### 3. Vertex Coordinates Analysis

#### Coordinate Ranges (20,996 vertices)

| Axis | Min | Max | Range | Mean | Median | Stdev |
|------|-----|-----|-------|------|--------|-------|
| **X** | -72.175 | 46.800 | 118.98m | -10.766 | -9.330 | 36.687 |
| **Y** | -88.150 | 31.250 | 119.40m | -17.556 | -14.845 | 30.825 |
| **Z** | -4.440 | 37.210 | 41.65m | 14.636 | 13.320 | 10.894 |

#### Z-Axis: 13 Floor Levels (Perfect Alignment Threads)

| Z Value (m) | Vertex Count | Interpretation |
|-------------|-------------|----------------|
| -4.44 | 620 | Foundation / basement |
| -1.56 | 893 | Sub-level |
| 2.12 | 2,697 | Ground floor |
| 5.48 | 2,262 | Level 1 |
| 8.20 | 2,522 | Level 2 |
| 13.32 | 2,443 | Level 3 |
| 17.78 | 1 | Isolated vertex |
| 17.96 | 2,130 | Level 4 |
| 22.12 | 2,093 | Level 5 |
| 26.28 | 2,216 | Level 6 |
| 29.64 | 1,750 | Level 7 |
| 32.36 | 1,136 | Level 8 |
| 37.21 | 233 | Roof |

**Observation**: Z-axis is already naturally clustered. The PRD's DBSCAN algorithm will detect these 13 floor levels as alignment threads with almost zero displacement needed (except possibly the 1 vertex at Z=17.78).

#### X and Y Axis: Unique Values (rounded to cm)

| Axis | Unique Values | Alignment Challenge |
|------|--------------|---------------------|
| **X** | 1,439 | High - many structural grid lines to detect |
| **Y** | 1,592 | High - many structural grid lines to detect |
| **Z** | 13 | Low - already naturally aligned |

---

### 4. Geometry Details by Type

#### Poteau (Column) - LineCurve
```
3DM Filaire_1:
  Start: (37.5000, 22.5000, -4.4400)   <- Bottom of column
  End:   (37.5000, 22.5000, -1.5600)   <- Top of column

DB Filaire_1:
  type: POTEAU, section_id: 36197, modeling: TIMOSHENKO
  y_local: "1, 0, 0", articulation: "111111_111111"
```
Columns are vertical lines (same X,Y - different Z). The PRD alignment only needs to snap X and Y coordinates.

#### Voile (Wall) - Brep
```
3DM Coque_1534 (4 vertices):
  V[0]: (-31.7776, -8.1237, -4.4400)
  V[1]: (-31.7776, -8.1237, -1.5600)
  V[2]: (-31.1199, -7.4716, -1.5600)
  V[3]: (-31.1199, -7.4716, -4.4400)

DB Coque_1534:
  type: VOILE, thickness: 0.04m, material: C25/30, modeling: DKT
```
Walls are planar Breps (4 vertices = rectangular panel). Z values match floor levels.

#### Dalle (Slab) - Brep
```
3DM Coque_1655 (8 vertices):
  V[0]: (-45.0912, -12.8350, 2.1200)
  V[1]: (-45.2162, -12.8350, 2.1200)
  ...
  V[7]: (-45.0912, -12.5546, 2.1200)
```
Slabs are horizontal Breps (all Z values identical). More complex shapes (up to 242 vertices).

#### Appuis (Support) - Point
```
3DM Appuis_6233:
  Location: (37.5000, 22.5000, -4.4400)

DB Appuis_6233:
  type: RIGIDE, geometry: PONCTUELLE
  DOF flags: x=1, y=1, z=1, rx=0, ry=0, rz=0
```
Supports are point locations with boundary conditions (fixed/free DOFs) stored in DB.

---

### 5. Name-Based Linkage (3DM <-> DB)

| Metric | Value |
|--------|-------|
| Objects in 3DM | 5,825 |
| Records in DB | 5,825 |
| **Matching names** | **5,824** (99.98%) |
| Only in 3DM | 1 (`Filaire_7415`) |
| Only in DB | 1 (`Filaire_7416`) |

**Name patterns:**
- `Coque_*`: 2,953 (all shell elements - voiles + dalles)
- `Filaire_*`: 2,718 (all linear elements - poteaux + poutres)
- `Appuis_*`: 153 (all supports)

The single name mismatch (`Filaire_7415` vs `Filaire_7416`) is likely a minor export/numbering discrepancy.

---

### 6. DB Schema Details (17 tables)

#### Core Tables
| Table | Rows | Purpose |
|-------|------|---------|
| `element` | 5,825 | Base entity (id, type discriminator) |
| `filaire` | 2,719 | Linear elements (POTEAU: 1,527 / POUTRE: 1,192) |
| `shell` | 2,953 | Surface elements (VOILE: 2,669 / DALLE: 284) |
| `support` | 153 | Boundary conditions (all RIGIDE/PONCTUELLE) |

#### Reference Tables
| Table | Rows | Purpose |
|-------|------|---------|
| `material` | 2 | C25/30, C25 (concrete) |
| `section` | varies | Rectangular profiles (R20x20, R25x25, etc.) |
| `group` | - | Element grouping |
| `element_group` | - | Many-to-many mapping |

#### Analysis Tables
| Table | Purpose |
|-------|---------|
| `mass_case` | Load cases |
| `element_mass_case` | Element-to-load mapping |
| `spring` | Spring elements |
| `additional_mass` | Extra mass definitions |
| `body` | Solid body elements |
| `freeform` | Free-form geometry |
| `shell_reinforcement` | Rebar layers |

---

### 7. Vertex Extraction: Proven Working Code

The following extraction strategy works with `rhino3dm` 8.17.0:

```python
import rhino3dm

model = rhino3dm.File3dm.Read("geometrie_2.3dm")
vertices = []

for obj in model.Objects:
    name = obj.Attributes.Name
    geom = obj.Geometry

    if isinstance(geom, rhino3dm.Brep):
        for vi in range(len(geom.Vertices)):
            v = geom.Vertices[vi]
            vertices.append((name, v.Location.X, v.Location.Y, v.Location.Z, vi))

    elif isinstance(geom, rhino3dm.LineCurve):
        vertices.append((name, geom.PointAtStart.X, geom.PointAtStart.Y, geom.PointAtStart.Z, 0))
        vertices.append((name, geom.PointAtEnd.X, geom.PointAtEnd.Y, geom.PointAtEnd.Z, 1))

    elif isinstance(geom, rhino3dm.PolylineCurve):
        for pi in range(geom.PointCount):
            p = geom.Point(pi)
            vertices.append((name, p.X, p.Y, p.Z, pi))

    elif isinstance(geom, rhino3dm.NurbsCurve):
        for pi in range(len(geom.Points)):
            p = geom.Points[pi]
            vertices.append((name, p.X, p.Y, p.Z, pi))

    elif isinstance(geom, rhino3dm.Point):
        vertices.append((name, geom.Location.X, geom.Location.Y, geom.Location.Z, 0))

# Result: 20,996 vertices with (element_name, x, y, z, vertex_index)
```

---

### 8. PRD Implementation Readiness

| PRD Requirement | Status | Detail |
|-----------------|--------|--------|
| F-01: DB Connection | Ready | SQLite via sqlite3 |
| F-02: Extraction & Validation | Ready | rhino3dm + sqlite3 extracts all data |
| F-03: Statistical Analysis | Ready | 20,996 vertices with full coordinates |
| F-04: DBSCAN Clustering | Ready | X/Y need clustering; Z already clustered |
| F-05: Thread Identification | Partially Ready | Z threads obvious; X/Y to be detected |
| F-06: Edge Cases | To Test | 1 isolated Z vertex at 17.78m; name mismatch |
| F-07: Vertex Alignment | Ready | All coordinates in meters |
| F-08: Output DB | Ready | Can create enriched vertices table |
| F-09: Post-Validation | Ready | Original coords preserved per object |
| F-10: Report | Ready | All statistics computable |

#### PRD Schema Adaptation Required

The PRD expects `elements` + `vertices` tables. The actual data requires:

1. **Create unified `elements` view/table** from `filaire` + `shell` + `support`
2. **Create `vertices` table** from 3dm extraction
3. **Link via name matching** (5,824/5,825 exact matches)

```sql
-- Unified elements view
CREATE VIEW prd_elements AS
SELECT id, LOWER(type) as type, name as nom FROM filaire
UNION ALL
SELECT id, LOWER(type) as type, name as nom FROM shell
UNION ALL
SELECT id, 'appui' as type, name as nom FROM support;

-- Vertices table (populated from rhino3dm extraction)
CREATE TABLE vertices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    element_id INTEGER NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL NOT NULL,
    vertex_index INTEGER NOT NULL,
    FOREIGN KEY (element_id) REFERENCES element(id)
);
```

---

## Code References

- `structure-batiment/data/geometrie_2.db` - SQLite database (952 KB, 17 tables, 5,825 elements)
- `structure-batiment/data/geometrie_2.3dm` - Rhino 3D model (49.4 MB, 5,825 objects, 20,996 vertices)
- `structure-batiment/prd/PRD.md:92-110` - PRD expected database schema
- `structure-batiment/prd/PRD.md:164-201` - DBSCAN clustering algorithm
- `structure-batiment/prd/PRD.md:297-321` - PRD enriched output schema

---

## Architecture Documentation

### Data Architecture

```
geometrie_2.3dm (49 MB)              geometrie_2.db (952 KB)
┌──────────────────────┐              ┌──────────────────────┐
│ 5,825 objects        │  linked by   │ 5,825 elements       │
│ 20,996 vertices      │◄── name ───►│ materials, sections   │
│ Brep/LineCurve/Point │              │ supports, loads       │
│ 7,753 layers         │              │ groups, reinforcement │
└──────────┬───────────┘              └──────────┬───────────┘
           │                                      │
           └──────────┬───────────────────────────┘
                      │
                      ▼
              ┌───────────────┐
              │  PRD Pipeline │
              │ 1. Extract    │ <- rhino3dm reads .3dm
              │ 2. Link       │ <- name matching
              │ 3. Cluster    │ <- DBSCAN on X, Y, Z
              │ 4. Align      │ <- snap to threads
              │ 5. Validate   │ <- displacement ≤ alpha
              │ 6. Output     │ <- enriched DB + report
              └───────────────┘
```

### Building Geometry Profile

```
Building footprint: ~119m x 119m
Building height:    ~42m (13 floor levels)
Elements:           5,825
  Walls (voile):    2,669 (45.8%)
  Columns (poteau): 1,527 (26.2%)
  Beams (poutre):   1,192 (20.5%)
  Slabs (dalle):      284 (4.9%)
  Supports:           153 (2.6%)
Total vertices:     20,996
```

---

## Related Research

- `docs/research/2026-02-03-prd-analysis-geometric-alignment-software.md` - Full PRD analysis
- `docs/research/2026-02-03-python-rhino3d-libraries.md` - Python libraries for .3dm processing

---

## Open Questions

1. **Name mismatch**: `Filaire_7415` (3dm) vs `Filaire_7416` (db) - which is correct? Is this a known export issue?

2. **Isolated Z vertex**: One vertex at Z=17.78m (between level 4 at 17.96m and level 3 at 13.32m). Is this a modeling error or a deliberate offset?

3. **Brep vertex precision**: Some Brep vertices have coordinates like -31.7776m. Are these sub-centimeter values intentional or modeling noise that should be aligned?

4. **PolylineCurve beams**: 157 beams are PolylineCurves (multi-point) rather than straight LineCurves. These may represent curved or multi-segment beams. How should intermediate vertices be handled during alignment?

5. **NurbsCurve beams**: 3 beams are NurbsCurves. Their control points may not lie exactly on the curve. Should alignment use control points or sampled curve points?

6. **Layer count > object count**: 7,753 layers for 5,825 objects. The extra ~1,928 layers may be empty organizational layers or deleted element remnants. Should these be cleaned up?

---

*Research completed on 2026-02-05*
