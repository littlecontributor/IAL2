from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import auto_install


class InstallerRepairTests(unittest.TestCase):
    def test_gradio_import_repair_keeps_the_supported_version_range(self):
        commands = []
        gradio_imports = 0

        def fake_run(command, **_kwargs):
            nonlocal gradio_imports
            commands.append(command)
            if len(command) > 1 and command[1] == "-c":
                import_stmt = command[2]
                if import_stmt.startswith("import gradio"):
                    gradio_imports += 1
                    if gradio_imports == 1:
                        return subprocess.CompletedProcess(
                            command, 1, "", "ImportError: simulated broken Gradio import"
                        )
                return subprocess.CompletedProcess(command, 0, "IMPORT_OK\n", "")
            return subprocess.CompletedProcess(command, 0, "", "")

        output = StringIO()
        with patch.object(auto_install, "run", side_effect=fake_run), redirect_stdout(output):
            broken = auto_install.verify_core_imports("python-test")

        self.assertEqual(broken, [])
        repair_commands = [
            command for command in commands
            if len(command) > 3 and command[1:3] == ["-m", "pip"] and "install" in command
        ]
        self.assertEqual(len(repair_commands), 1)
        self.assertIn("gradio>=4.44.0,<6.0.0", repair_commands[0])
        self.assertIn("simulated broken Gradio import", output.getvalue())
        self.assertIn("Import gradio OK après réinstall", output.getvalue())

    def test_powershell_wrapper_does_not_repeat_python_installation_steps(self):
        script_path = Path(__file__).resolve().parents[1] / "INSTALL.ps1"
        script = script_path.read_text(encoding="utf-8")
        launch = script.index("& $PY_BASE $autoInstaller @argsList")
        return_from_wrapper = script.index("exit $autoInstallExitCode", launch)
        duplicate_check = script.index('Write-Step "4/8 - Verification des imports reels')
        self.assertLess(launch, return_from_wrapper)
        self.assertLess(return_from_wrapper, duplicate_check)
        self.assertIn('pip="gradio>=4.44.0,<6.0.0"', script)

    def test_main_returns_failure_when_final_core_diagnostic_is_not_ready(self):
        initial_report = {
            "python": {"version": "3.11", "ok": True},
            "files": {"ok": True},
            "packages": {"ok": True, "missing_required": [], "broken_required": []},
            "ollama": {"ok": True, "models": []},
            "port": {"port": 7860, "free": True},
            "ready": True,
        }
        broken_report = {
            **initial_report,
            "packages": {"ok": False, "missing_required": [], "broken_required": ["gradio"]},
            "ready": False,
        }
        with (
            patch.object(auto_install.sys, "argv", ["auto_install.py", "--core", "--no-models"]),
            patch.object(auto_install, "diagnostic", side_effect=[initial_report, broken_report]),
            patch.object(auto_install, "ensure_venv", return_value="python-test"),
            patch.object(auto_install, "install_group", return_value=[]),
            patch.object(auto_install, "verify_core_imports", return_value=[]),
            patch.object(auto_install, "ensure_ollama_binary", return_value=True),
            patch.object(auto_install, "ensure_ollama_server", return_value=True),
            patch.object(auto_install.time, "sleep"),
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(auto_install.main(), 1)


if __name__ == "__main__":
    unittest.main()
