#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stt.py - Reconnaissance vocale (faster-whisper)
"""
from pathlib import Path

def transcribe(audio_path: str, model: str = "base", language: str = "fr", device: str = "cpu") -> str:
    """Transcrit un fichier audio."""
    try:
        from faster_whisper import WhisperModel

        # Modèle local ou téléchargé automatiquement
        whisper = WhisperModel(model, device=device, compute_type="int8")
        segments, info = whisper.transcribe(audio_path, language=language if language != "auto" else None)

        text = " ".join([s.text for s in segments])
        return text.strip()

    except ImportError:
        return "[STT] faster-whisper non installé - lancez INSTALL.ps1"
    except Exception as e:
        return f"[STT Erreur] {e}"

def transcribe_stream(audio_bytes, **kwargs):
    """Pour micro temps réel (utilisé par Gradio)."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        return transcribe(tmp_path, **kwargs)
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass
