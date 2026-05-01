#!/usr/bin/env bash
# build-agent.sh — Bundle the FlowKit Python agent into a standalone binary via PyInstaller
# Run this on each target OS (macOS, Windows) to produce the OS-specific binary.
# The output binary is placed in desktop/resources/agent/flowkit-agent[.exe]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/venv"
OUTPUT="$ROOT/desktop/resources/agent"

echo "==> Activating venv..."
source "$VENV/bin/activate"

echo "==> Installing PyInstaller..."
pip install pyinstaller --quiet

echo "==> Bundling agent..."
pyinstaller \
  --noconfirm \
  --onefile \
  --name flowkit-agent \
  --distpath "$OUTPUT" \
  --workpath /tmp/flowkit-build \
  --specpath /tmp/flowkit-spec \
  --add-data "$ROOT/agent:agent" \
  --hidden-import uvicorn \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import websockets \
  "$ROOT/agent/main.py"

echo "==> Done! Binary at: $OUTPUT/flowkit-agent"
ls -lh "$OUTPUT/"
