# Install AirPoint on Windows

AirPoint turns hand gestures into pointer movement, clicks, scrolling, zoom, and volume control.

Your camera frames stay on your PC and are never uploaded.

## 1. Download and install

1. Download [AirPoint_Setup_1.2.0.exe](https://github.com/Notmytypeo/AirPoint/releases/latest/download/AirPoint_Setup_1.2.0.exe).
2. Double-click the downloaded file.
3. Follow the setup steps and choose **Install**.
4. Start AirPoint from the desktop shortcut or Start menu.

If Windows shows **“Windows protected your PC”**, select **More info**, then **Run anyway**. This is expected because the app is not code-signed yet.

## 2. Allow camera access

When AirPoint opens for the first time, allow camera access. If the preview is black or no camera is found:

1. Open **Settings > Privacy & security > Camera**.
2. Turn on **Camera access**.
3. Turn on **Let desktop apps access your camera**.
4. Close and reopen AirPoint.

## 3. Start using AirPoint

1. Select the correct camera if you have more than one.
2. Sit about 45–100 cm from the camera with good front lighting.
3. Wait until the preview shows stable hand landmarks.
4. Click **Enable control**. The app minimizes while gesture control stays active.

To pause control, hold **both fists** for about a second. While paused, hold the pointer-hand fist to resume. Close AirPoint normally from its window to stop it.

## Common gestures

| Gesture | Result |
|---|---|
| Move your pointer-hand index finger | Move the pointer |
| Pinch pointer-hand index finger and thumb | Left click |
| Pinch pointer-hand middle finger and thumb | Right click |
| Pinch twice quickly | Double click; hold the second pinch and move to drag |
| Open the support-hand palm, then pinch and move up/down | Change volume |
| Pointer-hand index and middle fingers raised | Scroll |
| Pinch on both hands and move apart/together | Zoom |

## Troubleshooting

- **No camera preview:** check the Camera settings above and close other apps using the camera.
- **Manual focus says N/A:** the camera driver does not expose focus to AirPoint. Try **Camera controls…** in Camera preferences for the driver's native options.
- **Cursor moves unexpectedly:** pause AirPoint with both fists, then adjust lighting or hand distance before resuming.
- **AirPoint will not start:** reinstall it from the installer download and restart Windows if necessary.

## For developers

The Windows setup executable is built from `installer.iss` after running `build_exe.ps1`. Generated installers are intentionally kept out of Git and published through GitHub Releases.
