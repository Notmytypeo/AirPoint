# macOS installer output

This folder is where `build_mac.sh` writes macOS installer artifacts:

- `AirPoint.app` — the macOS application bundle.
- `AirPoint-macOS-arm64.zip` or `AirPoint-macOS-x86_64.zip` — the shareable installer archive.

These generated files are intentionally excluded from Git. Download the corresponding zip from the project's GitHub Releases, or run `./build_mac.sh` on a Mac to generate one.
