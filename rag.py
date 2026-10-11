#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RAG documentaire avec conservation des index existants et embeddings locaux."""
from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = PROJECT_ROOT / "chroma_db"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
LEGACY_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
BGE_M3_MODEL = "bge-m3"


def embedding_collection_name(collection_name: str, embedding_model: str) -> str:
    """Sépare les index vectoriels dont les dimensions/modèles ne sont pas compatibles."""
    if embedding_model == LEGACY_EMBEDDING_MODEL:
        return collection_name
    suffix = (
        embedding_model.casefold()
        .replace(":", "_")
        .replace("/", "_")
        .replace(".", "_")
        .replace("-", "_")
    )
    return f"{collection_name}__{suffix}"


class OllamaEmbeddingFunction:
    """Petit adaptateur SentenceTransformer-compatible vers l'API locale /api/embed."""

    def __init__(self, model: str = BGE_M3_MODEL, host: str = OLLAMA_HOST):
        self.model = model
        self.host = host.rstrip("/")

    def encode(self, texts):
        values = [texts] if isinstance(texts, str) else list(texts)
        if not values:
            return np.empty((0, 0), dtype=np.float32)
        if any(not isinstance(text, str) for text in values):
            raise ValueError("Les textes d'embedding doivent être des chaînes.")
        response = requests.post(
            f"{self.host}/api/embed",
            json={"model": self.model, "input": values},
            timeout=(10, 600),
        )
        response.raise_for_status()
        data = response.json()
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(values):
            raise RuntimeError("Ollama n'a pas renvoyé un vecteur par texte.")
        return np.asarray(vectors, dtype=np.float32)


def _ensure_bge_m3_ready(host: str) -> None:
    try:
        try:
            from . import ai_model_manager
        except ImportError:
            import ai_model_manager
        profile = ai_model_manager.hardware_profile.detect_machine_profile()
        if not ai_model_manager.is_model_compatible(BGE_M3_MODEL, profile):
            reason = ai_model_manager.compatibility_reason(BGE_M3_MODEL, profile)
            raise RuntimeError(f"BGE-M3 est masqué sur cette machine : {reason}")
        installed = ai_model_manager.list_installed_models(host=host)
        if not ai_model_manager.is_model_installed(BGE_M3_MODEL, installed):
            raise RuntimeError("Téléchargez d'abord BGE-M3 depuis l'onglet Modèles IA.")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Impossible de vérifier BGE-M3 dans Ollama : {exc}") from exc


@lru_cache(maxsize=1)
def _load_sentence_transformer(model_name: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


def get_embedding_function(
    embedding_model: str = LEGACY_EMBEDDING_MODEL,
    host: str = OLLAMA_HOST,
):
    """Retourne le modèle demandé; le défaut garde l'ancien index MiniLM intact."""
    if embedding_model == BGE_M3_MODEL:
        _ensure_bge_m3_ready(host)
        return OllamaEmbeddingFunction(BGE_M3_MODEL, host)
    if embedding_model != LEGACY_EMBEDDING_MODEL:
        raise ValueError(f"Modèle d'embedding non autorisé : {embedding_model}")
    try:
        try:
            from . import hardware_profile
        except ImportError:
            import hardware_profile
        profile = hardware_profile.detect_machine_profile()
        if float(profile.get("total_ram_gb") or 0) < 6:
            raise RuntimeError("MiniLM est masqué : au moins 6 Go de RAM sont requis pour le RAG.")
    except ImportError:
        pass
    try:
        return _load_sentence_transformer(embedding_model)
    except ImportError:
        return None


def available_embedding_choices(installed_ollama_models=None, profile=None):
    """Liste les moteurs réellement utilisables, sans basculer l'index historique."""
    try:
        try:
            from . import ai_model_manager
        except ImportError:
            import ai_model_manager
        current = profile or ai_model_manager.hardware_profile.detect_machine_profile()
    except Exception:
        ai_model_manager = None
        current = profile or {}

    choices = []
    total_ram = current.get("total_ram_gb") if isinstance(current, dict) else None
    if (
        isinstance(total_ram, (int, float))
        and total_ram >= 6
        and importlib.util.find_spec("sentence_transformers") is not None
    ):
        choices.append(("MiniLM — index historique conservé", LEGACY_EMBEDDING_MODEL))

    installed = installed_ollama_models
    if installed is None and ai_model_manager:
        try:
            installed = ai_model_manager.list_installed_models(host=OLLAMA_HOST)
        except Exception:
            installed = []
    if ai_model_manager and (
        ai_model_manager.is_model_compatible(BGE_M3_MODEL, current)
        and ai_model_manager.is_model_installed(BGE_M3_MODEL, installed or [])
    ):
        choices.append(("BGE-M3 — nouvel index multilingue (Ollama)", BGE_M3_MODEL))
    return choices


def get_chroma_client():
    try:
        import chromadb
        return chromadb.PersistentClient(path=str(CHROMA_DIR))
    except ImportError:
        return None


def ingest_file(
    file_path: str,
    collection_name: str = "documents",
    embedding_model: str = LEGACY_EMBEDDING_MODEL,
    host: str = OLLAMA_HOST,
):
    """Indexe un PDF/DOCX/TXT/Markdown dans l'index propre au modèle choisi."""
    try:
        import pypdf

        text = ""
        source = Path(file_path)
        if source.suffix.lower() == ".pdf":
            reader = pypdf.PdfReader(str(source))
            for page in reader.pages:
                text += page.extract_text() or ""
        elif source.suffix.lower() in {".txt", ".md"}:
            text = source.read_text(encoding="utf-8", errors="ignore")
        elif source.suffix.lower() == ".docx":
            try:
                import docx2txt
                text = docx2txt.process(str(source))
            except ImportError:
                text = ""
        else:
            text = source.read_text(encoding="utf-8", errors="ignore")

        if not text.strip():
            return False, "Aucun texte extrait"

        chunks = [text[index:index + 1_000] for index in range(0, len(text), 800)]
        client = get_chroma_client()
        if not client:
            return False, "ChromaDB non installé"
        embedding_function = get_embedding_function(embedding_model, host=host)
        if not embedding_function:
            return False, "sentence-transformers non installé; installez BGE-M3 depuis Modèles IA ou les dépendances RAG"

        target_collection_name = embedding_collection_name(collection_name, embedding_model)
        metadata = {"embedding_model": embedding_model}
        collection = client.get_or_create_collection(target_collection_name, metadata=metadata)
        ids = [f"{source.name}_{index}" for index in range(len(chunks))]
        embeddings = embedding_function.encode(chunks).tolist()
        collection.add(ids=ids, documents=chunks, embeddings=embeddings)
        return True, f"{len(chunks)} segments indexés avec {embedding_model} dans {target_collection_name}"
    except Exception as exc:
        return False, f"Erreur RAG : {exc}"


def query(
    question: str,
    collection_name: str = "documents",
    n_results: int = 3,
    embedding_model: str = LEGACY_EMBEDDING_MODEL,
    host: str = OLLAMA_HOST,
) -> str:
    """Recherche dans l'index qui correspond exactement au modèle d'embedding sélectionné."""
    try:
        client = get_chroma_client()
        if not client:
            return "RAG non disponible (ChromaDB manquant)"
        embedding_function = get_embedding_function(embedding_model, host=host)
        if not embedding_function:
            return "RAG non disponible (embeddings manquants)"

        target_collection_name = embedding_collection_name(collection_name, embedding_model)
        collection = client.get_or_create_collection(
            target_collection_name,
            metadata={"embedding_model": embedding_model},
        )
        query_embedding = embedding_function.encode([question]).tolist()
        results = collection.query(query_embeddings=query_embedding, n_results=n_results)
        documents = results.get("documents", [[]])[0]
        if not documents:
            return f"Aucun document indexé avec {embedding_model}. Importez-les à nouveau avec ce moteur."
        context = "\n\n".join(documents)
        return f"Contexte trouvé ({len(documents)} documents, {embedding_model}) :\n{context}\n\n---\nQuestion : {question}"
    except Exception as exc:
        return f"Erreur RAG : {exc}"


def list_collections():
    client = get_chroma_client()
    if not client:
        return []
    try:
        return [collection.name for collection in client.list_collections()]
    except Exception:
        return []
