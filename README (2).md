# MonApp — squelette d'application Python

Ce projet minimal contient une interface Tkinter, une logique séparée et deux tests unitaires. Il est prêt à être enrichi avec Qwen Code ou un éditeur.

## Lancer et tester

```powershell
python main.py
python -m unittest discover -s tests -v
```

## Préparer l'environnement de développement

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Ajoutez ensuite les bibliothèques propres à votre application dans `requirements.txt`.

## Construire un exécutable

```powershell
python -m pip install -r requirements-build.txt
python build_exe.py --name MonApp
```

Le résultat Windows sera `dist\MonApp.exe`. Pour conserver une console (outil en ligne de commande), ajoutez `--console`. Construisez et testez l'exécutable sur le système cible; les ressources externes et fichiers de données doivent être déclarés séparément à PyInstaller.

## Avec Qwen Code et Ollama

Depuis ce dossier, démarrez Qwen Code avec un modèle local configuré dans `~/.qwen/settings.json`. Demandez à l'agent d'inspecter d'abord les fichiers, de proposer un plan, puis de modifier le projet et d'exécuter les tests. Examinez ses changements avant de lancer toute commande de build.
