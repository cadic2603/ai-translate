---
description: Exposez AI Translate comme outils Model Context Protocol pour que Claude Desktop, Claude Code et d'autres clients MCP puissent traduire texte, fichiers et audio.
---

# Serveur MCP (`ait-mcp`)

Expose le pipeline de traduction comme outils **Model Context Protocol**
pour que des agents IA comme Claude Desktop et Claude Code puissent le
piloter directement — « Traduis ce PDF en français » devient un appel
d'outil, pas un copier-coller.

## Ce qui est exposé

Neuf outils :

| Outil | Objet |
|---|---|
| `translate_text` | Traduire une liste de chaînes |
| `translate_document` | Mettre en file d'attente des tâches de traduction de fichiers (renvoie les IDs de tâche) |
| `get_task_status` | Interroger l'état d'une tâche |
| `cancel_task` | Annulation coopérative des tâches en cours |
| `extract_image_text` | OCR ou vision LLM |
| `transcribe_audio` | Audio → SRT |
| `synthesize_speech` | Texte → MP3 / WAV |
| `query_glossary` | Lister les ensembles / entrées de glossaire |
| `list_languages` | Les 45 langues supportées |

## Lancer le serveur

```bash
ait-mcp                       # transport stdio (par défaut pour les agents desktop)
ait-mcp --transport sse       # Server-Sent Events pour clients web
ait-mcp --transport sse --port 9000
```

`stdio` est ce que tout client MCP attend, sauf si vous avez explicitement
configuré SSE.

## Ajouter à Claude Desktop

1. Ouvrez Claude Desktop → **Settings → Developer → Edit Config**
2. Ajoutez cette entrée sous `mcpServers` :

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    Remplacez `/absolute/path/to/ai-translate` par le chemin du repo cloné.

3. Quittez et rouvrez Claude Desktop. L'icône marteau devrait maintenant
   afficher « ai-translate » avec les 9 outils. Essayez :

    > « Traduis ce PDF (`/home/me/report.pdf`) en français — sauvegarde
    > la sortie à côté de la source. »

## Ajouter à Claude Code

`~/.config/claude-code/mcp_servers.json` (ou `claude mcp add` depuis
Claude Code) :

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Redémarrez Claude Code. Les mêmes 9 outils deviennent appelables.

## Ajouter à d'autres clients MCP

Tout client compatible MCP prend une forme similaire :

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (par défaut)

Pour les clients basés sur HTTP / SSE, lancez
`ait-mcp --transport sse --port 9000` et pointez le client sur
`http://localhost:9000`.

## Garanties de validation

Chaque outil renvoie la même forme d'erreur pour que les agents puissent
gérer les échecs de manière cohérente :

| Mauvaise entrée | Réponse de l'outil |
|---|---|
| Langue inconnue | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM non configuré | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Type de fichier non supporté | `ValueError` listant les extensions autorisées |
| `model="…"` mal formé (sans `:`) | `ValueError` au lieu d'utiliser silencieusement la valeur par défaut |
| IDs de tâche inconnus dans `cancel_task` | Renvoyés dans le tableau `unknown` — pas d'erreur |
| FFmpeg manquant pour `transcribe_audio` | `RuntimeError: FFmpeg is required…` (ré-emballé depuis le tag `FFMPEG_NOT_FOUND` brut du moteur) |

Les agents qui appellent ces outils peuvent compter sur ces contrats.

## Concurrence

`translate_document` exécute le pipeline dans un thread daemon. Chaque
batch reçoit son propre événement d'annulation, donc annuler un batch
ne dérange pas un autre. Le serveur MCP suit les pipelines actifs dans
une carte locale au processus (nettoyée automatiquement quand le
pipeline se termine).

## Cas d'usage

- **« Traduis la doc de cette codebase en vietnamien »** — pointez
  l'agent vers le dossier docs, il batche les appels `translate_document`
  et interroge `get_task_status` jusqu'à ce que chacun se termine.
- **« Quelles langues supportez-vous ? »** — l'agent appelle
  `list_languages`, lit la réponse.
- **« Traduis ce reçu japonais »** — l'agent appelle
  `extract_image_text` sur la photo, puis `translate_text` sur le résultat.
- **« Génère des sous-titres vietnamiens pour cet enregistrement Zoom »** —
  l'agent appelle `transcribe_audio` pour obtenir un SRT dans la langue
  source, puis `translate_text` sur chaque cue pour localiser, et
  réassemble le SRT.

!!! note "Le doublage vidéo n'est pas un outil MCP"
    Le pipeline complet STT → traduction → TTS → mux (la page
    **Doublage** de l'application desktop) n'est disponible qu'à
    travers la GUI pour le moment. Depuis MCP, vous pouvez composer
    l'équivalent vous-même avec `transcribe_audio` + `translate_text` +
    `synthesize_speech`, mais vous devrez gérer l'étape de mux
    sensible au timing (FFmpeg) à l'extérieur.

## Astuces

!!! tip "Configurez une fois, les agents fonctionnent partout"
    Le serveur MCP partage les clés d'API et les paramètres avec
    l'application desktop et le CLI. Configurez votre LLM / OCR / TTS
    une fois dans la GUI, puis tout agent qui parle à `ait-mcp` hérite
    de la même configuration.

!!! tip "Cache d'endpoint cold-start"
    Pour chaque paire `(endpoint, modèle)`, le choix
    chat-vs-responses-API et la variante de payload qui marche sont
    persistés dans `llm_endpoint_cache.json` du répertoire cache de
    l'OS (`~/.cache/ai-translate/` sur Linux,
    `~/Library/Caches/ai-translate/` sur macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` sur Windows). Les processus
    `ait-mcp` à froid sautent entièrement le probe d'auto-détection
    après le premier appel réussi — les agents qui spawnent le serveur
    à la demande ne payent pas les round-trips de détection de
    variantes à chaque invocation. Le cache est sûr multi-processus
    et multi-thread (read-merge-write sous RLock avec rename atomique).

!!! tip "Sélecteur de modèle par outil"
    Les outils `translate_text` et `translate_document` acceptent un
    paramètre `model` optionnel — les agents peuvent choisir un
    modèle rapide pour des tours rapides et un plus lourd pour la
    sortie de production sans que l'utilisateur ait besoin de
    reconfigurer l'application desktop.

!!! warning "Pipelines longue durée"
    `translate_document` renvoie immédiatement avec des IDs de tâche.
    L'agent est censé interroger `get_task_status` jusqu'à ce que
    chaque tâche atteigne `Done` ou `Failed`. N'attendez pas
    synchroniquement à l'intérieur de l'appel d'outil ; cela risque
    de déclencher le timeout du client MCP.
