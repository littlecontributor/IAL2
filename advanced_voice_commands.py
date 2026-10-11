#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""advanced_voice_commands.py - Commandes vocales avancées"""
import re

COMMANDS = {
    r"genere.*image.*de (.*)": "image",
    r"change.*personnalite.*(expert|prof|creatif|assistant)": "personality",
    r"montre.*ressources": "resources",
    r"nettoie.*fichiers": "clean",
    r"liste.*modeles": "list_models",
}

def parse_command(text: str):
    text = text.lower()
    for pattern, action in COMMANDS.items():
        m = re.search(pattern, text)
        if m:
            return action, m.groups()
    return "chat", (text,)

def execute(action, args, llm_func=None):
    if action == "image":
        return f"[Commande] Génération image : {args[0] if args else ''}"
    if action == "resources":
        from .resource_monitor import format_stats
        return format_stats()
    if action == "clean":
        from .auto_cleaner import clean_temp
        cleaned = clean_temp()
        return f"Nettoyé {len(cleaned)} fichiers"
    if action == "list_models":
        from .llm import list_models
        models = list_models()
        return f"Modèles : {', '.join(models)}"
    return None
