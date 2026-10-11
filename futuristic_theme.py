#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thème sobre et lisible pour l'interface IA Locale (sans ressource externe)."""
import gradio as gr


def get_theme():
    """Construit un thème sombre cohérent avec repli compatible Gradio."""
    try:
        theme = gr.themes.Soft(
            primary_hue="cyan",
            secondary_hue="violet",
            neutral_hue="slate",
            radius_size="lg",
            font="Inter, ui-sans-serif, system-ui, sans-serif",
        )
        theme.set(
            body_background_fill="#0b1020",
            body_background_fill_dark="#0b1020",
            block_background_fill="#111a2c",
            block_background_fill_dark="#111a2c",
        )
        return theme
    except Exception:
        return gr.themes.Default()


# CSS auto-contenu : fonctionne aussi hors ligne et dans l'aperçu intégré.
CUSTOM_CSS = """
:root {
    color-scheme: dark;
    --page: #0b1020;
    --surface: #111a2c;
    --surface-raised: #162238;
    --line: rgba(159, 183, 219, .15);
    --text: #edf3ff;
    --muted: #9aabc6;
    --cyan: #67e8f9;
    --violet: #a78bfa;
    --green: #86efac;
}

html, body, .gradio-container {
    background:
        radial-gradient(900px 480px at 8% -8%, rgba(34, 211, 238, .09), transparent 68%),
        radial-gradient(800px 500px at 100% 0%, rgba(139, 92, 246, .10), transparent 65%),
        var(--page) !important;
    color: var(--text) !important;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}

.gradio-container {
    max-width: 1480px !important;
    margin: 0 auto !important;
    padding: 24px clamp(14px, 3vw, 38px) 34px !important;
}

.hero {
    position: relative;
    overflow: hidden;
    margin: 0 0 22px;
    padding: clamp(22px, 4vw, 38px);
    border: 1px solid rgba(122, 190, 220, .19);
    border-radius: 24px;
    background:
        linear-gradient(115deg, rgba(14, 29, 48, .96), rgba(21, 25, 52, .88)),
        var(--surface);
    box-shadow: 0 24px 70px rgba(0, 0, 0, .22);
}
.hero::after {
    content: "";
    position: absolute;
    width: 300px;
    height: 300px;
    right: -110px;
    top: -150px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(103, 232, 249, .16), transparent 68%);
    pointer-events: none;
}
.hero-kicker {
    display: flex;
    align-items: center;
    gap: 9px;
    color: #9edee8;
    font-size: .72rem;
    font-weight: 700;
    letter-spacing: .12em;
}
.hero-pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 14px rgba(134, 239, 172, .65);
}
.hero h1 {
    margin: 12px 0 6px;
    color: #f5f8ff;
    font-size: clamp(2rem, 5vw, 3.2rem);
    font-weight: 760;
    letter-spacing: -.045em;
}
.hero h1 span {
    background: linear-gradient(90deg, var(--cyan), #c4b5fd);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
}
.hero p {
    max-width: 760px;
    margin: 0;
    color: #bdc9dc;
    font-size: clamp(.95rem, 2vw, 1.1rem);
    line-height: 1.65;
}
.hero-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 18px;
}
.hero-tags span {
    padding: 6px 11px;
    border: 1px solid rgba(165, 185, 218, .16);
    border-radius: 999px;
    background: rgba(255, 255, 255, .035);
    color: #c7d3e6;
    font-size: .78rem;
}

.tabs, .tab-nav {
    border-color: var(--line) !important;
}
.tab-nav button {
    color: var(--muted) !important;
    border-radius: 12px 12px 0 0 !important;
    transition: color .16s ease, background .16s ease;
}
.tab-nav button.selected {
    color: #effbff !important;
    background: rgba(103, 232, 249, .09) !important;
    border-color: rgba(103, 232, 249, .35) !important;
}
.block, .form, .gr-panel, .gr-box {
    border-color: var(--line) !important;
    border-radius: 16px !important;
    box-shadow: 0 10px 28px rgba(0, 0, 0, .12) !important;
}
label, .label, .prose h1, .prose h2, .prose h3 {
    color: #e6edf9 !important;
}
.prose, .markdown, .prose p, .prose li {
    color: #c5d1e4;
}
.prose a { color: var(--cyan) !important; }
.prose table { border-color: var(--line) !important; }
.prose th, .prose td { border-color: var(--line) !important; }

input, textarea, select, .wrap, .gr-textbox textarea, .gr-dropdown {
    background-color: rgba(9, 15, 29, .72) !important;
    color: var(--text) !important;
    border-color: rgba(151, 174, 207, .2) !important;
}
input:focus, textarea:focus, select:focus,
.gr-textbox textarea:focus, .gr-dropdown:focus-within {
    border-color: rgba(103, 232, 249, .66) !important;
    box-shadow: 0 0 0 3px rgba(103, 232, 249, .1) !important;
}
button, .gr-button {
    border-radius: 12px !important;
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}
.gr-button-primary, button.primary {
    border: 1px solid rgba(103, 232, 249, .35) !important;
    background: linear-gradient(110deg, #0e7490, #5b3aa7) !important;
    color: #f5fbff !important;
    box-shadow: 0 8px 24px rgba(8, 145, 178, .16) !important;
}
.gr-button-primary:hover, button.primary:hover {
    transform: translateY(-1px);
    box-shadow: 0 12px 30px rgba(8, 145, 178, .25) !important;
}
.gr-button-secondary, button.secondary {
    background: rgba(255, 255, 255, .045) !important;
    border-color: var(--line) !important;
    color: #d8e4f5 !important;
}

footer { color: var(--muted) !important; }
@media (max-width: 760px) {
    .gradio-container { padding: 12px 10px 24px !important; }
    .hero { border-radius: 18px; }
    .tab-nav button { padding-left: 10px !important; padding-right: 10px !important; }
}
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; }
}
"""
