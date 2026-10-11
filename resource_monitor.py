#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
resource_monitor.py - Monitoring CPU / RAM / disque
"""
import psutil
from pathlib import Path

def get_stats():
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path(__file__).resolve().parent.parent))
        return {
            "cpu_percent": cpu,
            "ram_percent": ram.percent,
            "ram_used_gb": round(ram.used / (1024**3), 2),
            "ram_total_gb": round(ram.total / (1024**3), 2),
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / (1024**3), 2),
        }
    except Exception as e:
        return {"error": str(e)}

def format_stats():
    s = get_stats()
    if "error" in s:
        return f"Erreur monitoring : {s['error']}"
    return f"CPU {s['cpu_percent']}% | RAM {s['ram_percent']}% ({s['ram_used_gb']}/{s['ram_total_gb']} GB) | Disque {s['disk_percent']}% libre {s['disk_free_gb']} GB"
