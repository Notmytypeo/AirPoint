#!/usr/bin/env bash
# ==============================================================================
# Run AirPoint on macOS
# ==============================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
PYTHON="$VENV/bin/python3"

if [ "$(uname)" != "Darwin" ]; then
    echo "This launcher must be run on macOS."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -f "$PYTHON" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV"
fi

# Install dependencies if mediapipe is missing
if ! "$PYTHON" -c "import mediapipe, cv2, PySide6, numpy" 2>/dev/null; then
    echo "Installing AirPoint dependencies..."
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install -r "$ROOT/requirements.txt"
fi

echo "=================================================="
echo "   Starting AirPoint...                           "
echo "=================================================="
echo ""
echo "NOTE: macOS will ask for these permissions on first run:"
echo "  • Camera access  (System Settings → Privacy → Camera)"
echo "  • Accessibility  (System Settings → Privacy → Accessibility)"
echo ""
echo "Grant both to enable gesture control."
echo ""

"$PYTHON" "$ROOT/main.py" "$@"
