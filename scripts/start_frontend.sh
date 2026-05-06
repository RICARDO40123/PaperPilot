#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"
echo "[PaperPilot] Starting frontend on http://127.0.0.1:8501"
python -m streamlit run app.py --server.port 8501
