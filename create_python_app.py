#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crée un projet de bureau Python depuis le modèle testé du dépôt."""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "templates" / "python_desktop_app"
APP_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def create_project(name: str, destination: str | Path) -> Path:
    """Copie un squelette Tkinter, sans écraser un dossier existant."""
    if not APP_NAME_RE.fullmatch(name):
        raise ValueError("Le nom doit commencer par une lettre et ne contenir que lettres, chiffres, tirets ou underscores (40 caractères maximum).")
    if name.upper() in WINDOWS_RESERVED_NAMES:
        raise ValueError(f"{name} est un nom réservé par Windows.")
    if not str(destination).strip():
        raise ValueError("Indiquez un dossier de destination non vide.")
    if not TEMPLATE_DIR.is_dir():
        raise FileNotFoundError(f"Modèle de projet absent : {TEMPLATE_DIR}")

    parent = Path(destination).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / name
    if target.exists():
        raise FileExistsError(f"Le chemin existe déjà, aucun fichier n'a été modifié : {target}")

    shutil.copytree(TEMPLATE_DIR, target)
    main_file = target / "main.py"
    main_text = main_file.read_text(encoding="utf-8")
    main_file.write_text(main_text.replace('APP_NAME = "MonApp"', f'APP_NAME = "{name}"'), encoding="utf-8")

    readme = target / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace("MonApp", name), encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Crée une application Python de bureau prête à tester et empaqueter.")
    parser.add_argument("name", help="Nom simple du projet, par exemple NotesLocal")
    parser.add_argument(
        "--destination",
        default=str(Path.home() / "IA-Projects"),
        help="Dossier parent (défaut : ~/IA-Projects)",
    )
    args = parser.parse_args()

    try:
        project = create_project(args.name, args.destination)
    except (ValueError, FileExistsError, FileNotFoundError, OSError) as exc:
        parser.error(str(exc))

    print(f"Projet créé : {project}")
    print("Étapes suivantes :")
    print(f"  1. Ouvrir le dossier dans VS Code ou lancer Qwen Code depuis : {project}")
    print("  2. Tester : python -m unittest discover -s tests -v")
    print("  3. Construire : python build_exe.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
