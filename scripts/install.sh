#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate
echo "==> Installing dependencies..."
pip install -r requirements.txt
echo "==> Copying .env if not present..."
[ -f .env ] || cp .env.example .env
echo "==> Done. Edit .env then run: scripts/run.sh"
