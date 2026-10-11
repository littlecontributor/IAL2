#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests unitaires hors ligne des modèles, du client Ollama et du nettoyage."""
import base64
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import ai_model_manager
import auto_cleaner
import auto_install
import llm
from scripts import ai_model_manager as packaged_model_manager
from model_catalog import DEFAULT_INSTALL_MODELS, DEFAULT_MODEL, LLM_MODELS, MODELS_CATALOG, ModelCategory


class ModelCatalogTests(unittest.TestCase):
    def test_catalog_contains_current_recommendations(self):
        ids = [model["id"] for model in LLM_MODELS]
        self.assertEqual(len(ids), len(set(ids)))
        for model_id in (
            "qwen3.8:27b",
            "qwen3.5:9b",
            "gemma4:12b",
            "gpt-oss:20b",
            "deepseek-r1:8b",
            "qwen3.5:4b",
            "qwen2.5-coder:7b",
            "devstral-small-2:24b",
            "qwen3-coder:30b",
        ):
            self.assertIn(model_id, ids)
        embedding_ids = [model.get("id") for model in MODELS_CATALOG[ModelCategory.EMBEDDING]]
        self.assertIn("bge-m3", embedding_ids)
        self.assertEqual(DEFAULT_MODEL, "qwen3.5:9b")
        self.assertEqual(DEFAULT_INSTALL_MODELS, ("qwen3.5:9b",))

    def test_model_categories_no_longer_include_3d(self):
        self.assertNotIn("3d", {category.value for category in ModelCategory})
        self.assertNotIn("THREED", ModelCategory.__members__)

    def test_model_pull_rejects_ids_outside_the_catalog(self):
        with self.assertRaises(ValueError):
            list(ai_model_manager.install_model_stream("not-a-curated-model"))

    def test_model_pull_reports_stream_progress(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [
            b'{"status":"pulling manifest"}',
            b'{"status":"downloading","completed":50,"total":100}',
            b'{"status":"success"}',
        ]
        high_profile = {"system": "Test", "architecture": "test", "total_ram_gb": 64, "gpus": [], "tier": "haut de gamme"}
        with (
            patch.object(ai_model_manager.hardware_profile, "detect_machine_profile", return_value=high_profile),
            patch("requests.post", return_value=response) as post,
        ):
            progress = list(ai_model_manager.install_model_stream("qwen3.5:4b"))

        self.assertEqual(len(progress), 4)
        self.assertIn("Préparation", progress[0])
        self.assertIn("50%", progress[2])
        self.assertIn("installé et prêt", progress[-1])
        self.assertTrue(post.called)
        self.assertEqual(post.call_args.kwargs["json"]["name"], "qwen3.5:4b")

    def test_coding_models_are_allowed_for_curated_installation(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [b'{"status":"success"}']
        high_profile = {"system": "Test", "architecture": "test", "total_ram_gb": 64, "gpus": [], "tier": "haut de gamme"}
        with (
            patch.object(ai_model_manager.hardware_profile, "detect_machine_profile", return_value=high_profile),
            patch("requests.post", return_value=response) as post,
        ):
            for model_id in ("qwen2.5-coder:7b", "qwen3-coder:30b"):
                progress = list(ai_model_manager.install_model_stream(model_id))
                self.assertIn("installé et prêt", progress[-1])

        self.assertEqual(post.call_count, 2)

    def test_installed_llm_list_excludes_models_not_suited_to_machine(self):
        low_profile = {"system": "Test", "architecture": "test", "total_ram_gb": 8, "gpus": [], "tier": "entrée de gamme"}
        installed = ["qwen3.5:4b", "qwen3.5:9b", "bge-m3:latest", "custom:latest"]
        llms = ai_model_manager.filter_compatible_installed_models(installed, low_profile)
        embeddings = ai_model_manager.filter_compatible_installed_models(
            installed, low_profile, category=ModelCategory.EMBEDDING
        )
        self.assertEqual(llms, ["qwen3.5:4b"])
        self.assertEqual(embeddings, ["bge-m3:latest"])

    def test_incompatible_heavy_model_download_is_blocked(self):
        low_profile = {"system": "Test", "architecture": "test", "total_ram_gb": 8, "gpus": [], "tier": "entrée de gamme"}
        with patch.object(ai_model_manager.hardware_profile, "detect_machine_profile", return_value=low_profile):
            with self.assertRaisesRegex(ValueError, "n'est pas proposé"):
                list(ai_model_manager.install_model_stream("devstral-small-2:24b"))

    def test_direct_install_paths_cannot_bypass_hardware_filter(self):
        low_profile = {"system": "Test", "architecture": "test", "total_ram_gb": 4, "gpus": [], "tier": "entrée de gamme"}
        with (
            patch.object(ai_model_manager.hardware_profile, "detect_machine_profile", return_value=low_profile),
            patch.object(ai_model_manager.subprocess, "run") as run_command,
        ):
            self.assertFalse(ai_model_manager.install_ollama_model("devstral-small-2:24b"))
            self.assertFalse(ai_model_manager.install_by_category("llm", "devstral-small-2:24b"))
            self.assertFalse(ai_model_manager.install_by_category("embedding", "bge-m3"))
            self.assertFalse(ai_model_manager.install_by_category("llm", "bge-m3"))
            self.assertFalse(ai_model_manager.install_by_category("embedding", "devstral-small-2:24b"))
            self.assertFalse(ai_model_manager.install_by_category("llm"))
            self.assertFalse(ai_model_manager.install_all())

        run_command.assert_not_called()

    def test_installer_does_not_download_a_default_model(self):
        with (
            patch.object(auto_install, "ensure_ollama_server") as ensure_server,
            patch.object(ai_model_manager, "install_ollama_model") as install,
        ):
            auto_install.install_ollama_models()
        ensure_server.assert_not_called()
        install.assert_not_called()

    def test_installer_blocks_explicit_model_when_hardware_is_insufficient(self):
        low_profile = {"system": "Test", "architecture": "test", "total_ram_gb": 8, "gpus": [], "tier": "entrée de gamme"}
        with (
            patch.object(
                auto_install.shutil,
                "which",
                side_effect=lambda name: "/usr/bin/ollama" if name == "ollama" else None,
            ),
            patch.object(auto_install, "ensure_ollama_server", return_value=True),
            patch.object(packaged_model_manager, "list_installed_models", return_value=[]),
            patch.object(packaged_model_manager.hardware_profile, "detect_machine_profile", return_value=low_profile),
            patch.object(packaged_model_manager.subprocess, "run") as run_command,
        ):
            auto_install.install_ollama_models(["devstral-small-2:24b"])
        run_command.assert_not_called()

    def test_small_machine_default_suggestion_is_hardware_compatible(self):
        low_profile = {"system": "Test", "architecture": "test", "total_ram_gb": 8, "gpus": [], "tier": "entrée de gamme"}
        self.assertEqual(ai_model_manager.select_default_install_model(low_profile), "qwen3.5:4b")

    def test_bge_m3_can_be_downloaded_from_the_curated_embedding_catalog(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [b'{"status":"success"}']
        high_profile = {"system": "Test", "architecture": "test", "total_ram_gb": 64, "gpus": [], "tier": "haut de gamme"}
        with (
            patch.object(ai_model_manager.hardware_profile, "detect_machine_profile", return_value=high_profile),
            patch("requests.post", return_value=response) as post,
        ):
            updates = list(ai_model_manager.install_model_stream("bge-m3"))
        self.assertIn("installé et prêt", updates[-1])
        self.assertEqual(post.call_args.kwargs["json"]["name"], "bge-m3")
        self.assertTrue(ai_model_manager.is_installable_model("bge-m3"))


class OllamaClientTests(unittest.TestCase):
    def test_chat_builds_history_and_encodes_attached_image(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"message": {"content": "Une image."}}
        with tempfile.NamedTemporaryFile(suffix=".png") as image:
            image.write(b"test-image-bytes")
            image.flush()
            with patch("requests.post", return_value=response) as post:
                answer = llm.chat(
                    "Que vois-tu ?",
                    model="qwen3.5:9b",
                    history=[("Bonjour", "Bonjour !")],
                    system="Réponds en français.",
                    temperature=0.4,
                    host="http://127.0.0.1:11434/",
                    image_path=image.name,
                    response_format="json",
                )

        self.assertEqual(answer, "Une image.")
        payload = post.call_args.kwargs["json"]
        messages = payload["messages"]
        self.assertEqual(messages[0], {"role": "system", "content": "Réponds en français."})
        self.assertEqual(messages[1]["content"], "Bonjour")
        self.assertEqual(messages[2]["content"], "Bonjour !")
        self.assertEqual(messages[-1]["content"], "Que vois-tu ?")
        self.assertEqual(messages[-1]["images"], [base64.b64encode(b"test-image-bytes").decode("ascii")])
        self.assertEqual(payload["options"]["temperature"], 0.4)
        self.assertEqual(payload["format"], "json")

    def test_missing_image_path_is_rejected(self):
        with self.assertRaises(ValueError):
            llm.build_messages("Analyse ça", image_path="/file/qui/nexiste/pas.png")


class CleanerTests(unittest.TestCase):
    def test_cleaner_preserves_the_persistent_rag_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs = root / "outputs"
            rag_db = root / "chroma_db"
            outputs.mkdir()
            rag_db.mkdir()
            output_file = outputs / "old.wav"
            rag_file = rag_db / "indexed-document.bin"
            output_file.write_text("temporary", encoding="utf-8")
            rag_file.write_text("persistent", encoding="utf-8")
            old_time = time.time() - 7200
            import os
            os.utime(output_file, (old_time, old_time))
            os.utime(rag_file, (old_time, old_time))

            with patch.object(auto_cleaner, "PROJECT_ROOT", root):
                cleaned = auto_cleaner.clean_temp(max_age_hours=1, dry_run=False)

            self.assertIn(str(output_file), cleaned)
            self.assertFalse(output_file.exists())
            self.assertTrue(rag_file.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
