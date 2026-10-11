#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dictation_mode.py - Dictée vocale avec sessions"""
from pathlib import Path
import json, time

class DictationSession:
    def __init__(self, session_id: str = None):
        self.id = session_id or f"dict_{int(time.time())}"
        self.segments = []
        self.start_time = time.time()

    def add_segment(self, text: str, timestamp: float = None):
        self.segments.append({"text": text, "ts": timestamp or time.time()})

    def get_full_text(self):
        return " ".join([s["text"] for s in self.segments])

    def export(self, fmt: str = "txt"):
        if fmt == "json":
            return json.dumps({"id": self.id, "segments": self.segments}, ensure_ascii=False, indent=2)
        return self.get_full_text()
