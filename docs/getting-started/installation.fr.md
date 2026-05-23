---
description: Installez AI Translate sur Windows, macOS ou Linux depuis des binaires précompilés ou les sources — couvre Python, FFmpeg et la configuration optionnelle de LibreOffice.
---

# Installation

## Ce qu'il vous faut

- **Python 3.12 ou plus récent** ([télécharger](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — gestionnaire de paquets Python rapide. Installez avec :

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **Une clé d'API LLM** — au choix :
    - [Google Gemini](https://aistudio.google.com/apikey) (palier gratuit disponible — recommandé pour démarrer)
    - Tout endpoint compatible OpenAI (OpenAI, Anthropic via proxy, Ollama / LM Studio local, etc.)

## Optionnel, mais débloque plus de fonctionnalités

| Outil | Utilisé par | Quand vous en avez besoin |
|---|---|---|
| **FFmpeg** ([télécharger](https://ffmpeg.org/download.html)) | Sous-titres, Voix, Doublage, Live | Tout flux audio/vidéo |
| **LibreOffice** ([télécharger](https://www.libreoffice.org/download/)) | Formats Office sur Linux/macOS | Traduction de l'ancien `.doc` / `.xls` / `.ppt`, ou tout fichier Office quand MS Office n'est pas installé |
| **Tesseract** ([guide d'installation](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | Moteur OCR (par défaut) | Page Extraire le texte, traduction de PDF scannés, traduction d'images intégrées |
| **MS Office** + **pywin32** | Office sur Windows | Traduction Office la plus fidèle sur Windows |

Vous pouvez installer AI Translate sans aucun de ces outils — les fonctions
qui en ont besoin vous le diront avant d'échouer.

## Configuration

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

Cela installe tout ce dont on a besoin pour exécuter l'application desktop,
le CLI et le serveur MCP.

## Lancement

=== "Application desktop"
    ```bash
    uv run python -m src.main
    ```

=== "Ligne de commande"
    ```bash
    uv run ait --version
    ```

=== "Serveur MCP"
    ```bash
    uv run ait-mcp           # transport stdio (pour Claude Desktop / Code)
    ```

## Ajouter votre clé d'API

La première fois que vous ouvrez l'application desktop :

1. Cliquez sur **Paramètres** dans la barre latérale
2. Ouvrez l'onglet **LLM**
3. Collez votre **clé d'API Google Gemini** (ou configurez un fournisseur
   personnalisé compatible OpenAI). Les utilisateurs entreprise peuvent
   basculer Gemini en **mode Vertex AI** — pointez-le vers un projet et
   une région GCP, fournissez optionnellement un chemin JSON de compte
   de service ; voir [Fournisseurs LLM](../setup/llm-providers.md) pour les détails.
4. Choisissez un modèle par défaut — toute variante Flash actuelle (par ex.
   `gemini-2.5-flash`) est un bon point de départ gratuit. Les variantes
   Pro offrent une meilleure qualité à un coût plus élevé.
5. Fermez les Paramètres — c'est terminé

Les clés sont stockées dans le **trousseau de votre OS** (Keychain macOS,
Credential Manager Windows, Secret Service GNOME / KDE sur Linux), pas en
clair sur le disque.

!!! tip "Installation headless / serveur"
    Si vous ne pouvez pas exécuter l'application desktop pour configurer les
    clés, voir [Fournisseurs LLM](../setup/llm-providers.md) pour les
    commandes CLI keychain.

## Suite : essayez-la

[Première traduction en 5 minutes →](first-translation.md){ .md-button .md-button--primary }
