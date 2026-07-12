# AirPoint

AirPoint is a local Windows and macOS desktop app that turns two-hand camera gestures into mouse and system-volume controls. Camera frames are processed on-device with MediaPipe; frames are never uploaded.

## Gestures

| Gesture | Action |
|---|---|
| Move right index finger | Move pointer |
| Right index finger + thumb pinch | Left click (other fingers may be folded) |
| Right middle finger + thumb pinch, with index/ring/little fingers open | Right click |
| Repeat the index pinch quickly, then release without moving | Double click |
| Repeat the index pinch, then hold and move beyond the threshold | Drag; release to drop |
| Hold both fists for 0.7 seconds | Pause gesture control |
| While paused, hold the active pointer-hand fist for 0.7 seconds | Resume gesture control |
| At app startup only: hold both fists together for 0.35 seconds, then release both | Activate gesture control |
| Show an open left palm, then pinch right index + thumb and move up/down | Volume up/down |
| Hold a left fist, then pinch right index + thumb and move up/down | Scroll up/down |
| Raise the right index + middle fingers, fold the other two, and move vertically | Two-finger scroll up/down |
| Pinch index + thumb on both hands, then move hands apart/together | Zoom in/out |
| Optional: either hand's index + middle + ring fingers, thumb/little folded, then swipe | Right/left: switch apps; up: Task View; down: Show Desktop |

The open left palm explicitly switches into volume mode, so its right-hand index pinch will not also left-click.
Whenever gesture control is activated, AirPoint places the pointer at the center of the virtual desktop once before hand movement begins.

## Developer mode

Open the **Developer calibration** tab to access live, persistent calibration controls. Every control has a short in-app description and safe bounds. The panel covers pointer smoothing/prediction/workspace/precision, pinch thresholds and hysteresis, click/pause/drag timing, scrolling/volume/zoom response, and swipe tabs. **Reset defaults** restores the tested baseline.

Three-finger application switching is disabled by default to keep ordinary pointer tracking unchanged. Enable it in Developer calibration under **Swipes**. It uses the raw center of either hand's index, middle, and ring fingertips; the thumb and little finger must remain folded. Right/left sends Alt+Tab/Alt+Shift+Tab, up opens Windows Task View, and down shows the desktop. The Swipes controls expose all thresholds and an optional live debug readout in the camera status pill.

## Download and install

- **Windows:** download **`AirPoint_Setup_1.0.0.exe`** from the [latest release](https://github.com/Notmytypeo/AirPoint/releases/latest), run it, and follow the installer. No Python installation is required.
- **macOS:** download the **`AirPoint-macOS-*.zip`** file from the [latest release](https://github.com/Notmytypeo/AirPoint/releases/latest), unzip it, then drag `AirPoint.app` to Applications. The first launch requires right-clicking the app and choosing **Open** because it is not Apple-notarized.

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

AirPoint starts maximized after Windows sign-in, with PowerShell hidden. To remove it from startup, run the same command with `-Remove`.

## Build a standalone Windows installer

Build the PyInstaller one-folder bundle, then compile `installer.iss` with Inno Setup:

```powershell
.\build_exe.ps1
iscc .\installer.iss
```

The distributable installer is written to `installer_output\AirPoint_Setup_1.0.0.exe`. The tracked `AirPoint.spec` file is required for reproducible builds; generated `build/`, `dist/`, and installer output remain excluded from Git.

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
- `app/filters.py` — adaptive One Euro pointer smoothing
- `app/system_control.py` — platform dispatcher + Windows `SendInput` mouse/keyboard events
- `app/system_control_macos.py` — macOS Quartz/CoreGraphics mouse/keyboard events
- `app/application.py` — Qt desktop interface

The camera requests the original high-quality 960×540 MJPEG input with driver-managed exposure, and MediaPipe runs in asynchronous live-stream mode. New frames replace stale work instead of waiting in a processing queue. Hand tracking uses the original 512-pixel inference frame and 768-pixel preview pipeline.
AirPoint also enforces a single running instance so two windows cannot compete for the camera and processor.
When minimized, AirPoint switches to tracking-only mode: preview rendering and UI telemetry pause while gesture processing retains HighQoS background execution.
Pinches use a calibrated blend of the original 2D thumb-to-fingertip ratio and MediaPipe world-landmark 3D separation, both normalized by palm scale. The 2D signal keeps front-facing contact responsive; the 3D component rejects edge-on projected overlaps. The Developer tab exposes the 3D blend. Deep contact and clear release remain immediate, while lightweight ratio smoothing, brief boundary confirmation, and release dropout protection prevent landmark jitter from creating or interrupting pinches.
Pointer motion uses a responsive One Euro filter plus a tiny radial tremor dead zone. Its amplified central workspace reaches screen edges with roughly 20% less physical hand travel while retaining sensitivity adjustment. Tracking uses a 512-pixel inference frame, while the lighter preview can refresh at up to 45 FPS and UI telemetry is throttled separately from gesture processing.
The pointer locks to its last stable position during click pinches and for 85 ms after release, preventing finger closure or separation from moving the click target. Dragging uses an anchored offset so movement begins from the locked cursor position.
Double pinching the right index finger performs the normal first click, then uses a movement threshold on the second pinch: releasing without movement completes a double click, while moving beyond the threshold continues as a drag.
Two-hand zoom requires index-thumb contact on both hands while at least two of the other three fingers remain visibly free; naturally curved free fingers are accepted. A left index pinch is explicitly excluded from left-fist scroll mode. Pinch-center distance is exponentially smoothed, uses a starting-separation-relative 5.5% step, and is rate-limited to one `Ctrl+wheel` step every 90 ms; both pinches must release before clicks resume.
Scroll mode gives a confirmed left fist priority over incidental thumb-index proximity inside the folded hand. A 180 ms fist grace period prevents one-frame landmark flicker from interrupting an active scroll, while a valid open-finger zoom pose still takes priority over scrolling.
Two-finger scrolling requires the index and middle fingers to be extended together while the ring and little fingers remain folded. Move away from the starting position and hold: AirPoint continuously scrolls in that direction, with speed based on distance. A neutral dead zone rejects hand jitter, and pointer movement is suppressed for the duration of the gesture.
When an index pinch begins over a Slider, ScrollBar, or Thumb exposed through Windows UI Automation or Microsoft Active Accessibility, AirPoint switches that pinch into a one-axis drag. Horizontal controls lock Y movement, vertical controls lock X movement, and motion is clamped to the control bounds. Controls that expose neither accessibility interface keep the normal locked-pointer click behavior.

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
