---
date: 2026-02-03T21:57:39Z
researcher: Claude Code
git_commit: not-a-git-repo
branch: no-branch
repository: necs
topic: "Python Libraries for Managing Rhino 3D Files"
tags: [research, python, rhino3d, 3dm, opennurbs, geometry, bim]
status: complete
last_updated: 2026-02-03
last_updated_by: Claude Code
---

# Research: Python Libraries for Managing Rhino 3D Files

**Date**: 2026-02-03T21:57:39Z
**Researcher**: Claude Code
**Git Commit**: not-a-git-repo
**Branch**: no-branch
**Repository**: necs

## Research Question

What's available in Python to manage Rhino 3D (.3dm) files?

## Summary

McNeel (the company behind Rhino) provides several official Python libraries for working with .3dm files. The primary library for standalone use is **rhino3dm**, which is based on OpenNURBS and allows full read/write access to .3dm files **without Rhino installed**. For advanced geometry operations, **compute-rhino3d** provides cloud-based access to RhinoCommon functions.

---

## Detailed Findings

### 1. rhino3dm (Primary Recommended Library)

**The main library for working with .3dm files in Python without Rhino installed.**

| Attribute | Value |
|-----------|-------|
| **Source** | [PyPI](https://pypi.org/project/rhino3dm/) / [GitHub](https://github.com/mcneel/rhino3dm) |
| **Version** | 8.17.0 (March 2025) |
| **License** | MIT |
| **Requires Rhino?** | No |
| **Platforms** | Windows, macOS 13+, Linux |
| **Python** | 3.7 - 3.13 |

**Installation**:
```bash
pip install rhino3dm
```

**Capabilities**:
- Read/write .3dm files
- Access all geometry types: points, curves, surfaces, meshes, BReps, SubDs
- Access layers, materials, object attributes, viewports
- Create new geometry programmatically

**Basic Usage**:
```python
import rhino3dm

# Read a file
model = rhino3dm.File3dm.Read('model.3dm')

# Iterate objects
for obj in model.Objects:
    geometry = obj.Geometry
    bbox = geometry.GetBoundingBox()
    print(f"BBox: {bbox.Min}, {bbox.Max}")

# Write a file
model = rhino3dm.File3dm()
pt = rhino3dm.Point3d(0, 0, 0)
model.Objects.AddPoint(pt)
model.Write("output.3dm", version=7)
```

**Documentation**:
- API Reference: https://mcneel.github.io/rhino3dm/python/api/index.html
- Samples: https://github.com/mcneel/rhino-developer-samples/tree/8/rhino3dm/py

---

### 2. compute-rhino3d (Cloud Compute Service)

**Extends rhino3dm with advanced RhinoCommon operations via cloud API.**

| Attribute | Value |
|-----------|-------|
| **Source** | [PyPI](https://pypi.org/project/compute-rhino3d/) / [GitHub](https://github.com/mcneel/compute.rhino3d) |
| **Version** | 0.12.2 |
| **License** | MIT |
| **Requires Rhino?** | No (cloud-based) |
| **Platforms** | All (pure Python) |

**Installation**:
```bash
pip install compute-rhino3d
```

**Capabilities**:
- 2,400+ API calls from RhinoCommon
- Advanced geometry operations not in rhino3dm
- Requires authentication token from rhino3d.com

**Usage**:
```python
import rhino3dm
import compute_rhino3d

compute_rhino3d.Util.authToken = "YOUR_TOKEN"
# Use compute functions for advanced operations
```

**Documentation**:
- Guide: https://developer.rhino3d.com/guides/compute/compute-python-getting-started/
- API: https://compute-rhino3d.readthedocs.io/en/latest/

---

### 3. RhinoCommon (Full SDK - Requires Rhino)

**Low-level .NET API accessible through Python when running inside Rhino.**

| Attribute | Value |
|-----------|-------|
| **Source** | Bundled with Rhino |
| **Requires Rhino?** | Yes |
| **Platforms** | Windows, macOS |
| **Python** | IronPython 2.7 (Rhino 7), CPython 3.9 (Rhino 8+) |

**Capabilities**:
- Full Rhino SDK access
- Plugin development
- All geometry operations

**Usage** (inside Rhino):
```python
import Rhino
# Full access to RhinoCommon classes
```

**Documentation**: https://developer.rhino3d.com/api/

---

### 4. rhinoscriptsyntax (High-Level API - Requires Rhino)

**Simplified scripting library built on RhinoCommon.**

| Attribute | Value |
|-----------|-------|
| **Source** | [GitHub](https://github.com/mcneel/rhinoscriptsyntax) |
| **Requires Rhino?** | Yes |
| **Platforms** | Windows, macOS |

**Usage** (inside Rhino):
```python
import rhinoscriptsyntax as rs
# Hundreds of easy-to-use functions
```

**Documentation**: https://developer.rhino3d.com/api/RhinoScriptSyntax

---

### 5. rhinoinside (Embed Rhino in Python - Windows Only)

**Embeds full Rhino functionality into standalone Python applications.**

| Attribute | Value |
|-----------|-------|
| **Source** | [PyPI](https://pypi.org/project/rhinoinside/) |
| **Version** | 0.8.2 |
| **Requires Rhino?** | Yes (installed, not running) |
| **Platforms** | Windows only |
| **Python** | 3.7+ (64-bit) |

**Installation**:
```bash
pip install rhinoinside
```

**Usage**:
```python
import rhinoinside
rhinoinside.load()  # or rhinoinside.load(8, 'net7.0')
import Rhino
# Full RhinoCommon access in standalone script
```

**Documentation**: https://github.com/mcneel/rhino.inside-cpython

---

## Comparison Matrix

| Library | Requires Rhino? | Read .3dm | Write .3dm | Geometry Ops | Platform |
|---------|----------------|-----------|-----------|--------------|----------|
| **rhino3dm** | No | ✅ | ✅ | Basic | All |
| **compute-rhino3d** | No (cloud) | via rhino3dm | via rhino3dm | Advanced | All |
| **RhinoCommon** | Yes | ✅ | ✅ | Full | Win/Mac |
| **rhinoscriptsyntax** | Yes | ✅ | ✅ | High-level | Win/Mac |
| **rhinoinside** | Yes (installed) | ✅ | ✅ | Full | Windows |

---

## Code Examples for Your Use Case

### Extract Vertices from .3dm File (For PRD Alignment Task)

```python
import rhino3dm

model = rhino3dm.File3dm.Read("geometrie_2.3dm")

vertices = []
for obj in model.Objects:
    geometry = obj.Geometry

    # Handle Mesh objects
    if geometry.ObjectType == rhino3dm.ObjectType.Mesh:
        mesh = geometry
        for v in range(len(mesh.Vertices)):
            vertices.append({
                'x': mesh.Vertices[v].X,
                'y': mesh.Vertices[v].Y,
                'z': mesh.Vertices[v].Z
            })

    # Handle Brep (polysurface) - convert to mesh first
    elif geometry.ObjectType == rhino3dm.ObjectType.Brep:
        brep = geometry
        for face in brep.Faces:
            mesh = face.GetMesh(rhino3dm.MeshType.Any)
            if mesh:
                for v in range(len(mesh.Vertices)):
                    vertices.append({
                        'x': mesh.Vertices[v].X,
                        'y': mesh.Vertices[v].Y,
                        'z': mesh.Vertices[v].Z
                    })

print(f"Extracted {len(vertices)} vertices")
```

### Convert .3dm to SQL Database

```python
import rhino3dm
import sqlite3

def convert_3dm_to_sql(input_file, output_db):
    model = rhino3dm.File3dm.Read(input_file)

    conn = sqlite3.connect(output_db)
    cursor = conn.cursor()

    # Create tables matching PRD schema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS elements (
            id INTEGER PRIMARY KEY,
            type VARCHAR(50),
            nom VARCHAR(100)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vertices (
            id INTEGER PRIMARY KEY,
            element_id INTEGER,
            x REAL,
            y REAL,
            z REAL,
            vertex_index INTEGER,
            FOREIGN KEY (element_id) REFERENCES elements(id)
        )
    ''')

    element_id = 0
    vertex_id = 0

    for obj in model.Objects:
        geometry = obj.Geometry
        element_id += 1

        # Determine element type
        obj_type = str(geometry.ObjectType).split('.')[-1].lower()
        obj_name = obj.Attributes.Name or f"element_{element_id}"

        cursor.execute(
            "INSERT INTO elements VALUES (?, ?, ?)",
            (element_id, obj_type, obj_name)
        )

        # Extract vertices based on geometry type
        mesh = None
        if geometry.ObjectType == rhino3dm.ObjectType.Mesh:
            mesh = geometry
        elif geometry.ObjectType == rhino3dm.ObjectType.Brep:
            for face in geometry.Faces:
                mesh = face.GetMesh(rhino3dm.MeshType.Any)
                break

        if mesh:
            for v_idx in range(len(mesh.Vertices)):
                cursor.execute(
                    "INSERT INTO vertices VALUES (?, ?, ?, ?, ?, ?)",
                    (vertex_id, element_id,
                     mesh.Vertices[v_idx].X,
                     mesh.Vertices[v_idx].Y,
                     mesh.Vertices[v_idx].Z,
                     v_idx)
                )
                vertex_id += 1

    conn.commit()
    conn.close()
    print(f"Converted {element_id} elements, {vertex_id} vertices")

# Usage
convert_3dm_to_sql("geometrie_2.3dm", "structure.db")
```

---

## Recommended Approach for PRD Implementation

For the Geometric Alignment Software described in the PRD, the recommended workflow:

1. **Use rhino3dm** to read the `.3dm` file
2. **Convert** geometry to the SQL schema defined in the PRD
3. **Process** with the alignment algorithm (DBSCAN clustering)
4. **Optionally** write results back to `.3dm` using rhino3dm

```bash
# Install required libraries
pip install rhino3dm
```

This approach:
- Does not require Rhino to be installed
- Works on all platforms
- Provides full access to geometry data
- Aligns with the PRD's SQLite/PostgreSQL/MySQL requirements

---

## Additional Resources

### Official Documentation
- rhino3dm API: https://mcneel.github.io/rhino3dm/python/api/index.html
- Developer Docs: https://developer.rhino3d.com/
- OpenNURBS: https://www.rhino3d.com/features/developer/opennurbs/

### GitHub Repositories
- rhino3dm: https://github.com/mcneel/rhino3dm
- Samples: https://github.com/mcneel/rhino-developer-samples/tree/8/rhino3dm/py
- compute.rhino3d: https://github.com/mcneel/compute.rhino3d

### Community
- Forum: https://discourse.mcneel.com/c/rhino-developer/rhino3dm/

---

## Related Research

- [2026-02-03-prd-analysis-geometric-alignment-software.md](./2026-02-03-prd-analysis-geometric-alignment-software.md) - PRD analysis showing the `geometrie_2.3dm` sample file that needs to be converted

---

## Open Questions

1. **Layer Structure**: Does the `geometrie_2.3dm` file use layers to organize structural elements (poteaux, poutres, dalles, voiles)?

2. **Geometry Types**: What geometry types are present in the file - meshes, BReps, or NURBS surfaces?

3. **Element Naming**: Are elements named in Rhino that could map to the `nom` field in the PRD schema?

---

*Research completed on 2026-02-03*
