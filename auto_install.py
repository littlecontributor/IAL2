#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_install.py - Orchestrateur clé en main V2
================================================
Flux d'installation :
  1. Diagnostic initial (preflight --json)
  2. Installation des dépendances requises et optionnelles
  3. Poids Ollama (LLM ou embedding) téléchargés uniquement sur choix explicite --model
  4. Re-diagnostic final pour confirmer l'état du projet

C'est le cœur de la correction "c'est brouillon" -> tout devient automatique et propre.

Usage:
    python auto_install.py                 # Dépendances et diagnostic; aucun poids IA par défaut
    python auto_install.py --diag-only     # Diagnostic seul
    python auto_install.py --core          # Core uniquement (rapide)
    python auto_install.py --models-only --model qwen3.5:4b  # Modèle choisi, après vérification matérielle
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_DIR = PROJECT_ROOT / ".venv"

# Groupes identiques à INSTALL.ps1
GROUPS = {
    "core": [
        "gradio>=4.44.0,<6.0.0", "gradio_client>=1.3.0", "ollama>=0.4.0",
        "PyYAML>=6.0.1", "psutil>=5.9.0", "requests>=2.31.0",
        "python-multipart>=0.0.9", "numpy>=1.26.0,<3.0.0", "Pillow>=10.0.0"
    ],
    "vocal": [
        "faster-whisper>=1.0.0", "sounddevice>=0.4.6", "soundfile>=0.12.1",
        "pydub>=0.25.1", "webrtcvad-wheels>=2.0.14", "playsound>=1.2.2",
        "piper-tts>=1.2.0"
    ],
    "rag": [
        "chromadb>=0.4.24", "sentence-transformers>=2.7.0", "langchain>=0.2.0",
        "langchain-community>=0.2.0", "langchain-text-splitters>=0.2.0",
        "pypdf>=4.2.0", "docx2txt>=0.8"
    ],
    "ia": [
        "torch>=2.2.0", "torchvision>=0.17.0", "torchaudio>=2.2.0",
        "transformers>=4.41.0", "diffusers>=0.29.0", "accelerate>=0.30.0"
    ],
    "coqui": ["TTS>=0.22.0"]
}

# Les poids LLM ne sont téléchargés que si l'utilisateur fournit un modèle explicite.

# Modèles STT Whisper (faster-whisper télécharge à la demande, on préchauffe)
STT_MODELS = ["base", "small"]

def cprint(msg, color=""):
    colors = {
        "cyan": "\033[96m", "green": "\033[92m", "yellow": "\033[93m",
        "red": "\033[91m", "grey": "\033[90m", "magenta": "\033[95m", "reset": "\033[0m"
    }
    if os.name == "nt" and not os.environ.get("WT_SESSION"):
        print(msg)
    else:
        print(f"{colors.get(color,'')}{msg}{colors['reset']}")

def step(n, total, msg):
    cprint(f"\n[{n}/{total}] {msg}", "cyan")

def ok(msg): cprint(f"  [OK] {msg}", "green")
def warn(msg): cprint(f"  [!]  {msg}", "yellow")
def err(msg): cprint(f"  [ERR] {msg}", "red")
def info(msg): cprint(f"       {msg}", "grey")

def get_python():
    """Retourne le python à utiliser (venv si existe, sinon sys.executable)"""
    candidates = [
        VENV_DIR / "Scripts" / "python.exe",
        VENV_DIR / "bin" / "python",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return sys.executable

def run(cmd, check=False, capture=False, timeout=None):
    """Exécute une commande."""
    if isinstance(cmd, str):
        shell = True
    else:
        shell = False
    try:
        result = subprocess.run(
            cmd, shell=shell, check=check,
            capture_output=capture, text=True, errors="replace",
            timeout=timeout
        )
        return result
    except Exception as e:
        if capture:
            return subprocess.CompletedProcess(cmd, 1, "", str(e))
        err(f"Commande échouée : {e}")
        return None

def diagnostic(json_output=False):
    """Lance preflight.py et retourne le rapport."""
    preflight = PROJECT_ROOT / "preflight.py"
    py = get_python()
    args = [py, str(preflight)]
    if json_output:
        args.append("--json")
    result = run(args, capture=True)
    if not result:
        return None
    if json_output:
        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            info(result.stdout[-500:])
            return None
    else:
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return {"ready": result.returncode == 0, "raw": result.stdout}

def ensure_venv():
    """Crée le venv s'il n'existe pas."""
    py_venv = VENV_DIR / "Scripts" / "python.exe" if os.name == "nt" else VENV_DIR / "bin" / "python"
    if py_venv.exists():
        ok(f"venv déjà présent : {py_venv}")
        return str(py_venv)

    cprint("  Création du venv .venv ...", "grey")
    # Cherche Python 3.11+
    base_py = sys.executable
    # Tente py -3.11
    if platform.system() == "Windows":
        for ver in ["-3.11", "-3.12", "-3"]:
            r = run(["py", ver, "-c", "import sys; print(sys.executable)"], capture=True)
            if r and r.returncode == 0 and r.stdout.strip():
                base_py = r.stdout.strip()
                ok(f"Python détecté via py {ver} : {base_py}")
                break

    r = run([base_py, "-m", "venv", str(VENV_DIR)], capture=True)
    if py_venv.exists():
        ok(f"venv créé : {VENV_DIR}")
        # upgrade pip
        run([str(py_venv), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "--quiet"], capture=True)
        ok("pip mis à jour")
        return str(py_venv)
    else:
        err(f"Échec création venv : {r.stderr if r else 'inconnu'}")
        return sys.executable

def install_group(py, name, packages):
    cprint(f"\n  -- Groupe {name} : {len(packages)} paquets --", "grey")
    failed = []
    for pkg in packages:
        cprint(f"     install {pkg} ...", "grey")
        r = run([py, "-m", "pip", "install", "--prefer-binary", "--disable-pip-version-check", "--quiet", pkg], capture=True)
        if r and r.returncode == 0:
            print("\033[92m OK\033[0m" if os.name != "nt" else " OK")
        else:
            # Réessaye sans --quiet pour voir l'erreur si critique
            if "gradio" in pkg or "ollama" in pkg or "numpy" in pkg:
                r2 = run([py, "-m", "pip", "install", "--prefer-binary", pkg], capture=True)
                if r2 and r2.returncode != 0:
                    warn(f"{pkg} échec : {r2.stderr[-200:] if r2.stderr else 'inconnu'}")
                    failed.append(pkg)
                else:
                    ok(f"{pkg} installé au 2e essai")
            else:
                warn(f"{pkg} échec (optionnel, ignoré)")
    return failed

def verify_core_imports(py):
    """Vrai import pour détecter wheels cassés, réinstalle si besoin."""
    core_imports = {
        "gradio": "gradio>=4.44.0,<6.0.0",
        "ollama": "ollama",
        "yaml": "PyYAML",
        "psutil": "psutil",
        "requests": "requests",
        "multipart": "python-multipart",
        "numpy": "numpy",
        "PIL": "Pillow",
    }
    broken = []
    for imp, pip_name in core_imports.items():
        r = run([py, "-c", f"import {imp}; print('IMPORT_OK')"], capture=True, timeout=30)
        if r and "IMPORT_OK" in (r.stdout or ""):
            ok(f"Import {imp} OK")
        else:
            warn(f"Import {imp} échoué -> réinstallation {pip_name}")
            err_msg = (r.stderr or r.stdout or "")[-300:] if r else "inconnu"
            info(f"cause : {err_msg}")
            run([py, "-m", "pip", "install", "--force-reinstall", "--no-cache-dir", "--quiet", pip_name], capture=True)
            r2 = run([py, "-c", f"import {imp}; print('IMPORT_OK')"], capture=True, timeout=30)
            if r2 and "IMPORT_OK" in (r2.stdout or ""):
                ok(f"Import {imp} OK après réinstall")
            else:
                err(f"Import {imp} toujours échoué")
                broken.append(pip_name)
    return broken

def ensure_ollama_binary():
    """Installe Ollama si absent."""
    if shutil.which("ollama"):
        ok(f"Ollama déjà installé : {shutil.which('ollama')}")
        return True

    system = platform.system()
    cprint("  Ollama non trouvé, installation...", "yellow")

    if system == "Windows":
        if shutil.which("winget"):
            cprint("  Installation via winget...", "grey")
            run("winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements", capture=True, timeout=300)
            time.sleep(5)
            if shutil.which("ollama"):
                ok("Ollama installé via winget")
                return True
        warn("Installez manuellement : https://ollama.com/download")
        warn("Puis relancez ce script")
        return False
    elif system == "Darwin":
        if shutil.which("brew"):
            run("brew install ollama", capture=True)
            if shutil.which("ollama"):
                ok("Ollama installé via brew")
                return True
        warn("Installez via https://ollama.com/download")
        return False
    else:  # Linux
        cprint("  Installation Linux via curl | sh", "grey")
        run("curl -fsSL https://ollama.com/install.sh | sh", capture=True, timeout=300)
        if shutil.which("ollama"):
            ok("Ollama installé")
            return True
        warn("Échec install Ollama Linux")
        return False

def ensure_ollama_server():
    """Démarre le serveur Ollama et attend qu'il réponde."""
    def is_up():
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as _:
                return True
        except Exception:
            return False

    if is_up():
        ok("Serveur Ollama déjà actif")
        return True

    if not shutil.which("ollama"):
        warn("Binaire ollama absent, serveur non démarré")
        return False

    cprint("  Démarrage serveur Ollama...", "grey")
    try:
        if os.name == "nt":
            subprocess.Popen(["ollama", "serve"], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        err(f"Impossible de démarrer ollama serve : {e}")
        return False

    for i in range(30):
        time.sleep(1)
        if is_up():
            ok("Serveur Ollama démarré")
            return True
    warn("Serveur Ollama ne répond pas après 30s")
    return False

def install_ollama_models(models=None):
    """Installe uniquement des modèles Ollama explicitement demandés et compatibles."""
    selected = list(models or [])
    if not selected:
        info("Aucun modèle Ollama choisi : aucun poids n'est téléchargé automatiquement.")
        info("Choisissez un bouton dans l'onglet Modèles IA, ou relancez avec --model <identifiant>.")
        return

    try:
        from scripts import ai_model_manager
    except ImportError as exc:
        warn(f"Gestionnaire matériel indisponible; téléchargement bloqué par prudence : {exc}")
        return

    if not shutil.which("ollama"):
        warn("Ollama absent, modèles non installés")
        return
    if not ensure_ollama_server():
        warn("Serveur Ollama injoignable, modèles non installés")
        return

    try:
        installed = ai_model_manager.list_installed_models()
    except Exception as exc:
        warn(f"Impossible de lister les modèles Ollama : {exc}")
        installed = []
    cprint(f"  Modèles déjà présents : {', '.join(installed) if installed else 'aucun'}", "grey")

    for model in selected:
        model_info = ai_model_manager.get_catalog_model(model)
        if model_info is None:
            warn(f"Modèle absent du catalogue local autorisé : {model}; téléchargement bloqué.")
            continue
        profile = ai_model_manager.hardware_profile.detect_machine_profile(refresh=True)
        compatible, reason = ai_model_manager.hardware_profile.model_compatibility(model_info, profile)
        if not compatible:
            warn(f"{model} masqué pour cette machine : {reason}")
            continue
        if ai_model_manager.is_model_installed(model, installed):
            ok(f"Modèle déjà présent : {model}")
            continue
        cprint(f"  Téléchargement explicite de {model} (peut prendre plusieurs minutes)...", "grey")
        if ai_model_manager.install_ollama_model(model):
            ok(f"Modèle installé : {model}")
        else:
            warn(f"Échec téléchargement {model}")

def install_tts_models():
    """Note pour Piper - les voix se téléchargent à la demande."""
    piper_dir = PROJECT_ROOT / "models" / "piper"
    piper_dir.mkdir(parents=True, exist_ok=True)
    ok(f"Dossier voix Piper prêt : {piper_dir}")
    info("Les voix Piper se téléchargeront automatiquement au 1er usage")

def main():
    parser = argparse.ArgumentParser(description="IA Locale - Installation clé en main V2")
    parser.add_argument("--core", action="store_true", help="Core uniquement (rapide)")
    parser.add_argument("--no-models", action="store_true", help="Sans modèles LLM")
    parser.add_argument("--models-only", action="store_true", help="Seulement modèles Ollama")
    parser.add_argument("--model", action="append", help="Modèle Ollama curaté (LLM ou embedding), choisi explicitement; option répétable")
    parser.add_argument("--diag-only", action="store_true", help="Diagnostic seul")
    parser.add_argument("--recreate", action="store_true", help="Recrée le venv")
    args = parser.parse_args()
    exit_code = 0

    cprint("="*70, "magenta")
    cprint("  IA LOCALE - INSTALLATION CLE EN MAIN V2", "magenta")
    cprint("  Flux : Diagnostic -> Install tout -> Re-diagnostic", "magenta")
    cprint("="*70, "magenta")
    cprint(f"  Projet : {PROJECT_ROOT}", "grey")
    cprint(f"  Python système : {sys.executable} {platform.python_version()}", "grey")

    TOTAL_STEPS = 8
    if args.diag_only:
        TOTAL_STEPS = 1
    if args.models_only:
        TOTAL_STEPS = 3

    # ------------------------------------------------------------------
    # 1. Diagnostic initial
    # ------------------------------------------------------------------
    step(1, TOTAL_STEPS, "Diagnostic initial (preflight)")
    report_initial = diagnostic(json_output=True)
    if report_initial:
        cprint(f"\n  Python : {report_initial['python']['version']} - {'OK' if report_initial['python']['ok'] else 'KO'}", "grey")
        cprint(f"  Fichiers : {'OK' if report_initial['files']['ok'] else 'KO'}", "grey")
        cprint(f"  Packages requis : {'OK' if report_initial['packages']['ok'] else 'MANQUANTS'}", "grey")
        if report_initial['packages']['missing_required']:
            warn(f"  Manquants : {', '.join(report_initial['packages']['missing_required'])}")
        if report_initial['packages']['broken_required']:
            warn(f"  Cassés : {', '.join(report_initial['packages']['broken_required'])}")
        cprint(f"  Ollama : {'OK' if report_initial['ollama']['ok'] else 'A installer/démarrer'}", "grey")
        cprint(f"  Port {report_initial['port']['port']} : {'libre' if report_initial['port']['free'] else 'utilisé'}", "grey")
    else:
        warn("Diagnostic initial JSON échoué, rapport texte :")
        diagnostic(json_output=False)

    if args.diag_only:
        cprint("\n  Diagnostic terminé (--diag-only)", "green")
        return 0

    # ------------------------------------------------------------------
    # 2. Venv
    # ------------------------------------------------------------------
    if args.models_only:
        py = get_python()
    else:
        step(2, TOTAL_STEPS, "Environnement virtuel (.venv)")
        if args.recreate and VENV_DIR.exists():
            warn("Suppression ancien venv (--recreate)")
            shutil.rmtree(VENV_DIR, ignore_errors=True)
        py = ensure_venv()
        cprint(f"  Python utilisé pour l'install : {py}", "grey")

        # ------------------------------------------------------------------
        # 3. Dépendances Python
        # ------------------------------------------------------------------
        step(3, TOTAL_STEPS, "Installation dépendances Python (tous les composants)")

        # Noyau léger ; les modèles IA sont installés séparément ci-dessous.
        install_group(py, "Core (obligatoire)", GROUPS["core"])

        if args.core:
            warn("Mode --core : groupes avancés ignorés")
        else:
            install_group(py, "Vocal (STT/TTS)", GROUPS["vocal"])
            install_group(py, "RAG / Vector DB", GROUPS["rag"])
            install_group(py, "IA / Génération d'images", GROUPS["ia"])
            # Coqui optionnel lourd
            cprint("\n  -- Groupe Coqui TTS (optionnel, lourd) --", "grey")
            r = run([py, "-m", "pip", "install", "--prefer-binary", "--quiet"] + GROUPS["coqui"], capture=True, timeout=600)
            if r and r.returncode == 0:
                ok("Coqui TTS installé")
            else:
                warn("Coqui TTS non installé (Piper assurera TTS)")

        # ------------------------------------------------------------------
        # 4. Vérification vrai import
        # ------------------------------------------------------------------
        step(4, TOTAL_STEPS, "Vérification imports réels (détection wheels cassés)")
        broken = verify_core_imports(py)
        if broken:
            err(f"Modules toujours cassés après réinstall : {', '.join(broken)}")
            warn("Essayez : --recreate ou supprimez .venv manuellement")
            exit_code = 1
        else:
            ok("Tous les modules coeur importables")

    # ------------------------------------------------------------------
    # 5. Ollama binaire
    # ------------------------------------------------------------------
    step(5 if not args.models_only else 2, TOTAL_STEPS, "Ollama - binaire")
    ensure_ollama_binary()

    # ------------------------------------------------------------------
    # 6. Ollama serveur
    # ------------------------------------------------------------------
    step(6 if not args.models_only else 3, TOTAL_STEPS, "Ollama - serveur")
    ensure_ollama_server()

    # ------------------------------------------------------------------
    # 7. Modèles
    # ------------------------------------------------------------------
    if args.no_models:
        warn("Installation des modèles ignorée (--no-models)")
    elif not args.model:
        warn("Aucun modèle Ollama sélectionné; aucun poids n'est téléchargé automatiquement.")
        info("Pour installer un seul modèle, utilisez l'onglet Modèles IA ou --model <identifiant>.")
    else:
        step(7 if not args.models_only else 3, TOTAL_STEPS, "Modèles Ollama explicitement sélectionnés")
        install_ollama_models(args.model)

    if not args.models_only and not args.core and not args.no_models:
        step(8, TOTAL_STEPS, "Voix / modèles optionnels")
        warn("Les poids STT ne sont pas pré-téléchargés; leur utilisation reste à la demande.")
        install_tts_models()

    # ------------------------------------------------------------------
    # 8. Re-diagnostic final (le plus important pour la demande)
    # ------------------------------------------------------------------
    if not args.models_only:
        step(TOTAL_STEPS, TOTAL_STEPS, "Re-diagnostic final (validation que tout est OK)")
        time.sleep(1)
        final_report = diagnostic(json_output=True)
        if final_report:
            cprint("\n" + "="*70, "magenta")
            cprint("  BILAN FINAL", "magenta")
            cprint("="*70, "magenta")
            ready = final_report.get("ready", False)
            if not ready:
                exit_code = 1
            cprint(f"  Python : {'OK' if final_report['python']['ok'] else 'KO'}", "green" if final_report['python']['ok'] else "red")
            cprint(f"  Fichiers : {'OK' if final_report['files']['ok'] else 'KO'}", "green" if final_report['files']['ok'] else "red")
            cprint(f"  Packages requis : {'OK' if final_report['packages']['ok'] else 'KO'}", "green" if final_report['packages']['ok'] else "red")
            cprint(f"  Ollama : {'OK' if final_report['ollama']['ok'] else 'Partiel'}", "green" if final_report['ollama']['ok'] else "yellow")
            cprint(f"  Modèles Ollama : {len(final_report['ollama']['models'])} installé(s) : {', '.join(final_report['ollama']['models'][:5])}", "grey")
            cprint(f"  Port {final_report['port']['port']} : {'libre' if final_report['port']['free'] else 'utilisé'}", "grey")

            if ready and final_report['ollama']['ok']:
                cprint("\n  🎉 INSTALLATION 100% OK - PRÊT À DÉMARRER", "green")
                cprint("  Lancez : ./START.ps1  ou  START.bat", "cyan")
                cprint(f"  Interface : http://127.0.0.1:{final_report['port']['port']}", "cyan")
            elif ready:
                cprint("\n  ✅ CORE OK - Ollama à finaliser", "yellow")
                cprint("  - Si Ollama manquant : https://ollama.com/download", "yellow")
                cprint("  - Choisissez un modèle compatible dans IA Locale > Modèles IA (ou avec auto_install.py --models-only --model ...)", "yellow")
                cprint("  - Démarrer : ./START.ps1", "cyan")
            else:
                cprint("\n  ❌ CORRECTIONS NÉCESSAIRES", "red")
                if final_report['packages']['missing_required']:
                    cprint(f"  Manquants : {final_report['packages']['missing_required']}", "red")
                if final_report['packages']['broken_required']:
                    cprint(f"  Cassés : {final_report['packages']['broken_required']}", "red")
                cprint("  Relancez : python auto_install.py --recreate", "yellow")
        else:
            cprint("\n  Re-diagnostic JSON échoué, affichage texte :", "yellow")
            diagnostic(json_output=False)
            exit_code = 1

    cprint("\n" + "="*70, "magenta")
    cprint("  FIN INSTALLATION CLÉ EN MAIN", "magenta")
    cprint("="*70, "magenta")
    return exit_code

if __name__ == "__main__":
    raise SystemExit(main())
