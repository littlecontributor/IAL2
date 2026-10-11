# IA Locale — assistant privé, modèles locaux

Interface Gradio en français pour discuter avec des modèles Ollama installés sur votre machine, utiliser un agent de développement avec validation des actions, analyser des images, interroger des documents, utiliser la voix et générer des images. Aucun compte cloud n'est nécessaire. La modélisation 3D et ses dépendances ont été retirées.

> **Shortlist de modèles vérifiée le 5 octobre 2026.** Les poids sont téléchargeables librement sous les licences indiquées. La taille du fichier Ollama n'est pas la RAM totale nécessaire à l'inférence : le contexte et les autres applications en consomment aussi.

## Démarrage rapide — Windows

1. Installez Python 3.11 ou 3.12, puis Ollama si le script ne peut pas l'installer automatiquement : <https://ollama.com/download>.
2. Ouvrez le dossier `ia-locale-cle-en-main` et double-cliquez sur **`INSTALL.bat`**. L'installation crée un environnement virtuel, vérifie les dépendances et démarre Ollama; **aucun poids LLM n'est téléchargé automatiquement**.
3. Lancez **`START.bat`**, puis ouvrez <http://127.0.0.1:7860>.

Le lanceur confie l'installation complète à l'orchestrateur Python une seule fois : création du `.venv`, vérification des imports et diagnostic final. Il ne relance pas une seconde passe d'installation après la fin de l'orchestrateur.

#### Si Windows bloque un script PowerShell non signé

Utilisez les lanceurs `.bat` fournis plutôt que d'exécuter directement un fichier `.ps1`. `INSTALL.bat` affiche la stratégie en vigueur, puis lance l'installateur dans un processus temporaire; il ne modifie pas la stratégie globale. Si le lancement échoue, exécutez `Get-ExecutionPolicy -List` dans PowerShell depuis le dossier du projet. Si `MachinePolicy` ou `UserPolicy` est défini, demandez à l'administrateur un lancement approuvé ou un script signé — ne cherchez pas à contourner cette règle. Si les deux champs sont `Undefined` et que vous faites confiance au ZIP téléchargé, vous pouvez retirer le marqueur Internet du seul script d'installation, puis relancer :

```powershell
Unblock-File .\INSTALL.ps1
.\INSTALL.bat -Recreate
```

`-Recreate` supprime et recrée le dossier `.venv` du projet. Cette procédure ne change pas les paramètres d'exécution de Windows.

Dans l'interface, ouvrez **Modèles IA** : le profil RAM/VRAM de la machine filtre les cartes et un bouton individuel est proposé pour chaque modèle compatible. Cliquez uniquement sur le modèle voulu, puis actualisez la liste du chat ou le choix RAG après le téléchargement.

### Commandes

```powershell
# Installation des dépendances et diagnostic; aucun poids LLM n'est téléchargé
python auto_install.py

# Installation rapide du noyau; aucun poids LLM n'est téléchargé
python auto_install.py --core

# Demande explicite d'un modèle : catalogue et RAM/VRAM sont vérifiés avant le pull
python auto_install.py --models-only --model qwen3.5:4b
python auto_install.py --models-only --model qwen2.5-coder:7b
python auto_install.py --models-only --model devstral-small-2:24b
python auto_install.py --models-only --model bge-m3

# Installation Windows avec téléchargement facultatif d'un modèle compatible
.\INSTALL.ps1 -Model qwen3.5:4b

# Diagnostic seul
python auto_install.py --diag-only
python preflight.py --json

# Tests unitaires locaux, sans Ollama ni téléchargement de poids
python -m unittest discover -s tests -v
```

Pour arrêter Ollama, utilisez l'icône de l'application ou le gestionnaire de processus de votre système. Les poids restent dans le répertoire Ollama ; le script de nettoyage du projet ne les supprime pas.

## Modèles locaux recommandés

| Modèle Ollama | Téléchargement indicatif | Seuil RAM/VRAM pour apparaître | Usage | Licence des poids |
|---|---:|---|---|---|
| `qwen3.8:27b` | ≈ 18 Go | 32 Go RAM, ou 24 Go VRAM + 16 Go RAM système | Haut de gamme : code, recherche, raisonnement et tâches longues | Apache 2.0 |
| `qwen3.5:9b` | ≈ 6,6 Go | 16 Go RAM, ou 10 Go VRAM + 8 Go RAM système | Équilibre général recommandé, français, code et images | Apache 2.0 |
| `gemma4:12b` | ≈ 7,7 Go | 16 Go RAM, ou 12 Go VRAM + 8 Go RAM système | Raisonnement et vision dans un format intermédiaire | Apache 2.0 |
| `gpt-oss:20b` | ≈ 14 Go | 24 Go RAM, ou 16 Go VRAM + 12 Go RAM système | Raisonnement avancé sur texte, agent local | Apache 2.0 |
| `deepseek-r1:8b` | ≈ 5,2 Go | 12 Go RAM, ou 8 Go VRAM + 8 Go RAM système | Raisonnement, logique et mathématiques | MIT¹ |
| `qwen3.5:4b` | ≈ 3,4 Go | 8 Go RAM, ou 6 Go VRAM + 8 Go RAM système | Modèle rapide pour une machine modeste, avec entrée image | Apache 2.0 |
| `qwen2.5-coder:7b` | ≈ 4,7 Go | 12 Go RAM, ou 8 Go VRAM + 8 Go RAM système | Code, débogage et petites applications | Apache 2.0 |
| `devstral-small-2:24b` | ≈ 15 Go | 32 Go RAM, ou 24 Go VRAM + 16 Go RAM système | Agent de code, exploration de dépôt et changements multi-fichiers | Apache 2.0 |
| `qwen3-coder:30b` | ≈ 19 Go | 32 Go RAM, ou 24 Go VRAM + 16 Go RAM système | Code avancé, dépôts et tâches agentiques | Apache 2.0 |
| `bge-m3` (embedding, pas chat) | ≈ 1,2 Go | 6 Go RAM système | RAG multilingue; index séparé de MiniLM | Voir la fiche modèle |

¹ `deepseek-r1:8b` est une variante distillée sur la base Qwen ; consultez sa fiche de licence et ses conditions d'origine avant redistribution.

Le catalogue lit le profil matériel au lancement et n'affiche que les modèles compatibles. Il compare séparément la taille indicative du téléchargement, le seuil de RAM système et le seuil VRAM (avec un plancher de RAM pour le mode GPU); la taille du fichier ne sert pas de substitut à la mémoire d'inférence. Si la RAM n'est pas détectée, les téléchargements sont bloqués par prudence. Aucun poids LLM n'est tiré automatiquement : chaque carte garde son bouton individuel et les commandes d'installation directes passent elles aussi par le contrôle matériel.

L'agent intégré utilise un protocole d'actions JSON commun : il ne dépend pas des appels d'outils natifs du modèle, mais la qualité d'obéissance au format varie selon le modèle. Devstral Small 2 ou Qwen Coder sont destinés au code.

Sources éditeur / bibliothèque officielle : [Qwen 3.8](https://ollama.com/library/qwen3.8:27b) · [Qwen 3.5 9B](https://ollama.com/library/qwen3.5:9b) · [Gemma 4 12B](https://ai.google.dev/gemma/docs/core/model_card_4) · [gpt-oss](https://openai.com/index/introducing-gpt-oss/) · [DeepSeek-R1 8B](https://ollama.com/library/deepseek-r1:8b) · [BGE-M3](https://ollama.com/library/bge-m3).

Modèles de programmation : [Qwen 2.5 Coder 7B](https://ollama.com/library/qwen2.5-coder:7b) · [Devstral Small 2 24B](https://ollama.com/library/devstral-small-2) · [Qwen3-Coder sur GitHub](https://github.com/QwenLM/Qwen3-Coder) · [Qwen3-Coder sur Ollama](https://ollama.com/library/qwen3-coder:30b).

> Les licences ci-dessus concernent les poids des modèles, pas le code de ce dépôt. L'absence d'un `LICENSE` à la racine du projet doit être résolue par le mainteneur avant redistribution.

## Fonctions

- **Chat local** avec les modèles installés dans Ollama et personnalités configurables.
- **Entrée image** dans le chat pour les modèles compatibles vision (Qwen et Gemma de la shortlist).
- **Catalogue LLM filtré par RAM/VRAM détectées**, avec estimation séparée de la taille téléchargée et de la mémoire d'inférence; un bouton individuel est conservé pour chaque modèle compatible, sans téléchargement automatique.
- **Mode agent de développement** : l'agent présente un plan à approuver, explore ensuite un projet et prépare les changements. Chaque écriture affiche un diff et une sauvegarde, annulable même après redémarrage via le journal local. Les sessions et décisions restent dans `~/.ia-locale/agent-journals`; un dépôt Git propre reçoit une branche de point de retour. Chaque commande demande ton approbation et, sauf lecture Git, s'exécute dans une copie conservée séparément du projet source.
- **Programmation locale** avec Qwen2.5-Coder 7B, Devstral Small 2 24B et Qwen3-Coder 30B; les modèles hors capacités détectées sont masqués. Voir le [guide de programmation et création d'exécutables](GUIDE_CODE_LOCAL.md).
- **Prompt personnalisé** dans un onglet séparé pour tester des instructions système et une température sans modifier les personnalités enregistrées.
- **Voix** : transcription par faster-whisper et synthèse par Piper ou Coqui.
- **Documents** : import PDF/DOCX/TXT/Markdown avec MiniLM (index historique) ou BGE-M3 via Ollama; chaque moteur garde un index séparé et BGE-M3 est proposé seulement installé et compatible.
- **Images** : génération Stable Diffusion via Diffusers ; l'inférence CPU peut être lente.
- **Système** : diagnostic, état Ollama, ressources et nettoyage de fichiers de sortie temporaires.

Les modèles vision sont capables de traiter les images, mais les images ne sont pas jointes aux messages historiques ultérieurs : pour une question de suivi visuelle, renvoyez l'image.

## Programmer et créer des exécutables

Le chat classique répond avec du code; le nouvel onglet **Agent développement** demande d'abord l'approbation d'un plan, puis affiche un diff et une sauvegarde avant chaque écriture. Le bouton **Restaurer la session** recharge explicitement le dernier historique local; toute action restée en attente doit encore être approuvée et un diff devenu périmé est rejeté. Le bouton **Annuler** restaure une écriture après redémarrage si le fichier n'a pas changé depuis. L'historique contient le contexte et des sorties de commandes; il reste local dans `~/.ia-locale/agent-journals`, sans synchronisation cloud, et peut être supprimé manuellement. Chaque commande demande aussi ton approbation; tests/build s'exécutent dans une copie sous `~/.ia-locale/agent-runs`, tandis que les lectures Git restent sur le dépôt. La copie exclut les secrets courants, `.git`, environnements virtuels et gros artefacts; limite 1 Go / 100 000 fichiers. Elle protège les fichiers du projet contre les effets d'une commande, mais **ne constitue pas un bac à sable OS** : le programme approuvé conserve les droits du compte et peut agir sur le réseau ou d'autres chemins. Les commandes Git status/diff/log sont en lecture seule. Le catalogue comprend Qwen2.5-Coder 7B (option plus légère) et Qwen3-Coder 30B (option plus puissante). Pour démarrer un projet de bureau Python prêt à modifier et tester :

```powershell
python scripts/create_python_app.py MonApp --destination "$HOME\IA-Projects"
cd "$HOME\IA-Projects\MonApp"
```

Le squelette inclut une interface Tkinter, des tests et un script de build PyInstaller. Le [guide de programmation locale](GUIDE_CODE_LOCAL.md) détaille le mode agent natif, les confirmations de sécurité et la construction d'un exécutable Windows; Qwen Code en terminal reste une option complémentaire. L'agent intégré utilise directement le LLM Ollama local sélectionné dans l'interface; `local_agent` conserve les approbations du plan, des écritures et des commandes.

## Retrait de la fonction 3D

L'onglet, les catégories de modèles, les options de configuration, les vérifications d'installation et les dépendances spécifiques à la génération 3D ont été retirés. `trimesh`, `scikit-image` et OpenCV ne sont plus installés uniquement pour cette fonction.

## Structure du dépôt

```text
ia-locale-cle-en-main/
├── INSTALL.bat / INSTALL.ps1       # Installation Windows
├── START.bat / START.ps1           # Lancement
├── TEST.bat / TEST.ps1             # Vérification Windows
├── auto_install.py                 # Installation / diagnostic multiplateforme
├── preflight.py                    # Diagnostic Python, packages, Ollama et port
├── README.md                       # Guide principal et audit
├── GUIDE_CODE_LOCAL.md             # Agent de code local et création d'exécutables
├── config/config.yaml              # Paramètres locaux
├── config/personalities/           # Personnalités du chat
├── scripts/
│   ├── ai_model_manager.py         # Gestionnaire Ollama et garde-fous matériels
│   ├── hardware_profile.py         # Détection RAM et VRAM à l'exécution
│   ├── create_python_app.py        # Générateur de squelette desktop testé
│   ├── model_catalog.py            # Shortlist, tailles et seuils matériels
│   ├── llm.py                      # Client Ollama texte + images
│   ├── local_agent.py              # Boucle agent, outils projet et confirmations
│   ├── agent_journal.py            # Journal local et reprise sûre des sessions
│   ├── rag.py                      # Indexation et recherche documentaire
│   ├── stt.py / tts.py             # Voix locale
│   └── ...                         # Monitoring, nettoyage, personnalités
├── templates/python_desktop_app/   # Squelette Tkinter + build PyInstaller
├── ui/futuristic_app.py            # Interface Gradio
├── ui/futuristic_theme.py          # Thème autonome hors ligne
├── tests/test_ia.py                # Tests catalogue, installation et compatibilité
├── tests/test_hardware_profile.py  # Détection RAM/VRAM et seuils
├── tests/test_rag_embeddings.py   # BGE-M3 et index RAG séparés
├── tests/test_local_agent.py       # Périmètre et approbations de l'agent
└── tests/test_app_scaffold.py      # Tests du générateur et du build
```

## Dépendances

- **Python** 3.11+ recommandé.
- **Ollama** pour servir les modèles LLM localement.
- `requirements-core.txt` installe l'interface et les utilitaires.
- `requirements.txt` ajoute les fonctions vocales, RAG et génération d'images. Ces modules ont un poids d'installation supérieur ; la génération d'images CPU est lente.

Le projet et le serveur Ollama communiquent par défaut sur `127.0.0.1:11434`. Les téléchargements de modèles nécessitent Internet ; une fois les poids présents, l'inférence du chat reste locale.

## Audit et améliorations proposées

Points corrigés dans cette version : catalogue LLM filtré par le profil RAM/VRAM détecté, téléchargements individuels sans pull automatique, blocage des chemins d'installation directs incompatibles, ajout de Devstral Small 2 et BGE-M3, retrait de la fonction 3D, chat vision et préservation de l'index documentaire.

Améliorations fonctionnelles à prioriser :

1. Faire produire une réponse par le LLM à partir des passages RAG et afficher les références (fichier/page), plutôt que retourner seulement les extraits trouvés.
2. Ajouter un vrai flux de tokens dans le chat, l'arrêt de génération et la persistance/export des conversations.
3. Remplacer les fichiers silencieux de repli TTS par une erreur explicite et proposer un test de voix installé.
4. Ajouter des tests de bout en bout pour l'installation Ollama, le chat vision, STT/TTS et la recherche RAG.

Améliorations visuelles :

1. Ajouter un mode clair/sombre avec contraste vérifié et une vraie prise en charge mobile/tablette.
2. Présenter l'état Ollama, le modèle actif, la mémoire et les tâches en cours dans un bandeau compact.
3. Regrouper les outils dans une navigation latérale ou des cartes plutôt que multiplier les onglets.
4. Ajouter un aperçu des conversations, des documents indexés et des images générées, avec actions de copie/téléchargement.

## Licence du projet

À ajouter par le mainteneur du dépôt. Les modèles listés ont leurs propres licences ; leur téléchargement n'accorde pas de droits supplémentaires sur le code du projet.
