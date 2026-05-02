#!/usr/bin/env bash
set -euo pipefail

# Vault root = parent of this scripts/ directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

# Pick python
if command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

VENV_DIR="70_Imports/.venv"
REQ_FILE="70_Imports/scripts/requirements.txt"
IMPORTER="70_Imports/scripts/namoo_excel_import.py"

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
  "$PY" -m venv "$VENV_DIR"
fi

# Activate venv
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "$REQ_FILE"

# Run importer
python "$IMPORTER" --create-companies "$@"