---
date: 2026-02-06T15:39:21Z
researcher: Claude Code
git_commit: no-commit
branch: main
repository: necs
topic: "Deep Analysis of geometrie_2.db for Coordinate Data"
tags: [research, database, sqlite, coordinates, geometry, schema-analysis]
status: complete
last_updated: 2026-02-06
last_updated_by: Claude Code
---

# Research: Deep Analysis of geometrie_2.db for Coordinate Data

**Date**: 2026-02-06T15:39:21Z
**Researcher**: Claude Code
**Git Commit**: no-commit
**Branch**: main
**Repository**: necs

## Research Question

Analyze the `geometrie_2.db` file more closely to determine if coordinate data is stored within it, potentially in encoded or non-obvious forms.

## Summary

**Confirmed: `geometrie_2.db` contains zero spatial coordinates.** Every table and every column was examined. The database stores exclusively structural engineering *properties* (materials, sections, boundary conditions, local axis orientations, DOF constraints, groupings) but no vertex positions, node coordinates, or encoded geometry data. There are no BLOB columns, no serialized JSON geometry, and no hidden coordinate encoding.

The only columns that superficially resemble coordinates are:
- `filaire.y_local` — local axis *direction vectors* (orientation, not position)
- `support.x/y/z` — DOF constraint *flags* (0 or 1), not coordinates
- `support.kx/ky/kz` — spring *stiffness* values, not positions

---

## Detailed Findings

### 1. Complete Table Inventory (17 tables)

| Table | Rows | Column Count | Contains Coordinates? |
|-------|------|-------------|----------------------|
| `element` | 5,825 | 2 | No — only `id` (INT) and `type` (TEXT: "filaire"/"shell"/"support") |
| `filaire` | 2,719 | 14 | No — structural properties only |
| `shell` | 2,953 | 16 | No — structural properties only |
| `support` | 153 | 30 | No — boundary conditions only |
| `section` | 109 | ~15 | No — cross-section geometry (width, height, area, inertia) |
| `material` | 2 | ~5 | No — material properties (C25/30, C25) |
| `group` | 160 | ~3 | No — group names |
| `element_group` | 10,178 | 2 | No — element-to-group mapping |
| `mass_case` | 2 | ~3 | No — load case definitions |
| `element_mass_case` | 0 | ~5 | Empty |
| `additional_mass` | 0 | ~10 | Empty |
| `freeform` | 0 | ~5 | Empty |
| `spring` | 0 | ~20 | Empty |
| `body` | 0 | ~5 | Empty |
| `shell_reinforcement` | 0 | ~5 | Empty |
| `alembic_version` | 1 | 1 | No — DB migration version |
| `sqlite_sequence` | 1 | 2 | No — auto-increment tracker |

### 2. Columns That Look Like Coordinates But Aren't

#### `filaire.y_local` (TEXT)
```
"1, 0, 0"
"-1, 0, 0"
"0, 1, 0"
"-0.707, 0.707, 0"
```
These are **local axis orientation vectors** — they define which direction is "up" for a beam element's cross-section. There are only 24 distinct values across 2,719 elements. They are NOT positions.

#### `support.x`, `support.y`, `support.z` (INTEGER)
```
x=1, y=1, z=1     (translation blocked in all directions)
rx=0, ry=0, rz=0   (rotation free in all directions)
```
These are **DOF constraint flags** (0=free, 1=blocked). They describe boundary conditions, NOT spatial positions.

#### `support.kx`, `support.ky`, `support.kz` (REAL)
All NULL for the 153 supports (all are type RIGIDE = infinitely stiff). These would be spring stiffness constants, NOT coordinates.

#### `support.geometry` (TEXT)
Values: `"PONCTUELLE"` (131 rows) or `"LINEIQUE"` (22 rows). This is a geometry **type descriptor**, not coordinate data.

#### `shell.x_local`, `shell.z_local` (TEXT)
All empty strings. Would contain local axis directions if defined, but none are.

### 3. What the Database Actually Stores

The database is a **structural analysis model** exported from a FEM (Finite Element Method) software. It contains:

- **Element topology** (which elements exist, their types)
- **Material assignments** (concrete grades)
- **Section assignments** (cross-section profiles: R20x20, R25x25, etc.)
- **Boundary conditions** (rigid supports with DOF constraints)
- **Modeling parameters** (Timoshenko beams, DKT shells)
- **Articulations** (connection types: 111111_111111 = fully fixed)
- **Element grouping** (160 groups organizing elements by floor/zone)

### 4. No Hidden Geometry Encoding

Checked exhaustively:
- **No BLOB columns** in any table
- **No JSON strings** containing coordinates
- **No comma-separated coordinate strings** (only `y_local` direction vectors)
- **No views or triggers** that compute/expose coordinates
- **No tables** with names containing geo/coord/point/vertex/node
- **6 empty tables** (body, freeform, spring, additional_mass, element_mass_case, shell_reinforcement) — none would contain coordinates even if populated

### 5. Where Coordinates Actually Live

The coordinates exist in `geometrie_2.3dm` (Rhino 3D file, 49.4 MB) and have been extracted into `geometrie_2_prd.db` (3.25 MB) via the ETL pipeline. The ETL-produced database adds:
- `elements` table (5,825 rows): unified element registry with PRD-compliant schema
- `vertices` table (20,994 rows): actual x, y, z coordinates extracted from the .3dm file

---

## Architecture Documentation

### Data Architecture (Confirmed)

```
geometrie_2.3dm (49.4 MB)           geometrie_2.db (952 KB)
┌─────────────────────────┐          ┌─────────────────────────┐
│ GEOMETRY                │          │ PROPERTIES              │
│ • 5,825 3D objects      │          │ • 5,825 element records │
│ • 20,996 vertices       │          │ • Materials (C25/30)    │
│ • Brep, LineCurve, etc. │          │ • Sections (R20x20...) │
│ • Coordinates in meters │          │ • Supports (DOF flags)  │
│                         │          │ • Groups (160)          │
│ NO properties           │          │ NO coordinates          │
└─────────────────────────┘          └─────────────────────────┘
         │                                      │
         └──────── linked by element name ──────┘
                   (5,824/5,825 match)
```

This is a common pattern in structural engineering software: geometry and properties are stored separately. The `.3dm` file is the geometric model, the `.db` is the analysis model attributes. They are companions, not standalone.

---

## Code References

- `structure-batiment/data/geometrie_2.db` — SQLite database, 952 KB, 17 tables, zero coordinate data
- `structure-batiment/data/geometrie_2.3dm` — Rhino 3D model, 49.4 MB, 5,825 objects, 20,996 vertices
- `structure-batiment/data/geometrie_2_prd.db` — ETL output with `elements` + `vertices` tables (coordinates)

---

## Related Research

- `docs/research/2026-02-05-geometrie2-database-prd-alignment.md` — Initial .3dm + .db cross-reference analysis
- `docs/research/2026-02-03-python-rhino3d-libraries.md` — Python libraries for .3dm processing
- `docs/plans/2026-02-05-etl-rhino-to-prd-database.md` — ETL pipeline plan (extract from .3dm, load to DB)

---

## Open Questions

1. **Why no coordinates in the .db?** This appears to be by design in the source FEM software — it separates the geometric model (.3dm) from the analysis model attributes (.db). This is common in tools like Robot Structural Analysis, SCIA, or similar BIM-to-FEM workflows where Rhino/Grasshopper handles geometry and the analysis engine stores properties separately.

2. **Could the source software export coordinates to the .db?** Unknown. The database uses Alembic migrations (version `e39c239e0468`), suggesting it's generated by a Python/SQLAlchemy application that may have intentionally excluded geometry from the schema.

---

*Research completed on 2026-02-06*
