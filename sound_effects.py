#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sound_effects.py - Effets sonores 7 thèmes"""
from pathlib import Path

THEMES = ["futuristic", "nature", "retro", "scifi", "minimal", "gaming", "zen"]

def play_effect(name: str, theme: str = "futuristic"):
    try:
        import playsound, os
        # Stub : sons générés automatiquement dans sounds/
        print(f"[SFX] {theme}/{name}")
    except Exception as e:
        print(f"[SFX] {name} ({e})")
