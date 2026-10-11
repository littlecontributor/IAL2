#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Outils Ollama, filtrage matériel et téléchargements suivis."""
import json
import os
import shutil
import subprocess
from typing import Dict, Iterable, List, Optional

try:  # package import: scripts.ai_model_manager
    from . import hardware_profile
    from .model_catalog import (
        DEFAULT_INSTALL_MODELS,
        LLM_MODELS,
        LOW_MEMORY_DEFAULT_ORDER,
        MODELS_CATALOG,
        ModelCategory,
    )
except ImportError:  # import direct depuis ui/ ou scripts/
    import hardware_profile
    from model_catalog import (
        DEFAULT_INSTALL_MODELS,
        LLM_MODELS,
        LOW_MEMORY_DEFAULT_ORDER,
        MODELS_CATALOG,
        ModelCategory,
    )

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def list_models() -> None:
    """Affiche seulement les modèles installables adaptés à la machine détectée."""
    profile = hardware_profile.detect_machine_profile(refresh=True)
    print("\n[Machine détectée]")
    print(f"  {hardware_profile.format_machine_profile(profile)}")
    print("\n[LLM Ollama compatibles]")
    compatible = get_compatible_catalog_models(ModelCategory.LLM, profile)
    for model in compatible:
        badge = " [recommandé]" if model["recommended"] else ""
        print(
            f"  - {model['id']} ({model['size']}){badge}\n"
            f"    {model['use_case']} | {model['license']}"
        )
    for cat in (ModelCategory.STT, ModelCategory.TTS, ModelCategory.IMAGE, ModelCategory.EMBEDDING):
        print(f"\n[{cat.value.upper()}]")
        for model in get_compatible_catalog_models(cat, profile):
            name = model.get("name", model.get("id", "?"))
            desc = model.get("desc", model.get("use_case", ""))
            print(f"  - {name} ({model['size']}) : {desc}")


def _ollama_installable_models() -> List[Dict]:
    """Retourne les références Ollama téléchargeables dans les catégories retenues."""
    embeddings = [
        model for model in MODELS_CATALOG[ModelCategory.EMBEDDING]
        if isinstance(model.get("id"), str) and model.get("id")
    ]
    return [*LLM_MODELS, *embeddings]


def get_catalog_model(name: str) -> Optional[Dict]:
    return next((model for model in _ollama_installable_models() if model.get("id") == name), None)


def is_catalog_model(name: str) -> bool:
    """Compatibilité historique : indique si l'identifiant est un LLM du catalogue."""
    return any(model["id"] == name for model in LLM_MODELS)


def is_installable_model(name: str) -> bool:
    return get_catalog_model(name) is not None


def is_model_compatible(name: str, profile: Optional[Dict] = None) -> bool:
    model = get_catalog_model(name)
    if model is None:
        return False
    current = profile or hardware_profile.detect_machine_profile()
    compatible, _ = hardware_profile.model_compatibility(model, current)
    return compatible


def compatibility_reason(name: str, profile: Optional[Dict] = None) -> str:
    model = get_catalog_model(name)
    if model is None:
        return "Modèle absent du catalogue local autorisé."
    current = profile or hardware_profile.detect_machine_profile()
    return hardware_profile.model_compatibility(model, current)[1]


def get_compatible_catalog_models(category: ModelCategory, profile: Optional[Dict] = None) -> List[Dict]:
    current = profile or hardware_profile.detect_machine_profile()
    if category == ModelCategory.LLM:
        models = LLM_MODELS
    elif category == ModelCategory.EMBEDDING:
        models = [model for model in MODELS_CATALOG[category] if model.get("id")]
    else:
        return list(MODELS_CATALOG[category])
    return [model for model in models if hardware_profile.model_compatibility(model, current)[0]]


def _matches_installed_name(installed_name: str, catalog_id: str) -> bool:
    return installed_name == catalog_id or installed_name == f"{catalog_id}:latest"


def is_model_installed(model_id: str, installed_names: Iterable[str]) -> bool:
    return any(
        isinstance(name, str) and _matches_installed_name(name, model_id)
        for name in installed_names
    )


def filter_compatible_installed_models(
    installed_names: Iterable[str],
    profile: Optional[Dict] = None,
    category: ModelCategory = ModelCategory.LLM,
) -> List[str]:
    """Masque les modèles hors catalogue/catégorie ou non adaptés au matériel."""
    current = profile or hardware_profile.detect_machine_profile()
    if category == ModelCategory.LLM:
        models = LLM_MODELS
    elif category == ModelCategory.EMBEDDING:
        models = [model for model in MODELS_CATALOG[ModelCategory.EMBEDDING] if model.get("id")]
    else:
        models = []
    supported = {
        model["id"]
        for model in models
        if model.get("id") and hardware_profile.model_compatibility(model, current)[0]
    }
    visible = []
    for name in installed_names:
        if not isinstance(name, str):
            continue
        if any(_matches_installed_name(name, model_id) for model_id in supported):
            visible.append(name)
    return visible


def select_default_install_model(profile: Optional[Dict] = None) -> Optional[str]:
    """Choisit le défaut s'il convient, sinon le premier modèle léger compatible."""
    current = profile or hardware_profile.detect_machine_profile()
    candidates = tuple(dict.fromkeys((*DEFAULT_INSTALL_MODELS, *LOW_MEMORY_DEFAULT_ORDER)))
    for model_id in candidates:
        if is_model_compatible(model_id, current):
            return model_id
    return None


def list_installed_models(host: str = OLLAMA_HOST) -> List[str]:
    """Retourne les modèles réellement présents dans le serveur local Ollama."""
    import requests

    response = requests.get(f"{host.rstrip('/')}/api/tags", timeout=5)
    response.raise_for_status()
    return [str(model.get("name", "")) for model in response.json().get("models", []) if model.get("name")]


def _ensure_model_compatible(model: str, profile: Optional[Dict] = None) -> Dict:
    model_info = get_catalog_model(model)
    if model_info is None:
        raise ValueError(f"Modèle absent du catalogue IA Locale : {model}")
    current = profile or hardware_profile.detect_machine_profile(refresh=True)
    compatible, reason = hardware_profile.model_compatibility(model_info, current)
    if not compatible:
        raise ValueError(f"{model} n'est pas proposé pour cette machine : {reason}")
    return current


def _format_pull_update(model: str, data: Dict) -> str:
    status = str(data.get("status", "Téléchargement"))
    completed, total = data.get("completed"), data.get("total")
    if isinstance(completed, (int, float)) and isinstance(total, (int, float)) and total > 0:
        percent = min(100, int(completed * 100 / total))
        return f"⬇️ {model} — {status} : {percent}%"
    if status.lower() == "success":
        return f"✅ {model} installé et prêt."
    return f"⏳ {model} — {status}"


def install_model_stream(model: str, host: str = OLLAMA_HOST) -> Iterable[str]:
    """Télécharge un LLM ou embedding Ollama seulement si le matériel est compatible."""
    _ensure_model_compatible(model)
    import requests

    yield f"Préparation du téléchargement de {model}…"
    url = f"{host.rstrip('/')}/api/pull"
    with requests.post(
        url,
        json={"name": model, "stream": True},
        stream=True,
        timeout=(10, 3600),
    ) as response:
        response.raise_for_status()
        saw_update = False
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            update = json.loads(line)
            if update.get("error"):
                raise RuntimeError(str(update["error"]))
            saw_update = True
            yield _format_pull_update(model, update)
        if not saw_update:
            raise RuntimeError("Ollama n'a renvoyé aucune progression de téléchargement.")


def install_ollama_model(name: str) -> bool:
    """Installe un seul modèle Ollama autorisé et compatible avec le matériel."""
    try:
        _ensure_model_compatible(name)
    except ValueError as exc:
        print(str(exc))
        return False
    if not shutil.which("ollama"):
        print("Ollama est introuvable. Installez-le depuis https://ollama.com/download")
        return False
    print(f"Téléchargement de {name}…")
    result = subprocess.run(["ollama", "pull", name], check=False)
    return result.returncode == 0


def install_by_category(category: str, model_name: Optional[str] = None) -> bool:
    """Installe un choix explicite; aucun poids LLM n'est téléchargé par défaut."""
    try:
        cat = ModelCategory(category)
    except ValueError:
        print(f"Catégorie inconnue : {category}")
        return False

    if cat == ModelCategory.LLM:
        if not model_name:
            print("Choisissez explicitement un modèle compatible dans l'interface ou avec --model.")
            return False
        if not is_catalog_model(model_name):
            print(f"{model_name} n'est pas un LLM du catalogue.")
            return False
        return install_ollama_model(model_name)
    if cat == ModelCategory.EMBEDDING:
        if not model_name:
            print("Choisissez un embedding compatible dans le catalogue pour l'installer.")
            return False
        if not any(
            model.get("id") == model_name
            for model in MODELS_CATALOG[ModelCategory.EMBEDDING]
        ):
            print(f"{model_name} n'est pas un embedding du catalogue.")
            return False
        return install_ollama_model(model_name)
    if cat == ModelCategory.STT:
        try:
            from faster_whisper import WhisperModel
            selected = [model_name] if model_name else ["base"]
            for model in selected:
                print(f"Téléchargement STT {model}…")
                WhisperModel(model, device="cpu", compute_type="int8")
            return True
        except ImportError:
            print("faster-whisper n'est pas installé")
            return False
    print(f"Installation de la catégorie {cat.value} : téléchargement géré au premier usage.")
    return False


def install_all(model: Optional[str] = None) -> bool:
    """Installe un modèle explicitement choisi; aucun modèle n'est tiré automatiquement."""
    if not model:
        print("Aucun modèle sélectionné; aucun poids LLM téléchargé.")
        return False
    return install_ollama_model(model)
