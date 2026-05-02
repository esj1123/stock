#!/usr/bin/env bash
set -euo pipefail

# Repo root = parent of this scripts/ directory.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

VENV_DIR=".venv"
REQ_FILE="70_Imports/scripts/requirements.txt"
MAIN_PY="70_Imports/scripts/main.py"

if [ ! -d "$VENV_DIR" ]; then
  "$PY" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install -r "$REQ_FILE"

has_action=false
for arg in "$@"; do
  case "$arg" in
    import|report|qa|all)
      has_action=true
      break
      ;;
  esac
done

if [ "$has_action" = true ]; then
  python "$MAIN_PY" "$@"
else
  python "$MAIN_PY" all "$@"
fi
