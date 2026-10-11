#!/usr/bin/env python3
"""Tests hors ligne du générateur de projets et du script de build."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TEMPLATE_DIR = PROJECT_ROOT / "templates" / "python_desktop_app"
sys.path.insert(0, str(SCRIPTS_DIR))

from create_python_app import create_project


def load_build_module():
    spec = importlib.util.spec_from_file_location("template_build_exe", TEMPLATE_DIR / "build_exe.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


build_exe = load_build_module()


class AppScaffoldTests(unittest.TestCase):
    def test_scaffold_creates_named_project_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = create_project("DemoLocal", temp_dir)
            self.assertTrue((project / "main.py").is_file())
            self.assertTrue((project / "build_exe.py").is_file())
            self.assertIn('APP_NAME = "DemoLocal"', (project / "main.py").read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                create_project("DemoLocal", temp_dir)

    def test_scaffold_rejects_unsafe_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for name in ("../outside", "2StartsWithNumber", "bad name", "x" * 41, "CON", "COM1"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    create_project(name, temp_dir)

    def test_build_command_is_scoped_to_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            root = temp_root / "project"
            root.mkdir()
            entry = root / "main.py"
            entry.write_text("print('test')\n", encoding="utf-8")
            command = build_exe.build_command(root, "main.py", "DemoLocal")
            self.assertIn("--windowed", command)
            self.assertIn(str(entry.resolve()), command)
            self.assertEqual(command[1:3], ["-m", "PyInstaller"])

            outside = temp_root / "outside.py"
            outside.write_text("print('outside')\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_exe.build_command(root, "../outside.py", "DemoLocal")

    def test_build_name_is_validated_and_console_is_optional(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "main.py").write_text("print('test')\n", encoding="utf-8")
            for invalid_name in ("../unsafe", "CON"):
                with self.subTest(name=invalid_name), self.assertRaises(ValueError):
                    build_exe.build_command(root, "main.py", invalid_name)
            command = build_exe.build_command(root, "main.py", "CliTool", console=True)
            self.assertNotIn("--windowed", command)


if __name__ == "__main__":
    unittest.main(verbosity=2)
