"""Tests hors ligne du profil matériel et du filtrage des modèles."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import hardware_profile
from model_catalog import LLM_MODELS


class HardwareProfileTests(unittest.TestCase):
    def test_machine_profile_detects_ram_and_nvidia_vram(self):
        with (
            patch.object(hardware_profile, "_memory_bytes", return_value=(32 * 1024**3, 24 * 1024**3)),
            patch.object(hardware_profile, "_detect_nvidia_gpus", return_value=[
                {"name": "GPU test", "vram_gb": 24.0, "kind": "nvidia"},
            ]),
            patch.object(hardware_profile, "_detect_rocm_gpus", return_value=[]),
            patch.object(hardware_profile.platform, "system", return_value="Linux"),
            patch.object(hardware_profile.platform, "machine", return_value="x86_64"),
        ):
            profile = hardware_profile.detect_machine_profile(refresh=True)

        self.assertEqual(profile["total_ram_gb"], 32.0)
        self.assertEqual(profile["gpu_name"], "GPU test")
        self.assertEqual(profile["gpu_vram_gb"], 24.0)
        self.assertEqual(profile["tier"], "haut de gamme")

    def test_heavy_model_requires_ram_or_sufficient_gpu(self):
        coder = next(model for model in LLM_MODELS if model["id"] == "qwen3-coder:30b")
        cpu_mid = {"total_ram_gb": 16, "gpus": []}
        gpu_high = {
            "total_ram_gb": 16,
            "gpus": [{"name": "GPU test", "vram_gb": 24, "kind": "nvidia"}],
        }

        supported, reason = hardware_profile.model_compatibility(coder, cpu_mid)
        self.assertFalse(supported)
        self.assertIn("32 Go", reason)
        supported, reason = hardware_profile.model_compatibility(coder, gpu_high)
        self.assertTrue(supported)
        self.assertIn("GPU détecté", reason)

    def test_vram_threshold_is_checked_separately_from_download_size(self):
        devstral = next(model for model in LLM_MODELS if model["id"] == "devstral-small-2:24b")
        self.assertEqual(devstral["size"], "≈ 15 Go")
        self.assertEqual(devstral["min_ram_gb"], 32)
        self.assertEqual(devstral["min_vram_gb"], 24)
        self.assertEqual(devstral["min_ram_with_gpu_gb"], 16)

        nearly_enough_gpu = {
            "total_ram_gb": 16,
            "gpus": [{"name": "GPU test", "vram_gb": 23.9, "kind": "nvidia"}],
        }
        self.assertFalse(hardware_profile.model_compatibility(devstral, nearly_enough_gpu)[0])
        enough_gpu = {
            "total_ram_gb": 16,
            "gpus": [{"name": "GPU test", "vram_gb": 24, "kind": "nvidia"}],
        }
        self.assertTrue(hardware_profile.model_compatibility(devstral, enough_gpu)[0])
        self.assertTrue(hardware_profile.model_compatibility(devstral, {"total_ram_gb": 32, "gpus": []})[0])

    def test_unknown_ram_fails_closed(self):
        model = next(item for item in LLM_MODELS if item["id"] == "qwen3.5:4b")
        supported, reason = hardware_profile.model_compatibility(model, {"total_ram_gb": None, "gpus": []})
        self.assertFalse(supported)
        self.assertIn("masqué par prudence", reason)

    def test_cached_profile_is_returned_as_a_copy(self):
        with (
            patch.object(hardware_profile, "_memory_bytes", return_value=(16 * 1024**3, 8 * 1024**3)),
            patch.object(hardware_profile, "_detect_nvidia_gpus", return_value=[]),
            patch.object(hardware_profile, "_detect_rocm_gpus", return_value=[]),
            patch.object(hardware_profile.platform, "system", return_value="Linux"),
            patch.object(hardware_profile.platform, "machine", return_value="x86_64"),
        ):
            first = hardware_profile.detect_machine_profile(refresh=True)
            first["total_ram_gb"] = -1
            second = hardware_profile.detect_machine_profile()
        self.assertEqual(second["total_ram_gb"], 16.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
