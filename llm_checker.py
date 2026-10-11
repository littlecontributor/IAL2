#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérifications locales du moteur Ollama et de PyTorch."""
import os

import requests


def check_all(host: str = None):
    host = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
    results = {}
    try:
        response = requests.get(f"{host}/api/tags", timeout=3)
        response.raise_for_status()
        models = [model.get("name", "?") for model in response.json().get("models", [])]
        results["ollama"] = {"ok": True, "host": host, "models": models}
    except Exception as exc:
        results["ollama"] = {"ok": False, "host": host, "error": str(exc)}

    try:
        import torch
        results["torch"] = {
            "ok": True,
            "version": torch.__version__,
            "cuda": torch.cuda.is_available(),
        }
    except ImportError:
        results["torch"] = {"ok": False, "error": "non installé"}
    except Exception as exc:
        results["torch"] = {"ok": False, "error": str(exc)}

    return results


if __name__ == "__main__":
    import json
    print(json.dumps(check_all(), indent=2, ensure_ascii=False))
