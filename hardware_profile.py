"""Détection locale et conservatrice de la RAM et de la mémoire GPU."""
from __future__ import annotations

import copy
import json
import os
import platform
import shutil
import subprocess
import sys
from functools import lru_cache
from typing import Any

try:
    import psutil
except ImportError:  # La dépendance est prévue au noyau, mais le fallback garde le module importable.
    psutil = None

_GIB = 1024**3
_MIB = 1024**2


def _memory_bytes() -> tuple[int | None, int | None]:
    if psutil is not None:
        try:
            memory = psutil.virtual_memory()
            return int(memory.total), int(memory.available)
        except (OSError, RuntimeError, AttributeError, ValueError):
            pass

    if sys.platform.startswith("linux"):
        try:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            total_pages = int(os.sysconf("SC_PHYS_PAGES"))
            available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
            return page_size * total_pages, page_size * available_pages
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
                shell=False,
            )
            total = int(result.stdout.strip()) if result.returncode == 0 else 0
            return (total, None) if total > 0 else (None, None)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass

    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys), int(status.ullAvailPhys)
        except (AttributeError, OSError, TypeError):
            pass
    return None, None


def _gib(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    # Arrondir vers le bas pour ne pas rendre visible un modèle à la limite du seuil.
    return int(float(value) / _GIB * 10) / 10


def _detect_nvidia_gpus() -> list[dict[str, Any]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return []
    try:
        result = subprocess.run(
            [executable, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    detected = []
    for line in result.stdout.splitlines():
        columns = [column.strip() for column in line.split(",")]
        if len(columns) < 2:
            continue
        try:
            memory_mib = float(columns[-1].replace("MiB", "").strip())
        except ValueError:
            continue
        if memory_mib <= 0:
            continue
        detected.append({
            "name": ", ".join(columns[:-1]) or "GPU NVIDIA",
            "vram_gb": _gib(memory_mib * _MIB),
            "kind": "nvidia",
        })
    return detected


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("value", "Value", "vram_total", "VRAM Total Memory (B)"):
            if key in value:
                return _numeric_value(value[key])
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _find_rocm_memory(node: Any) -> list[tuple[str, float]]:
    found: list[tuple[str, float]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key)
            normalized = key_text.casefold()
            if "vram total memory" in normalized or normalized in {"vram_total", "memory.total"}:
                amount = _numeric_value(value)
                if amount and amount > 0:
                    found.append((key_text, amount))
            else:
                found.extend(_find_rocm_memory(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_find_rocm_memory(value))
    return found


def _detect_rocm_gpus() -> list[dict[str, Any]]:
    executable = shutil.which("rocm-smi")
    if not executable:
        return []
    try:
        result = subprocess.run(
            [executable, "--showmeminfo", "vram", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
            shell=False,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []

    detected = []
    for index, (_, total_bytes) in enumerate(_find_rocm_memory(data)):
        detected.append({
            "name": f"GPU AMD/ROCm {index + 1}",
            "vram_gb": _gib(total_bytes),
            "kind": "rocm",
        })
    return detected


@lru_cache(maxsize=1)
def _detect_machine_profile_cached() -> dict[str, Any]:
    total_bytes, available_bytes = _memory_bytes()
    total_ram = _gib(total_bytes)
    available_ram = _gib(available_bytes)
    system = platform.system()
    architecture = platform.machine()
    gpus = _detect_nvidia_gpus()
    if not gpus:
        gpus = _detect_rocm_gpus()

    # Apple Silicon partage la RAM entre CPU et GPU; on ne crédite au GPU qu'une
    # enveloppe indicative, en laissant 6 Go au système et aux autres processus.
    if system == "Darwin" and architecture.casefold() in {"arm64", "aarch64"} and total_ram:
        unified_budget = max(0.0, total_ram - 6.0)
        if unified_budget > 0:
            gpus.append({
                "name": "Apple Silicon (mémoire unifiée estimée)",
                "vram_gb": round(unified_budget, 1),
                "kind": "apple-unified",
            })

    gpus.sort(key=lambda item: float(item.get("vram_gb", 0)), reverse=True)
    best_gpu = gpus[0] if gpus else None
    if total_ram is None:
        tier = "indéterminé"
    elif (best_gpu and best_gpu["vram_gb"] >= 20) or total_ram >= 48:
        tier = "haut de gamme"
    elif (best_gpu and best_gpu["vram_gb"] >= 8) or total_ram >= 24:
        tier = "intermédiaire / puissant"
    elif total_ram >= 12:
        tier = "standard"
    else:
        tier = "entrée de gamme"

    return {
        "system": system,
        "architecture": architecture,
        "total_ram_gb": total_ram,
        "available_ram_gb": available_ram,
        "gpus": gpus,
        "gpu_name": best_gpu["name"] if best_gpu else None,
        "gpu_vram_gb": best_gpu["vram_gb"] if best_gpu else None,
        "tier": tier,
    }


def detect_machine_profile(refresh: bool = False) -> dict[str, Any]:
    """Détecte la machine au lancement; refresh=True recalcule après changement matériel."""
    if refresh:
        _detect_machine_profile_cached.cache_clear()
    return copy.deepcopy(_detect_machine_profile_cached())


def model_compatibility(model: dict[str, Any], profile: dict[str, Any]) -> tuple[bool, str]:
    """Vérifie des seuils prudents de RAM totale ou VRAM dédiée du catalogue."""
    total_ram = profile.get("total_ram_gb")
    if not isinstance(total_ram, (int, float)) or total_ram <= 0:
        return False, "La mémoire système n'a pas pu être détectée; modèle masqué par prudence."

    min_ram = float(model.get("min_ram_gb", 8))
    min_vram = float(model.get("min_vram_gb", 0))
    min_ram_with_gpu = float(model.get("min_ram_with_gpu_gb", min_ram))
    if total_ram >= min_ram:
        return True, f"RAM système détectée : {total_ram:g} Go (seuil : {min_ram:g} Go)."

    gpus = profile.get("gpus", [])
    for gpu in gpus if isinstance(gpus, list) else []:
        vram = gpu.get("vram_gb") if isinstance(gpu, dict) else None
        if isinstance(vram, (int, float)) and vram >= min_vram > 0 and total_ram >= min_ram_with_gpu:
            return True, (
                f"GPU détecté : {gpu.get('name', 'GPU')} ({vram:g} Go VRAM) "
                f"et {total_ram:g} Go RAM système."
            )

    if min_vram > 0:
        gpu = profile.get("gpu_vram_gb")
        gpu_note = (
            f"VRAM détectée : {gpu:g} Go; seuil GPU : {min_vram:g} Go, "
            f"avec au moins {min_ram_with_gpu:g} Go de RAM système."
            if isinstance(gpu, (int, float))
            else f"GPU dédié d'au moins {min_vram:g} Go VRAM requis, avec {min_ram_with_gpu:g} Go de RAM système."
        )
        return False, f"RAM détectée : {total_ram:g} Go; seuil CPU : {min_ram:g} Go. {gpu_note}"
    return False, f"RAM détectée : {total_ram:g} Go; seuil requis : {min_ram:g} Go."


def format_machine_profile(profile: dict[str, Any]) -> str:
    """Retourne un résumé lisible pour l'interface et le diagnostic."""
    total_ram = profile.get("total_ram_gb")
    ram_text = f"{total_ram:g} Go RAM" if isinstance(total_ram, (int, float)) else "RAM indéterminée"
    gpus = profile.get("gpus", [])
    if isinstance(gpus, list) and gpus:
        gpu_text = "; ".join(
            f"{gpu.get('name', 'GPU')} — {gpu.get('vram_gb', '?')} Go mémoire GPU estimée/détectée"
            for gpu in gpus[:2]
            if isinstance(gpu, dict)
        )
    else:
        gpu_text = "aucun GPU compatible détecté (filtrage selon la RAM)"
    return (
        f"Machine détectée : **{profile.get('system', 'OS inconnu')} {profile.get('architecture', '')}**, "
        f"{ram_text}, {gpu_text}. Profil : **{profile.get('tier', 'indéterminé')}**."
    )
