import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
UI_PATH = PROJECT_ROOT / "ui" / "futuristic_app.py"


def load_ui_module():
    """Charge les fonctions de l'interface avec un stub Gradio minimal (non installé en CI)."""
    fake_gradio = types.ModuleType("gradio")
    fake_gradio.update = lambda **kwargs: {"__gr_update__": kwargs}
    fake_gradio.themes = types.SimpleNamespace(
        Soft=lambda **kwargs: object(),
        Default=lambda **kwargs: object(),
    )
    ui_directory = str(UI_PATH.parent)
    if ui_directory not in sys.path:
        sys.path.insert(0, ui_directory)
    spec = importlib.util.spec_from_file_location("futuristic_app_clarification_test", UI_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"gradio": fake_gradio}):
        spec.loader.exec_module(module)
    return module


class AgentClarificationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = load_ui_module()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "projet"
        self.workspace.mkdir()
        self.responses = []

        class FakeLlm:
            def __init__(inner_self, responses):
                inner_self.responses = responses
                inner_self.calls = []

            def chat(inner_self, *args, **kwargs):
                inner_self.calls.append({"args": args, "kwargs": kwargs})
                return inner_self.responses.pop(0)

        self.fake_llm = FakeLlm(self.responses)
        self.patches = [
            patch.object(self.ui, "llm", self.fake_llm),
            patch.object(self.ui, "is_model_compatible_fn", return_value=True),
            patch.object(self.ui, "_persist_agent_state", side_effect=lambda state, conversation, event=None: (dict(state), "")),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patches)])

    def test_native_agent_calls_the_selected_local_ollama_model(self):
        self.responses.append(json.dumps({"message": "Terminé.", "action": {"type": "done"}}))
        events = list(self.ui._agent_continue("qwen-local", [], self._approved_state()))

        self.assertEqual(self.fake_llm.calls[-1]["kwargs"]["model"], "qwen-local")
        self.assertEqual(self.fake_llm.calls[-1]["kwargs"]["response_format"], "json")
        self.assertEqual(self.fake_llm.calls[-1]["kwargs"]["host"], self.ui.LLM_HOST)
        self.assertIn("✅ Tâche terminée", events[-1][3])

    def test_question_is_added_to_chat_when_agent_repeats_ask(self):
        ask = json.dumps({
            "message": "Quel langage et quelles bibliothèques ?",
            "action": {"type": "ask_user"},
        }, ensure_ascii=False)
        self.responses.extend([ask, ask])
        state = {
            "messages": [{"role": "user", "content": "Crée un Tetris."}],
            "pending": None,
            "workspace": str(self.workspace),
            "remaining_steps": 12,
            "plan_approved": True,
            "awaiting_clarification": False,
            "journal_persisted": True,
        }

        events = list(self.ui._agent_continue("qwen-test", [], state))
        output = events[-1]
        self.assertIn("Quel langage et quelles bibliothèques ?", output[0][-1]["content"])
        self.assertTrue(output[2]["awaiting_clarification"])
        self.assertIn("réponds dans le champ", output[3])

    def test_user_can_answer_or_request_default_and_resume_approved_plan(self):
        write = json.dumps({
            "message": "Je prépare le code du jeu.",
            "action": {"type": "write_file", "path": "main.py", "content": "print('Tetris')\n"},
        }, ensure_ascii=False)
        self.responses.append(write)
        state = {
            "messages": [
                {"role": "user", "content": "Crée un Tetris."},
                {"role": "assistant", "content": "Réponse JSON: demande de précision"},
            ],
            "pending": None,
            "workspace": str(self.workspace),
            "remaining_steps": 8,
            "plan_approved": True,
            "awaiting_clarification": True,
            "journal_persisted": True,
        }
        conversation = [{"role": "assistant", "content": "❓ Question de l'agent : Quel langage ?"}]

        events = list(self.ui.agent_start_fn(
            "continue", conversation, state, "qwen-test", str(self.workspace)
        ))
        output = events[-1]
        self.assertEqual(output[2]["pending"]["type"], "write_file")
        self.assertTrue(output[2]["plan_approved"])
        self.assertFalse(output[2]["awaiting_clarification"])
        self.assertTrue(any(
            "hypothèse standard" in message.get("content", "").casefold()
            for message in output[2]["messages"]
        ))
        self.assertFalse((self.workspace / "main.py").exists())

    def _approved_state(self):
        return {
            "messages": [{"role": "user", "content": "Crée un Tetris."}],
            "pending": None,
            "workspace": str(self.workspace),
            "remaining_steps": 18,
            "plan_approved": True,
            "awaiting_clarification": False,
            "journal_persisted": True,
        }

    def test_missing_python_dependency_shows_install_approval_without_another_model_question(self):
        command = self.ui.local_agent.prepare_pending_action(str(self.workspace), {
            "type": "run_command", "argv": ["python", "-m", "unittest", "discover", "-s", "tests"],
        })
        state = self._approved_state()
        state["pending"] = command
        state["remaining_steps"] = 5
        failure = "Code de sortie : 1\\nSTDERR:\\nModuleNotFoundError: No module named 'pygame'\\nFAILED (errors=1)"

        with patch.object(self.ui.local_agent, "_execute_approved_action", return_value=(failure, None, None)):
            events = list(self.ui._agent_resolve_fn(True, [], state, "qwen-test"))

        output = events[-1]
        self.assertEqual(output[2]["pending"]["type"], "install_prerequisites")
        self.assertEqual(output[2]["pending"]["packages"], ["pygame"])
        self.assertIn("Prérequis Python manquant", output[3])
        self.assertIn("pygame", output[4])
        self.assertIn("Installer les prérequis", output[7]["__gr_update__"]["value"])
        self.assertIn("Rien ne sera installé avant ton approbation", output[0][-1]["content"])
        self.assertEqual(self.responses, [])

    def test_approved_prerequisite_install_resumes_the_approved_plan(self):
        state = self._approved_state()
        state["pending"] = self.ui.local_agent.prepare_pending_action(str(self.workspace), {
            "type": "install_prerequisites", "manager": "python", "packages": ["pygame"],
        })
        self.responses.append(json.dumps({"message": "Les tests passent maintenant.", "action": {"type": "done"}}))

        with patch.object(
            self.ui.local_agent, "_install_python_prerequisites", return_value="Code de sortie : 0\\nSuccessfully installed pygame"
        ):
            events = list(self.ui._agent_resolve_fn(True, [], state, "qwen-test"))

        self.assertIn("Installation des prérequis terminée", events[0][0][-1]["content"])
        self.assertIn("✅ Tâche terminée", events[-1][3])
        self.assertIsNone(events[-1][2]["pending"])

    def test_approved_plan_can_be_resumed_after_model_error(self):
        # Le modèle échoue avant de rendre un résultat; la reprise doit rester disponible.
        events = list(self.ui._agent_continue("qwen-test", [], self._approved_state()))
        output = events[-1]

        self.assertIn("Protocole agent / modèle", output[3])
        self.assertEqual(output[2]["remaining_steps"], 0)
        self.assertTrue(output[10]["__gr_update__"]["interactive"])

    def test_approved_plan_can_be_resumed_after_unexpected_agent_exception(self):
        with patch.object(self.ui.local_agent, "agent_loop", side_effect=RuntimeError("erreur inattendue")):
            events = list(self.ui._agent_continue("qwen-test", [], self._approved_state()))
        output = events[-1]

        self.assertIn("erreur inattendue", output[3])
        self.assertEqual(output[2]["remaining_steps"], 0)
        self.assertTrue(output[10]["__gr_update__"]["interactive"])

    def test_resume_recovers_approved_plan_from_matching_journal_if_ui_state_lost(self):
        conversation = [
            {"role": "user", "content": "Crée un Tetris."},
            {"role": "assistant", "content": "✅ Plan approuvé."},
            {"role": "assistant", "content": "✅ Action approuvée et exécutée. requirements.txt écrit."},
        ]
        saved_state = self._approved_state()
        saved_state["remaining_steps"] = 0
        saved_state["messages"] = [
            {"role": "user", "content": "Crée un Tetris."},
            {"role": "user", "content": "L'utilisateur a approuvé le plan."},
        ]
        lost_ui_state = {
            "messages": [],
            "pending": None,
            "workspace": str(self.workspace),
            "remaining_steps": 0,
            "plan_approved": False,
            "awaiting_clarification": False,
        }
        self.responses.append(json.dumps({"message": "Tetris terminé.", "action": {"type": "done"}}))
        restored = {"state": saved_state, "conversation": conversation, "updated_at": "now"}

        with patch.object(self.ui.local_agent, "load_agent_session", return_value=restored):
            events = list(self.ui.agent_resume_fn(
                conversation, lost_ui_state, "qwen-test", str(self.workspace)
            ))

        self.assertIn("récupéré depuis le journal", events[0][3])
        output = events[-1]
        self.assertIn("✅ Tâche terminée", output[3])
        self.assertTrue(output[2]["plan_approved"])
        self.assertTrue(any("Reprends maintenant le plan déjà approuvé" in item.get("content", "")
                            for item in output[2]["messages"]))

    def test_resume_does_not_restore_approved_plan_from_a_different_chat(self):
        saved_conversation = [
            {"role": "user", "content": "Crée un Tetris."},
            {"role": "assistant", "content": "✅ Plan approuvé."},
        ]
        restored = {"state": self._approved_state(), "conversation": saved_conversation}
        lost_ui_state = {
            "messages": [], "pending": None, "workspace": str(self.workspace),
            "remaining_steps": 0, "plan_approved": False,
            "awaiting_clarification": False,
        }
        other_chat = [{"role": "user", "content": "Autre tâche."}]

        with patch.object(self.ui.local_agent, "load_agent_session", return_value=restored):
            events = list(self.ui.agent_resume_fn(
                other_chat, lost_ui_state, "qwen-test", str(self.workspace)
            ))

        self.assertIn("Aucun plan approuvé", events[-1][3])
        self.assertEqual(len(self.responses), 0)


if __name__ == "__main__":
    unittest.main()
