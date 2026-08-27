# AirPoint

AirPoint is a local Windows and macOS desktop app that turns two-hand camera gestures into mouse and system-volume controls. Camera frames are processed on-device with MediaPipe; frames are never uploaded.

## Choose your installer

You do **not** need to download the source code or install Python. Choose one option below.

| Your computer | Download | Beginner guide |
|---|---|---|
| **Windows 10 or 11** | [AirPoint Windows installer (.exe)](https://github.com/Notmytypeo/AirPoint/releases/latest/download/AirPoint_Setup_1.4.2.exe) | [Windows installation guide](windows_installer/README.md) |
| **MacBook with Apple chip** (M1, M2, M3, or M4) | [AirPoint Apple Silicon installer (.zip)](https://github.com/Notmytypeo/AirPoint/releases/latest/download/AirPoint-macOS-arm64.zip) | [macOS installation guide](mac_installer/README.md) |
| **Older Intel MacBook** | Download `AirPoint-macOS-x86_64.zip` from the [latest release](https://github.com/Notmytypeo/AirPoint/releases/latest) when available | [macOS installation guide](mac_installer/README.md) |

The `windows_installer/` and `mac_installer/` folders contain instructions only. The large installer files are kept on the **Releases** page so downloading is simple and reliable.

## Gestures

| Gesture | Action |
|---|---|
| Move right index finger | Move pointer |
| Right index finger + thumb pinch | Left click (other fingers may be folded) |
| Right middle finger + thumb pinch, with index/ring/little fingers open | Right click |
| Right ring finger + thumb pinch, with index/middle/little fingers open | Middle click |
| First index + thumb pinch with two free fingers, then move the whole hand vertically | Guarded one-hand scroll up/down |
| Repeat the index pinch quickly, then release without moving | Double click |
| Repeat the index pinch, then hold and move beyond the threshold | Drag; release to drop |
| Hold both fists for 0.7 seconds | Pause gesture control |
| While paused, hold the active pointer-hand fist for 0.7 seconds | Resume gesture control |
| At app startup only: hold both fists together for 0.35 seconds, then release both | Activate gesture control |
| Show an open left palm, then pinch right index + thumb and move up/down | Volume up/down |
| Hold a left fist, then pinch right index + thumb and move up/down | Scroll up/down |
| Raise the right index + middle fingers, fold the other two, and move vertically | Two-finger scroll up/down |
| Pinch index + thumb on both hands, then move hands apart/together | Zoom in/out |
| Either hand's index + middle + ring fingers raised, little finger folded and thumb relaxed, then swipe | Right/left: switch apps; up: Task View; down: Show Desktop |

The open left palm explicitly switches into volume mode, so its right-hand index pinch will not also left-click.
Whenever gesture control is activated, AirPoint places the pointer at the center of the virtual desktop once before hand movement begins.
Use **When control starts** to keep the main window open (default), minimize it to the taskbar, or hide it to the notification area while tracking continues.

## Developer mode

Open the **Developer calibration** tab to access live, persistent calibration controls. **Recommended controls** keeps everyday adjustments approachable; **All advanced controls** exposes the full bounded algorithm. The panel now covers adaptive neural-inference and preview rates, asynchronous face rejection, pointer smoothing/prediction/workspace/precision, pinch hysteresis, guarded pinch-scroll arbitration, click/pause/drag timing, scrolling/volume/zoom response, and swipes. Coupled values are normalized into safe relationships, and **Reset defaults** restores the tested baseline.

Three-finger application switching is disabled by default to keep ordinary pointer tracking unchanged. Enable it in Developer calibration under **Swipes**. It uses the center of either hand's index, middle, and ring fingertips; the thumb and little finger must remain folded. Right/left sends Alt+Tab/Alt+Shift+Tab, up opens Windows Task View, and down shows the desktop. The detector scales motion thresholds from palm width, uses an outlier-resistant trajectory estimate, and tolerates one dropped pose frame. Each safeguard can be switched independently in Developer calibration, which also exposes an optional live debug readout in the camera status pill.

## Run

### Windows

Requirements: Windows 10/11, a webcam, and Python 3.10 or newer.

```powershell
.\run.ps1
```

### macOS

Requirements: macOS 12+, a webcam, and Python 3.10 or newer (install via [Homebrew](https://brew.sh): `brew install python`).

```bash
chmod +x run_mac.sh
./run_mac.sh
```

macOS will request two permissions on first launch:
- **Camera** — System Settings → Privacy & Security → Camera
- **Accessibility** — System Settings → Privacy & Security → Accessibility (required for mouse/keyboard control)

Grant both to enable gesture control.

On first launch, the script creates `.venv`, installs dependencies, and the app downloads Google's MediaPipe hand-landmarker model (about 8 MB) into `models/`. The app starts in preview-only mode. Verify that landmarks are stable before pressing **Activate gesture control**.

If Windows blocks the camera, enable **Settings → Privacy & security → Camera → Let desktop apps access your camera**.

The mirrored camera feed is calibrated so left/right labels match your physical hands by default. **Swap L/R** is enabled by default for the mirrored preview; toggle it only if a specific external camera reports them reversed.

Enable **Left-handed** beside the camera selector to mirror every hand-specific feature. The left hand then controls the pointer, clicks, drag, pause, and two-finger scrolling; the right hand becomes the support hand for volume and fist-assisted scrolling. Zoom and startup activation continue to use both hands.

## Start automatically with Windows

Run this once from PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-Startup.ps1"
```

You can also enable **Launch at startup** directly in the Camera preferences. AirPoint starts minimized after Windows sign-in so the gesture-status badge remains available without opening the main window. To remove it from startup, turn the option off or run the same command with `-Remove`.

## Build a standalone Windows installer

Build the versioned PyInstaller bundle and Inno Setup installer:

```powershell
.\build_installer.ps1
```

The distributable installer is written to `installer_output\AirPoint_Setup_1.4.2.exe`. The version comes from `app/__init__.py`, and the same value is embedded in the app executable and passed into Inno Setup. The tracked `AirPoint.spec` file is required for reproducible builds; generated `build/`, `dist/`, and installer output remain excluded from Git.

## Build a macOS .app bundle

On a Mac, run:

```bash
chmod +x build_mac.sh
./build_mac.sh
```

The app bundle and distributable zip are written to `mac_installer/`. Release downloads are recommended for end users.

## Accuracy tips

- Keep both hands 45–100 cm from the camera and avoid strong backlighting.
- Start near the center of the preview. Lower sensitivity for extra precision.
- Make deliberate pinches with a small separation between gestures.
- For volume, keep the left palm clearly open while moving the pinched right hand vertically.

## Architecture

- `app/camera_worker.py` — camera capture and MediaPipe tracking on a dedicated thread
- `app/gestures.py` — gesture geometry, hysteresis, drag/pause state machine
- `app/filters.py` — adaptive One Euro pointer smoothing with reversal-aware prediction
- `app/system_control.py` — platform dispatcher + Windows `SendInput` mouse/keyboard events
- `app/system_control_macos.py` — macOS Quartz/CoreGraphics mouse/keyboard events
- `app/application.py` — Qt desktop interface

The camera requests a high-quality 960×540 MJPEG input with driver-managed exposure, and MediaPipe runs in asynchronous live-stream mode. A phase-preserving scheduler submits at up to 30 FPS with single-frame backpressure, drops to 16 FPS while searching with no hand, and immediately restores the active rate after detection. Hand tracking keeps the accuracy-safe 512-pixel inference frame; preview work is separately capped at 24 FPS and one queued UI frame.
AirPoint also enforces a single running instance so two windows cannot compete for the camera and processor; launching it again restores an existing minimized or notification-area window.
The current gesture is shown in a click-through, always-on-top badge at the bottom-left of the primary display. It stays updated while the main AirPoint window is minimized.
When minimized, AirPoint switches to tracking-only mode: preview rendering and UI telemetry pause while gesture processing retains HighQoS background execution.
Pinches use a calibrated blend of the original 2D thumb-to-fingertip ratio and MediaPipe world-landmark 3D separation, both normalized by palm scale. The 2D signal keeps front-facing contact responsive; the 3D component rejects edge-on projected overlaps. The Developer tab exposes the 3D blend. Deep contact remains immediate, while lightweight ratio smoothing, brief boundary confirmation, and one-frame clear-release dropout protection prevent landmark jitter from creating or interrupting pinches.
Pointer motion uses a responsive One Euro filter plus a tiny radial tremor dead zone. Its confidence gate estimates velocity from timestamps rather than frame count, so steady movement stays responsive across variable inference cadence and dropped frames; rejected landmarks hold the exact last emitted pointer position instead of snapping back behind prediction. Its amplified central workspace reaches screen edges with roughly 20% less physical hand travel while retaining sensitivity adjustment. Face rejection scans a 256-pixel image on a separate worker roughly twice per second, so eyeglasses/face protection no longer stalls capture or neural inference. New tracks wait for two independent clean face-scan source frames before they can become continuity-qualified.
The pointer locks to its last stable position during click pinches and for 25 ms after release, preventing finger closure or separation from moving the click target. Dragging uses an anchored offset so movement begins from the locked cursor position.
Double pinching the right index finger performs the normal first click, then uses a movement threshold on the second pinch: releasing without movement completes a double click, while moving beyond the threshold continues as a drag.
Two-hand zoom requires index-thumb contact on both hands while at least two of the other three fingers remain visibly free; naturally curved free fingers are accepted. A left index pinch is explicitly excluded from left-fist scroll mode. Pinch-center distance is exponentially smoothed, uses a starting-separation-relative 5.5% step, and is rate-limited to one `Ctrl+wheel` step every 90 ms; both pinches must release before clicks resume.
Scroll mode gives a confirmed left fist priority over incidental thumb-index proximity inside the folded hand. A 180 ms fist grace period prevents one-frame landmark flicker from interrupting an active scroll, while a valid open-finger zoom pose still takes priority over scrolling.
Two-finger scrolling requires the index and middle fingers to be extended together while the ring and little fingers remain folded. Move away from the starting position and hold: AirPoint continuously scrolls in that direction, with speed based on distance. A neutral dead zone rejects hand jitter, and pointer movement is suppressed for the duration of the gesture.
One-hand pinch scrolling classifies only the first index pinch and tracks the median palm center rather than fingertip motion. It requires a short hold, three consistent samples, vertical-axis dominance, stable palm scale, sufficient confidence, and bounded frame-to-frame motion. Active scroll is consumed until release, so it cannot leak into a click or arm the next pinch as a drag; the second pinch always retains double-click/drag priority.
Optional **Slider-aware pinch dragging** uses Windows UI Automation or Microsoft Active Accessibility to lock pinch movement to a Slider, ScrollBar, or Thumb. It is disabled by default because accessibility hit-testing can block some systems for tens of milliseconds; enabling it trades latency for one-axis control detection.

## Test

The gesture engine is deliberately independent from Qt, OpenCV, and MediaPipe so it can be unit tested without a camera:

```powershell
# Windows
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

```bash
# macOS
.venv/bin/python3 -m unittest discover -s tests -v
```
