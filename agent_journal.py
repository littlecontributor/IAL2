"""Journal local et atomique des sessions de l'agent IA Locale."""
import hashlib
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_VERSION = 1
JOURNAL_NAMESPACE = (".ia-locale", "agent-journals")
MAX_JOURNAL_BYTES = 8 * 1024 * 1024
MAX_JOURNAL_EVENTS = 200
MAX_JOURNAL_MESSAGES = 40
MAX_CONVERSATION_MESSAGES = 120
MAX_EVENT_TEXT = 8_000
MAX_EVENT_DIFF = 20_000
MAX_SAVED_MESSAGE = 300_000
_LOCK = threading.RLock()


class JournalError(ValueError):
    """Journal absent, invalide ou impossible à écrire sans risque."""


def _canonical_root(workspace: str) -> Path:
    if not isinstance(workspace, str) or not workspace.strip():
        raise JournalError("Le dossier projet du journal est absent.")
    try:
        root = Path(workspace).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise JournalError(f"Le dossier du journal est inaccessible : {exc}") from exc
    if not root.is_dir():
        raise JournalError("Le chemin du journal n'est pas un dossier projet.")
    return root


def _project_key(root: Path) -> str:
    normalized = os.path.normcase(str(root.resolve()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def journal_path(workspace: str) -> Path:
    """Retourne le chemin sûr du journal, hors dossier du projet."""
    root = _canonical_root(workspace)
    home = Path.home().resolve()
    candidate = home.joinpath(*JOURNAL_NAMESPACE, f"{_project_key(root)}.json")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(home)
    except ValueError as exc:
        raise JournalError("Le journal sortirait du profil utilisateur; opération refusée.") from exc
    return resolved


def _empty_document(root: Path) -> dict:
    return {
        "version": JOURNAL_VERSION,
        "workspace": str(root),
        "updated_at": None,
        "state": {},
        "conversation": [],
        "events": [],
    }


def _read_document(root: Path) -> dict | None:
    path = journal_path(str(root))
    if not path.exists():
        return None
    try:
        if path.stat().st_size > MAX_JOURNAL_BYTES:
            raise JournalError("Le journal dépasse la taille maximale; il n'a pas été chargé ni remplacé.")
        document = json.loads(path.read_text(encoding="utf-8"))
    except JournalError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JournalError(f"Le journal local est illisible; il est conservé intact : {exc}") from exc
    if not isinstance(document, dict) or document.get("version") != JOURNAL_VERSION:
        raise JournalError("Version du journal inconnue; le fichier est conservé intact.")
    try:
        stored_root = Path(str(document.get("workspace", ""))).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise JournalError("Le chemin du projet dans le journal est invalide.") from exc
    if stored_root != root:
        raise JournalError("Le journal ne correspond pas exactement au dossier projet sélectionné.")
    if not isinstance(document.get("state"), dict) or not isinstance(document.get("conversation"), list):
        raise JournalError("Le journal n'a pas le format attendu; il est conservé intact.")
    if not isinstance(document.get("events", []), list):
        raise JournalError("La liste des événements du journal est invalide.")
    return document


def _text(value, limit: int) -> str:
    if not isinstance(value, str):
        value = str(value)
    if len(value) > limit:
        return value[:limit] + "\n… contenu tronqué dans le journal local …"
    return value


def _normalize_state(state: dict, root: Path) -> dict:
    state = state if isinstance(state, dict) else {}
    messages = []
    raw_messages = state.get("messages", [])
    if isinstance(raw_messages, list):
        for item in raw_messages[-MAX_JOURNAL_MESSAGES:]:
            if not isinstance(item, dict) or item.get("role") not in {"user", "assistant", "system"}:
                continue
            if not isinstance(item.get("content"), str):
                continue
            messages.append({
                "role": item["role"],
                "content": _text(item["content"], MAX_SAVED_MESSAGE),
            })
    pending = state.get("pending")
    if pending is not None and not isinstance(pending, dict):
        pending = None
    undo_stack = state.get("undo_stack", [])
    if not isinstance(undo_stack, list):
        undo_stack = []
    undo_stack = [item for item in undo_stack[-20:] if isinstance(item, dict)]
    remaining = state.get("remaining_steps", 0)
    try:
        remaining = max(0, min(100, int(remaining)))
    except (TypeError, ValueError):
        remaining = 0
    branch = state.get("git_checkpoint_branch")
    if not isinstance(branch, str):
        branch = None
    return {
        "messages": messages,
        "pending": pending,
        "workspace": str(root),
        "remaining_steps": remaining,
        "plan_approved": bool(state.get("plan_approved", False)),
        "awaiting_clarification": bool(state.get("awaiting_clarification", False)),
        "undo_stack": undo_stack,
        "git_checkpoint_branch": branch[:200] if branch else None,
    }


def _normalize_conversation(conversation) -> list:
    normalized = []
    if not isinstance(conversation, list):
        return normalized
    for item in conversation[-MAX_CONVERSATION_MESSAGES:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        normalized.append({"role": item["role"], "content": _text(content, 12_000)})
    return normalized


def _normalize_event(event) -> dict | None:
    if not isinstance(event, dict):
        return None
    kind = event.get("kind", "event")
    record = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": _text(kind, 80),
    }
    string_limits = {
        "summary": 1_000,
        "path": 1_000,
        "result": MAX_EVENT_TEXT,
        "diff": MAX_EVENT_DIFF,
        "status": 1_000,
        "decision": 100,
        "stage_path": 2_000,
    }
    for key, limit in string_limits.items():
        if isinstance(event.get(key), str):
            record[key] = _text(event[key], limit)
    argv = event.get("argv")
    if isinstance(argv, (list, tuple)) and all(isinstance(item, str) for item in argv[:40]):
        record["argv"] = [_text(item, 500) for item in argv[:40]]
    if isinstance(event.get("exit_code"), int):
        record["exit_code"] = event["exit_code"]
    return record


def _encode(document: dict) -> bytes:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _trim_to_limit(document: dict) -> bytes:
    encoded = _encode(document)
    while len(encoded) > MAX_JOURNAL_BYTES:
        events = document.get("events", [])
        conversation = document.get("conversation", [])
        messages = document.get("state", {}).get("messages", [])
        if events:
            del events[0]
        elif conversation:
            del conversation[0]
        elif len(messages) > 1:
            del messages[0]
        else:
            raise JournalError("La session dépasse la taille autorisée; le journal précédent reste intact.")
        encoded = _encode(document)
    return encoded


def save_session(workspace: str, state: dict, conversation, event: dict | None = None) -> str:
    """Enregistre atomiquement l'état, l'historique et un événement localement."""
    root = _canonical_root(workspace)
    path = journal_path(str(root))
    with _LOCK:
        existing = _read_document(root) or _empty_document(root)
        events = list(existing.get("events", []))[-MAX_JOURNAL_EVENTS:]
        record = _normalize_event(event)
        if record:
            events.append(record)
        document = {
            "version": JOURNAL_VERSION,
            "workspace": str(root),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "state": _normalize_state(state, root),
            "conversation": _normalize_conversation(conversation),
            "events": events[-MAX_JOURNAL_EVENTS:],
        }
        payload = _trim_to_limit(document)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=f".{path.name}-", suffix=f"-{uuid.uuid4().hex[:6]}.tmp", delete=False
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(payload)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            os.replace(temp_path, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            try:
                if "temp_path" in locals() and temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            raise JournalError(f"Impossible d'enregistrer le journal local : {exc}") from exc
    return str(path)


def load_session(workspace: str) -> dict | None:
    """Charge le dernier journal du projet sans jamais exécuter son action en attente."""
    root = _canonical_root(workspace)
    with _LOCK:
        document = _read_document(root)
    if document is None:
        return None
    document["events"] = document.get("events", [])[-MAX_JOURNAL_EVENTS:]
    document["journal_path"] = str(journal_path(str(root)))
    return document
