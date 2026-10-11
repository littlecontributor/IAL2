#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
personality_manager.py - Rôles et personnalités
"""
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PERSONALITIES_DIR = PROJECT_ROOT / "config" / "personalities"

DEFAULT_PERSONALITIES = {
    "assistant": {"name": "Assistant", "system": "Tu es un assistant IA utile, concis et bienveillant.", "emoji": "🤖"},
    "expert_technique": {"name": "Expert Technique", "system": "Tu es un expert technique senior. Réponses précises, avec code et exemples.", "emoji": "💻"},
    "professeur": {"name": "Professeur", "system": "Tu es un professeur pédagogue. Explique simplement avec exemples.", "emoji": "🎓"},
    "creatif": {"name": "Créatif", "system": "Tu es un assistant créatif, imaginatif, qui propose des idées originales.", "emoji": "🎨"},
    "coach": {"name": "Coach", "system": "Tu es un coach motivant, bienveillant, qui aide à progresser.", "emoji": "💪"},
    "humour": {"name": "Humour", "system": "Tu es drôle, avec humour léger, sans être lourd.", "emoji": "😂"},
    "scientifique": {"name": "Scientifique", "system": "Tu es un scientifique rigoureux, tu cites tes sources et nuances.", "emoji": "🔬"},
    "enfant": {"name": "Pour Enfant", "system": "Tu expliques comme à un enfant de 10 ans, simple et amusant.", "emoji": "🧒"},
}

def ensure_personalities():
    PERSONALITIES_DIR.mkdir(parents=True, exist_ok=True)
    for key, data in DEFAULT_PERSONALITIES.items():
        f = PERSONALITIES_DIR / f"{key}.yaml"
        if not f.exists():
            with open(f, "w", encoding="utf-8") as out:
                yaml.safe_dump(data, out, allow_unicode=True)

def list_personalities():
    ensure_personalities()
    pers = []
    for f in PERSONALITIES_DIR.glob("*.yaml"):
        try:
            with open(f, "r", encoding="utf-8") as inp:
                data = yaml.safe_load(inp)
                data["id"] = f.stem
                pers.append(data)
        except:
            continue
    return pers

def get_personality(pid: str):
    ensure_personalities()
    f = PERSONALITIES_DIR / f"{pid}.yaml"
    if not f.exists():
        return DEFAULT_PERSONALITIES.get(pid, DEFAULT_PERSONALITIES["assistant"])
    with open(f, "r", encoding="utf-8") as inp:
        return yaml.safe_load(inp)
