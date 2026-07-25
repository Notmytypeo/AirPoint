# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the AirPoint one-folder bundle."""

import os
import importlib

block_cipher = None

# Locate packages so we can grab their data files.
mediapipe_dir = os.path.dirname(importlib.import_module("mediapipe").__file__)
cv2_dir = os.path.dirname(importlib.import_module("cv2").__file__)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        # Hand-landmarker model
        (os.path.join("models", "hand_landmarker.task"), "models"),
        # App assets (SVG icon etc.)
        (os.path.join("app", "assets"), os.path.join("app", "assets")),
        # MediaPipe needs its data files (protobuf configs, TFLite delegates)
        (mediapipe_dir, "mediapipe"),
        # Lightweight face/eyeglasses veto for rejecting hand-shaped facial features
        (os.path.join(cv2_dir, "data", "haarcascade_frontalface_default.xml"), os.path.join("cv2", "data")),
        (os.path.join(cv2_dir, "data", "haarcascade_eye_tree_eyeglasses.xml"), os.path.join("cv2", "data")),
    ],
    hiddenimports=[
        "mediapipe",
        "mediapipe.tasks",
        "mediapipe.tasks.python",
        "mediapipe.tasks.python.vision",
        "mediapipe.tasks.python.vision.hand_landmarker",
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
        "numpy",
        "cv2",
        "uiautomation",
        "absl",
        "absl.logging",
        "flatbuffers",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
        # MediaPipe's audio extras are not used by this vision-only app.
        "sounddevice",
        "_sounddevice",
        "_sounddevice_data",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AirPoint",
    icon=os.path.join("app", "assets", "airpoint-logo.ico"),
    version=os.environ.get("AIRPOINT_VERSION_FILE"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # No console window for a GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AirPoint",
)
