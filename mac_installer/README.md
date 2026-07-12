# Install AirPoint on macOS

AirPoint lets you control the pointer, clicks, scrolling, zoom, and volume with hand gestures. It works entirely on your Mac; camera frames are not uploaded.

## 1. Download the right file

Open the [latest AirPoint release](https://github.com/Notmytypeo/AirPoint/releases/latest).

- For a Mac with an **Apple chip** (M1, M2, M3, or M4), download `AirPoint-macOS-arm64.zip`.
- For an older **Intel** Mac, download `AirPoint-macOS-x86_64.zip` when it is available on the release page.

To check which Mac you have, select **Apple menu > About This Mac**. The **Chip** line says Apple or Intel.

## 2. Install the app

1. Double-click the downloaded zip file in Downloads.
2. Drag `AirPoint.app` into the **Applications** folder.
3. Open Applications, then **right-click AirPoint** and choose **Open**.
4. Choose **Open** again in the macOS security prompt.

The right-click step is needed only the first time because this app is not Apple-notarized.

## 3. Allow required permissions

AirPoint needs two permissions. Keep the app open while you set them.

1. Open **System Settings > Privacy & Security > Camera** and turn on AirPoint.
2. Open **System Settings > Privacy & Security > Accessibility** and turn on AirPoint.

If AirPoint is not listed, click **+**, choose `AirPoint.app` from Applications, then turn its switch on. Restart AirPoint afterward.

## 4. Start using it

1. Open AirPoint from Applications.
2. Choose the correct camera if you have more than one.
3. Stand or sit about 45–100 cm from the camera with good front lighting.
4. Wait until the preview shows stable hand landmarks.
5. Click **Enable control**. The app minimizes while gesture control stays active.

To pause, hold **both fists** for about a second. While paused, hold the pointer-hand fist to resume. Close AirPoint normally from its window to stop it.

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

For the complete gesture list and calibration controls, see the repository [README](../README.md).

## Troubleshooting

- **No camera preview:** confirm the Camera permission and close other apps that are using the camera.
- **Preview works but the pointer does not move:** confirm the Accessibility permission, then quit and reopen AirPoint.
- **macOS says the app cannot be opened:** ensure you moved it into Applications, then right-click it and choose **Open**.
- **The app will not open at all:** download the installer matching the Mac's chip (Apple Silicon vs Intel).

## For developers

This folder is also the output location for `build_mac.sh`:

- `AirPoint.app` is the macOS application bundle.
- `AirPoint-macOS-arm64.zip` or `AirPoint-macOS-x86_64.zip` is the shareable installer archive.

Generated installers are intentionally excluded from Git and are distributed through GitHub Releases.
