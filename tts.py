#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tts.py - Synthèse vocale multi-voix (Piper / Coqui)
"""
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPER_MODELS_DIR = PROJECT_ROOT / "models" / "piper"

def list_piper_voices():
    """Liste les voix Piper installées."""
    if not PIPER_MODELS_DIR.exists():
        return []
    voices = []
    for f in PIPER_MODELS_DIR.glob("*.onnx"):
        voices.append(f.stem)
    return voices

def tts_piper(text: str, voice: str = "fr_FR-siwis-medium", speed: float = 1.0, output_path: str = None) -> str:
    """Synthèse via Piper TTS."""
    try:
        from piper import PiperVoice
        import wave

        # Cherche modèle
        model_path = PIPER_MODELS_DIR / f"{voice}.onnx"
        config_path = PIPER_MODELS_DIR / f"{voice}.onnx.json"

        if not model_path.exists():
            # Voix par défaut : essaye de télécharger ou fallback
            # Pour V2, on simule si modèle absent
            return _tts_fallback(text, output_path, f"Piper voix {voice} non trouvée, fallback")

        voice_obj = PiperVoice.load(str(model_path), str(config_path))

        if output_path is None:
            output_path = str(PROJECT_ROOT / "outputs" / f"tts_{os.urandom(4).hex()}.wav")
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with wave.open(output_path, "wb") as wav_file:
            voice_obj.synthesize_wav(text, wav_file, length_scale=1.0/speed)

        return output_path

    except ImportError:
        return _tts_fallback(text, output_path, "Piper non installé")
    except Exception as e:
        return _tts_fallback(text, output_path, f"Piper erreur: {e}")

def tts_coqui(text: str, model: str = "tts_models/fr/mai/tacotron2-DDC", output_path: str = None) -> str:
    """Synthèse via Coqui TTS."""
    try:
        from TTS.api import TTS
        if output_path is None:
            output_path = str(PROJECT_ROOT / "outputs" / f"tts_coqui_{os.urandom(4).hex()}.wav")
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        tts = TTS(model)
        tts.tts_to_file(text=text, file_path=output_path)
        return output_path
    except ImportError:
        return _tts_fallback(text, output_path, "Coqui TTS non installé")
    except Exception as e:
        return _tts_fallback(text, output_path, f"Coqui erreur: {e}")

def _tts_fallback(text: str, output_path: str, reason: str) -> str:
    """Fallback silencieux : génère un wav vide + log."""
    print(f"[TTS Fallback] {reason}")
    if output_path is None:
        output_path = str(PROJECT_ROOT / "outputs" / f"tts_fallback_{os.urandom(4).hex()}.wav")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Génère un wav silencieux de 1s pour ne pas casser l'UI
    try:
        import wave, struct
        with wave.open(output_path, 'w') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(struct.pack('<' + 'h'*22050, *([0]*22050)))
    except:
        Path(output_path).touch()

    return output_path

def synthesize(text: str, provider: str = "piper", **kwargs) -> str:
    """API unifiée."""
    if provider == "coqui":
        return tts_coqui(text, **kwargs)
    return tts_piper(text, **kwargs)
