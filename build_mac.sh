#!/usr/bin/env bash
# ==============================================================================
# Build AirPoint .app bundle for macOS using PyInstaller
# Must be run ON a Mac — cannot cross-compile from Windows.
# ==============================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
PYTHON="$VENV/bin/python3"

if [ ! -f "$PYTHON" ]; then
    echo "Run ./run_mac.sh first to create the virtual environment."
    exit 1
fi

# Install PyInstaller if not present
if ! "$PYTHON" -c "import PyInstaller" 2>/dev/null; then
    echo "Installing PyInstaller..."
    "$PYTHON" -m pip install pyinstaller
fi

# Ensure the hand-landmarker model exists
if [ ! -f "$ROOT/models/hand_landmarker.task" ]; then
    echo "Downloading hand-landmarker model..."
    "$PYTHON" -c "from app.model_manager import ensure_hand_model; ensure_hand_model()"
fi

MEDIAPIPE_DIR=$("$PYTHON" -c "import mediapipe, os; print(os.path.dirname(mediapipe.__file__))")

echo "=================================================="
echo "   Building AirPoint.app...                       "
echo "=================================================="

"$PYTHON" -m PyInstaller \
    --name "AirPoint" \
    --windowed \
    --noconfirm \
    --clean \
    --add-data "models/hand_landmarker.task:models" \
    --add-data "app/assets:app/assets" \
    --add-data "$MEDIAPIPE_DIR:mediapipe" \
    --hidden-import "mediapipe" \
    --hidden-import "mediapipe.tasks" \
    --hidden-import "mediapipe.tasks.python" \
    --hidden-import "mediapipe.tasks.python.vision" \
    --hidden-import "mediapipe.tasks.python.vision.hand_landmarker" \
    --hidden-import "PySide6.QtSvg" \
    --hidden-import "PySide6.QtSvgWidgets" \
    --hidden-import "numpy" \
    --hidden-import "cv2" \
    --hidden-import "matplotlib" \
    --hidden-import "matplotlib.backends" \
    --hidden-import "matplotlib.backends.backend_agg" \
    --hidden-import "absl" \
    --hidden-import "absl.logging" \
    --hidden-import "flatbuffers" \
    --hidden-import "sounddevice" \
    --exclude-module "tkinter" \
    --exclude-module "scipy" \
    --exclude-module "pandas" \
    --exclude-module "IPython" \
    --exclude-module "jupyter" \
    main.py

echo ""
echo "=================================================="
echo "   Build complete! ✅                              "
echo "=================================================="
echo "   Output: dist/AirPoint.app"
echo ""
echo "   To run:  open dist/AirPoint.app"
echo "   To share: zip -r AirPoint.zip dist/AirPoint.app"
echo "=================================================="
