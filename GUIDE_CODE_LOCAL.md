# Programmer et créer des exécutables avec l'IA locale

Ce guide explique le mode agent de programmation intégré à IA Locale : **Ollama** sert un modèle local, et l'onglet **Agent développement** peut explorer un dossier projet, préparer des modifications puis demander une approbation avant chaque écriture ou commande. **Qwen Code** en terminal reste une alternative facultative.

> L'installation de Qwen Code et le premier téléchargement du modèle nécessitent Internet. Une fois les logiciels et poids installés, les requêtes au modèle peuvent rester sur Ollama local. Le dépôt IA Locale ne contient pas les poids.

## 1. Choisir et télécharger un modèle de code

| Machine indicative | Modèle | Poids Ollama | Usage |
|---|---|---:|---|
| PC personnel/portable | `qwen2.5-coder:7b` | ≈ 4,7 Go | Génération de fonctions, débogage et petites applications; seuil conseillé 12 Go RAM ou 8 Go VRAM + 8 Go RAM |
| Poste puissant | `devstral-small-2:24b` | ≈ 15 Go | Modèle spécialisé d'agent de code; 32 Go RAM, ou 24 Go VRAM + 16 Go RAM |
| Poste puissant | `qwen3-coder:30b` | ≈ 19 Go | Analyse de dépôt, changements multi-fichiers et programmation agentique; 32 Go RAM, ou 24 Go VRAM + 16 Go RAM |

La mémoire d'exécution dépasse la taille du téléchargement : elle dépend aussi du contexte et des autres applications. Le modèle général `qwen3.5:9b` reste utile pour réfléchir à l'architecture; Devstral Small 2 et Qwen Coder sont des choix spécialisés pour le code.

Le catalogue détecte la RAM et la VRAM à l'exécution. Les cartes et menus n'affichent que les modèles adaptés; si la RAM ne peut pas être détectée, l'installation est bloquée par prudence. **Aucun poids LLM n'est téléchargé automatiquement.** Pour demander un modèle explicitement depuis PowerShell, utilisez le gestionnaire qui applique le même contrôle matériel :

```powershell
python auto_install.py --models-only --model qwen2.5-coder:7b
# Pour une machine avec assez de RAM/VRAM :
python auto_install.py --models-only --model devstral-small-2:24b
```

On peut aussi cliquer sur le bouton individuel de chaque fiche compatible dans l'onglet **Modèles IA**. Une commande directe `ollama pull` contourne les vérifications d'IA Locale; préférez l'interface ou `auto_install.py`.

## 2. Créer un projet de départ

Le dépôt comprend un squelette Tkinter minimal avec logique séparée, tests unitaires et script de build. Il crée le projet dans `~/IA-Projects` par défaut; pour le créer ailleurs, indiquez un autre dossier parent :

```powershell
python scripts/create_python_app.py MonApp --destination "$HOME\IA-Projects"
cd "$HOME\IA-Projects\MonApp"
python -m unittest discover -s tests -v
```

Le générateur limite le nom à des caractères sûrs et refuse d'écraser un dossier existant. Les fichiers créés restent modifiables.

## 3. Utiliser l'agent intégré à IA Locale

1. Lancez IA Locale avec `START.bat` (Windows) ou la commande de démarrage de votre système.
2. Ouvrez l'onglet **Agent développement**. Le dossier par défaut est `~/IA-Projects`; cliquez sur **Créer / vérifier le dossier** ou indiquez le chemin d'un dossier projet existant.
3. Choisissez un modèle Ollama déjà installé. Si vous venez de le télécharger, cliquez sur **Actualiser les modèles**.
4. Écrivez une tâche précise, par exemple « inspecte l'application, corrige le test qui échoue et explique les changements ». L'agent affiche d'abord son plan; aucune lecture ni action n'est lancée tant que tu ne l'as pas approuvé.
5. Après l'approbation du plan, l'agent peut lister, lire et rechercher dans le dossier projet. Chaque modification de fichier affiche un diff et attend ton approbation; chaque commande de test ou compilation demande aussi un accord distinct. Si tu refuses, ajoute éventuellement un retour dans le champ prévu pour guider une nouvelle proposition.
6. Après une écriture, le bouton **Annuler la dernière écriture** restaure le fichier si son contenu est toujours celui écrit par l'agent; tu peux remonter la pile une écriture à la fois. Les anciennes versions sont conservées dans `~/.ia-locale/agent-backups`. L'historique, les décisions et la pile Annuler sont sauvegardés localement dans `~/.ia-locale/agent-journals`. Après redémarrage, clique sur **Restaurer la session** après avoir sélectionné le même dossier; les actions restées en attente ne s'exécutent jamais automatiquement et doivent être approuvées de nouveau. Si un diff ne correspond plus au fichier actuel, il est écarté.

Les outils de lecture/écriture refusent les chemins qui sortent du dossier projet et bloquent les fichiers `.env`, les clés SSH et `.git`. Avant la première écriture, si le dossier est la racine d'un dépôt Git propre avec un commit de référence, IA Locale crée et sélectionne une branche `ia-locale-agent-...` comme point de retour; si le dépôt est sale, non Git, sans commit initial ou imbriqué dans un dépôt plus large, elle ne change pas de branche et s'appuie sur la sauvegarde locale. **Les commandes de test/build approuvées (sauf lectures Git) s'exécutent sur une copie conservée dans `~/.ia-locale/agent-runs/<id-projet>/run-...`; leurs fichiers produits restent là, pas dans le projet source.** La copie exclut les secrets courants, `.git`, environnements virtuels, caches et artefacts lourds; elle est limitée à 1 Go et 100 000 fichiers. Un projet trop volumineux n'est pas lancé. Les commandes gardent les droits du compte : **ce n'est pas un bac à sable OS** et un script peut encore accéder au réseau ou à d'autres chemins. Vérifie chaque commande approuvée; les lectures Git status/diff/log consultent le projet source sans le modifier.

Le journal local contient les échanges de l'agent, des extraits de fichiers et les sorties de commandes; il n'est pas synchronisé vers un service cloud. Pour effacer les données d'un projet, supprime son fichier JSON dans `~/.ia-locale/agent-journals`; les copies d'exécution peuvent être supprimées sous `~/.ia-locale/agent-runs`.

L'agent intégré utilise un protocole JSON commun et ne nécessite pas que le modèle prenne en charge les appels d'outils natifs. Le respect du protocole varie selon les modèles; les modèles Coder sont préférables pour les changements multi-fichiers. Ce mode ne lance pas de commande ni n'écrit de fichier sans approbation.

### Mode agent natif avec Ollama

Dans **Agent développement**, choisissez un modèle dans **Modèle Ollama de l'agent**. La liste contient uniquement les modèles locaux déjà installés et compatibles avec le matériel détecté; **Actualiser les modèles** recharge la liste après un téléchargement depuis l'onglet **Modèles IA**. Ce LLM local produit le plan et pilote les étapes de l'agent directement via Ollama. Aucun service cloud, Node.js ou moteur d'agent externe n'est requis.

`local_agent` orchestre l'exploration du dossier choisi et contrôle chaque écriture et commande. Le plan doit d'abord être approuvé; les écritures et les commandes sont ensuite proposées séparément avec leur propre approbation. Une erreur du LLM local est affichée sans basculer vers un fournisseur distant.

### Alternative facultative : Qwen Code en terminal

**Qwen Code** est un agent de terminal open source qui peut également se connecter à Ollama via son API compatible OpenAI. Cette option est séparée de l'onglet Agent intégré.

1. Installez Node.js 22 ou plus récent.
2. Installez Qwen Code :

```powershell
npm install -g @qwen-code/qwen-code@latest
```

3. Vérifiez qu'Ollama fonctionne et que le modèle est téléchargé (`ollama list`). Depuis le dossier du projet, lancez :

```powershell
qwen --auth-type openai --model qwen2.5-coder:7b --openai-base-url http://127.0.0.1:11434/v1 --openai-api-key ollama
```

Pour utiliser le 30B, remplacez `qwen2.5-coder:7b` par `qwen3-coder:30b`.

Si les options de lancement changent selon la version, Qwen Code peut recevoir un fournisseur local dans `~/.qwen/settings.json` (ou `.qwen/settings.json` dans le projet). Exemple à **fusionner** avec les réglages existants :

```json
{
  "env": { "OLLAMA_API_KEY": "ollama" },
  "modelProviders": {
    "openai": [
      {
        "id": "qwen3-coder:30b",
        "name": "Qwen3-Coder 30B (Ollama local)",
        "envKey": "OLLAMA_API_KEY",
        "baseUrl": "http://127.0.0.1:11434/v1",
        "generationConfig": {
          "timeout": 300000,
          "streamIdleTimeoutMs": 600000,
          "maxRetries": 1,
          "contextWindowSize": 32768,
          "samplingParams": { "temperature": 0.2, "max_tokens": 4096 }
        }
      }
    ]
  }
}
```

Pour la variante légère, remplacez l'identifiant du modèle par `qwen2.5-coder:7b`. Voir la [configuration officielle des fournisseurs](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/model-providers/) et le [guide d'installation de Qwen Code](https://qwenlm.github.io/qwen-code-docs/en/users/quickstart/).

### Exemple de demande

```text
Dans ce dossier, crée une petite application de gestion de tâches en Python.
Inspecte le projet et propose un plan avant de modifier des fichiers.
Ajoute les tests, lance-les, corrige les erreurs et explique comment construire
un exécutable Windows. Ne supprime pas les fichiers existants sans me demander.
```

## 4. Construire l'exécutable Windows

Dans le projet squelette créé à l'étape 2 :

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-build.txt
python build_exe.py --name MonApp
```

L'exécutable est écrit dans `dist\MonApp.exe`. Pour un outil en console, ajoutez `--console`. Le script valide que le point d'entrée reste dans le dossier du projet et appelle PyInstaller sans shell. Pour des icônes, modèles ou fichiers de données, des réglages de build supplémentaires peuvent être nécessaires.

Un `.exe` Windows doit être construit et testé sous Windows. PyInstaller ne fabrique pas depuis un système les exécutables natifs de tous les autres systèmes. Évitez d'embarquer des poids IA de plusieurs gigaoctets sans nécessité; fournissez plutôt des instructions de téléchargement séparées.

## 5. Garde-fous

- Faites travailler l'agent dans un dossier de projet séparé, pas directement dans le dépôt IA Locale.
- Faites une sauvegarde Git et examinez les différences avant de garder ses modifications.
- Gardez l'approbation de chaque écriture/commande activée et lisez l'action proposée : l'agent peut produire du code ou des commandes erronés.
- Demandez des tests et une procédure de lancement avant de construire l'exécutable.
- Utilisez l'adresse Ollama locale et ne fournissez pas de clé cloud si vous voulez rester sans abonnement.

## Références

- [Qwen Code — dépôt GitHub](https://github.com/QwenLM/qwen-code)
- [Qwen3-Coder — dépôt éditeur](https://github.com/QwenLM/Qwen3-Coder)
- [Devstral Small 2 24B sur Ollama](https://ollama.com/library/devstral-small-2)
- [Qwen3-Coder 30B sur Ollama](https://ollama.com/library/qwen3-coder:30b)
- [Qwen2.5-Coder 7B sur Ollama](https://ollama.com/library/qwen2.5-coder:7b)
