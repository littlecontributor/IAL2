# Historique de maintenance — mise à jour du 5 octobre 2026

Ce dépôt a été récupéré et relu fichier par fichier avant modification. Cette note remplace le mémo V2 devenu obsolète, dont plusieurs affirmations ne correspondaient plus au code présent.

## Modifications effectuées

- Retrait de l'onglet de modélisation 3D, de sa configuration, des catégories de modèles, des tests, des contrôles de diagnostic et des paquets qui lui étaient spécifiques.
- Remplacement des anciens modèles Ollama par une shortlist curatée et datée : Qwen 3.8 27B, Qwen 3.5 9B/4B, Gemma 4 12B, gpt-oss 20B et DeepSeek R1 8B.
- Ajout d'un catalogue de modèles avec tailles indicatives, cas d'usage, mémoire conseillée, licences et liens de référence.
- Ajout de Qwen2.5-Coder 7B, Devstral Small 2 24B et Qwen3-Coder 30B au catalogue pour couvrir les usages de programmation sur machine modeste et poste puissant.
- Détection runtime de RAM/VRAM et seuils distincts (taille du poids téléchargé, RAM système, VRAM GPU); cartes, choix LLM installés et chemins d'installation filtrés par compatibilité.
- Ajout de BGE-M3 comme embedding Ollama téléchargeable individuellement, avec moteur RAG multilingue et index Chroma séparé de l'index MiniLM historique.
- Ajout d'un guide de développement local : agent intégré IA Locale, Qwen Code facultatif via Ollama et création d'exécutables Python.
- Ajout d'un générateur sûr de squelette Tkinter (sans écrasement), d'un script de build PyInstaller borné au dossier du projet et de tests hors ligne.
- Ajout d'un onglet « Agent développement » natif à IA Locale : plan obligatoire avant les outils, boucle d'actions JSON avec Ollama, diff avant écriture, sauvegardes et annulation persistantes, journal local restaurable, branche Git si le dépôt est propre, confirmations et commandes limitées.
- Les commandes de test/build approuvées s'exécutent dans une copie de projet conservée hors du dossier source; les lectures Git restent sur le dépôt. La copie exclut les secrets courants et les gros artefacts et est bornée en taille/nombre de fichiers.
- Ajout d'un téléchargeur Ollama à progression visible dans l'interface, puis remplacement du menu déroulant unique par un bouton d'installation/actualisation sur chaque fiche de modèle. Le catalogue UI limite les téléchargements aux références répertoriées.
- Aucun poids LLM n'est téléchargé automatiquement lors de l'installation complète; un LLM n'est téléchargé que sur clic individuel ou demande explicite `--model`, après contrôle du catalogue et du matériel.
- Ajout d'une entrée image au chat et envoi local du contenu encodé à l'API Ollama pour les modèles vision.
- Remplacement de l'ancien onglet au libellé « non censuré » et à l'historique mal assemblé par un chat à instructions système personnalisables, sans promesse trompeuse sur le comportement des poids.
- Le sélecteur du chat ne prétend plus qu'un modèle absent est installé ; il est actualisable après un téléchargement.
- Modernisation du thème sans police ni ressource CDN obligatoire.
- Correction de la purge temporaire : l'index ChromaDB persistant n'est plus parcouru par le nettoyeur.
- Remplacement du test de simulation non bloquant par des tests unitaires hors ligne.

## Limites identifiées, non résolues dans cette passe

- La recherche RAG renvoie des extraits de documents mais ne demande pas encore au LLM de rédiger une réponse sourcée.
- Le chat n'affiche pas encore le flux de tokens en direct et les conversations ne sont pas persistées.
- L'agent IA Locale utilise un protocole JSON commun, pas les appels d'outils natifs propres à chaque modèle. Les tests/build approuvés protègent le dossier source en tournant dans une copie, mais ne sont pas isolés par un bac à sable OS : le processus conserve les droits de l'utilisateur et peut avoir des effets hors de la copie; les confirmations restent essentielles.
- Le fallback TTS peut produire un fichier silencieux si le moteur/voix est absent ; le statut doit être clarifié avant usage régulier.
- La génération d'images peut être très lente en CPU et n'active pas encore automatiquement le GPU disponible.
- Le dépôt ne contient pas de fichier `LICENSE` pour son propre code ; seul le modèle choisi possède les licences référencées dans le catalogue.

## Vérification locale

Les tests unitaires sont conçus pour ne pas télécharger de modèle ni exiger un serveur Ollama :

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
python preflight.py --json
```

Un test complet de l'interface, de l'installation Windows et de chaque modèle nécessite la machine cible, les dépendances complètes et Ollama. Les tailles de modèles peuvent évoluer ; les fiches Ollama sont la source de référence au moment du téléchargement.
