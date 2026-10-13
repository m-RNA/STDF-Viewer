"""Run the batch file through cmd, including quoted file arguments and failures."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows batch launcher")
class WindowsLauncherTests(unittest.TestCase):
    def setUp(self):
        area = ROOT / "logs/site-map-qa/launcher"
        area.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="viewer 中文 & ! ", dir=area)
        self.root = Path(self.temporary.name).resolve()
        self.assertTrue(self.root.is_relative_to(area.resolve()))
        self.addCleanup(self.temporary.cleanup)
        shutil.copyfile(ROOT / "start-viewer.bat", self.root / "start-viewer.bat")
        (self.root / "STDF-Viewer.py").write_text(
            "import json, os, sys\nfrom pathlib import Path\n"
            "Path('captured.json').write_text(json.dumps({'argv': sys.argv[1:], "
            "'cwd': os.getcwd(), 'platform': os.environ.get('QT_QPA_PLATFORM')}), "
            "encoding='utf-8')\n", encoding="utf-8")

    def copyEnvironment(self):
        source = Path(sys.executable).resolve().parent
        if not (source.parent / "pyvenv.cfg").is_file() or not (source / "pythonw.exe").is_file():
            self.skipTest("Requires a Windows virtual environment")
        scripts = self.root / ".venv/Scripts"
        scripts.mkdir(parents=True)
        for name in ("python.exe", "pythonw.exe"):
            shutil.copyfile(source / name, scripts / name)
        shutil.copyfile(source.parent / "pyvenv.cfg", scripts.parent / "pyvenv.cfg")
        return source.parent / "Lib/site-packages"

    def runLauncher(self, args=(), packages=None):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        if packages is not None:
            env["PYTHONPATH"] = str(packages)
        files = " ".join(f'"{arg}"' for arg in args)
        command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{self.root / "start-viewer.bat"}" {files}"'
        return subprocess.run(command, cwd=ROOT.parent, env=env, input="\n",
                              capture_output=True, encoding="utf-8", errors="replace", timeout=20)

    def test_missing_environment_fails_with_visible_message(self):
        result = self.runLauncher()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(".venv Python environment is missing", result.stdout)
        self.assertFalse((self.root / "captured.json").exists())

    def test_missing_dependencies_fail_without_launching(self):
        self.copyEnvironment()
        result = self.runLauncher()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("dependencies are unavailable", result.stdout)
        self.assertIn("ModuleNotFoundError", (self.root / "logs/launcher-check.log").read_text(encoding="utf-8"))
        self.assertFalse((self.root / "captured.json").exists())

    def test_launch_uses_project_folder_and_preserves_file_arguments(self):
        modules = ("PyQt5", "numpy", "pydantic", "pyqtgraph", "tomlkit", "xlsxwriter", "rust_stdf_helper")
        if any(importlib.util.find_spec(module) is None for module in modules):
            self.skipTest("Viewer dependencies unavailable")
        packages = self.copyEnvironment()
        files = [str(self.root / "测试 A & B!.stdf"), str(self.root / "second file.stdf.gz")]
        result = self.runLauncher(files, packages)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        captured = self.root / "captured.json"
        deadline = time.monotonic() + 10
        while not captured.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue(captured.exists(), result.stdout + result.stderr)
        data = json.loads(captured.read_text(encoding="utf-8"))
        self.assertEqual(data["argv"], files)
        self.assertEqual(Path(data["cwd"]), self.root)
        self.assertEqual(data["platform"], "windows")
        self.assertEqual((self.root / "logs/launcher-check.log").read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
