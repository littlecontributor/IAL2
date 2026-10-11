#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_paths.py - Chemins portables (Windows / Linux / macOS)
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def get_path(name: str) -> Path:
    mapping = {
        "root": PROJECT_ROOT,
        "config": PROJECT_ROOT / "config",
        "ui": PROJECT_ROOT / "ui",
        "scripts": PROJECT_ROOT / "scripts",
        "models": PROJECT_ROOT / "models",
        "outputs": PROJECT_ROOT / "outputs",
        "sounds": PROJECT_ROOT / "sounds",
        "chroma_db": PROJECT_ROOT / "chroma_db",
    }
    return mapping.get(name, PROJECT_ROOT / name)

def ensure_dirs():
    for d in ["models", "outputs", "sounds", "chroma_db", "config/personalities"]:
        (PROJECT_ROOT / d).mkdir(parents=True, exist_ok=True)
