#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests du périmètre fichier et du cycle de confirmation de l'agent local."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import local_agent


class LocalAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "projet"
        self.workspace.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def approve_plan(self, state):
        response = json.dumps({
            "message": "Voici mon plan.",
            "action": {
                "type": "plan",
                "summary": "Réaliser la tâche demandée",
                "steps": ["Inspecter les fichiers utiles", "Effectuer les changements et vérifier le résultat"],
            },
        })
        pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))[-1]
        self.assertEqual(pending["kind"], "pending")
        self.assertEqual(pending["state"]["pending"]["type"], "plan")
        approved, _ = local_agent.resolve_pending_action(pending["state"], approved=True)
        self.assertTrue(approved["plan_approved"])
        return approved

    def test_workspace_rejects_home_and_filesystem_root(self):
        with self.assertRaises(local_agent.AgentError):
            local_agent.validate_workspace(str(Path.home()))
        with self.assertRaises(local_agent.AgentError):
            local_agent.validate_workspace(str(Path(Path.home().anchor)))
        with self.assertRaises(local_agent.AgentError):
            local_agent.validate_workspace(str(Path.home() / ".ia-locale"))

    def test_file_tools_list_read_and_search_inside_project(self):
        source = self.workspace / "src"
        source.mkdir()
        (source / "main.py").write_text("def greet():\n    return 'bonjour'\n", encoding="utf-8")
        (self.workspace / "secret.txt").write_text("bonjour secret", encoding="utf-8")
        (self.workspace / ".env").write_text("TOKEN=do-not-read", encoding="utf-8")

        listed = local_agent.list_files(str(self.workspace))
        read = local_agent.read_file(str(self.workspace), "src/main.py")
        results = local_agent.search_text(str(self.workspace), "bonjour")

        self.assertIn("src/main.py", listed)
        self.assertNotIn(".env", "\n".join(listed))
        self.assertIn("return 'bonjour'", read)
        self.assertEqual(len(results), 2)
        self.assertTrue(any("src/main.py:2" in result for result in results))
        with self.assertRaises(local_agent.AgentError):
            local_agent.read_file(str(self.workspace), ".env")

    def test_file_tools_reject_parent_traversal_and_external_symlinks(self):
        outside = Path(self.temp_dir.name) / "outside.txt"
        outside.write_text("ne pas lire", encoding="utf-8")
        with self.assertRaises(local_agent.AgentError):
            local_agent.read_file(str(self.workspace), "../outside.txt")

        link = self.workspace / "external-link.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Création de liens symboliques non permise par cet environnement")
        with self.assertRaises(local_agent.AgentError):
            local_agent.read_file(str(self.workspace), "external-link.txt")

    def test_proposed_write_is_not_applied_until_approval(self):
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Crée un fichier hello.py")
        )
        response = json.dumps({
            "message": "Je prépare un petit fichier Python.",
            "action": {"type": "write_file", "path": "hello.py", "content": "print('bonjour')\n"},
        })
        events = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))
        pending = events[-1]

        self.assertEqual(pending["kind"], "pending")
        self.assertFalse((self.workspace / "hello.py").exists())
        current, _ = local_agent.resolve_pending_action(pending["state"], approved=True)
        self.assertEqual((self.workspace / "hello.py").read_text(encoding="utf-8"), "print('bonjour')\n")
        self.assertIsNone(current["pending"])
        self.assertEqual(current["undo_stack"][-1]["path"], "hello.py")
        local_agent.undo_last_write(str(self.workspace), current["undo_stack"][-1])
        self.assertFalse((self.workspace / "hello.py").exists())

    def test_plan_must_be_approved_before_any_tool(self):
        state = local_agent.begin_user_turn(None, str(self.workspace), "Inspecte et corrige le projet")
        responses = iter([
            json.dumps({"message": "Je liste les fichiers.", "action": {"type": "list_files", "path": "."}}),
            json.dumps({
                "message": "Voici le plan.",
                "action": {"type": "plan", "summary": "Analyser puis corriger", "steps": ["Inspecter", "Corriger", "Tester"]},
            }),
        ])
        with patch("local_agent.list_files") as list_tool:
            events = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: next(responses)))
        self.assertEqual(events[-1]["kind"], "pending")
        self.assertEqual(events[-1]["state"]["pending"]["type"], "plan")
        list_tool.assert_not_called()
        summary, preview = local_agent.describe_pending_action(str(self.workspace), events[-1]["state"]["pending"])
        self.assertIn("PLAN À APPROUVER", summary)
        self.assertIn("3. Tester", preview)

    def test_malformed_model_reply_gets_one_format_retry_without_using_step_budget(self):
        malformed_replies = (
            "Je vais créer un Tetris attrayant. Quel langage et quels outils souhaitez-vous ?",
            json.dumps({
                "message": "Je vais créer un Tetris; indiquez le langage.",
                "action": "ask_user: quel langage ?",
            }, ensure_ascii=False),
        )
        plan_response = json.dumps({
            "message": "Je propose un jeu Tetris web autonome; tu pourras ajuster cette hypothèse dans le plan.",
            "action": {
                "type": "plan",
                "summary": "Créer un Tetris web attrayant dans le dossier sélectionné",
                "steps": ["Examiner le dossier après approbation", "Créer le jeu", "Vérifier le lancement"],
            },
        }, ensure_ascii=False)

        for malformed in malformed_replies:
            with self.subTest(malformed=malformed[:40]):
                state = local_agent.begin_user_turn(None, str(self.workspace), "Crée-moi un Tetris attrayant et captivant.")
                state["remaining_steps"] = 1
                responses = iter([malformed, plan_response])
                seen = []

                def model_call(messages, system_prompt):
                    seen.append((list(messages), system_prompt))
                    return next(responses)

                events = list(local_agent.agent_loop(str(self.workspace), state, model_call, max_steps=1))
                self.assertEqual(events[-1]["kind"], "pending")
                self.assertEqual(events[-1]["state"]["pending"]["type"], "plan")
                self.assertEqual(events[-1]["state"]["remaining_steps"], 0)
                self.assertEqual(len(seen), 2)
                self.assertTrue(any("reformule une fois" in event.get("status", "") for event in events))
                self.assertTrue(all(prompt == local_agent.AGENT_SYSTEM_PROMPT for _, prompt in seen))
                self.assertTrue(any(
                    "La réponse précédente ne respectait pas le protocole" in item.get("content", "")
                    for item in events[-1]["state"]["messages"]
                ))
                self.assertIn("Tetris web", events[-1]["reply"])
                self.assertFalse(any((self.workspace / name).exists() for name in ("index.html", "main.py")))

    def test_clarification_after_approved_plan_is_retried_with_defaults_before_write(self):
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Crée-moi un Tetris attrayant.")
        )
        ask = json.dumps({
            "message": "Quel langage et quels outils souhaitez-vous ?",
            "action": {"type": "ask_user"},
        }, ensure_ascii=False)
        write = json.dumps({
            "message": "Je pars sur une version web autonome avec HTML, CSS et JavaScript.",
            "action": {"type": "write_file", "path": "index.html", "content": "<!doctype html><title>Tetris</title>\\n"},
        }, ensure_ascii=False)
        responses = iter([ask, write])
        prompts = []

        def model_call(messages, system_prompt):
            prompts.append(system_prompt)
            return next(responses)

        events = list(local_agent.agent_loop(str(self.workspace), state, model_call))
        self.assertEqual(events[-1]["kind"], "pending")
        self.assertEqual(events[-1]["state"]["pending"]["type"], "write_file")
        self.assertIn("index.html", events[-1]["state"]["pending"]["path"])
        self.assertFalse((self.workspace / "index.html").exists())
        self.assertEqual(len(prompts), 2)
        self.assertTrue(all(prompt == local_agent.AGENT_CONTINUATION_SYSTEM_PROMPT for prompt in prompts))
        self.assertTrue(any("Choisis une hypothèse standard" in item.get("content", "") for item in events[-1]["state"]["messages"]))
        self.assertTrue(any("hypothèse par défaut" in event.get("status", "") for event in events))

    def test_repeated_clarification_after_approved_plan_is_shown_to_user(self):
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Crée-moi un Tetris attrayant.")
        )
        ask = json.dumps({
            "message": "Quel langage souhaitez-vous ?",
            "action": {"type": "ask_user"},
        }, ensure_ascii=False)
        calls = []
        events = list(local_agent.agent_loop(
            str(self.workspace), state,
            lambda *_: (calls.append(True), ask)[1],
        ))
        self.assertEqual(events[-1]["kind"], "clarification")
        self.assertIn("Quel langage souhaitez-vous ?", events[-1]["reply"])
        self.assertIn("réponds dans le champ", events[-1]["reply"].casefold())
        self.assertIn("affichée dans la conversation", events[-1]["status"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(events[-1]["state"]["plan_approved"])
        self.assertTrue(events[-1]["state"]["awaiting_clarification"])
        self.assertIsNone(events[-1]["state"]["pending"])
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_answering_clarification_resumes_approved_plan_without_new_plan(self):
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Crée-moi un Tetris.")
        )
        ask = json.dumps({
            "message": "Confirme le langage et la bibliothèque.",
            "action": {"type": "ask_user"},
        }, ensure_ascii=False)
        clarification = list(local_agent.agent_loop(
            str(self.workspace), state, lambda *_: ask,
        ))[-1]
        answered = local_agent.answer_agent_clarification(
            clarification["state"], str(self.workspace), "Python avec Pygame, sous Windows."
        )
        self.assertFalse(answered["awaiting_clarification"])
        self.assertTrue(answered["plan_approved"])
        self.assertIn("Python avec Pygame", answered["messages"][-1]["content"])

        write = json.dumps({
            "message": "Je prépare le jeu demandé.",
            "action": {"type": "write_file", "path": "main.py", "content": "print('Tetris')\\n"},
        }, ensure_ascii=False)
        resumed = list(local_agent.agent_loop(str(self.workspace), answered, lambda *_: write))[-1]
        self.assertEqual(resumed["kind"], "pending")
        self.assertEqual(resumed["state"]["pending"]["type"], "write_file")
        self.assertTrue(resumed["state"]["plan_approved"])
        self.assertFalse((self.workspace / "main.py").exists())

    def test_clarification_answer_must_keep_same_project_and_plan(self):
        state = {
            "messages": [], "pending": None, "workspace": str(self.workspace),
            "remaining_steps": 3, "plan_approved": True, "awaiting_clarification": True,
        }
        other = Path(self.temp_dir.name) / "autre"
        other.mkdir()
        with self.assertRaises(local_agent.AgentError):
            local_agent.answer_agent_clarification(state, str(other), "Pygame")
        with self.assertRaises(local_agent.AgentError):
            local_agent.answer_agent_clarification(state, str(self.workspace), " ")
        with self.assertRaises(local_agent.AgentError):
            local_agent.continue_approved_task(state, str(self.workspace))
        self.assertTrue(state["awaiting_clarification"])

    def test_malformed_model_reply_stops_after_one_safe_retry(self):
        state = local_agent.begin_user_turn(None, str(self.workspace), "Crée-moi un Tetris.")
        malformed = json.dumps({"message": "Je vais le faire.", "action": None})
        calls = []

        def model_call(messages, system_prompt):
            calls.append(True)
            return malformed

        events = list(local_agent.agent_loop(str(self.workspace), state, model_call))
        self.assertEqual(events[-1]["kind"], "error")
        self.assertIn("après une tentative de correction", events[-1]["status"])
        self.assertIn("Aucune action n'a été exécutée", events[-1]["status"])
        self.assertEqual(len(calls), 2)
        self.assertIsNone(events[-1]["state"]["pending"])
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_approved_plan_continues_instead_of_requiring_the_same_plan_again(self):
        source = self.workspace / "app.py"
        source.write_text("print('bonjour')\n", encoding="utf-8")
        state = local_agent.begin_user_turn(None, str(self.workspace), "Inspecte le projet puis explique son entrée.")
        plan_response = json.dumps({
            "message": "Voici le plan.",
            "action": {"type": "plan", "summary": "Lire et expliquer", "steps": ["Lire app.py", "Résumer"]},
        })
        pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: plan_response))[-1]
        approved, _ = local_agent.resolve_pending_action(pending["state"], approved=True)
        self.assertTrue(approved["plan_approved"])

        duplicate_plan = json.dumps({
            "message": "Je reformule le plan.",
            "action": {"type": "plan", "summary": "Même plan reformulé", "steps": ["Lire app.py", "Résumer"]},
        })
        read_action = json.dumps({
            "message": "Je lis le fichier prévu.",
            "action": {"type": "read_file", "path": "app.py"},
        })
        done = json.dumps({"message": "Le point d'entrée affiche bonjour.", "action": {"type": "done"}})
        responses = iter([duplicate_plan, read_action, done])
        prompts = []

        def model_call(messages, system_prompt):
            prompts.append(system_prompt)
            return next(responses)

        events = list(local_agent.agent_loop(str(self.workspace), approved, model_call))
        self.assertEqual(events[-1]["kind"], "done")
        self.assertEqual(events[-1]["state"]["pending"], None)
        self.assertTrue(all(prompt == local_agent.AGENT_CONTINUATION_SYSTEM_PROMPT for prompt in prompts))
        self.assertTrue(any(
            "Un plan a déjà été approuvé" in item.get("content", "")
            for item in events[-1]["state"]["messages"]
        ))
        self.assertTrue(any("print('bonjour')" in item.get("content", "") for item in events[-1]["state"]["messages"]))
        self.assertFalse((self.workspace / "nouveau.py").exists())

    def test_step_limit_is_a_resumable_pause_not_a_completed_task(self):
        (self.workspace / "README.md").write_text("Jeu à créer", encoding="utf-8")
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Crée un jeu dans ce dossier.")
        )
        state["remaining_steps"] = 1
        response = json.dumps({"message": "J'inspecte le projet.", "action": {"type": "list_files", "path": "."}})
        events = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))
        paused = events[-1]
        self.assertEqual(paused["kind"], "paused")
        self.assertTrue(paused["state"]["plan_approved"])
        self.assertEqual(paused["state"]["remaining_steps"], 0)
        self.assertIsNone(paused["state"]["pending"])
        self.assertIn("Continuer la tâche", paused["status"])
        resumed = local_agent.continue_approved_task(paused["state"], str(self.workspace))
        self.assertTrue(resumed["plan_approved"])
        self.assertEqual(resumed["remaining_steps"], local_agent.MAX_STEPS_PER_TURN)

    def test_approved_plan_can_resume_after_step_limit_without_replanning(self):
        (self.workspace / "app.py").write_text("print('bonjour')\n", encoding="utf-8")
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Crée un petit jeu dans ce dossier.")
        )
        state["remaining_steps"] = 0
        resumed = local_agent.continue_approved_task(state, str(self.workspace))
        self.assertTrue(resumed["plan_approved"])
        self.assertEqual(resumed["remaining_steps"], local_agent.MAX_STEPS_PER_TURN)
        self.assertEqual(resumed["messages"][-1]["role"], "user")
        self.assertIn("plan déjà approuvé", resumed["messages"][-1]["content"])

        read = json.dumps({"message": "Je reprends la lecture.", "action": {"type": "read_file", "path": "app.py"}})
        done = json.dumps({"message": "Le projet est prêt.", "action": {"type": "done"}})
        responses = iter([read, done])
        prompts = []
        events = list(local_agent.agent_loop(
            str(self.workspace), resumed,
            lambda messages, prompt: (prompts.append(prompt), next(responses))[1],
        ))
        self.assertEqual(events[-1]["kind"], "done")
        self.assertTrue(all(prompt == local_agent.AGENT_CONTINUATION_SYSTEM_PROMPT for prompt in prompts))
        self.assertEqual(events[-1]["reply"], "Le projet est prêt.")

        blocked = dict(resumed, pending={"type": "write_file"})
        with self.assertRaises(local_agent.AgentError):
            local_agent.continue_approved_task(blocked, str(self.workspace))

    def test_repeated_plan_does_not_consume_remaining_step_budget(self):
        (self.workspace / "app.py").write_text("print('bonjour')\n", encoding="utf-8")
        state = local_agent.begin_user_turn(None, str(self.workspace), "Analyse ce projet.")
        initial_plan = json.dumps({
            "message": "Plan.",
            "action": {"type": "plan", "summary": "Analyser", "steps": ["Lire"]},
        })
        pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: initial_plan))[-1]
        approved, _ = local_agent.resolve_pending_action(pending["state"], approved=True)
        budget = approved["remaining_steps"]
        duplicate = json.dumps({
            "message": "Plan encore.",
            "action": {"type": "plan", "summary": "Même plan", "steps": ["Lire"]},
        })
        read_action = json.dumps({
            "message": "Je lis l'étape prévue.",
            "action": {"type": "read_file", "path": "app.py"},
        })
        done = json.dumps({"message": "Analyse terminée.", "action": {"type": "done"}})
        responses = iter([duplicate] + [read_action] * (budget - 1) + [done])
        calls = []

        events = list(local_agent.agent_loop(
            str(self.workspace), approved,
            lambda *_: (calls.append(True), next(responses))[1],
        ))
        self.assertEqual(events[-1]["kind"], "done")
        self.assertEqual(len(calls), budget + 1)
        self.assertEqual(events[-1]["reply"], "Analyse terminée.")

    def test_repeated_plan_after_approval_stops_before_step_limit(self):
        state = local_agent.begin_user_turn(None, str(self.workspace), "Analyse ce projet.")
        initial_plan = json.dumps({
            "message": "Plan.",
            "action": {"type": "plan", "summary": "Analyser", "steps": ["Lire"]},
        })
        pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: initial_plan))[-1]
        approved, _ = local_agent.resolve_pending_action(pending["state"], approved=True)
        duplicate = json.dumps({
            "message": "Encore un plan.",
            "action": {"type": "plan", "summary": "Toujours analyser", "steps": ["Lire"]},
        })
        calls = []
        responses = iter([duplicate, duplicate])
        events = list(local_agent.agent_loop(
            str(self.workspace), approved,
            lambda *_: (calls.append(True), next(responses))[1],
        ))
        self.assertEqual(events[-1]["kind"], "error")
        self.assertIn("répété un plan déjà approuvé", events[-1]["status"])
        self.assertNotIn("Limite d'étapes atteinte", events[-1]["status"])
        self.assertEqual(len(calls), 2)
        self.assertFalse((self.workspace / "nouveau.py").exists())

    def test_file_diff_backup_and_undo_restore_previous_content(self):
        target = self.workspace / "app.py"
        target.write_text("print('avant')\n", encoding="utf-8")
        state = self.approve_plan(local_agent.begin_user_turn(None, str(self.workspace), "Modifie app.py"))
        response = json.dumps({
            "message": "Je change le message.",
            "action": {"type": "write_file", "path": "app.py", "content": "print('après')\n"},
        })
        pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))[-1]
        backups = Path(self.temp_dir.name) / "backups"
        with patch("local_agent._backup_directory", return_value=backups):
            summary, diff = local_agent.describe_pending_action(str(self.workspace), pending["state"]["pending"])
            self.assertIn("-print('avant')", diff)
            self.assertIn("+print('après')", diff)
            self.assertIn("sauvegarde locale", summary)
            with patch("local_agent._try_git_checkpoint", return_value=("ia-locale-agent-test", "Branche de point de retour créée : ia-locale-agent-test.")):
                updated_state, outcome = local_agent.resolve_pending_action(pending["state"], approved=True)
            self.assertIn("ia-locale-agent-test", outcome)
            self.assertEqual(target.read_text(encoding="utf-8"), "print('après')\n")
            undo_record = updated_state["undo_stack"][-1]
            self.assertEqual(Path(undo_record["backup_path"]).read_text(encoding="utf-8"), "print('avant')\n")
            local_agent.undo_last_write(str(self.workspace), undo_record)
        self.assertEqual(target.read_text(encoding="utf-8"), "print('avant')\n")

    def test_session_journal_restores_undo_history_after_restart(self):
        target = self.workspace / "app.py"
        target.write_text("print('avant')\n", encoding="utf-8")
        backups = Path(self.temp_dir.name) / "backups"
        journal_file = Path(self.temp_dir.name) / "journal.json"
        state = self.approve_plan(local_agent.begin_user_turn(None, str(self.workspace), "Modifie app.py"))
        response = json.dumps({
            "message": "Je propose le changement.",
            "action": {"type": "write_file", "path": "app.py", "content": "print('après')\n"},
        })
        pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))[-1]
        with (
            patch("local_agent._backup_directory", return_value=backups),
            patch("local_agent._try_git_checkpoint", return_value=(None, "pas de dépôt Git")),
            patch("local_agent.agent_journal.journal_path", return_value=journal_file),
        ):
            updated, _ = local_agent.resolve_pending_action(pending["state"], approved=True)
            local_agent.save_agent_session(
                str(self.workspace), updated,
                [{"role": "user", "content": "Modifie app.py"}, {"role": "assistant", "content": "Fichier modifié."}],
                event={"kind": "write_applied", "path": "app.py", "result": "Écriture approuvée."},
            )
            restored = local_agent.load_agent_session(str(self.workspace))
            self.assertEqual(restored["state"]["undo_stack"][-1]["path"], "app.py")
            self.assertEqual(restored["conversation"][-1]["content"], "Fichier modifié.")
            self.assertEqual(restored["events"][-1]["kind"], "write_applied")
            self.assertTrue(journal_file.is_file())
            self.assertNotEqual(journal_file.parent, self.workspace)
            local_agent.undo_last_write(str(self.workspace), restored["state"]["undo_stack"][-1])
        self.assertEqual(target.read_text(encoding="utf-8"), "print('avant')\n")

    def test_session_journal_restores_waiting_clarification(self):
        journal_file = Path(self.temp_dir.name) / "journal.json"
        state = {
            "messages": [{"role": "assistant", "content": "Quel langage ?"}],
            "pending": None,
            "workspace": str(self.workspace),
            "remaining_steps": 5,
            "plan_approved": True,
            "awaiting_clarification": True,
            "undo_stack": [],
        }
        with patch("local_agent.agent_journal.journal_path", return_value=journal_file):
            local_agent.save_agent_session(
                str(self.workspace), state,
                [{"role": "assistant", "content": "❓ Question de l'agent : Quel langage ?"}],
            )
            restored = local_agent.load_agent_session(str(self.workspace))
        self.assertTrue(restored["state"]["plan_approved"])
        self.assertTrue(restored["state"]["awaiting_clarification"])
        self.assertIn("Quel langage ?", restored["conversation"][-1]["content"])

    def test_restored_pending_write_is_not_executed_automatically(self):
        target = self.workspace / "app.py"
        target.write_text("print('avant')\n", encoding="utf-8")
        journal_file = Path(self.temp_dir.name) / "journal.json"
        action = local_agent.prepare_pending_action(str(self.workspace), {
            "type": "write_file", "path": "app.py", "content": "print('après')\n",
        })
        state = {
            "messages": [{"role": "user", "content": "Change app.py"}],
            "pending": action, "workspace": str(self.workspace), "remaining_steps": 2,
            "plan_approved": True, "undo_stack": [], "git_checkpoint_branch": None,
        }
        with patch("local_agent.agent_journal.journal_path", return_value=journal_file):
            local_agent.save_agent_session(str(self.workspace), state, [])
            restored = local_agent.load_agent_session(str(self.workspace))
        self.assertEqual(restored["state"]["pending"]["type"], "write_file")
        self.assertEqual(target.read_text(encoding="utf-8"), "print('avant')\n")

    def test_restored_prerequisite_install_stays_pending_until_user_approves_again(self):
        journal_file = Path(self.temp_dir.name) / "journal.json"
        action = local_agent.prepare_pending_action(str(self.workspace), {
            "type": "install_prerequisites", "manager": "python", "packages": ["pygame"],
        })
        state = {
            "messages": [{"role": "user", "content": "Installe pygame si absent"}],
            "pending": action, "workspace": str(self.workspace), "remaining_steps": 2,
            "plan_approved": True, "undo_stack": [], "git_checkpoint_branch": None,
        }
        with (
            patch("local_agent.agent_journal.journal_path", return_value=journal_file),
            patch("local_agent._install_python_prerequisites") as install,
        ):
            local_agent.save_agent_session(str(self.workspace), state, [])
            restored = local_agent.load_agent_session(str(self.workspace))

        self.assertEqual(restored["state"]["pending"]["type"], "install_prerequisites")
        self.assertEqual(restored["state"]["pending"]["packages"], ["pygame"])
        install.assert_not_called()

    def test_restore_discards_pending_diff_if_source_changed(self):
        target = self.workspace / "app.py"
        target.write_text("print('avant')\n", encoding="utf-8")
        journal_file = Path(self.temp_dir.name) / "journal.json"
        action = local_agent.prepare_pending_action(str(self.workspace), {
            "type": "write_file", "path": "app.py", "content": "print('proposé')\n",
        })
        state = {
            "messages": [], "pending": action, "workspace": str(self.workspace),
            "remaining_steps": 1, "plan_approved": True, "undo_stack": [],
        }
        with patch("local_agent.agent_journal.journal_path", return_value=journal_file):
            local_agent.save_agent_session(str(self.workspace), state, [])
            target.write_text("print('changement manuel')\n", encoding="utf-8")
            restored = local_agent.load_agent_session(str(self.workspace))
        self.assertIsNone(restored["state"]["pending"])
        self.assertIn("n'a pas été restaurée", restored["warning"])
        self.assertEqual(target.read_text(encoding="utf-8"), "print('changement manuel')\n")

    def test_corrupt_journal_is_never_overwritten(self):
        journal_file = Path(self.temp_dir.name) / "journal.json"
        journal_file.write_text("{invalid json", encoding="utf-8")
        with patch("local_agent.agent_journal.journal_path", return_value=journal_file):
            with self.assertRaises(local_agent.AgentError):
                local_agent.load_agent_session(str(self.workspace))
            with self.assertRaises(local_agent.AgentError):
                local_agent.save_agent_session(str(self.workspace), {}, [])
        self.assertEqual(journal_file.read_text(encoding="utf-8"), "{invalid json")

    def test_journal_path_is_outside_project(self):
        path = local_agent.agent_journal.journal_path(str(self.workspace))
        with self.assertRaises(ValueError):
            path.relative_to(self.workspace)
        self.assertEqual(path.parent.name, "agent-journals")

    def test_git_checkpoint_branch_requires_a_clean_project(self):
        if not shutil.which("git"):
            self.skipTest("Git n'est pas installé")
        subprocess.run(["git", "init", "-q"], cwd=self.workspace, check=True)
        subprocess.run(["git", "config", "user.name", "IA Locale Test"], cwd=self.workspace, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.workspace, check=True)
        (self.workspace / "README.md").write_text("initial", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.workspace, check=True)
        subprocess.run(["git", "commit", "-qm", "initial"], cwd=self.workspace, check=True)

        branch, message = local_agent._try_git_checkpoint(self.workspace)
        current_branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=self.workspace, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(current_branch, branch)
        self.assertIn("créée", message)

        (self.workspace / "README.md").write_text("modification utilisateur", encoding="utf-8")
        next_branch, message = local_agent._try_git_checkpoint(self.workspace)
        self.assertIsNone(next_branch)
        self.assertIn("déjà des changements", message)

    def test_stale_diff_is_not_written_after_file_changes(self):
        target = self.workspace / "main.py"
        target.write_text("print('original')\n", encoding="utf-8")
        state = self.approve_plan(local_agent.begin_user_turn(None, str(self.workspace), "Modifie main.py"))
        response = json.dumps({
            "message": "Je propose ce changement.",
            "action": {"type": "write_file", "path": "main.py", "content": "print('proposé')\n"},
        })
        pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))[-1]
        target.write_text("print('modification manuelle')\n", encoding="utf-8")
        with self.assertRaises(local_agent.AgentError):
            local_agent.resolve_pending_action(pending["state"], approved=True)
        self.assertEqual(target.read_text(encoding="utf-8"), "print('modification manuelle')\n")

    def test_undo_refuses_to_overwrite_later_manual_changes(self):
        target = self.workspace / "main.py"
        target.write_text("print('original')\n", encoding="utf-8")
        state = self.approve_plan(local_agent.begin_user_turn(None, str(self.workspace), "Modifie main.py"))
        response = json.dumps({
            "message": "Je propose ce changement.",
            "action": {"type": "write_file", "path": "main.py", "content": "print('agent')\n"},
        })
        pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))[-1]
        with patch("local_agent._backup_directory", return_value=Path(self.temp_dir.name) / "backups"), \
                patch("local_agent._try_git_checkpoint", return_value=(None, "pas de dépôt Git")):
            updated_state, _ = local_agent.resolve_pending_action(pending["state"], approved=True)
        target.write_text("print('travail utilisateur')\n", encoding="utf-8")
        with self.assertRaises(local_agent.AgentError):
            local_agent.undo_last_write(str(self.workspace), updated_state["undo_stack"][-1])
        self.assertEqual(target.read_text(encoding="utf-8"), "print('travail utilisateur')\n")

    def test_refused_write_is_not_applied(self):
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Crée un fichier")
        )
        response = json.dumps({
            "message": "Écriture proposée.",
            "action": {"type": "write_file", "path": "hello.py", "content": "print('x')"},
        })
        pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))[-1]
        current, outcome = local_agent.resolve_pending_action(pending["state"], approved=False)
        self.assertFalse((self.workspace / "hello.py").exists())
        self.assertIn("refusé", outcome)
        self.assertIsNone(current["pending"])

    def test_pending_write_rejects_secrets_and_traversal(self):
        for path in ("../outside.py", ".env", ".ssh/key", ".git/config"):
            with self.subTest(path=path), self.assertRaises(local_agent.AgentError):
                local_agent.prepare_pending_action(
                    str(self.workspace), {"type": "write_file", "path": path, "content": "secret"}
                )

    def test_commands_require_approval_and_disallow_shell_or_escape(self):
        valid = local_agent.prepare_pending_action(
            str(self.workspace),
            {"type": "run_command", "argv": ["python", "-m", "unittest", "discover", "-s", "tests"]},
        )
        self.assertEqual(valid["argv"][:3], ["python", "-m", "unittest"])
        for argv in (
            ["python", "-c", "print(1)"],
            ["python", "-m", "pip", "install", "example"],
            ["bash", "-c", "echo unsafe"],
            ["python", "-m", "unittest", "../other"],
            ["python", "-m", "unittest", ";", "echo", "bad"],
            ["git", "diff", "--ext-diff"],
            ["git", "diff", "--textconv"],
        ):
            with self.subTest(argv=argv), self.assertRaises(local_agent.AgentError):
                local_agent.prepare_pending_action(str(self.workspace), {"type": "run_command", "argv": argv})

    def test_install_prerequisites_proposal_is_validated_and_visible(self):
        action = local_agent.prepare_pending_action(str(self.workspace), {
            "type": "install_prerequisites", "manager": "python", "packages": ["pygame"],
            "reason": "Le test signale un module absent.",
        })
        self.assertEqual(action["packages"], ["pygame"])
        summary, preview = local_agent.describe_pending_action(str(self.workspace), action)
        self.assertIn("APPROBATION REQUISE", summary)
        self.assertIn("PyPI : pygame", summary)
        self.assertIn(".venv", summary)
        self.assertIn("--only-binary=:all:", preview)
        self.assertIn("aucune installation", summary)

        for invalid in (
            {"manager": "npm", "packages": ["pygame"]},
            {"manager": "python", "packages": ["--index-url"]},
            {"manager": "python", "packages": ["https://example.invalid/pkg.whl"]},
            {"manager": "python", "packages": ["pygame;python -c"]},
            {"manager": "python", "packages": ["pygame"] * (local_agent.MAX_PREREQUISITE_PACKAGES + 1)},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(local_agent.AgentError):
                local_agent.prepare_pending_action(str(self.workspace), {"type": "install_prerequisites", **invalid})

    def test_failed_python_test_offers_missing_module_for_installation(self):
        command = local_agent.prepare_pending_action(str(self.workspace), {
            "type": "run_command", "argv": ["python", "-m", "unittest", "discover", "-s", "tests"],
        })
        state = {
            "messages": [], "pending": command, "workspace": str(self.workspace),
            "remaining_steps": 0, "plan_approved": True, "awaiting_clarification": False,
        }
        failure = "Code de sortie : 1\\nSTDERR:\\nModuleNotFoundError: No module named 'pygame'\\nFAILED (errors=1)"
        with patch("local_agent._execute_approved_action", return_value=(failure, None, None)):
            updated, outcome = local_agent.resolve_pending_action(state, approved=True)

        self.assertEqual(updated["pending"]["type"], "install_prerequisites")
        self.assertEqual(updated["pending"]["packages"], ["pygame"])
        self.assertTrue(updated["plan_approved"])
        self.assertIn("attend maintenant ton accord", outcome)
        self.assertEqual(local_agent._missing_python_packages_from_result(
            "Code de sortie : 0\\nModuleNotFoundError: No module named 'pygame'"
        ), [])
        self.assertEqual(local_agent._missing_python_packages_from_result(
            "Code de sortie : 1\\nModuleNotFoundError: No module named 'json'"
        ), [])

    def test_agent_install_prerequisite_action_waits_for_explicit_approval(self):
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Lance le jeu et corrige les prérequis.")
        )
        response = json.dumps({
            "message": "Le test signale pygame absent; je propose son installation dans l'environnement du projet.",
            "action": {"type": "install_prerequisites", "manager": "python", "packages": ["pygame"]},
        }, ensure_ascii=False)
        with patch("local_agent._install_python_prerequisites") as install:
            pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))[-1]
            self.assertEqual(pending["kind"], "pending")
            self.assertEqual(pending["state"]["pending"]["type"], "install_prerequisites")
            install.assert_not_called()

    def test_prerequisites_install_only_runs_after_approval_and_uses_wheels(self):
        action = local_agent.prepare_pending_action(str(self.workspace), {
            "type": "install_prerequisites", "manager": "python", "packages": ["pygame"],
        })
        state = {
            "messages": [], "pending": action, "workspace": str(self.workspace),
            "remaining_steps": 5, "plan_approved": True, "awaiting_clarification": False,
        }
        with (
            patch("local_agent.venv.EnvBuilder") as builder,
            patch("local_agent.subprocess.run") as install,
        ):
            refused, refusal = local_agent.resolve_pending_action(state, approved=False)
            self.assertIsNone(refused["pending"])
            self.assertIn("refusé", refusal)
            builder.assert_not_called()
            install.assert_not_called()
            self.assertFalse((self.workspace / ".venv").exists())

            def create_fake_venv(path):
                environment = Path(path)
                bin_dir = environment / ("Scripts" if local_agent.os.name == "nt" else "bin")
                bin_dir.mkdir(parents=True)
                (environment / "pyvenv.cfg").write_text("home = test", encoding="utf-8")
                (bin_dir / ("python.exe" if local_agent.os.name == "nt" else "python")).touch()

            builder.return_value.create.side_effect = create_fake_venv
            install.return_value = Mock(returncode=0, stdout="Successfully installed pygame", stderr="")
            approved, result = local_agent.resolve_pending_action(state, approved=True)

        self.assertIsNone(approved["pending"])
        builder.return_value.create.assert_called_once_with(str(self.workspace / ".venv"))
        install.assert_called_once()
        argv = install.call_args.args[0]
        self.assertEqual(argv[0], str(self.workspace / ".venv" / ("Scripts" if local_agent.os.name == "nt" else "bin") / ("python.exe" if local_agent.os.name == "nt" else "python")))
        self.assertIn("--isolated", argv)
        self.assertIn("--index-url", argv)
        self.assertIn("https://pypi.org/simple", argv)
        self.assertIn("--only-binary=:all:", argv)
        self.assertEqual(argv[-1], "pygame")
        self.assertEqual(install.call_args.kwargs["cwd"], str(self.workspace))
        self.assertFalse(install.call_args.kwargs["shell"])
        self.assertIn("Code de sortie : 0", result)

    def test_regular_env_folder_is_not_mistaken_for_a_virtual_environment(self):
        (self.workspace / "env").mkdir()
        run_base = self.workspace.parent / "agent-runs"
        with (
            patch("local_agent._command_runs_directory", return_value=run_base),
            patch("local_agent.subprocess.run") as run_command,
        ):
            run_command.return_value = Mock(returncode=0, stdout="OK", stderr="")
            local_agent.execute_pending_action(str(self.workspace), {
                "type": "run_command", "argv": ["python", "-m", "unittest"],
            })
        self.assertEqual(run_command.call_args.args[0], ["python", "-m", "unittest"])

    def test_python_tests_use_the_project_venv_after_prerequisite_install(self):
        environment = self.workspace / ".venv"
        bin_dir = environment / ("Scripts" if local_agent.os.name == "nt" else "bin")
        bin_dir.mkdir(parents=True)
        (environment / "pyvenv.cfg").write_text("home = test", encoding="utf-8")
        python = bin_dir / ("python.exe" if local_agent.os.name == "nt" else "python")
        python.touch()
        run_base = self.workspace.parent / "agent-runs"
        with (
            patch("local_agent._command_runs_directory", return_value=run_base),
            patch("local_agent.subprocess.run") as run_command,
        ):
            run_command.return_value = Mock(returncode=0, stdout="OK", stderr="")
            local_agent.execute_pending_action(str(self.workspace), {
                "type": "run_command", "argv": ["python", "-m", "unittest", "discover"],
            })

        run_command.assert_called_once()
        self.assertEqual(run_command.call_args.args[0][0], str(python))
        self.assertNotEqual(run_command.call_args.kwargs["cwd"], str(self.workspace))
        self.assertEqual(run_command.call_args.kwargs["env"]["VIRTUAL_ENV"], str(environment.resolve()))
        self.assertTrue(run_command.call_args.kwargs["env"]["PATH"].startswith(str(bin_dir.resolve())))

    def test_command_is_not_run_until_approved(self):
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Lance les tests")
        )
        response = json.dumps({
            "message": "Je propose la commande de test.",
            "action": {"type": "run_command", "argv": ["python", "-m", "unittest", "discover"]},
        })
        run_base = self.workspace.parent / "agent-runs"
        with (
            patch("local_agent._command_runs_directory", return_value=run_base),
            patch("local_agent.subprocess.run") as run_command,
        ):
            run_command.return_value = Mock(returncode=0, stdout="OK", stderr="")
            pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))[-1]
            self.assertEqual(pending["kind"], "pending")
            run_command.assert_not_called()
            _, outcome = local_agent.resolve_pending_action(pending["state"], approved=True)

        run_command.assert_called_once()
        self.assertIn("Code de sortie : 0", outcome)
        self.assertIn("Copie d'exécution conservée", outcome)
        self.assertFalse(run_command.call_args.kwargs["shell"])
        self.assertNotEqual(run_command.call_args.kwargs["cwd"], str(self.workspace))
        self.assertTrue(run_command.call_args.kwargs["cwd"].startswith(str(run_base)))
        self.assertTrue(Path(run_command.call_args.kwargs["cwd"]).is_dir())

    def test_approved_command_changes_only_the_retained_stage_copy(self):
        script = self.workspace / "probe.py"
        script.write_text(
            "from pathlib import Path\n"
            "Path('marker.txt').write_text('dans la copie', encoding='utf-8')\n"
            "Path('env_seen.txt').write_text(str(Path('.env').exists()), encoding='utf-8')\n"
            "Path('alias_seen.txt').write_text(str(Path('env_alias.txt').exists()), encoding='utf-8')\n"
            "Path('git_seen.txt').write_text(str(Path('.git').exists()), encoding='utf-8')\n",
            encoding="utf-8",
        )
        (self.workspace / ".env").write_text("TOKEN=secret", encoding="utf-8")
        env_alias = self.workspace / "env_alias.txt"
        try:
            env_alias.symlink_to(".env")
            env_alias_created = True
        except (OSError, NotImplementedError):
            env_alias_created = False
        (self.workspace / ".git").mkdir()
        (self.workspace / ".git" / "config").write_text("private", encoding="utf-8")
        run_base = self.workspace.parent / "agent-runs"
        action = {"type": "run_command", "argv": ["python", "probe.py"]}

        with patch("local_agent._command_runs_directory", return_value=run_base):
            result = local_agent.execute_pending_action(str(self.workspace), action)

        stage_line = result.splitlines()[0]
        stage = Path(stage_line.split(": ", 1)[1])
        self.assertTrue(stage.is_dir())
        self.assertIn("Code de sortie : 0", result)
        self.assertFalse((self.workspace / "marker.txt").exists())
        self.assertEqual((stage / "marker.txt").read_text(encoding="utf-8"), "dans la copie")
        self.assertEqual((stage / "env_seen.txt").read_text(encoding="utf-8"), "False")
        self.assertEqual((stage / "git_seen.txt").read_text(encoding="utf-8"), "False")
        if env_alias_created:
            self.assertEqual((stage / "alias_seen.txt").read_text(encoding="utf-8"), "False")
        self.assertTrue((self.workspace / ".env").exists())
        self.assertTrue((self.workspace / ".git" / "config").exists())

    def test_read_only_git_query_stays_in_source_project(self):
        action = {"type": "run_command", "argv": ["git", "status", "--short"]}
        with patch("local_agent.subprocess.run") as run_command:
            run_command.return_value = Mock(returncode=0, stdout="## main\n", stderr="")
            result = local_agent.execute_pending_action(str(self.workspace), action)
        self.assertIn("lecture seule", result)
        self.assertEqual(run_command.call_args.kwargs["cwd"], str(self.workspace))
        self.assertEqual(run_command.call_args.args[0][:5], ["git", "-c", "core.pager=cat", "-c", "diff.external="])
        self.assertEqual(run_command.call_args.kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")

    def test_oversized_project_is_not_run_or_copied(self):
        (self.workspace / "large.txt").write_text("too large for limit", encoding="utf-8")
        run_base = self.workspace.parent / "agent-runs"
        with (
            patch("local_agent.MAX_COMMAND_STAGE_BYTES", 1),
            patch("local_agent._command_runs_directory", return_value=run_base),
            patch("local_agent.subprocess.run") as run_command,
        ):
            with self.assertRaisesRegex(local_agent.AgentError, "Aucune commande n'a été exécutée"):
                local_agent.execute_pending_action(
                    str(self.workspace), {"type": "run_command", "argv": ["python", "-m", "unittest"]}
                )
        run_command.assert_not_called()
        self.assertFalse(run_base.exists())

    def test_python_script_command_must_be_inside_project(self):
        (self.workspace / "build.py").write_text("print('ok')", encoding="utf-8")
        action = local_agent.prepare_pending_action(
            str(self.workspace), {"type": "run_command", "argv": ["python", "build.py"]}
        )
        self.assertEqual(action["argv"], ["python", "build.py"])

    def test_agent_parser_accepts_json_after_model_preface(self):
        parsed = local_agent.parse_agent_response(
            'Voici l\'étape suivante : ```json\\n{"message":"Je termine.","action":{"type":"done"}}\\n```'
        )
        self.assertEqual(parsed["action"]["type"], "done")
        with self.assertRaises(local_agent.AgentError):
            local_agent.parse_agent_response("Je ne renvoie pas de JSON.")

    def test_read_action_runs_automatically_then_agent_finishes(self):
        (self.workspace / "README.md").write_text("Projet exemple", encoding="utf-8")
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Regarde les fichiers")
        )
        responses = iter([
            json.dumps({"message": "Je regarde le projet.", "action": {"type": "list_files", "path": "."}}),
            json.dumps({"message": "Le projet contient README.md.", "action": {"type": "done"}}),
        ])
        events = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: next(responses)))

        self.assertEqual(events[-1]["kind"], "done")
        final_state = events[-1]["state"]
        self.assertTrue(any("README.md" in item["content"] for item in final_state["messages"] if item["role"] == "user"))

    def test_new_request_is_blocked_while_action_is_pending(self):
        state = self.approve_plan(
            local_agent.begin_user_turn(None, str(self.workspace), "Crée un fichier")
        )
        response = json.dumps({
            "message": "Écriture proposée.",
            "action": {"type": "write_file", "path": "new.txt", "content": "test"},
        })
        pending = list(local_agent.agent_loop(str(self.workspace), state, lambda *_: response))[-1]
        with self.assertRaises(local_agent.AgentError):
            local_agent.begin_user_turn(pending["state"], str(self.workspace), "Autre demande")


if __name__ == "__main__":
    unittest.main(verbosity=2)
