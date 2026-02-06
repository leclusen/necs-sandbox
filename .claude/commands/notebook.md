---
name: notebook
description: Start Jupyter notebook server or work with notebooks
args: [start|stop|list] [notebook_file]
---

Manage Jupyter notebooks in the workspace.

## Usage

```
/notebook start
/notebook stop
/notebook list
/notebook analyze notebook.ipynb
```

## Actions

### Start Jupyter Server

```bash
source venv/bin/activate
jupyter notebook
# or
jupyter lab
```

Opens in browser at http://localhost:8888

### Stop Server

Find and stop running Jupyter processes:
```bash
jupyter notebook stop
# or kill the process
```

### List Notebooks

```
Glob: **/*.ipynb
```

### Analyze Notebook

Read and summarize a specific notebook:
- Extract cells and outputs
- List imports and dependencies
- Identify visualizations
- Document data sources

## Installation

If Jupyter is not installed:
```bash
pip install jupyter jupyterlab notebook
```

## Notebook Structure

- Code cells - Python code execution
- Markdown cells - Documentation
- Outputs - Results, plots, dataframes

## Common Libraries in Notebooks

```python
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
```

## Tips

- Keep notebooks in a `notebooks/` directory
- Export important notebooks to Python scripts
- Clear output before committing: `jupyter nbconvert --clear-output`
- Use `%matplotlib inline` for plots

## Examples

```
/notebook start
/notebook list
/notebook analyze analysis.ipynb
```
