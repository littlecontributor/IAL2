#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preflight.py - Diagnostic IA Locale V2 (clé en main)
=====================================================
Vérifie sans dépendance externe (stdlib uniquement) :
  1. Version Python
  2. Fichiers du projet
  3. Packages Python (via VRAI import, pas seulement find_spec)
  4. Ollama (binaire, serveur, modèles)
  5. Port de l'interface

Nouveautés V2 (correction demandée) :
  - --json      : sortie JSON pour l'orchestrateur
  - --auto-fix  : installe automatiquement les dépendances manquantes
  - Diagnostic clair en 3 phases pour INSTALL.ps1
  - Codes retour stables

Usage:
    python preflight.py                  # rapport complet
    python preflight.py --fix            # affiche les commandes pip
    python preflight.py --auto-fix       # installe automatiquement (pip)
    python preflight.py --json           # sortie JSON machine
    python preflight.py --quiet          # code retour uniquement
"""

import importlib.util
import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_FILE = PROJECT_ROOT / "config" / "config.yaml"

# ------------------------------------------------------------------
# Table : pip -> import (corrige bug des tirets)
# ------------------------------------------------------------------
REQUIRED_PACKAGES = [
    ("Interface web",        "gradio",            "gradio",            "interface"),
    ("Client Ollama",        "ollama",            "ollama",            "llm"),
    ("Configuration",        "PyYAML",            "yaml",              "base"),
    ("Monitoring",           "psutil",            "psutil",            "systeme"),
    ("Requêtes HTTP",        "requests",          "requests",          "base"),
    ("Upload fichiers",      "python-multipart",  "multipart",         "interface"),
    ("Calcul numérique",     "numpy",             "numpy",             "base"),
    ("Images Pillow",        "Pillow",            "PIL",               "ia"),
]

OPTIONAL_PACKAGES = [
    ("Reconnaissance vocale", "faster-whisper",       "faster_whisper",       "vocal", "STT temps réel"),
    ("Synthèse Piper",        "piper-tts",            "piper",                "vocal", "TTS léger"),
    ("Synthèse Coqui",        "TTS",                  "TTS",                  "vocal", "TTS multi-voix"),
    ("Audio lecture",         "sounddevice",          "sounddevice",          "vocal", "Lecture audio"),
    ("Audio WAV",             "soundfile",            "soundfile",            "vocal", "Effets sonores"),
    ("Audio MP3",             "pydub",                "pydub",                "vocal", "Effets sonores"),
    ("PyTorch",               "torch",                "torch",                "ia",    "Génération d'images"),
    ("Transformers",          "transformers",         "transformers",         "ia",    "Modèles"),
    ("Diffusers",             "diffusers",            "diffusers",            "ia",    "Génération d'images"),
    ("Embeddings",            "sentence-transformers","sentence_transformers","rag",   "RAG"),
    ("Base vectorielle",      "chromadb",             "chromadb",             "rag",   "RAG"),
    ("LangChain",             "langchain",            "langchain",            "rag",   "RAG"),
    ("VAD",                   "webrtcvad-wheels",     "webrtcvad",            "vocal", "Dictée"),
]

# Couleurs (désactivées sous Windows sans WT)
GREEN, RED, YELLOW, CYAN, GREY, RESET = (
    "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[90m", "\033[0m"
)
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    GREEN = RED = YELLOW = CYAN = GREY = RESET = ""

def ok(m):    print(f"  {GREEN}[OK]{RESET}     {m}")
def ko(m):    print(f"  {RED}[MANQUE]{RESET} {m}")
def warn(m):  print(f"  {YELLOW}[!]{RESET}      {m}")
def info(m):  print(f"  {GREY}         {m}{RESET}")
def title(m): print(f"\n{CYAN}=== {m} ==={RESET}")

def has_module(import_name):
    try:
        return importlib.util.find_spec(import_name) is not None
    except Exception:
        return False

def import_ok(import_name, timeout=90):
    """Vrai import isolé pour détecter wheels cassés."""
    env = dict(os.environ)
    env.setdefault("GRADIO_ANALYTICS_ENABLED", "false")
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import importlib,sys; importlib.import_module(sys.argv[1])", import_name],
            capture_output=True, text=True, errors="replace", timeout=timeout, env=env
        )
        if r.returncode == 0:
            return True, ""
        lines = [ln.strip() for ln in (r.stderr or r.stdout or "").splitlines() if ln.strip()]
        return False, (lines[-1] if lines else "échec import inconnu")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

def check_python():
    title("1. Version Python")
    major, minor = sys.version_info[:2]
    print(f"  Version : {sys.version.split()[0]}")
    print(f"  Exécutable : {sys.executable}")
    if (major, minor) >= (3, 11):
        ok("Python 3.11+ (recommandé)")
        return True, f"{major}.{minor}"
    if (major, minor) >= (3, 10):
        warn("Python 3.10 détecté : fonctionne, 3.11+ recommandé")
        return True, f"{major}.{minor}"
    ko(f"Python {major}.{minor} trop ancien : installez Python 3.11")
    return False, f"{major}.{minor}"

def check_files():
    title("2. Fichiers du projet")
    expected = [
        "ui/futuristic_app.py",
        "ui/futuristic_theme.py",
        "config/config.yaml",
        "scripts/llm.py",
        "scripts/model_catalog.py",
        "scripts/hardware_profile.py",
        "scripts/ai_model_manager.py",
        "scripts/create_python_app.py",
        "templates/python_desktop_app/main.py",
        "templates/python_desktop_app/build_exe.py",
        "templates/python_desktop_app/requirements-build.txt",
        "tests/test_app_scaffold.py",
        "scripts/tts.py",
        "scripts/stt.py",
        "scripts/rag.py",
        "requirements.txt",
        "auto_install.py",
        "GUIDE_CODE_LOCAL.md",
    ]
    all_ok = True
    for rel in expected:
        if (PROJECT_ROOT / rel).exists():
            ok(rel)
        else:
            ko(f"{rel} introuvable")
            all_ok = False
    return all_ok

def check_packages(fix=False, auto_fix=False):
    title("3. Packages Python (vrai import)")
    missing_req, broken_req, missing_opt = [], [], []

    print(f"  {CYAN}-- Requis --{RESET}")
    for label, pip_name, import_name, _cat in REQUIRED_PACKAGES:
        found = has_module(import_name)
        imp_ok, imp_err = import_ok(import_name) if found else (False, "absent")
        if imp_ok:
            ok(f"{label} ({pip_name})")
        else:
            ko(f"{label} ({pip_name})")
            if found:
                info(f"présent mais import impossible : {imp_err}")
                broken_req.append(pip_name)
            else:
                missing_req.append(pip_name)

    print(f"\n  {CYAN}-- Optionnels --{RESET}")
    for label, pip_name, import_name, _cat, feat in OPTIONAL_PACKAGES:
        if has_module(import_name):
            ok(f"{label} ({pip_name}) - {feat}")
        else:
            warn(f"{label} ({pip_name}) - {feat} [optionnel]")
            missing_opt.append(pip_name)

    if fix or auto_fix:
        if missing_req:
            print(f"\n  {CYAN}A installer (absents) :{RESET}")
            print(f'    "{sys.executable}" -m pip install ' + " ".join(missing_req))
        if broken_req:
            print(f"\n  {CYAN}A réinstaller (cassés) :{RESET}")
            print(f'    "{sys.executable}" -m pip install --force-reinstall --no-cache-dir ' + " ".join(broken_req))
        if missing_opt:
            print(f"\n  {CYAN}Optionnels :{RESET}")
            print(f'    "{sys.executable}" -m pip install ' + " ".join(missing_opt))

    if auto_fix:
        if missing_req or broken_req:
            print(f"\n  {CYAN}[AUTO-FIX] Installation des requis manquants...{RESET}")
            try:
                cmd = [sys.executable, "-m", "pip", "install", "--prefer-binary", "--quiet"] + missing_req + broken_req
                # force reinstall for broken
                if broken_req:
                    subprocess.run([sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-cache-dir", "--quiet"] + broken_req, check=False)
                if missing_req:
                    subprocess.run(cmd, check=False)
                print(f"  {GREEN}Auto-fix requis terminé{RESET}")
            except Exception as e:
                print(f"  {RED}Auto-fix échoué : {e}{RESET}")

    pkgs_ok = len(missing_req) == 0 and len(broken_req) == 0
    return pkgs_ok, missing_req, broken_req, missing_opt

def http_json(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        return None

def check_ollama():
    title("4. Ollama (moteur LLM local)")
    from shutil import which
    binary = which("ollama") or which("ollama.exe")
    ollama_ok = True
    if binary:
        ok(f"Binaire : {binary}")
    else:
        warn("Binaire 'ollama' absent du PATH (https://ollama.com/download)")
        ollama_ok = False

    tags = http_json("http://127.0.0.1:11434/api/tags")
    if tags is None:
        warn("Serveur Ollama injoignable sur http://127.0.0.1:11434 (lancez : ollama serve)")
        ollama_ok = False
        models = []
    else:
        models = [m.get("name", "?") for m in tags.get("models", [])]
        ok(f"Serveur actif - {len(models)} modèle(s)")
        for m in models[:15]:
            info(f"- {m}")
        if len(models) > 15:
            info(f"... et {len(models)-15} autre(s)")
        if not models:
            warn("Aucun modèle : choisissez-en un depuis l'onglet Modèles IA; le catalogue filtre selon RAM/VRAM")
            # ne bloque pas le démarrage, mais signalé
    return ollama_ok, models, bool(binary)

def read_port():
    port, host = 7860, "127.0.0.1"
    try:
        text = CONFIG_FILE.read_text(encoding="utf-8", errors="ignore")
        section = None
        for raw in text.splitlines():
            line = raw.split("#")[0].rstrip()
            if not line.strip():
                continue
            if not line.startswith(" ") and line.rstrip().endswith(":"):
                section = line.strip().rstrip(":").strip()
                continue
            if section == "ui" and ":" in line:
                k, _, v = line.partition(":")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "port":
                    port = int(v)
                elif k == "host":
                    host = v
    except Exception:
        pass
    return host, port

def check_port():
    title("5. Port interface")
    host, port = read_port()
    print(f"  Config : {host}:{port} (config/config.yaml)")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.2)
    in_use = s.connect_ex(("127.0.0.1", port)) == 0
    s.close()
    if in_use:
        warn(f"Port {port} déjà utilisé (instance en cours ?)")
        info(f"Ouvrez http://127.0.0.1:{port}")
        return port, False
    ok(f"Port {port} libre")
    return port, True

def build_report_silent():
    """Version silencieuse pour --json (pas de print)."""
    # Python
    major, minor = sys.version_info[:2]
    py_ok = (major, minor) >= (3, 10)
    py_ver = f"{major}.{minor}"

    # Fichiers
    expected = [
        "ui/futuristic_app.py",
        "ui/futuristic_theme.py",
        "config/config.yaml",
        "scripts/llm.py",
        "scripts/model_catalog.py",
        "scripts/hardware_profile.py",
        "scripts/ai_model_manager.py",
        "scripts/create_python_app.py",
        "templates/python_desktop_app/main.py",
        "templates/python_desktop_app/build_exe.py",
        "templates/python_desktop_app/requirements-build.txt",
        "tests/test_app_scaffold.py",
        "scripts/tts.py",
        "scripts/stt.py",
        "scripts/rag.py",
        "requirements.txt",
        "auto_install.py",
        "GUIDE_CODE_LOCAL.md",
    ]
    files_ok = all((PROJECT_ROOT / p).exists() for p in expected)

    # Packages
    missing_req, broken_req, missing_opt = [], [], []
    for label, pip_name, import_name, _cat in REQUIRED_PACKAGES:
        found = has_module(import_name)
        imp_ok, _ = import_ok(import_name) if found else (False, "absent")
        if not imp_ok:
            if found:
                broken_req.append(pip_name)
            else:
                missing_req.append(pip_name)
    for label, pip_name, import_name, _cat, feat in OPTIONAL_PACKAGES:
        if not has_module(import_name):
            missing_opt.append(pip_name)
    pkgs_ok = len(missing_req) == 0 and len(broken_req) == 0

    # Ollama
    from shutil import which
    binary = which("ollama") or which("ollama.exe")
    tags = http_json("http://127.0.0.1:11434/api/tags")
    if tags is None:
        ollama_ok = False
        models = []
    else:
        models = [m.get("name", "?") for m in tags.get("models", [])]
        ollama_ok = True

    # Port
    host, port = read_port()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.2)
    in_use = s.connect_ex(("127.0.0.1", port)) == 0
    s.close()
    port_free = not in_use

    return {
        "python": {"ok": py_ok, "version": py_ver, "exe": sys.executable},
        "files": {"ok": files_ok},
        "packages": {"ok": pkgs_ok, "missing_required": missing_req, "broken_required": broken_req, "missing_optional": missing_opt},
        "ollama": {"ok": ollama_ok, "binary": bool(binary), "models": models},
        "port": {"port": port, "free": port_free},
        "ready": py_ok and files_ok and pkgs_ok,
    }

def build_report():
    py_ok, py_ver = check_python()
    files_ok = check_files()
    pkgs_ok, miss_req, broken_req, miss_opt = check_packages(fix=False)
    ollama_ok, ollama_models, ollama_bin = check_ollama()
    port, port_free = check_port()
    return {
        "python": {"ok": py_ok, "version": py_ver, "exe": sys.executable},
        "files": {"ok": files_ok},
        "packages": {"ok": pkgs_ok, "missing_required": miss_req, "broken_required": broken_req, "missing_optional": miss_opt},
        "ollama": {"ok": ollama_ok, "binary": ollama_bin, "models": ollama_models},
        "port": {"port": port, "free": port_free},
        "ready": py_ok and files_ok and pkgs_ok,
    }

def main():
    args = set(sys.argv[1:])
    is_json = "--json" in args
    is_fix = "--fix" in args
    is_auto = "--auto-fix" in args
    is_quiet = "--quiet" in args

    if is_quiet:
        py_ok = sys.version_info[:2] >= (3, 10)
        files_ok = all((PROJECT_ROOT / p).exists() for p in ["ui/futuristic_app.py", "config/config.yaml"])
        pkgs_ok = True
        for _, _, imp, _ in REQUIRED_PACKAGES:
            if not has_module(imp):
                pkgs_ok = False
                break
            ok_imp, _ = import_ok(imp)
            if not ok_imp:
                pkgs_ok = False
                break
        sys.exit(0 if (py_ok and files_ok and pkgs_ok) else 1)

    if is_json:
        # Pas de couleurs en JSON + version silencieuse (pas de prints parasites)
        global GREEN, RED, YELLOW, CYAN, GREY, RESET
        GREEN = RED = YELLOW = CYAN = GREY = RESET = ""
        report = build_report_silent()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0 if report["ready"] else 1)

    print("="*70)
    print("  PREFLIGHT - IA LOCALE V2 - Diagnostic clé en main")
    print("="*70)
    print(f"  Projet : {PROJECT_ROOT}")
    print(f"  Python : {sys.executable}")

    py_ok, _ = check_python()
    files_ok = check_files()
    pkgs_ok, miss_req, broken_req, miss_opt = check_packages(fix=is_fix or is_auto, auto_fix=is_auto)
    ollama_ok, models, _ = check_ollama()
    port, port_free = check_port()

    print("\n" + "="*70)
    print("  RÉSULTAT")
    print("="*70)
    print(f"  Python .............. {'OK' if py_ok else 'A CORRIGER'}")
    print(f"  Fichiers ............ {'OK' if files_ok else 'A CORRIGER'}")
    print(f"  Packages requis ..... {'OK' if pkgs_ok else 'A CORRIGER'}")
    print(f"  Ollama .............. {'OK' if ollama_ok else 'A DEMARRER'}")
    print(f"  Port {port} ........... {'LIBRE' if port_free else 'UTILISE'}")

    if not py_ok:
        print(f"\n  {RED}-> Installez Python 3.11 puis relancez.{RESET}")
        sys.exit(2)
    if not pkgs_ok:
        print(f"\n  {RED}-> Packages requis manquants :{RESET}")
        if miss_req: print(f"     Absents : {', '.join(miss_req)}")
        if broken_req: print(f"     Cassés : {', '.join(broken_req)}")
        print(f'     Fix : "{sys.executable}" -m pip install -r requirements.txt')
        sys.exit(1)

    print(f"\n  {GREEN}-> Prêt à démarrer : START.bat (ou ./START.ps1){RESET}")
    print(f"  {GREEN}-> Interface : http://127.0.0.1:{port}{RESET}\n")
    sys.exit(0)

if __name__ == "__main__":
    main()
