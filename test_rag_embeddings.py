"""Tests hors ligne du nouvel embedding Ollama et de la séparation des index."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import ai_model_manager
import rag


class RagEmbeddingTests(unittest.TestCase):
    def test_bge_adapter_uses_local_ollama_embed_endpoint(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
        with patch("requests.post", return_value=response) as post:
            vectors = rag.OllamaEmbeddingFunction("bge-m3", "http://ollama.local/").encode(["bonjour", "code"])

        self.assertEqual(vectors.shape, (2, 2))
        self.assertEqual(post.call_args.args[0], "http://ollama.local/api/embed")
        self.assertEqual(post.call_args.kwargs["json"], {"model": "bge-m3", "input": ["bonjour", "code"]})

    def test_bge_adapter_rejects_incomplete_response(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"embeddings": [[0.1, 0.2]]}
        with (
            patch("requests.post", return_value=response),
            self.assertRaisesRegex(RuntimeError, "un vecteur par texte"),
        ):
            rag.OllamaEmbeddingFunction().encode(["un", "deux"])

    def test_each_embedding_model_uses_a_separate_chroma_index(self):
        self.assertEqual(
            rag.embedding_collection_name("documents", rag.LEGACY_EMBEDDING_MODEL),
            "documents",
        )
        self.assertEqual(
            rag.embedding_collection_name("documents", rag.BGE_M3_MODEL),
            "documents__bge_m3",
        )

    def test_ingestion_writes_bge_vectors_to_its_own_index(self):
        collection = Mock()
        client = Mock()
        client.get_or_create_collection.return_value = collection
        encoder = Mock()
        vectors = Mock()
        vectors.tolist.return_value = [[0.1, 0.2]]
        encoder.encode.return_value = vectors

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "notes.txt"
            source.write_text("Texte à indexer.", encoding="utf-8")
            with (
                patch.dict(sys.modules, {"pypdf": types.ModuleType("pypdf")}),
                patch.object(rag, "get_chroma_client", return_value=client),
                patch.object(rag, "get_embedding_function", return_value=encoder),
            ):
                success, message = rag.ingest_file(str(source), embedding_model=rag.BGE_M3_MODEL)

        self.assertTrue(success)
        self.assertIn("documents__bge_m3", message)
        client.get_or_create_collection.assert_called_once_with(
            "documents__bge_m3",
            metadata={"embedding_model": rag.BGE_M3_MODEL},
        )
        collection.add.assert_called_once()
        self.assertEqual(collection.add.call_args.kwargs["ids"], ["notes.txt_0"])

    def test_bge_query_uses_its_matching_index(self):
        collection = Mock()
        collection.query.return_value = {"documents": [["Passage pertinent."]]}
        client = Mock()
        client.get_or_create_collection.return_value = collection
        encoder = Mock()
        vectors = Mock()
        vectors.tolist.return_value = [[0.1, 0.2]]
        encoder.encode.return_value = vectors

        with (
            patch.object(rag, "get_chroma_client", return_value=client),
            patch.object(rag, "get_embedding_function", return_value=encoder),
        ):
            answer = rag.query("Que dit le document ?", embedding_model=rag.BGE_M3_MODEL)

        self.assertIn("Passage pertinent.", answer)
        client.get_or_create_collection.assert_called_once_with(
            "documents__bge_m3",
            metadata={"embedding_model": rag.BGE_M3_MODEL},
        )
        self.assertEqual(collection.query.call_args.kwargs["query_embeddings"], [[0.1, 0.2]])

    def test_bge_is_offered_only_if_installed_and_compatible(self):
        high_profile = {"total_ram_gb": 16, "gpus": []}
        with patch("importlib.util.find_spec", return_value=None):
            choices = rag.available_embedding_choices(["bge-m3:latest"], high_profile)
        self.assertEqual(choices, [("BGE-M3 — nouvel index multilingue (Ollama)", "bge-m3")])

        low_profile = {"total_ram_gb": 4, "gpus": []}
        with patch("importlib.util.find_spec", return_value=None):
            hidden = rag.available_embedding_choices(["bge-m3:latest"], low_profile)
        self.assertEqual(hidden, [])

    def test_bge_backend_requires_the_local_model_to_be_installed(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"models": []}
        high_profile = {"system": "Test", "architecture": "test", "total_ram_gb": 16, "gpus": []}
        with (
            patch.object(ai_model_manager.hardware_profile, "detect_machine_profile", return_value=high_profile),
            patch("requests.get", return_value=response),
            self.assertRaisesRegex(RuntimeError, "Téléchargez d'abord BGE-M3"),
        ):
            rag.get_embedding_function(rag.BGE_M3_MODEL, host="http://ollama.local")


if __name__ == "__main__":
    unittest.main(verbosity=2)
