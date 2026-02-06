---
name: python_test
description: Run Python tests using pytest or unittest
args: [test_file or directory] [pytest args]
---

Runs Python tests in the workspace using pytest (preferred) or unittest.

## Usage

```
/python_test
/python_test tests/
/python_test tests/test_geometry.py
/python_test -v -k test_intersection
```

## Steps

1. If a virtual environment exists, activate it
2. Check if pytest is available
3. Run tests with pytest (or fall back to unittest)
4. Display test results and coverage if available

## Testing Frameworks

### pytest (preferred)
```bash
pytest
pytest tests/
pytest tests/test_file.py
pytest -v -k pattern
pytest --cov=module
```

### unittest (fallback)
```bash
python3 -m unittest discover
python3 -m unittest tests.test_module
```

## Common Options

- `-v, --verbose` - Verbose output
- `-k EXPRESSION` - Run tests matching expression
- `-x, --exitfirst` - Exit on first failure
- `--cov=MODULE` - Measure code coverage
- `-s` - Don't capture output (show print statements)
- `--pdb` - Drop into debugger on failures

## Examples

```
/python_test
/python_test tests/test_geometry.py -v
/python_test -k "intersection or union"
/python_test --cov=geometry --cov-report=html
```
