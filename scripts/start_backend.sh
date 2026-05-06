#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"
echo "[PaperPilot] Starting backend on http://127.0.0.1:8000"
python -m uvicorn api.main:app --reload --port 8000
