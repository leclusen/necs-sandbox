#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Install package in dev mode if not already installed
if ! "$VENV_DIR/bin/pip" show structure-aligner &>/dev/null; then
    echo "Installing dependencies..."
    "$VENV_DIR/bin/pip" install -e "$SCRIPT_DIR[dev]"
fi

# Generate a date-based output directory
OUTPUT_DIR="$SCRIPT_DIR/output/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"
echo "Output directory: $OUTPUT_DIR"

# Run with output directory and all arguments forwarded
exec "$VENV_DIR/bin/python" -m structure_aligner "$@" \
    --output "$OUTPUT_DIR/aligned.db" \
    --report "$OUTPUT_DIR/report.json"
