#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_cleaner.py - Nettoyage automatique
"""
from pathlib import Path
import time
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def clean_temp(max_age_hours: int = 24, dry_run: bool = False):
    """Nettoie outputs, logs, temp audio."""
    now = time.time()
    max_age = max_age_hours * 3600
    cleaned = []

    # Seuls les artefacts temporaires sont éligibles. La base RAG contient
    # les documents indexés par l'utilisateur et ne doit jamais être purgée ici.
    dirs_to_clean = [
        PROJECT_ROOT / "outputs",
        PROJECT_ROOT / "sounds",
    ]

    for d in dirs_to_clean:
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if not f.is_file():
                continue
            # Ne pas supprimer les modèles
            if "models" in str(f):
                continue
            try:
                age = now - f.stat().st_mtime
                if age > max_age:
                    if not dry_run:
                        f.unlink()
                    cleaned.append(str(f))
            except:
                continue

    # Logs racine
    for log in PROJECT_ROOT.glob("*.log"):
        try:
            age = now - log.stat().st_mtime
            if age > max_age:
                if not dry_run:
                    log.unlink()
                cleaned.append(str(log))
        except:
            pass

    return cleaned

if __name__ == "__main__":
    files = clean_temp(dry_run=False)
    print(f"Nettoyés : {len(files)} fichiers")
    for f in files[:20]:
        print(f"  - {f}")
