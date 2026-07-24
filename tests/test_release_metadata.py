import re
import unittest
from pathlib import Path

from app import __version__


ROOT = Path(__file__).resolve().parent.parent


class ReleaseMetadataTests(unittest.TestCase):
    def test_application_version_uses_semver(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_windows_download_links_use_application_version(self):
        filename = f"AirPoint_Setup_{__version__}.exe"
        for relative_path in ("README.md", "windows_installer/README.md"):
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn(filename, text)

    def test_installer_requires_version_from_build_script(self):
        installer = (ROOT / "installer.iss").read_text(encoding="utf-8")
        build_script = (ROOT / "build_installer.ps1").read_text(encoding="utf-8")

        self.assertIn("#ifndef MyAppVersion", installer)
        self.assertNotRegex(installer, r'#define MyAppVersion\s+"\d')
        self.assertIn("from app import __version__", build_script)

    def test_windows_workflow_has_no_hardcoded_installer_version(self):
        workflow = (ROOT / ".github/workflows/windows-installer.yml").read_text(encoding="utf-8")

        self.assertNotIn("AirPoint_Setup_1.0.0.exe", workflow)
        self.assertIsNone(re.search(r"AirPoint_Setup_\d+\.\d+\.\d+\.exe", workflow))

    def test_macos_workflow_uses_supported_intel_runner(self):
        workflow = (ROOT / ".github/workflows/macos-installer.yml").read_text(encoding="utf-8")

        self.assertIn("runner: macos-15-intel", workflow)
        self.assertNotIn("runner: macos-13", workflow)

    def test_requirements_support_intel_macos_mediapipe(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("mediapipe>=0.10.21,<0.11", requirements)
        self.assertIn("opencv-contrib-python>=4.11,<5", requirements)
        self.assertIn("numpy>=1.26,<3", requirements)


if __name__ == "__main__":
    unittest.main()
