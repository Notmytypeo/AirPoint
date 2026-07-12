# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AirPoint — one-folder bundle."""

import os
import importlib

block_cipher = None

# ── Locate packages so we can grab their data files ──────────────────
mediapipe_dir = os.path.dirname(importlib.import_module("mediapipe").__file__)

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
        # MediaPipe transitive dependencies
        "matplotlib",
        "matplotlib.backends",
        "matplotlib.backends.backend_agg",
        "absl",
        "absl.logging",
        "flatbuffers",
        "sounddevice",
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
