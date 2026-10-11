#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Client Ollama pour les conversations locales (texte et image)."""
import base64
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def list_models(host: str = OLLAMA_HOST) -> List[str]:
    """Liste les modèles installés ; retourne une liste vide si Ollama est hors ligne."""
    try:
        response = requests.get(f"{host.rstrip('/')}/api/tags", timeout=5)
        response.raise_for_status()
        return [str(model.get("name", "")) for model in response.json().get("models", []) if model.get("name")]
    except (requests.RequestException, ValueError, TypeError):
        return []


def _history_messages(history) -> List[Dict[str, str]]:
    """Normalise l'historique Gradio tuple ou messages vers l'API Ollama."""
    result: List[Dict[str, str]] = []
    for item in history or []:
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and content is not None:
                result.append({"role": role, "content": str(content)})
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            user_text, assistant_text = item[0], item[1]
            if user_text is not None:
                result.append({"role": "user", "content": str(user_text)})
            if assistant_text is not None:
                result.append({"role": "assistant", "content": str(assistant_text)})
    return result


def _encode_image(image_path: Optional[str]) -> Optional[str]:
    if not image_path:
        return None
    path = Path(image_path).expanduser()
    if not path.is_file():
        raise ValueError("Le fichier image fourni est introuvable.")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("Le fichier image est vide.")
    if size > MAX_IMAGE_BYTES:
        raise ValueError("Image trop volumineuse (limite : 20 Mo). Réduisez sa taille puis réessayez.")
    return base64.b64encode(path.read_bytes()).decode("ascii")


def build_messages(
    message: str,
    history: Optional[Iterable] = None,
    system: str = "",
    image_path: Optional[str] = None,
) -> List[Dict]:
    """Construit la liste de messages Ollama, avec image facultative pour les modèles vision."""
    messages: List[Dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend(_history_messages(history))

    user_message = {"role": "user", "content": message or ""}
    encoded_image = _encode_image(image_path)
    if encoded_image:
        user_message["images"] = [encoded_image]
    messages.append(user_message)
    return messages


def chat(
    message: str,
    model: str = "qwen3.5:9b",
    history: Optional[Iterable] = None,
    system: str = "",
    temperature: float = 0.7,
    host: str = OLLAMA_HOST,
    image_path: Optional[str] = None,
    response_format: Optional[object] = None,
) -> str:
    """Dialogue local avec Ollama; response_format peut contraindre la structure de sortie."""
    try:
        payload = {
            "model": model,
            "messages": build_messages(message, history=history, system=system, image_path=image_path),
            "stream": False,
            "options": {"temperature": float(temperature)},
        }
        if response_format is not None:
            payload["format"] = response_format
        response = requests.post(f"{host.rstrip('/')}/api/chat", json=payload, timeout=(10, 600))
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "") or data.get("response", "")
    except Exception as exc:
        return (
            f"[Erreur LLM {model} : {exc}] — Vérifiez qu'Ollama est démarré et que le modèle compatible est installé. "
            "Ouvrez l'onglet Modèles IA pour choisir un modèle adapté; son bouton contrôle la compatibilité avant téléchargement. "
            "Pour analyser une image, choisissez un modèle compatible vision."
        )


def chat_stream(
    message: str,
    model: str = "qwen3.5:9b",
    history: Optional[Iterable] = None,
    system: str = "",
    temperature: float = 0.7,
    host: str = OLLAMA_HOST,
    image_path: Optional[str] = None,
):
    """Générateur de tokens ; compatible avec les réponses JSON en flux d'Ollama."""
    try:
        payload = {
            "model": model,
            "messages": build_messages(message, history=history, system=system, image_path=image_path),
            "stream": True,
            "options": {"temperature": float(temperature)},
        }
        with requests.post(
            f"{host.rstrip('/')}/api/chat",
            json=payload,
            stream=True,
            timeout=(10, 600),
        ) as response:
            response.raise_for_status()
            full = ""
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="replace")
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        full += chunk
                        yield full
                    if data.get("error"):
                        yield f"[Erreur Ollama : {data['error']}]"
                        return
                    if data.get("done"):
                        break
                except (json.JSONDecodeError, TypeError):
                    continue
    except Exception as exc:
        yield f"[Erreur stream : {exc}]"


def check_ollama(host: str = OLLAMA_HOST) -> bool:
    try:
        response = requests.get(f"{host.rstrip('/')}/api/tags", timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False
