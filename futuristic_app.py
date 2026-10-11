#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interface Gradio de l'assistant IA local.

Fonctions : chat Ollama (texte + images sur modèles vision), catalogue/installateur
LLM, voix, RAG documentaire, génération d'images, personnalités et outils système.
"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))

from project_paths import ensure_dirs
ensure_dirs()

import gradio as gr
import yaml

try:
    from futuristic_theme import get_theme, CUSTOM_CSS
except ImportError:
    get_theme = lambda: gr.themes.Soft()
    CUSTOM_CSS = ""

try:
    import llm
except Exception as exc:
    llm = None
    print(f"[WARN] llm.py non chargeable : {exc}")

try:
    import ai_model_manager
except Exception as exc:
    ai_model_manager = None
    print(f"[WARN] ai_model_manager.py non chargeable : {exc}")

try:
    import hardware_profile
except Exception as exc:
    hardware_profile = None
    print(f"[WARN] Détection matérielle indisponible : {exc}")

try:
    import local_agent
except Exception as exc:
    local_agent = None
    print(f"[WARN] local_agent.py non chargeable : {exc}")

try:
    from model_catalog import DEFAULT_MODEL, LLM_MODELS, LOW_MEMORY_DEFAULT_ORDER, ModelCategory
except ImportError:
    DEFAULT_MODEL = "qwen3.5:9b"
    LLM_MODELS = []
    LOW_MEMORY_DEFAULT_ORDER = ("qwen3.5:4b",)
    ModelCategory = None

try:
    import tts
except Exception:
    tts = None

try:
    import stt
except Exception:
    stt = None

try:
    import rag
except Exception:
    rag = None

try:
    import personality_manager
    personality_manager.ensure_personalities()
except Exception:
    personality_manager = None

try:
    import resource_monitor
except Exception:
    resource_monitor = None

try:
    import auto_cleaner
except Exception:
    auto_cleaner = None

try:
    import llm_checker
except Exception:
    llm_checker = None


CONFIG_FILE = PROJECT_ROOT / "config" / "config.yaml"


def load_config():
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as config_file:
            return yaml.safe_load(config_file) or {}
    except Exception as exc:
        print(f"[WARN] Configuration par défaut utilisée : {exc}")
        return {
            "ui": {"port": 7860, "host": "127.0.0.1", "title": "IA Locale"},
            "llm": {"host": "http://127.0.0.1:11434", "default_model": DEFAULT_MODEL},
        }


CONFIG = load_config()
LLM_CONFIG = CONFIG.get("llm", {})
LLM_HOST = str(LLM_CONFIG.get("host", "http://127.0.0.1:11434")).rstrip("/")
DEFAULT_MODEL = str(LLM_CONFIG.get("default_model", DEFAULT_MODEL))
UI_PORT = int(CONFIG.get("ui", {}).get("port", 7860))


def current_machine_profile(refresh=False):
    if hardware_profile:
        try:
            return hardware_profile.detect_machine_profile(refresh=refresh)
        except Exception:
            pass
    return {"system": "inconnu", "architecture": "", "total_ram_gb": None, "gpus": [], "tier": "indéterminé"}


def all_installed_models_fn():
    if llm:
        return llm.list_models(host=LLM_HOST)
    return []


def compatible_installed_models(installed=None, profile=None):
    installed = all_installed_models_fn() if installed is None else list(installed)
    profile = profile or current_machine_profile()
    if ai_model_manager:
        return ai_model_manager.filter_compatible_installed_models(installed, profile)
    return []


def list_models_fn(profile=None):
    return compatible_installed_models(profile=profile)


def is_model_compatible_fn(model_name, profile=None):
    if not ai_model_manager or not model_name:
        return False
    return ai_model_manager.is_model_compatible(model_name, profile or current_machine_profile())


def machine_and_models_status(profile, installed):
    summary = hardware_profile.format_machine_profile(profile) if hardware_profile else "Machine indéterminée; modèles lourds masqués par prudence."
    compatible = compatible_installed_models(installed, profile)
    hidden = max(0, len(installed) - len(compatible))
    model_status = f"Ollama : **{len(compatible)} modèle(s) compatible(s) installé(s)**."
    if hidden:
        model_status += f" {hidden} modèle(s) installé(s) masqué(s) (hors catalogue ou trop exigeant(s))."
    return f"{summary}\n\n{model_status}"


def initial_model_value(models=None):
    models = models if models is not None else list_models_fn()
    for model_name in dict.fromkeys((DEFAULT_MODEL, *LOW_MEMORY_DEFAULT_ORDER)):
        if model_name in models:
            return model_name
    return models[0] if models else None


def refresh_models_fn(current_model=None):
    profile = current_machine_profile()
    installed = all_installed_models_fn()
    models = compatible_installed_models(installed, profile)
    selected = current_model if current_model in models else initial_model_value(models)
    return gr.Dropdown(choices=models, value=selected, label="Modèle installé"), machine_and_models_status(profile, installed)


def refresh_agent_models_fn(current_model=None):
    profile = current_machine_profile()
    installed = all_installed_models_fn()
    models = compatible_installed_models(installed, profile)
    selected = current_model if current_model in models else initial_model_value(models)
    return gr.update(choices=models, value=selected), machine_and_models_status(profile, installed)


def model_card_markdown(model):
    recommended = " · ⭐ recommandé" if model.get("recommended") else ""
    min_ram = float(model.get("min_ram_gb", 8))
    min_vram = float(model.get("min_vram_gb", 0))
    if min_vram > 0:
        min_ram_with_gpu = float(model.get("min_ram_with_gpu_gb", min_ram))
        memory_requirement = (
            f"RAM CPU ≥ {min_ram:g} Go, ou VRAM GPU ≥ {min_vram:g} Go "
            f"+ RAM système ≥ {min_ram_with_gpu:g} Go"
        )
    else:
        memory_requirement = f"RAM système ≥ {min_ram:g} Go"
    return (
        f"### [{model['name']}]({model['source_url']}){recommended}\n\n"
        f"`{model['id']}` · **Téléchargement : {model['size']}** · **Mémoire requise : {memory_requirement}**\n\n"
        f"{model['use_case']}\n\n"
        f"**Entrées :** {model['capabilities']} · **Licence :** {model['license']}"
    )


def install_model_button_fn(model_name, initial_label):
    """Télécharge un modèle et met à jour l'état du bouton associé."""
    if not ai_model_manager:
        yield "❌ Gestionnaire de modèles indisponible. Vérifiez l'installation du projet.", gr.update(
            value=initial_label, interactive=True
        )
        return
    if not model_name:
        yield "❌ Identifiant de modèle absent.", gr.update(value=initial_label, interactive=True)
        return
    try:
        yield f"⏳ Démarrage de {model_name}…", gr.update(value="⏳ Téléchargement…", interactive=False)
        for update in ai_model_manager.install_model_stream(model_name, host=LLM_HOST):
            yield update, gr.update(value="⏳ Téléchargement…", interactive=False)
        yield f"✅ {model_name} installé. Actualisez la liste du chat pour le sélectionner.", gr.update(
            value="↻ Mettre à jour", interactive=True
        )
    except Exception as exc:
        yield f"❌ Échec de l'installation de {model_name} : {exc}", gr.update(
            value="Réessayer", interactive=True
        )


def list_personalities_fn():
    if personality_manager:
        personalities = personality_manager.list_personalities()
        return [(f"{item.get('emoji', '')} {item.get('name', item['id'])}", item["id"]) for item in personalities]
    return [("🤖 Assistant", "assistant")]


def chat_fn(message, history, model, personality_id, temperature, image_path=None):
    if not llm:
        return "Le module de dialogue local n'est pas disponible. Réinstallez les dépendances du projet."
    if not model:
        return "Aucun modèle compatible n'est installé. Ouvrez l'onglet « Modèles IA » pour voir les modèles adaptés à cette machine."
    if not is_model_compatible_fn(model):
        return "Ce modèle est masqué sur cette machine car ses besoins en mémoire dépassent le profil détecté."

    text = (message or "").strip()
    if not text and not image_path:
        return "Écrivez un message ou joignez une image."
    if not text and image_path:
        text = "Décris cette image et réponds en français."

    if personality_manager:
        personality = personality_manager.get_personality(personality_id or "assistant")
        system = personality.get("system", "")
    else:
        system = ""

    return llm.chat(
        text,
        model=model,
        history=history or [],
        system=system,
        temperature=temperature,
        host=LLM_HOST,
        image_path=image_path,
    )


def custom_prompt_chat_fn(message, history, model, system_prompt, temperature):
    """Chat séparé pour les personnes qui veulent écrire leurs propres instructions système."""
    if not llm:
        return "Le module de dialogue local n'est pas disponible."
    if not model:
        return "Aucun modèle compatible installé. Consultez les modèles proposés pour cette machine."
    if not is_model_compatible_fn(model):
        return "Ce modèle est masqué sur cette machine car ses besoins en mémoire dépassent le profil détecté."
    if not message or not message.strip():
        return "Saisissez un message."
    return llm.chat(
        message.strip(),
        model=model,
        history=history or [],
        system=(system_prompt or "").strip(),
        temperature=temperature,
        host=LLM_HOST,
    )


def refresh_advanced_models_fn(current_model=None):
    models = list_models_fn()
    selected = current_model if current_model in models else initial_model_value(models)
    return gr.Dropdown(choices=models, value=selected, label="Modèle installé")


def prepare_agent_workspace_fn(path):
    """Crée/vérifie le dossier projet à la demande de l'utilisateur."""
    if not local_agent:
        return path, "❌ Module agent indisponible. Vérifiez les fichiers du projet."
    try:
        workspace = local_agent.validate_workspace(path, create=True)
        return str(workspace), f"✅ Dossier projet prêt : {workspace}"
    except Exception as exc:
        return path, f"❌ {exc}"


def _agent_event_for_journal(event, state):
    """Transforme les événements agent en journal local compact et lisible."""
    if not local_agent or not isinstance(event, dict):
        return None
    kind = event.get("kind")
    if kind == "pending":
        pending = (state or {}).get("pending") or {}
        action_type = pending.get("type")
        if action_type == "plan":
            return {
                "kind": "plan_proposed",
                "summary": pending.get("summary", "Plan proposé"),
                "diff": "\n".join(pending.get("steps", [])),
            }
        if action_type == "write_file":
            try:
                summary, diff = local_agent.describe_pending_action(state.get("workspace", ""), pending)
            except Exception as exc:
                summary, diff = "Écriture proposée", str(exc)
            return {"kind": "write_proposed", "summary": summary, "path": pending.get("path", ""), "diff": diff}
        if action_type == "run_command":
            return {"kind": "command_proposed", "summary": "Commande proposée pour approbation", "argv": pending.get("argv", [])}
        if action_type == "install_prerequisites":
            return {
                "kind": "prerequisites_install_proposed",
                "summary": "Installation Python proposée : " + ", ".join(pending.get("packages", [])),
            }
    if kind == "clarification":
        return {"kind": "clarification_requested", "summary": event.get("question", event.get("reply", "Question de clarification"))}
    if kind == "paused":
        return {"kind": "task_paused", "summary": event.get("reply", event.get("status", "Tâche en pause"))}
    if kind == "done":
        return {"kind": "task_finished", "summary": event.get("reply", event.get("status", "Tâche terminée"))}
    if kind == "error":
        return {"kind": "agent_error", "result": event.get("status", "Erreur agent")}
    return None


def _persist_agent_state(state, conversation, event=None):
    """Sauvegarde la session localement et bloque les actions si le journal est indisponible."""
    current = dict(state or {})
    if not local_agent or not current.get("workspace"):
        return current, ""
    try:
        local_agent.save_agent_session(current["workspace"], current, conversation or [], event=event)
        current["journal_persisted"] = True
        return current, ""
    except Exception as exc:
        current["journal_persisted"] = False
        return current, f"\n\n⚠️ Journal local non sauvegardé — approbation d'écriture/commande suspendue : {exc}"


def agent_restore_fn(history, state, workspace):
    """Restaure explicitement la dernière session locale, sans exécuter d'action en attente."""
    conversation = list(history or [])
    state = dict(state or {})
    if state.get("pending") or state.get("messages") or conversation:
        return _agent_ui_values(
            conversation, "", state,
            "Une conversation est déjà ouverte. Termine-la ou clique d'abord sur Nouvelle conversation avant de restaurer.",
        )
    if not local_agent:
        return _agent_ui_values(conversation, "", state, "❌ Module agent indisponible.")
    try:
        restored = local_agent.load_agent_session(workspace)
    except Exception as exc:
        return _agent_ui_values(conversation, "", state, f"❌ Journal non chargé : {exc}")
    if not restored:
        return _agent_ui_values(conversation, "", state, "Aucune session sauvegardée pour ce dossier projet.")
    restored_state = dict(restored["state"])
    restored_state["journal_persisted"] = True
    restored_conversation = list(restored.get("conversation", []))
    updated_at = restored.get("updated_at") or "date inconnue"
    status = (
        f"✅ Session restaurée depuis {updated_at}. {len(restored.get('events', []))} événement(s) dans le journal. "
        "Aucune action en attente n'a été exécutée; toute écriture/commande restaurée exige un nouvel accord."
    )
    if restored.get("warning"):
        status += f"\n\n⚠️ {restored['warning']}"
    status += f"\n\nJournal local : `{restored.get('journal_path', '')}`"
    restored_state, save_warning = _persist_agent_state(restored_state, restored_conversation)
    status += save_warning
    return _agent_ui_values(restored_conversation, "", restored_state, status)


def _agent_pending_ui(state):
    pending = (state or {}).get("pending")
    if not pending or not local_agent:
        return "", ""
    try:
        return local_agent.describe_pending_action(state.get("workspace", ""), pending)
    except Exception as exc:
        return f"Action en attente invalide : {exc}", ""


def _agent_ui_values(conversation, message, state, status, feedback=""):
    summary, preview = _agent_pending_ui(state)
    pending = (state or {}).get("pending") or {}
    has_pending = bool(pending)
    has_undo = bool((state or {}).get("undo_stack")) and not has_pending
    is_plan = pending.get("type") == "plan"
    try:
        remaining_steps = int((state or {}).get("remaining_steps", 0) or 0)
    except (TypeError, ValueError):
        remaining_steps = 0
    awaiting_clarification = bool((state or {}).get("awaiting_clarification"))
    can_continue = bool((state or {}).get("plan_approved")) and remaining_steps <= 0 and not has_pending and not awaiting_clarification
    return (
        conversation,
        message,
        state,
        status,
        summary,
        preview,
        feedback,
        gr.update(
            value=(
                "✅ Approuver le plan" if is_plan
                else "✅ Installer les prérequis" if pending.get("type") == "install_prerequisites"
                else "✅ Approuver et continuer"
            ),
            interactive=has_pending and bool((state or {}).get("journal_persisted", True)),
        ),
        gr.update(
            value=(
                "⛔ Refuser / ajuster le plan" if is_plan
                else "⛔ Refuser l'installation" if pending.get("type") == "install_prerequisites"
                else "⛔ Refuser et demander une alternative"
            ),
            interactive=has_pending,
        ),
        gr.update(interactive=has_undo),
        gr.update(interactive=can_continue),
    )


def _agent_continue(model, conversation, state):
    """Exécute l'agent natif avec le modèle Ollama local sélectionné."""
    state = dict(state or {})
    if not local_agent:
        yield _agent_ui_values(conversation, "", state, "❌ Module agent indisponible.")
        return
    if not llm:
        yield _agent_ui_values(conversation, "", state, "❌ Le client Ollama n'est pas disponible.")
        return
    if not model:
        yield _agent_ui_values(conversation, "", state, "❌ Sélectionne un modèle Ollama compatible installé.")
        return
    if not is_model_compatible_fn(model):
        yield _agent_ui_values(
            conversation, "", state,
            "❌ Ce modèle n'est pas compatible avec le profil matériel détecté; il n'a pas été lancé.",
        )
        return

    def model_call(messages, system):
        if not messages or messages[-1].get("role") != "user":
            raise ValueError("L'historique agent n'attend pas une réponse utilisateur/outils.")
        latest = messages[-1].get("content", "")
        return llm.chat(
            latest,
            model=model,
            history=messages[:-1],
            system=system,
            temperature=0.1,
            host=LLM_HOST,
            response_format="json",
        )

    try:
        for event in local_agent.agent_loop(state.get("workspace", ""), state, model_call):
            state = dict(event.get("state", state))
            status = event.get("status", "")
            if (
                event.get("kind") == "error"
                and state.get("plan_approved")
                and not state.get("pending")
                and not state.get("awaiting_clarification")
            ):
                # Un échec interrompt la boucle avant qu'elle n'ait remis le budget à zéro.
                # Laisser Continuer actif permet une reprise explicite avec le même plan.
                state["remaining_steps"] = 0
            if event.get("kind") in {"pending", "clarification", "done", "paused", "error"}:
                reply = event.get("reply")
                if reply:
                    conversation = list(conversation or []) + [{"role": "assistant", "content": reply}]
            journal_event = _agent_event_for_journal(event, state)
            state, journal_warning = _persist_agent_state(state, conversation, event=journal_event)
            if journal_warning:
                status += journal_warning
            yield _agent_ui_values(conversation, "", state, status)
    except Exception as exc:
        if (
            state.get("plan_approved")
            and not state.get("pending")
            and not state.get("awaiting_clarification")
        ):
            # Même une exception inattendue ne doit pas bloquer la reprise du plan approuvé.
            state["remaining_steps"] = 0
        state, journal_warning = _persist_agent_state(
            state, conversation, event={"kind": "agent_error", "result": str(exc)}
        )
        yield _agent_ui_values(conversation, "", state, f"❌ Erreur agent : {exc}" + journal_warning)

def _is_continue_agent_request(message):
    normalized = " ".join((message or "").strip().casefold().split())
    return normalized in {
        "continue", "continuer", "continue la tâche", "continue la tache",
        "continuer la tâche", "continuer la tache", "reprends", "reprendre",
        "reprends la tâche", "reprends la tache", "poursuis", "poursuivre",
    }


def _recover_approved_agent_state_from_journal(history, state, workspace):
    """Récupère un plan approuvé si le navigateur a perdu son gr.State, sans croiser les sessions."""
    current = dict(state or {})
    if current.get("plan_approved") or current.get("pending") or current.get("awaiting_clarification"):
        return None
    if not local_agent:
        return None
    try:
        root = local_agent.validate_workspace(workspace)
        if current.get("workspace") and local_agent.validate_workspace(current["workspace"]) != root:
            return None
        restored = local_agent.load_agent_session(str(root))
    except Exception:
        return None
    if not isinstance(restored, dict) or not isinstance(restored.get("state"), dict):
        return None
    saved_state = dict(restored["state"])
    if not saved_state.get("plan_approved") or saved_state.get("pending") or saved_state.get("awaiting_clarification"):
        return None

    def signature(items):
        return [
            (item["role"], item["content"])
            for item in (items or [])
            if isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
        ]

    visible = signature(history)
    persisted = signature(restored.get("conversation"))
    overlap = min(8, len(visible), len(persisted))
    if overlap < 2 or visible[-overlap:] != persisted[-overlap:]:
        return None
    saved_state["workspace"] = str(root)
    saved_state["journal_persisted"] = True
    return saved_state


def agent_resume_fn(history, state, model, workspace):
    """Reprend le même plan approuvé avec le LLM Ollama natif."""
    conversation = list(history or [])
    state = dict(state or {})
    if not local_agent:
        yield _agent_ui_values(conversation, "", state, "❌ Module agent indisponible.")
        return
    recovered_state = _recover_approved_agent_state_from_journal(conversation, state, workspace)
    recovered_from_journal = recovered_state is not None
    if recovered_from_journal:
        state = recovered_state
    try:
        state = local_agent.continue_approved_task(state, workspace)
    except Exception as exc:
        yield _agent_ui_values(conversation, "", state, f"❌ Reprise impossible : {exc}")
        return
    conversation.append({"role": "assistant", "content": "↻ Je reprends le plan approuvé à la prochaine étape non terminée."})
    state, journal_warning = _persist_agent_state(
        state, conversation,
        event={"kind": "task_resumed", "summary": "Reprise du plan approuvé après la limite d'étapes."},
    )
    recovery_note = "⚠️ État de l'interface récupéré depuis le journal de cette conversation. " if recovered_from_journal else ""
    status = recovery_note + "↻ Reprise de la tâche en cours; le plan reste approuvé." + journal_warning
    yield _agent_ui_values(conversation, "", state, status)
    yield from _agent_continue(model, conversation, state)

def agent_start_fn(message, history, state, model, workspace):
    """Démarre une demande ou reprend explicitement un plan approuvé."""
    conversation = list(history or [])
    state = dict(state or {"messages": [], "pending": None, "workspace": "", "remaining_steps": 0})
    normalized_message = " ".join((message or "").strip().casefold().split())
    is_continue = _is_continue_agent_request(message)
    try:
        remaining_steps = int(state.get("remaining_steps", 0) or 0)
    except (TypeError, ValueError):
        remaining_steps = 0

    if state.get("awaiting_clarification"):
        if not normalized_message:
            yield _agent_ui_values(
                conversation, "", state,
                "❓ Réponds à la question affichée dans la conversation, ou écris « continue » pour que l'agent choisisse une hypothèse standard.",
            )
            return
        if not local_agent:
            yield _agent_ui_values(conversation, message or "", state, "❌ Module agent indisponible.")
            return
        if not llm or not model:
            yield _agent_ui_values(conversation, message or "", state, "❌ Sélectionne un modèle Ollama compatible avant de répondre.")
            return
        if not is_model_compatible_fn(model):
            yield _agent_ui_values(conversation, message or "", state, "❌ Le modèle sélectionné n'est pas compatible avec cette machine.")
            return
        try:
            answered_state = local_agent.answer_agent_clarification(state, workspace, message)
        except Exception as exc:
            yield _agent_ui_values(conversation, message or "", state, f"❌ Réponse non transmise : {exc}")
            return
        conversation.append({"role": "user", "content": (message or "").strip()})
        answered_state, journal_warning = _persist_agent_state(
            answered_state,
            conversation,
            event={"kind": "clarification_answered", "summary": (message or "").strip()[:1_000]},
        )
        yield _agent_ui_values(
            conversation, "", answered_state,
            "✅ Réponse reçue; l'agent reprend le plan déjà approuvé." + journal_warning,
        )
        yield from _agent_continue(model, conversation, answered_state)
        return

    if is_continue or (
        not normalized_message and state.get("plan_approved") and remaining_steps <= 0
    ):
        yield from agent_resume_fn(history, state, model, workspace)
        return
    if not local_agent:
        yield _agent_ui_values(conversation, message or "", state, "❌ Module agent indisponible.")
        return
    try:
        root = local_agent.validate_workspace(workspace)
        state_workspace = state.get("workspace")
        if state_workspace:
            old_root = local_agent.validate_workspace(state_workspace)
            if old_root != root:
                if state.get("pending"):
                    yield _agent_ui_values(
                        conversation, message or "", state,
                        "Une action est en attente pour un autre dossier. Reviens à ce projet ou refuse/restaure l'action avant de changer de dossier.",
                    )
                    return
                state = {"messages": [], "pending": None, "workspace": "", "remaining_steps": 0,
                         "plan_approved": False, "awaiting_clarification": False,
                         "undo_stack": [], "git_checkpoint_branch": None}
                conversation = []
        else:
            previous = local_agent.load_agent_session(str(root))
            if previous:
                previous_state = dict(previous["state"])
                if previous_state.get("pending"):
                    previous_state["journal_persisted"] = True
                    yield _agent_ui_values(
                        previous.get("conversation", []), message or "", previous_state,
                        "Une session précédente contient une action en attente. Restaure-la, puis approuve ou refuse explicitement cette action avant d'en commencer une autre.",
                    )
                    return
                state = {
                    "messages": [], "pending": None, "workspace": "", "remaining_steps": 0,
                    "plan_approved": False,
                    "awaiting_clarification": False,
                    "undo_stack": previous_state.get("undo_stack", []),
                    "git_checkpoint_branch": previous_state.get("git_checkpoint_branch"),
                    "journal_persisted": True,
                }
        state = local_agent.begin_user_turn(state, str(root), message or "")
        state["journal_persisted"] = True
    except Exception as exc:
        yield _agent_ui_values(conversation, message or "", state, f"❌ {exc}")
        return

    conversation.append({"role": "user", "content": (message or "").strip()})
    request_event = {"kind": "user_request", "summary": (message or "").strip()[:1_000]}
    state, journal_warning = _persist_agent_state(state, conversation, event=request_event)
    status = "🗺️ L'agent prépare un plan; aucune lecture ni modification ne démarre avant ton accord."
    if journal_warning:
        status += journal_warning
    yield _agent_ui_values(conversation, "", state, status)
    yield from _agent_continue(model, conversation, state)


def _agent_resolve_fn(approved, history, state, model, feedback=""):
    conversation = list(history or [])
    state = dict(state or {})
    if not local_agent:
        yield _agent_ui_values(conversation, "", state, "❌ Module agent indisponible.")
        return
    pending = dict(state.get("pending") or {})
    pending_type = pending.get("type")
    if approved and pending_type in {"write_file", "run_command", "install_prerequisites"}:
        pre_event = {
            "kind": "action_approval_started",
            "path": pending.get("path", ""),
            "argv": pending.get("argv", []),
            "summary": "Installation approuvée : " + ", ".join(pending.get("packages", []))
            if pending_type == "install_prerequisites" else "",
        }
        state, journal_warning = _persist_agent_state(state, conversation, event=pre_event)
        if not state.get("journal_persisted", True):
            yield _agent_ui_values(
                conversation, "", state,
                "Action bloquée : impossible de sauvegarder son approbation dans le journal local." + journal_warning,
                feedback,
            )
            return
    try:
        state, outcome = local_agent.resolve_pending_action(state, approved=approved, feedback=feedback)
    except Exception as exc:
        status = f"❌ Action non exécutée : {exc}"
        state, journal_warning = _persist_agent_state(
            state, conversation,
            event={"kind": "action_failed", "path": pending.get("path", ""), "result": str(exc)},
        )
        yield _agent_ui_values(conversation, "", state, status + journal_warning, feedback)
        return

    auto_install = dict(state.get("pending") or {})
    if approved and pending_type == "run_command" and auto_install.get("type") == "install_prerequisites":
        packages = auto_install.get("packages", [])
        visible_result = outcome.split("Résultat réel :\n", 1)[-1][:4_000]
        conversation.append({
            "role": "assistant",
            "content": (
                "❌ La commande a échoué; sa sortie signale un module Python manquant.\n\n"
                f"{visible_result}\n\n"
                f"Je peux proposer l'installation de {', '.join(packages)} dans l'environnement isolé du projet. "
                "Rien ne sera installé avant ton approbation."
            ),
        })
        status = "⚠️ Prérequis Python manquant détecté. Examine l'action et approuve-la si tu souhaites l'installer."
        state, journal_warning = _persist_agent_state(
            state,
            conversation,
            event={
                "kind": "prerequisites_install_proposed",
                "summary": "Installation à approuver : " + ", ".join(packages),
            },
        )
        yield _agent_ui_values(conversation, "", state, status + journal_warning, feedback)
        return

    if approved and pending_type == "plan":
        conversation.append({"role": "assistant", "content": "✅ Plan approuvé. L'agent commence maintenant l'inspection du projet."})
        status = "✅ Plan approuvé. L'agent reprend son travail…"
        journal_event = {"kind": "plan_approved", "summary": pending.get("summary", "Plan approuvé")}
    elif approved:
        visible_result = outcome.split("Résultat réel :\n", 1)[-1][:4_000]
        if pending_type == "install_prerequisites":
            install_succeeded = "Code de sortie : 0" in visible_result
            conversation.append({
                "role": "assistant",
                "content": (
                    ("✅ Installation des prérequis terminée." if install_succeeded else "⚠️ L'installation des prérequis n'a pas abouti.")
                    + f"\n\n{visible_result}"
                ),
            })
            status = (
                "✅ Environnement Python du projet mis à jour. L'agent reprend le plan approuvé…"
                if install_succeeded else "⚠️ Installation en échec; l'agent reprend le plan avec le résultat réel…"
            )
            journal_event = {
                "kind": "prerequisites_install_completed",
                "summary": ", ".join(pending.get("packages", [])),
                "result": outcome,
            }
        else:
            conversation.append({"role": "assistant", "content": f"✅ Action approuvée et exécutée.\n\n{visible_result}"})
            status = "✅ Action exécutée. L'agent reprend son travail…"
            journal_event = {
                "kind": "write_applied" if pending_type == "write_file" else "command_completed",
                "path": pending.get("path", ""),
                "argv": pending.get("argv", []),
                "result": outcome,
            }
    else:
        prefix = "⛔ Plan refusé." if pending_type == "plan" else "⛔ Action refusée."
        conversation.append({"role": "assistant", "content": f"{prefix} L'agent va intégrer ton retour et proposer la suite."})
        status = "Plan/action refusé; reprise de l'agent…"
        journal_event = {
            "kind": "plan_refused" if pending_type == "plan" else "action_refused",
            "path": pending.get("path", ""),
            "argv": pending.get("argv", []),
            "decision": (feedback or "refus sans commentaire")[:1_000],
        }
    state, journal_warning = _persist_agent_state(state, conversation, event=journal_event)
    status += journal_warning
    yield _agent_ui_values(conversation, "", state, status)
    yield from _agent_continue(model, conversation, state)


def agent_approve_fn(history, state, model):
    yield from _agent_resolve_fn(True, history, state, model)


def agent_reject_fn(history, state, model, feedback):
    yield from _agent_resolve_fn(False, history, state, model, feedback=feedback)


def agent_undo_fn(history, state):
    conversation = list(history or [])
    state = dict(state or {})
    if not local_agent:
        return _agent_ui_values(conversation, "", state, "❌ Module agent indisponible.")
    if state.get("pending"):
        return _agent_ui_values(conversation, "", state, "Traite d'abord l'action en attente avant d'annuler une écriture.")
    undo_stack = list(state.get("undo_stack", []))
    if not undo_stack:
        return _agent_ui_values(conversation, "", state, "Aucune écriture agent à annuler.")
    try:
        outcome = local_agent.undo_last_write(state.get("workspace", ""), undo_stack[-1])
    except Exception as exc:
        return _agent_ui_values(conversation, "", state, f"❌ Annulation impossible : {exc}")
    state["undo_stack"] = undo_stack[:-1]
    messages = list(state.get("messages", []))
    messages.append({"role": "user", "content": f"Résultat de l'outil annulation : {outcome}. Ne considère pas cette modification comme présente."})
    state["messages"] = messages[-local_agent.MAX_CONTEXT_MESSAGES:]
    conversation.append({"role": "assistant", "content": f"↶ {outcome}"})
    state, journal_warning = _persist_agent_state(
        state, conversation, event={"kind": "write_undone", "path": undo_stack[-1].get("path", ""), "result": outcome}
    )
    return _agent_ui_values(conversation, "", state, "↶ Dernière écriture agent annulée." + journal_warning)


def agent_clear_fn(history, state):
    state = dict(state or {})
    if state.get("pending"):
        return _agent_ui_values(
            history or [], "", state,
            "Approuve ou refuse d'abord l'action en attente; la conversation n'a pas été effacée.",
        )
    clean_state = {
        "messages": [],
        "pending": None,
        "workspace": state.get("workspace", ""),
        "remaining_steps": 0,
        "plan_approved": False,
        "awaiting_clarification": False,
        "undo_stack": list(state.get("undo_stack", [])), 
        "git_checkpoint_branch": state.get("git_checkpoint_branch"),
        "journal_persisted": state.get("journal_persisted", True),
    }
    clean_state, journal_warning = _persist_agent_state(
        clean_state, [], event={"kind": "conversation_cleared", "summary": "Conversation effacée; sauvegardes Annuler conservées."}
    )
    return _agent_ui_values([], "", clean_state, "Nouvelle conversation agent." + journal_warning)


def stt_fn(audio_path, model):
    if not stt:
        return "Reconnaissance vocale indisponible (faster-whisper non installé)."
    if audio_path is None:
        return ""
    return stt.transcribe(audio_path, model=model)


def tts_fn(text, provider, voice):
    if not tts:
        return None, "Synthèse vocale indisponible."
    if not text or not text.strip():
        return None, "Texte vide."
    try:
        if provider == "coqui":
            output = tts.tts_coqui(text)
        else:
            output = tts.tts_piper(text, voice=voice)
        return output, f"Audio généré : {Path(output).name}"
    except Exception as exc:
        return None, f"Erreur TTS : {exc}"


def rag_embedding_choices_fn(current_model=None):
    if not rag or not hasattr(rag, "available_embedding_choices"):
        return gr.update(choices=[], value=None), "Moteurs d'embedding indisponibles."
    choices = rag.available_embedding_choices(all_installed_models_fn(), current_machine_profile())
    values = [value for _, value in choices]
    selected = current_model if current_model in values else (values[0] if values else None)
    status = (
        "Le modèle d'embedding sélectionné garde son propre index; pour BGE-M3, réimportez les documents afin de les indexer dans le nouvel espace."
        if choices else
        "Aucun moteur d'embedding compatible n'est prêt. Installez les dépendances RAG ou téléchargez BGE-M3 depuis Modèles IA si proposé."
    )
    return gr.update(choices=choices, value=selected), status


def rag_ingest_fn(file, embedding_model=None):
    if not rag:
        return "RAG indisponible (dépendances manquantes)."
    if file is None:
        return "Aucun document sélectionné."
    file_path = file.name if hasattr(file, "name") else str(file)
    _, message = rag.ingest_file(file_path, embedding_model=embedding_model or rag.LEGACY_EMBEDDING_MODEL, host=LLM_HOST)
    return message


def rag_query_fn(question, embedding_model=None):
    if not rag:
        return "RAG indisponible (dépendances manquantes)."
    if not question or not question.strip():
        return "Saisissez une question."
    selected = embedding_model or rag.LEGACY_EMBEDDING_MODEL
    return rag.query(question, embedding_model=selected, host=LLM_HOST)


def monitor_fn():
    if resource_monitor:
        return resource_monitor.format_stats()
    return "Monitoring indisponible (psutil manquant)."


def clean_fn():
    if auto_cleaner:
        cleaned = auto_cleaner.clean_temp(dry_run=False)
        return f"Nettoyage terminé : {len(cleaned)} fichier(s).\n" + "\n".join(cleaned[:20])
    return "Nettoyage indisponible."


def check_llm_fn():
    if llm_checker:
        result = llm_checker.check_all(host=LLM_HOST)
        result["installed_models"] = list_models_fn()
        return json.dumps(result, indent=2, ensure_ascii=False)
    if llm:
        return f"Ollama actif : {llm.check_ollama(LLM_HOST)}\nModèles installés : {', '.join(list_models_fn()) or 'aucun'}"
    return "Vérification LLM indisponible."


def diagnostic_fn():
    """Lance le diagnostic des dépendances et retourne sa sortie."""
    preflight = PROJECT_ROOT / "preflight.py"
    try:
        result = subprocess.run(
            [sys.executable, str(preflight)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=90,
            cwd=str(PROJECT_ROOT),
        )
        return result.stdout + ("\n" + result.stderr if result.stderr else "")
    except Exception as exc:
        return f"Erreur diagnostic : {exc}"


def install_core_fn():
    """Démarre l'installation de base en arrière-plan (sans tirer plusieurs modèles)."""
    auto_installer = PROJECT_ROOT / "auto_install.py"

    def run_install():
        try:
            subprocess.run(
                [sys.executable, str(auto_installer), "--core"],
                cwd=str(PROJECT_ROOT),
                timeout=1800,
                check=False,
            )
        except Exception as exc:
            print(f"[INSTALL] Échec : {exc}")

    threading.Thread(target=run_install, daemon=True).start()
    return "Installation du noyau lancée. Les modèles IA se choisissent séparément dans l'onglet « Modèles IA »."


def generate_image_fn(prompt, steps, guidance):
    if not prompt or not prompt.strip():
        return None, "Décrivez l'image à générer."
    try:
        import torch
        from diffusers import StableDiffusionPipeline

        model_id = CONFIG.get("images", {}).get("model", "stabilityai/stable-diffusion-2-1-base")
        pipeline = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=torch.float32)
        pipeline = pipeline.to("cpu")
        image = pipeline(prompt, num_inference_steps=int(steps), guidance_scale=float(guidance)).images[0]

        output_path = PROJECT_ROOT / "outputs" / f"img_{os.urandom(4).hex()}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
        return str(output_path), f"Image générée : {output_path.name}"
    except ImportError as exc:
        return None, f"Génération d'images indisponible (torch/diffusers manquants) : {exc}"
    except Exception as exc:
        return None, f"Erreur de génération : {exc}"


def build_ui():
    machine_profile = current_machine_profile()
    all_installed_models = all_installed_models_fn()
    installed_models = compatible_installed_models(all_installed_models, machine_profile)
    selected_model = initial_model_value(installed_models)
    initial_status = machine_and_models_status(machine_profile, all_installed_models)
    if not all_installed_models:
        initial_status += "\n\nOllama est hors ligne ou aucun modèle n'est installé; ouvrez l'onglet **Modèles IA**."
    elif not installed_models:
        initial_status += "\n\nAucun LLM installé ne correspond aux ressources détectées."
    embedding_choices = (
        rag.available_embedding_choices(all_installed_models, machine_profile)
        if rag and hasattr(rag, "available_embedding_choices") else []
    )
    embedding_default = next((value for _, value in embedding_choices), None)

    with gr.Blocks(
        theme=get_theme(),
        css=CUSTOM_CSS,
        title=CONFIG.get("ui", {}).get("title", "IA Locale"),
    ) as demo:
        gr.HTML("""
        <header class="hero">
          <div class="hero-kicker"><span class="hero-pulse"></span> CONFIDENTIEL · TRAITEMENT SUR CET APPAREIL</div>
          <h1>IA <span>Locale</span></h1>
          <p>Votre espace privé pour dialoguer, explorer vos documents et développer des projets avec un agent local.</p>
          <div class="hero-tags"><span>Ollama</span><span>Agent développement</span><span>Sans compte cloud</span></div>
        </header>
        """)

        with gr.Tab("💬 Chat"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=4, min_width=430):
                    chatbot = gr.Chatbot(label="Conversation", height=480, type="tuples")
                    image_input = gr.Image(
                        type="filepath",
                        label="Image facultative — choisissez un modèle compatible vision",
                    )
                    msg = gr.Textbox(
                        label="Votre message",
                        placeholder="Posez une question…",
                        lines=2,
                    )
                    with gr.Row():
                        send_btn = gr.Button("Envoyer", variant="primary")
                        clear_btn = gr.Button("Effacer la conversation")
                with gr.Column(scale=1, min_width=250):
                    gr.Markdown("### Réglages")
                    model_dropdown = gr.Dropdown(
                        choices=installed_models,
                        value=selected_model,
                        label="Modèle installé",
                        allow_custom_value=False,
                    )
                    models_status = gr.Markdown(initial_status)
                    refresh_models_btn = gr.Button("Actualiser les modèles")
                    personality_dropdown = gr.Dropdown(
                        choices=list_personalities_fn(),
                        value="assistant",
                        label="Personnalité",
                    )
                    temp_slider = gr.Slider(
                        0,
                        1.5,
                        value=float(LLM_CONFIG.get("temperature", 0.7)),
                        label="Température",
                    )
                    gr.Markdown("Les modèles vision acceptent une image jointe. Le chat et Ollama restent sur votre machine.")

            def on_send(message, history, model, personality_id, temperature, image_path):
                message = message or ""
                if not message.strip() and not image_path:
                    return history or [], "", None
                response = chat_fn(message, history, model, personality_id, temperature, image_path)
                shown_message = message.strip() or "Décris cette image et réponds en français."
                if image_path:
                    shown_message = "🖼️ Image jointe\n" + shown_message
                return (history or []) + [(shown_message, response)], "", None

            send_btn.click(
                on_send,
                [msg, chatbot, model_dropdown, personality_dropdown, temp_slider, image_input],
                [chatbot, msg, image_input],
            )
            msg.submit(
                on_send,
                [msg, chatbot, model_dropdown, personality_dropdown, temp_slider, image_input],
                [chatbot, msg, image_input],
            )
            clear_btn.click(lambda: ([], "", None), None, [chatbot, msg, image_input])
            refresh_models_btn.click(
                refresh_models_fn,
                [model_dropdown],
                [model_dropdown, models_status],
            )

        with gr.Tab("🛠️ Agent développement"):
            gr.Markdown(
                "## Agent de programmation local\n"
                "L'agent présente d'abord un plan à approuver. Après accord, il peut explorer le projet et lire/rechercher "
                "dans ses fichiers; les écritures montrent un diff, créent une sauvegarde et proposent un bouton Annuler. "
                "Chaque commande de test ou compilation demande aussi ton approbation et s'exécute sur une copie du projet. "
                "La session et les décisions sont sauvegardées localement pour pouvoir être restaurées. "
                "Chaque lot autorise jusqu'à 24 étapes. Si le lot se termine avant la tâche, clique sur « Continuer la tâche » : le plan approuvé sera repris sans repartir de zéro."
            )
            gr.Markdown(
                "**Sécurité :** les outils de fichiers sont confinés au dossier choisi et bloquent les chemins qui en sortent ainsi que les secrets courants. "
                "Les sauvegardes de fichiers sont dans ~/.ia-locale/agent-backups; les sessions/décisions sont dans ~/.ia-locale/agent-journals. "
                "Un dépôt Git propre reçoit aussi une branche de point de retour. Les commandes approuvées (sauf les lectures Git) s'exécutent sur une copie conservée sous ~/.ia-locale/agent-runs, pas sur le projet source. "
                "Ce n'est pas un bac à sable OS : elles gardent les droits du compte et peuvent avoir des effets hors de la copie. "
                "Le journal local peut contenir des messages, extraits de fichiers et sorties de commandes; il n'est pas synchronisé dans le cloud et peut être supprimé manuellement. "
                "Les actions en attente ne sont jamais exécutées à la restauration et doivent être approuvées de nouveau. IA Locale ne lance pas de shell composé. "
                "Le LLM sélectionné communique uniquement avec Ollama local; local_agent orchestre les outils et garde les confirmations. "
                "Chaque écriture et commande continue d'exiger un accord distinct."
            )
            with gr.Row():
                agent_workspace = gr.Textbox(
                    value=str(Path.home() / "IA-Projects"),
                    label="Dossier du projet à confier à l'agent",
                    placeholder="Ex. C:\\Users\\toi\\IA-Projects\\MonApp",
                    scale=5,
                )
                agent_workspace_btn = gr.Button("Créer / vérifier le dossier", scale=1)
                agent_restore_btn = gr.Button("Restaurer la session", variant="secondary", scale=1)
            agent_workspace_status = gr.Markdown(
                "Choisis un dossier dédié à un projet, puis clique sur **Créer / vérifier le dossier**."
            )
            agent_workspace_btn.click(
                prepare_agent_workspace_fn,
                [agent_workspace],
                [agent_workspace, agent_workspace_status],
            )

            with gr.Row():
                agent_model = gr.Dropdown(
                    choices=installed_models,
                    value=selected_model,
                    label="Modèle Ollama de l'agent",
                    allow_custom_value=False,
                    scale=4,
                )
                agent_models_status = gr.Markdown(initial_status)
                agent_refresh_models_btn = gr.Button("Actualiser les modèles")
                agent_refresh_models_btn.click(
                    refresh_agent_models_fn,
                    [agent_model],
                    [agent_model, agent_models_status],
                )

            gr.Markdown(
                "**Mode agent natif :** le LLM Ollama choisi ci-dessus pilote la tâche; seuls les modèles locaux installés et compatibles sont proposés. "
                "Aucun compte cloud ni sous-agent externe n'est utilisé."
            )

            agent_chatbot = gr.Chatbot(
                label="Conversation agent",
                height=430,
                type="messages",
            )
            agent_state = gr.State(value={
                "messages": [], "pending": None, "workspace": "", "remaining_steps": 0,
                "plan_approved": False, "awaiting_clarification": False,
                "undo_stack": [], "git_checkpoint_branch": None,
                "journal_persisted": True,
            })
            agent_message = gr.Textbox(
                label="Tâche à réaliser",
                placeholder="Ex. Analyse ce projet, corrige le bug décrit et lance les tests.",
                lines=3,
            )
            with gr.Row():
                agent_send_btn = gr.Button("Lancer l'agent", variant="primary")
                agent_continue_btn = gr.Button("↻ Continuer la tâche", variant="secondary", interactive=False)
                agent_clear_btn = gr.Button("Nouvelle conversation")
            agent_status = gr.Markdown("L'agent attend une tâche.")
            agent_pending_summary = gr.Textbox(
                label="Plan ou action à examiner",
                lines=5,
                interactive=False,
            )
            agent_pending_preview = gr.Textbox(
                label="Plan, diff ou commande proposée",
                lines=12,
                max_lines=35,
                interactive=False,
            )
            agent_feedback = gr.Textbox(
                label="Retour facultatif pour ajuster un plan / demander une alternative",
                placeholder="Ex. conserve l'API existante et ne modifie pas config.yaml.",
                lines=2,
            )
            with gr.Row():
                agent_approve_btn = gr.Button("✅ Approuver le plan / l'action", variant="primary", interactive=False)
                agent_reject_btn = gr.Button("⛔ Refuser / demander un ajustement", variant="secondary", interactive=False)
                agent_undo_btn = gr.Button("↶ Annuler la dernière écriture", variant="secondary", interactive=False)

            agent_outputs = [
                agent_chatbot,
                agent_message,
                agent_state,
                agent_status,
                agent_pending_summary,
                agent_pending_preview,
                agent_feedback,
                agent_approve_btn,
                agent_reject_btn,
                agent_undo_btn,
                agent_continue_btn,
            ]
            agent_inputs = [agent_message, agent_chatbot, agent_state, agent_model, agent_workspace]
            agent_restore_btn.click(
                agent_restore_fn,
                [agent_chatbot, agent_state, agent_workspace],
                agent_outputs,
                concurrency_limit=1,
                concurrency_id="local-agent",
            )
            agent_send_btn.click(
                agent_start_fn,
                agent_inputs,
                agent_outputs,
                concurrency_limit=1,
                concurrency_id="local-agent",
            )
            agent_continue_btn.click(
                agent_resume_fn,
                [agent_chatbot, agent_state, agent_model, agent_workspace],
                agent_outputs,
                concurrency_limit=1,
                concurrency_id="local-agent",
            )
            agent_message.submit(
                agent_start_fn,
                agent_inputs,
                agent_outputs,
                concurrency_limit=1,
                concurrency_id="local-agent",
            )
            agent_approve_btn.click(
                agent_approve_fn,
                [agent_chatbot, agent_state, agent_model],
                agent_outputs,
                concurrency_limit=1,
                concurrency_id="local-agent",
            )
            agent_reject_btn.click(
                agent_reject_fn,
                [agent_chatbot, agent_state, agent_model, agent_feedback],
                agent_outputs,
                concurrency_limit=1,
                concurrency_id="local-agent",
            )
            agent_undo_btn.click(
                agent_undo_fn,
                [agent_chatbot, agent_state],
                agent_outputs,
                concurrency_limit=1,
                concurrency_id="local-agent",
            )
            agent_clear_btn.click(agent_clear_fn, [agent_chatbot, agent_state], agent_outputs)

        with gr.Tab("🧠 Modèles IA"):
            gr.Markdown(
                "## Modèles locaux adaptés à cette machine\n"
                "Le catalogue est filtré au lancement selon la RAM détectée et la VRAM GPU disponible. "
                "Les seuils sont conservateurs; ils ne garantissent pas la vitesse. Les modèles hors critères n'ont pas de bouton de téléchargement."
            )
            gr.Markdown(hardware_profile.format_machine_profile(machine_profile) if hardware_profile else initial_status)
            eligible_llms = (
                ai_model_manager.get_compatible_catalog_models(ModelCategory.LLM, machine_profile)
                if ai_model_manager and ModelCategory else []
            )
            gr.Markdown(
                f"**{len(eligible_llms)} LLM(s) affiché(s) sur {len(LLM_MODELS)}**. "
                "Les modèles installés hors catalogue restent masqués. Pour recalculer le profil après un changement matériel, redémarrez IA Locale."
            )
            with gr.Row():
                refresh_catalog_btn = gr.Button("Actualiser les modèles installés")
                refresh_catalog_btn.click(
                    refresh_models_fn,
                    [model_dropdown],
                    [model_dropdown, models_status],
                )
            install_progress = gr.Textbox(
                label="Progression du dernier téléchargement",
                lines=4,
                interactive=False,
                placeholder="Cliquez sur le bouton d'un modèle compatible pour suivre Ollama ici.",
            )
            for model in LLM_MODELS:
                visible = is_model_compatible_fn(model["id"], machine_profile)
                with gr.Row(equal_height=True, visible=visible):
                    gr.Markdown(model_card_markdown(model))
                    installed = ai_model_manager.is_model_installed(model["id"], all_installed_models) if ai_model_manager else False
                    button_label = "↻ Mettre à jour" if installed else "⬇ Télécharger"
                    install_button = gr.Button(
                        button_label,
                        variant="primary" if model.get("recommended") else "secondary",
                    )
                    install_button.click(
                        install_model_button_fn,
                        inputs=[gr.State(value=model["id"]), gr.State(value=button_label)],
                        outputs=[install_progress, install_button],
                        concurrency_limit=1,
                        concurrency_id="ollama-model-download",
                    )

            embedding_models = (
                ai_model_manager.get_compatible_catalog_models(ModelCategory.EMBEDDING, machine_profile)
                if ai_model_manager and ModelCategory else []
            )
            if embedding_models:
                gr.Markdown("### Embeddings pour les documents (RAG)")
                for model in embedding_models:
                    with gr.Row(equal_height=True):
                        gr.Markdown(model_card_markdown(model))
                        installed = ai_model_manager.is_model_installed(model["id"], all_installed_models)
                        button_label = "↻ Mettre à jour" if installed else "⬇ Télécharger"
                        install_button = gr.Button(button_label, variant="secondary")
                        install_button.click(
                            install_model_button_fn,
                            inputs=[gr.State(value=model["id"]), gr.State(value=button_label)],
                            outputs=[install_progress, install_button],
                            concurrency_limit=1,
                            concurrency_id="ollama-model-download",
                        )
            gr.Markdown(
                "Après un téléchargement, actualisez les modèles installés. Pour BGE-M3, actualisez aussi le choix du moteur dans l'onglet Documents. "
                "Aucun poids n'est téléchargé automatiquement."
            )

        with gr.Tab("🧪 Prompt personnalisé"):
            gr.Markdown(
                "### Instructions système personnalisées\n"
                "Testez un rôle, un format ou un style sans modifier les fichiers de personnalité. "
                "Le texte système guide le modèle, sans garantir qu'il suivra chaque consigne."
            )
            with gr.Row():
                custom_model = gr.Dropdown(
                    choices=installed_models,
                    value=selected_model,
                    label="Modèle installé",
                )
                custom_temperature = gr.Slider(0, 1.5, value=0.7, label="Température")
                custom_refresh_btn = gr.Button("Actualiser")
            custom_refresh_btn.click(
                refresh_advanced_models_fn,
                [custom_model],
                [custom_model],
            )
            custom_system_prompt = gr.Textbox(
                label="Instructions système",
                lines=5,
                placeholder="Exemple : réponds en français, avec des étapes courtes et un exemple concret.",
            )
            custom_chatbot = gr.Chatbot(label="Conversation personnalisée", height=380, type="tuples")
            custom_msg = gr.Textbox(label="Votre message", placeholder="Écrivez ici…", lines=2)
            with gr.Row():
                custom_send_btn = gr.Button("Envoyer", variant="primary")
                custom_clear_btn = gr.Button("Effacer")

            def on_custom_send(message, history, model, system_prompt, temperature):
                message = message or ""
                if not message.strip():
                    return history or [], ""
                response = custom_prompt_chat_fn(message, history, model, system_prompt, temperature)
                return (history or []) + [(message, response)], ""

            custom_send_btn.click(
                on_custom_send,
                [custom_msg, custom_chatbot, custom_model, custom_system_prompt, custom_temperature],
                [custom_chatbot, custom_msg],
            )
            custom_msg.submit(
                on_custom_send,
                [custom_msg, custom_chatbot, custom_model, custom_system_prompt, custom_temperature],
                [custom_chatbot, custom_msg],
            )
            custom_clear_btn.click(lambda: ([], ""), None, [custom_chatbot, custom_msg])

        with gr.Tab("🎙️ Voix — transcription"):
            gr.Markdown("### Reconnaissance vocale locale · faster-whisper")
            with gr.Row():
                audio_input = gr.Audio(type="filepath", label="Audio à transcrire")
                stt_model = gr.Dropdown(
                    choices=["base", "small", "medium", "large-v3"],
                    value="base",
                    label="Taille Whisper",
                )
            stt_output = gr.Textbox(label="Transcription", lines=5)
            stt_btn = gr.Button("Transcrire", variant="primary")
            stt_btn.click(stt_fn, [audio_input, stt_model], [stt_output])

        with gr.Tab("🔊 Voix — synthèse"):
            gr.Markdown("### Synthèse vocale locale · Piper / Coqui")
            tts_text = gr.Textbox(label="Texte à prononcer", lines=3)
            with gr.Row():
                tts_provider = gr.Dropdown(choices=["piper", "coqui"], value="piper", label="Moteur")
                tts_voice = gr.Textbox(value="fr_FR-siwis-medium", label="Voix Piper")
            tts_audio = gr.Audio(label="Audio généré", type="filepath")
            tts_log = gr.Textbox(label="État")
            tts_btn = gr.Button("Générer l'audio", variant="primary")
            tts_btn.click(tts_fn, [tts_text, tts_provider, tts_voice], [tts_audio, tts_log])

        with gr.Tab("📚 Documents"):
            gr.Markdown(
                "### RAG documentaire\nImportez des PDF, DOCX, TXT ou Markdown puis posez vos questions. "
                "MiniLM conserve l'index historique; BGE-M3 crée un index distinct et multilingue."
            )
            with gr.Row():
                rag_embedding_model = gr.Dropdown(
                    choices=embedding_choices,
                    value=embedding_default,
                    label="Moteur d'embedding compatible installé",
                    allow_custom_value=False,
                    scale=4,
                )
                rag_embedding_refresh = gr.Button("Actualiser les moteurs")
            rag_embedding_status = gr.Markdown(
                "Chaque moteur possède un index séparé. Réindexez les documents après avoir choisi BGE-M3."
                if embedding_choices else
                "Aucun moteur compatible prêt; installez BGE-M3 depuis Modèles IA si cette machine le permet."
            )
            rag_embedding_refresh.click(
                rag_embedding_choices_fn,
                [rag_embedding_model],
                [rag_embedding_model, rag_embedding_status],
            )
            rag_file = gr.File(label="Document à ajouter")
            rag_ingest_btn = gr.Button("Indexer le document")
            rag_ingest_log = gr.Textbox(label="État de l'indexation")
            rag_question = gr.Textbox(label="Question sur vos documents")
            rag_answer = gr.Textbox(label="Résultat", lines=7)
            rag_query_btn = gr.Button("Rechercher", variant="primary")
            rag_ingest_btn.click(rag_ingest_fn, [rag_file, rag_embedding_model], [rag_ingest_log])
            rag_query_btn.click(rag_query_fn, [rag_question, rag_embedding_model], [rag_answer])

        with gr.Tab("🎨 Images"):
            gr.Markdown("### Génération d'images locale\nLe premier lancement peut télécharger les poids du modèle et être lent sur CPU.")
            img_prompt = gr.Textbox(label="Description", placeholder="Un paysage brumeux au lever du soleil…")
            with gr.Row():
                img_steps = gr.Slider(5, 50, value=20, step=1, label="Étapes")
                img_guidance = gr.Slider(1, 15, value=7.5, label="Fidélité au prompt")
            img_btn = gr.Button("Générer", variant="primary")
            img_output = gr.Image(label="Résultat")
            img_log = gr.Textbox(label="État")
            img_btn.click(generate_image_fn, [img_prompt, img_steps, img_guidance], [img_output, img_log])

        with gr.Tab("🎭 Personnalités"):
            gr.Markdown("### Choisissez le ton du chat")
            personalities = personality_manager.list_personalities() if personality_manager else []
            gr.JSON(value=personalities, label="Profils disponibles")

        with gr.Tab("⚙️ Système"):
            gr.Markdown("### Diagnostic et outils locaux")
            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### Diagnostic")
                    diag_btn = gr.Button("Lancer le diagnostic", variant="secondary")
                    diag_output = gr.Textbox(label="Rapport", lines=14)
                    diag_btn.click(diagnostic_fn, None, [diag_output])
                    gr.Markdown("#### Installation du noyau")
                    install_btn = gr.Button("Installer / réparer les dépendances de base", variant="primary")
                    install_log = gr.Textbox(label="État de l'installation")
                    install_btn.click(install_core_fn, None, [install_log])
                with gr.Column():
                    gr.Markdown("#### Ressources")
                    monitor_btn = gr.Button("Mesurer CPU / RAM / disque")
                    monitor_output = gr.Textbox(label="Ressources système")
                    monitor_btn.click(monitor_fn, None, [monitor_output])
                    gr.Markdown("#### Ollama")
                    check_btn = gr.Button("Vérifier le moteur et les modèles")
                    check_output = gr.Textbox(label="État Ollama", lines=7)
                    check_btn.click(check_llm_fn, None, [check_output])
                    gr.Markdown("#### Fichiers temporaires")
                    clean_btn = gr.Button("Nettoyer les fichiers temporaires")
                    clean_output = gr.Textbox(label="Résultat")
                    clean_btn.click(clean_fn, None, [clean_output])

        gr.Markdown("---\n**IA Locale** · Dialogue, fichiers et modèles traités sur votre machine. Ollama doit être installé et démarré pour le chat.")

    return demo


if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name=CONFIG.get("ui", {}).get("host", "127.0.0.1"),
        server_port=UI_PORT,
        share=False,
        show_error=True,
    )
