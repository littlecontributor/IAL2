#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Catalogue curaté des modèles locaux IA Locale (mis à jour le 05/10/2026).

Les tailles sont les poids à télécharger, non la mémoire nécessaire à l'inférence.
Les seuils matériels sont des estimations conservatrices qui servent à masquer les
modèles trop exigeants; un résultat positif ne garantit ni vitesse ni qualité.
"""
from enum import Enum


class ModelCategory(str, Enum):
    LLM = "llm"
    STT = "stt"
    TTS = "tts"
    IMAGE = "image"
    EMBEDDING = "embedding"


LLM_MODELS = [
    {
        "id": "qwen3.8:27b",
        "name": "Qwen 3.8 · 27B",
        "size": "≈ 18 Go",
        "memory": "32 Go RAM (CPU) ou VRAM GPU 24 Go + 16 Go RAM système",
        "use_case": "Meilleur choix haut de gamme : code, recherche, raisonnement et tâches longues",
        "capabilities": "Texte · images · raisonnement",
        "license": "Apache-2.0",
        "recommended": False,
        "min_ram_gb": 32,
        "min_vram_gb": 24,
        "min_ram_with_gpu_gb": 16,
        "source_url": "https://ollama.com/library/qwen3.8:27b",
    },
    {
        "id": "qwen3.5:9b",
        "name": "Qwen 3.5 · 9B",
        "size": "≈ 6,6 Go",
        "memory": "16 Go RAM (CPU) ou VRAM GPU 10 Go + 8 Go RAM système",
        "use_case": "Équilibre recommandé : français, usage général, code et documents",
        "capabilities": "Texte · images · raisonnement",
        "license": "Apache-2.0",
        "recommended": True,
        "min_ram_gb": 16,
        "min_vram_gb": 10,
        "min_ram_with_gpu_gb": 8,
        "source_url": "https://ollama.com/library/qwen3.5:9b",
    },
    {
        "id": "gemma4:12b",
        "name": "Gemma 4 · 12B",
        "size": "≈ 7,7 Go",
        "memory": "16 Go RAM (CPU) ou VRAM GPU 12 Go + 8 Go RAM système",
        "use_case": "Bon raisonnement et vision dans un format intermédiaire",
        "capabilities": "Texte · images · raisonnement",
        "license": "Apache-2.0",
        "recommended": False,
        "min_ram_gb": 16,
        "min_vram_gb": 12,
        "min_ram_with_gpu_gb": 8,
        "source_url": "https://ollama.com/library/gemma4:12b",
    },
    {
        "id": "gpt-oss:20b",
        "name": "gpt-oss · 20B",
        "size": "≈ 14 Go",
        "memory": "24 Go RAM (CPU) ou VRAM GPU 16 Go + 12 Go RAM système",
        "use_case": "Raisonnement poussé sur texte; suit le protocole JSON de l'agent intégré",
        "capabilities": "Texte · raisonnement",
        "license": "Apache-2.0",
        "recommended": False,
        "min_ram_gb": 24,
        "min_vram_gb": 16,
        "min_ram_with_gpu_gb": 12,
        "source_url": "https://ollama.com/library/gpt-oss:20b",
    },
    {
        "id": "deepseek-r1:8b",
        "name": "DeepSeek R1 · 8B",
        "size": "≈ 5,2 Go",
        "memory": "12 Go RAM (CPU) ou VRAM GPU 8 Go + 8 Go RAM système",
        "use_case": "Spécialiste compact pour raisonnement, logique et mathématiques",
        "capabilities": "Texte · raisonnement",
        "license": "MIT (variante distillée Qwen)",
        "recommended": False,
        "min_ram_gb": 12,
        "min_vram_gb": 8,
        "min_ram_with_gpu_gb": 8,
        "source_url": "https://ollama.com/library/deepseek-r1:8b",
    },
    {
        "id": "qwen3.5:4b",
        "name": "Qwen 3.5 · 4B",
        "size": "≈ 3,4 Go",
        "memory": "8 Go RAM (CPU) ou VRAM GPU 6 Go + 8 Go RAM système",
        "use_case": "Pour commencer sur un PC modeste, tout en gardant une entrée image",
        "capabilities": "Texte · images · raisonnement",
        "license": "Apache-2.0",
        "recommended": False,
        "min_ram_gb": 8,
        "min_vram_gb": 6,
        "min_ram_with_gpu_gb": 8,
        "source_url": "https://ollama.com/library/qwen3.5:4b",
    },
    {
        "id": "qwen2.5-coder:7b",
        "name": "Qwen 2.5 Coder · 7B",
        "size": "≈ 4,7 Go",
        "memory": "12 Go RAM (CPU) ou VRAM GPU 8 Go + 8 Go RAM système",
        "use_case": "Code, débogage et petites applications sur un PC personnel",
        "capabilities": "Texte · programmation",
        "license": "Apache-2.0",
        "recommended": False,
        "min_ram_gb": 12,
        "min_vram_gb": 8,
        "min_ram_with_gpu_gb": 8,
        "source_url": "https://ollama.com/library/qwen2.5-coder:7b",
    },
    {
        "id": "devstral-small-2:24b",
        "name": "Devstral Small 2 · 24B",
        "size": "≈ 15 Go",
        "memory": "32 Go RAM (CPU) ou VRAM GPU 24 Go + 16 Go RAM système",
        "use_case": "Modèle spécialisé pour agent de code, exploration de dépôt et changements multi-fichiers",
        "capabilities": "Texte · images · programmation agentique",
        "license": "Apache-2.0",
        "recommended": False,
        "min_ram_gb": 32,
        "min_vram_gb": 24,
        "min_ram_with_gpu_gb": 16,
        "source_url": "https://ollama.com/library/devstral-small-2",
    },
    {
        "id": "qwen3-coder:30b",
        "name": "Qwen 3 Coder · 30B A3B",
        "size": "≈ 19 Go",
        "memory": "32 Go de RAM ou VRAM GPU 24 Go + 16 Go RAM système",
        "use_case": "Code avancé, analyse de dépôt et agent de programmation local",
        "capabilities": "Texte · programmation · contexte long",
        "license": "Apache-2.0",
        "recommended": False,
        "min_ram_gb": 32,
        "min_vram_gb": 24,
        "min_ram_with_gpu_gb": 16,
        "source_url": "https://ollama.com/library/qwen3-coder:30b",
    },
]

DEFAULT_MODEL = "qwen3.5:9b"
# Ordre de suggestion uniquement; les installateurs n'effectuent aucun pull sans choix explicite.
DEFAULT_INSTALL_MODELS = (DEFAULT_MODEL,)
LOW_MEMORY_DEFAULT_ORDER = (
    "qwen3.5:4b",
    "qwen3.5:9b",
    "qwen2.5-coder:7b",
    "deepseek-r1:8b",
    "gemma4:12b",
    "gpt-oss:20b",
    "devstral-small-2:24b",
    "qwen3.8:27b",
    "qwen3-coder:30b",
)

MODELS_CATALOG = {
    ModelCategory.LLM: LLM_MODELS,
    ModelCategory.STT: [
        {"name": "base", "size": "150 Mo", "desc": "Whisper base, rapide"},
        {"name": "small", "size": "500 Mo", "desc": "Whisper small, meilleur compromis FR"},
        {"name": "medium", "size": "1,5 Go", "desc": "Whisper medium, meilleure précision"},
    ],
    ModelCategory.TTS: [
        {"name": "fr_FR-siwis-medium", "size": "60 Mo", "desc": "Piper français, voix Siwis"},
        {"name": "fr_FR-upmc-medium", "size": "60 Mo", "desc": "Piper français, voix UPMC"},
    ],
    ModelCategory.IMAGE: [
        {"name": "stabilityai/stable-diffusion-2-1-base", "size": "≈ 5 Go", "desc": "Stable Diffusion 2.1"},
    ],
    ModelCategory.EMBEDDING: [
        {
            "name": "MiniLM (index historique)",
            "size": "≈ 90 Mo",
            "desc": "Moteur sentence-transformers conservé pour les index RAG existants",
        },
        {
            "id": "bge-m3",
            "name": "BGE-M3 · Embeddings",
            "size": "≈ 1,2 Go",
            "memory": "6 Go de RAM conseillés",
            "use_case": "Recherche RAG multilingue pour documents, français et documentation technique",
            "capabilities": "Embeddings · plus de 100 langues · contexte 8K",
            "license": "Voir la fiche modèle",
            "recommended": False,
            "min_ram_gb": 6,
            "min_vram_gb": 0,
            "min_ram_with_gpu_gb": 6,
            "source_url": "https://ollama.com/library/bge-m3",
        },
    ],
}
