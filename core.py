"""Fonctions sans interface, faciles à tester."""


def make_greeting(name: str) -> str:
    """Retourne une salutation propre pour l'interface."""
    cleaned = " ".join((name or "").strip().split())
    if not cleaned:
        return "Bonjour !"
    return f"Bonjour, {cleaned} !"
