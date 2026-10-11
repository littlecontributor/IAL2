#!/usr/bin/env python3
"""Construit un exécutable PyInstaller dans le dossier dist/ du projet."""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

APP_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def build_command(project_root: str | Path, entry: str, name: str, console: bool = False) -> list[str]:
    """Construit une commande PyInstaller sans shell et limitée au projet."""
    root = Path(project_root).resolve()
    if not APP_NAME_RE.fullmatch(name):
        raise ValueError("Le nom doit commencer par une lettre et ne contenir que lettres, chiffres, tirets ou underscores (40 caractères maximum).")
    if name.upper() in WINDOWS_RESERVED_NAMES:
        raise ValueError(f"{name} est un nom réservé par Windows.")

    entry_path = (root / entry).resolve()
    try:
        entry_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Le point d'entrée doit se trouver dans le dossier du projet.") from exc
    if not entry_path.is_file():
        raise FileNotFoundError(f"Point d'entrée introuvable : {entry_path}")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name",
        name,
        "--distpath",
        str(root / "dist"),
        "--workpath",
        str(root / "build" / "work"),
        "--specpath",
        str(root / "build"),
    ]
    if not console:
        command.append("--windowed")
    command.append(str(entry_path))
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Empaquette main.py avec PyInstaller.")
    parser.add_argument("--entry", default="main.py", help="Point d'entrée relatif au projet (défaut : main.py)")
    parser.add_argument("--name", default="MonApp", help="Nom de l'exécutable")
    parser.add_argument("--console", action="store_true", help="Garde la fenêtre console (utile pour les outils CLI)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    if importlib.util.find_spec("PyInstaller") is None:
        print("PyInstaller n'est pas installé. Lancez : python -m pip install -r requirements-build.txt", file=sys.stderr)
        return 2

    try:
        command = build_command(project_root, args.entry, args.name, console=args.console)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2

    (project_root / "dist").mkdir(parents=True, exist_ok=True)
    (project_root / "build" / "work").mkdir(parents=True, exist_ok=True)
    print(f"Construction de {args.name} depuis {args.entry}…")
    result = subprocess.run(command, cwd=project_root, check=False)
    if result.returncode == 0:
        suffix = ".exe" if sys.platform == "win32" else ""
        print(f"Exécutable créé dans : {project_root / 'dist' / (args.name + suffix)}")
    else:
        print("Échec PyInstaller : corrigez les erreurs ci-dessus puis relancez.", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
