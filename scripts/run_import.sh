#!/usr/bin/env bash
set -euo pipefail

# Repo root = parent of this scripts/ directory.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Keep the virtual environment outside the repository and outside Google Drive
# synced Vaults by default so dependency files are never mixed with live data.
if command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

if [ -n "${STOCK_VENV_DIR:-}" ]; then
  VENV_DIR="$STOCK_VENV_DIR"
else
  VENV_DIR="$HOME/.local/share/06_stock/.venv"
fi
REQ_FILE="70_Imports/scripts/requirements.txt"
MAIN_PY="70_Imports/scripts/main.py"

mkdir -p "$(dirname "$VENV_DIR")"

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
