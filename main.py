#!/usr/bin/env python3
"""Point d'entrée de l'application de bureau."""
import tkinter as tk
from tkinter import ttk

from app.core import make_greeting

APP_NAME = "MonApp"


def main() -> None:
    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("480x300")
    root.minsize(360, 240)

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 20, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Squelette local prêt à personnaliser avec votre agent de code.").pack(anchor="w", pady=(4, 20))

    ttk.Label(frame, text="Votre nom").pack(anchor="w")
    name_var = tk.StringVar()
    name_entry = ttk.Entry(frame, textvariable=name_var)
    name_entry.pack(fill="x", pady=(6, 12))

    result_var = tk.StringVar(value="Votre application fonctionne.")
    ttk.Label(frame, textvariable=result_var, wraplength=420).pack(anchor="w", pady=(0, 12))

    def greet() -> None:
        result_var.set(make_greeting(name_var.get()))

    ttk.Button(frame, text="Dire bonjour", command=greet).pack(anchor="w")
    name_entry.focus_set()
    root.mainloop()


if __name__ == "__main__":
    main()
