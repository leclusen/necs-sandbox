---
name: python_setup
description: Set up Python virtual environment and install dependencies
args: [--clean]
---

Sets up a Python development environment with virtual environment and dependencies.

## Usage

```
/python_setup
/python_setup --clean
```

## Steps

### 1. Create Virtual Environment

```bash
python3 -m venv venv
```

If `--clean` is specified, remove existing venv first:
```bash
rm -rf venv
python3 -m venv venv
```

### 2. Activate Virtual Environment

```bash
source venv/bin/activate
```

### 3. Upgrade pip

```bash
pip install --upgrade pip
```

### 4. Install Dependencies

Check for and install from (in order):
- `requirements.txt`
- `pyproject.toml` (with `pip install -e .`)
- `setup.py` (with `pip install -e .`)

```bash
pip install -r requirements.txt
# or
pip install -e .
```

### 5. Install Development Dependencies (if exist)

- `requirements-dev.txt`
- `dev-requirements.txt`

```bash
pip install -r requirements-dev.txt
```

### 6. Display Installed Packages

```bash
pip list
```

## Common Dependencies for This Workspace

Geometry/Spatial:
- numpy
- shapely
- scipy
- matplotlib

3D/CAD:
- rhino3dm
- trimesh
- open3d
- ifcopenshell

Data Science:
- pandas
- seaborn
- jupyter

Development:
- pytest
- black
- ruff
- mypy

## Verification

After setup, verify by running:
```bash
python3 --version
pip list
pytest --version
```

## Examples

```
/python_setup
/python_setup --clean
```
