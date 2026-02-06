---
name: python_run
description: Run Python scripts or modules
args: <script.py or -m module_name> [arguments]
---

Runs a Python script or module in the workspace.

## Usage

```
/python_run script.py
/python_run script.py --arg value
/python_run -m module_name
```

## Steps

1. If a virtual environment exists, activate it first
2. Run the Python script or module with provided arguments
3. Display the output
4. If errors occur, show the full traceback

## Virtual Environment Detection

Check for virtual environment in these locations:
- `./venv/`
- `./env/`
- `./.venv/`

Activate command (if venv exists):
```bash
source venv/bin/activate  # Linux/Mac
```

## Running

```bash
python3 script.py [args]
# or
python3 -m module_name [args]
```

## Examples

```
/python_run main.py
/python_run process_geometry.py --input data/model.3dm
/python_run -m pytest tests/
```
