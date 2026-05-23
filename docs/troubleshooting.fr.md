---
description: Diagnostiquez les problèmes d'AI Translate — polices manquantes, erreurs FFmpeg, problèmes de convertisseur LibreOffice, échecs de configuration OCR, et authentification de l'API LLM.
---

# Dépannage

Erreurs courantes, ce qu'elles signifient, et comment les corriger.

## Erreurs de configuration

### "LLM is not configured"

Vous n'avez pas encore ajouté de clé d'API. Ouvrez l'application
desktop → **Paramètres → LLM** → collez une clé. Voir
[Fournisseurs LLM](setup/llm-providers.md) pour le guide complet.

### `AUTH_ERROR`

La clé d'API LLM est incorrecte ou expirée.

- **Gemini** — générez une nouvelle clé à
  <https://aistudio.google.com/apikey>, recollez dans
  **Paramètres → LLM**.
- **Fournisseur personnalisé** — vérifiez que la clé est valide (curl
  l'endpoint manuellement avec le même header `Authorization: Bearer …`).
  Si l'endpoint a changé, mettez aussi à jour le champ **Endpoint API**.

### `QUOTA_ERROR`

Vous avez atteint la limite du palier gratuit ou du plan payant.

- **Palier gratuit Gemini** — le quota de requêtes quotidien varie
  par modèle (voir <https://ai.google.dev/gemini-api/docs/rate-limits>).
  Attendez un jour, ou passez en payant.
- **OpenAI / autres** — vérifiez votre tableau de bord facturation.
  Beaucoup de fournisseurs ont des "spend caps" qui mettent en pause
  les requêtes quand vous les atteignez.

### `MODEL_NOT_FOUND`

Le nom de modèle que vous avez choisi n'est pas disponible.

- Fournisseurs personnalisés — assurez-vous que le modèle est dans
  la liste **Models** séparée par virgules dans **Paramètres → LLM**.
- Liste Gemini intégrée — basculez vers un modèle documenté dans
  **Paramètres → LLM → Modèle Gemini par défaut**.

### `VISION_NOT_SUPPORTED`

Vous avez choisi un modèle non-vision et tenté de traduire une image /
PDF scanné. Basculez vers un modèle dont le nom contient `flash`,
`pro` ou `vision` (par ex. `gpt-4o` pour OpenAI, toute variante
Gemini Flash ou Pro actuelle pour Gemini).

## Erreurs audio / vidéo

### `FFMPEG_NOT_FOUND`

FFmpeg n'est pas dans le PATH. Voir [Configuration FFmpeg](setup/ffmpeg.md)
pour la commande d'installation pour votre OS.

Le serveur MCP réécrit ceci en : *"FFmpeg is required to decode this
audio/video file but is not installed or not on PATH."*

### La page Live n'affiche pas de sous-titres

- **Mauvaise source audio** — ouvrez **Paramètres → Live → Source
  audio** et assurez-vous que cela correspond à ce que vous voulez
  réellement (Microphone / Système / Les deux).
- **Micro coupé** — vérifiez les paramètres son de l'OS ; l'application
  utilise votre périphérique d'entrée par défaut.
- **Audio système non configuré** — voir
  [Capture audio système](setup/system-audio.md) pour les étapes
  loopback macOS / Windows.

### Sortie vocale silencieuse / vide

- **ElevenLabs sans clé** — la page Voice montre une boîte de dialogue
  amicale en pré-vol ; si elle est passée, le fichier peut être des
  octets vides. Vérifiez **Paramètres → Service → ElevenLabs API key**.
- **Erreur réseau Edge TTS** — Edge TTS nécessite Internet ; si votre
  pare-feu bloque `speech.platform.bing.com`, basculez vers
  ElevenLabs, Google Cloud TTS, ou **Piper TTS** (entièrement hors ligne).

### Boîte de dialogue "Piper voice not installed"

Les pages Voice / Dubbing / Translate Text vérifient en pré-vol que
la voix Piper pour votre langue cible est sur le disque avant qu'un
worker ne démarre. Si elle ne l'est pas, vous voyez un modal avec un
bouton **Ouvrir les paramètres**.

Pour télécharger la voix :

1. Cliquez sur **Ouvrir les paramètres** dans la boîte de dialogue
   (ou ouvrez **Paramètres → Voix** manuellement).
2. Assurez-vous que **Méthode TTS** est définie sur **Piper TTS**.
3. Cliquez sur **Télécharger les voix maintenant** pour ouvrir la
   boîte de dialogue de la bibliothèque de voix.
4. Trouvez la ligne de votre langue cible, puis cliquez sur **Female
   voice** ou **Male voice** à côté. Les voix sont des fichiers ONNX
   d'environ 25–60 Mo téléchargés depuis HuggingFace ; une fois par langue.
5. Fermez la boîte de dialogue et relancez votre tâche de traduction
   / voice / dub.

Si votre langue cible n'est pas dans la liste, elle n'a pas de
couverture Piper — le moteur se replie silencieusement sur Edge TTS
au moment de la synthèse, donc vous n'avez pas réellement besoin de
télécharger quoi que ce soit. Les 13 langues sans voix Piper
aujourd'hui : biélorusse, bengali, chinois (traditionnel), croate,
estonien, hébreu, japonais, khmer, coréen, lituanien, malais,
mongolien, thaï.

La page **Traduction en direct** est le seul endroit qui *ne montrera
pas* cette boîte de dialogue — interrompre un flux live avec un modal
serait pire que le repli, donc les cas de voix manquante là-bas vont
silencieusement vers Edge TTS.

## Erreurs de traduction de documents

### La traduction PDF échoue sur une page spécifique

Les PDF utilisent un checkpointing par page — les pages réussies ne
sont pas refaites. La page échouée logge un stack dans `app.log` ;
coupables courants :

- La page est un **scan sans couche de texte** et l'OCR n'est pas
  configuré. Configurez **Paramètres → OCR** (voir
  [Moteurs OCR](setup/ocr-engines.md)).
- La page contient une **mise en page mathématique complexe** que le
  LLM a mal traitée. Essayez un modèle plus fort (une variante Pro
  plutôt que Flash).

### La traduction Office casse le formatage

- **Formats modernes** (`.docx`, `.xlsx`, `.pptx`) — le formatage est
  préservé par run via round-trip HTML. Si vous voyez des balises `<b>`
  errantes dans la sortie, le LLM ne les a pas fermées — relancez avec
  un modèle plus fort.
- **Formats anciens** (`.doc`, `.xls`, `.ppt`) — activez
  **Paramètres → Traduction → Auto-convert legacy** pour une bien
  meilleure fidélité. Le pipeline convertit en `.docx` d'abord, traduit,
  reconvertit.

### La file de traduction s'arrête en milieu de batch

Quittez l'application et vérifiez la base de données :

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

Les lignes `Translating` qui n'ont pas été touchées depuis plusieurs
minutes signifient qu'un worker a crashé silencieusement. Relancez
l'application desktop — elle reprend automatiquement les tâches
Pending / Translating au démarrage.

## Problèmes transversaux

### Plusieurs fichiers à la fois traduits silencieusement comme un seul

Déposez un fichier à la fois, OU vérifiez la colonne **Files** dans
l'en-tête de la file — elle devrait montrer le nombre que vous avez
déposé. Le plafond de 100 fichiers affiche une notification quand il
est dépassé.

### La barre latérale affiche un spinner pour toujours

Indique qu'un worker est encore signalé comme en cours. Quittez
l'application proprement (pas de SIGKILL) — les hooks de nettoyage
autouse réinitialisent les drapeaux. Si un SIGKILL a laissé l'état
bloqué, nettoyez les workers DB manuellement :

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Où sont les logs ? {: #where-are-the-logs }

| OS | Chemin |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Les logs capturent toujours DEBUG+ quel que soit le verbeux console.
La sortie console est INFO+ par défaut ; passez `--verbose` au CLI
pour mirrorer le log fichier complet sur stdout.

## Toujours bloqué ?

- Voir la [FAQ](faq.md) pour les questions de niveau conception.
- Déposez un issue à <https://github.com/cadic2603/ai-translate/issues>
  avec : OS, version Python, la commande qui échoue, le slice
  pertinent de `app.log`, et une description de ce que vous attendiez.
