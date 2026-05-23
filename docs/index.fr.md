---
description: AI Translate est un traducteur desktop gratuit et multiplateforme pour documents, PDF, sous-titres, audio et parole en direct dans plus de 45 langues.
---

# AI Translate

Un traducteur desktop gratuit et multiplateforme qui gère **45 langues** et
va bien au-delà du texte brut — il traduit documents, audio, vidéos, parole
en direct, captures d'écran et plus encore, le tout via un seul pipeline
piloté par LLM.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Application desktop**

    ---

    Glissez un fichier, choisissez une langue cible, recevez une copie
    traduite. Glisser-déposer, historique, glossaires, tout y est.

    [:octicons-arrow-right-24: Démarrage en 5 minutes](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Ligne de commande**

    ---

    `ait report.docx --target French` — le même pipeline, scriptable et
    sans interface. Utile pour la CI, les tâches batch, les serveurs.

    [:octicons-arrow-right-24: Guide CLI](cli.md)

-   :material-robot-outline:{ .lg .middle } **Agents IA (MCP)**

    ---

    Exposez la traduction comme outils Model Context Protocol pour que
    Claude Desktop, Claude Code et autres clients MCP puissent les appeler
    directement.

    [:octicons-arrow-right-24: Configuration MCP](mcp.md)

</div>

## Ce que vous pouvez traduire

| Type | Formats |
|---|---|
| **Documents Office** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, plus l'ancien `.doc` / `.xls` / `.ppt` |
| **PDF** | traduction extract-overlay avec préservation de la mise en page, traduction des signets / formulaires / liens, repli OCR pour les scans |
| **Texte & web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Sous-titres** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Localisation** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Images** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR ou vision LLM) |
| **Audio** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Vidéo** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (pipeline de doublage complet) |

## Fonctionnalités phares {: #headline-features }

- **[Traduire le texte](features/translate-text.md)** — traduction LLM instantanée avec détection automatique, édition sur place, lecture TTS. Les langues de droite à gauche (arabe, hébreu, persan) s'affichent nativement.
- **[Traduire un document](features/translate-document.md)** — déposez des fichiers, regardez le spinner de progression par tâche, obtenez les copies traduites côte à côte. Les cibles RTL reçoivent le balisage bidi approprié ; `Ctrl+P` / `Ctrl+G` mettent en pause et reprennent la file.
- **[Générer un sous-titre (STT)](features/generate-subtitle.md)** — transcrit l'audio / vidéo en SRT / VTT / ASS / SSA.
- **[Générer la voix (TTS)](features/generate-voice.md)** — synthétise les sous-titres en MP3 / WAV avec timing.
- **[Doublage vidéo](features/dubbing.md)** — STT → traduction → TTS → remixage complet dans la vidéo source.
- **[Traduction en direct](features/live-translation.md)** — overlay de sous-titres en temps réel depuis le micro ou l'audio système.
- **[Extraire le texte](features/extract-text.md)** — OCR ou vision LLM → `.txt` / `.docx`.
- **[Glossaire](features/glossary.md)** — applique une terminologie cohérente à toutes les traductions.

!!! tip "Mode Vertex AI pour Gemini"
    Les utilisateurs entreprise peuvent basculer les appels Gemini de l'API
    Developer vers **Vertex AI** dans **Paramètres → LLM** — pointez-le vers
    votre projet et région GCP, fournissez optionnellement un chemin JSON
    de compte de service. Voir
    [Fournisseurs LLM](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "Première fois ici ?"
    Commencez par l'[installation](getting-started/installation.md), puis le
    [tutoriel de première traduction en 5 minutes](getting-started/first-translation.md).
    Vous aurez un document traduit en moins de 10 minutes depuis un clone frais.
