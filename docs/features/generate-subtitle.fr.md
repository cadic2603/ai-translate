---
description: Générez des sous-titres SRT, VTT, ASS ou SSA depuis n'importe quel audio ou vidéo — utilise Whisper ou Google Cloud Speech-to-Text pour une transcription de haute qualité.
---

# Générer un sous-titre (STT)

Transcrit l'audio ou la vidéo en sous-titres avec timing. Capte la
parole et émet du SRT / VTT / ASS / SSA — avec traduction optionnelle
dans le même passage.

## Ce qu'il vous faut

- **FFmpeg** dans `PATH` pour le décodage audio/vidéo — voir [Configuration FFmpeg](../setup/ffmpeg.md).
- Un backend de transcription, l'un de :
    - **faster-whisper** — local, hors ligne, gratuit (par défaut ; aucune configuration nécessaire)
    - **Google Cloud Speech-to-Text** — cloud, payant, plus précis sur l'audio bruyant. Voir [Configuration Google Cloud](../setup/google-cloud.md).
    - **Soniox** — cloud, payant, temps réel et diarisation des locuteurs. Voir [Configuration Soniox](../setup/soniox.md).

## Pas à pas

1. Cliquez sur **Générer un sous-titre** dans la barre latérale.
2. Déposez un ou plusieurs fichiers audio / vidéo (`.mp3`, `.wav`,
   `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma`, `.mp4`, `.webm`, `.mkv`,
   `.avi`, `.mov`, `.wmv`).
3. Choisissez la **Langue source** (la langue *parlée* dans l'audio) — laissez
   sur `Détection automatique` pour que Whisper la détecte.
4. Choisissez une **Langue cible** — choisissez `Pas de traduction` pour
   une transcription brute, ou n'importe laquelle des 45 langues
   supportées pour traduire la transcription dans le même passage.
5. Choisissez le **Format de sortie** (SRT / VTT / ASS / SSA).
6. Cliquez sur **Générer** (ou `Ctrl+Entrée`).
7. Surveillez la file. **Ouvrez** la ligne quand fini.

## Choix du format

| Format | Idéal pour |
|---|---|
| **SRT** | Universel — presque tous les lecteurs le supportent |
| **VTT** | Éléments `<track>` HTML5 `<video>` |
| **ASS / SSA** | Karaoké, sous-titres stylisés, flux fansub |

Les quatre formats round-trip via le même parseur, donc vous pouvez
changer le format de sortie sur une re-traduction sans perdre le timing.

## Taille du modèle Whisper

Changez dans **Paramètres → Sous-titre** :

| Modèle | Taille | Vitesse | Précision |
|---|---|---|---|
| `tiny` | ~75 Mo | très rapide | basse |
| `base` (par défaut) | ~150 Mo | rapide | correcte |
| `small` | ~500 Mo | moyenne | bonne |
| `medium` | ~1,5 Go | lente | élevée |
| `large` | ~3 Go | très lente | meilleure |

Les modèles se téléchargent à la première utilisation et sont mis en
cache localement. Sur une connexion lente, la première exécution
semble longue ; les suivantes sont rapides.

## Comparaison des méthodes STT

| Backend | Coût | En ligne ? | Diarisation des locuteurs | Langues |
|---|---|---|---|---|
| **Whisper** (local) | Gratuit | Non | Non | 99 |
| **Google Cloud STT** | Payant | Oui | Oui (modèle `latest_long`) | 125+ |
| **Soniox** | Payant | Oui | Oui (étiquettes par token) | 60+ |

Changez dans **Paramètres → Sous-titre → Méthode STT**.

## Astuces

- **Bouton Stop** — interrompt un batch en cours. Les fichiers en file
  derrière l'actif restent en file ; vous pouvez reprendre plus tard.
- **Re-générer** — clic droit sur une entrée Done pour relancer avec
  un format / langue / méthode STT différent.
- **Audio long** — Whisper gère bien des heures d'audio ; budgétisez
  ~1 minute de traitement par minute d'audio sur CPU avec le modèle `base`.

## Raccourcis

| Raccourci | Action |
|---|---|
| `Ctrl+Entrée` | Générer |
| `Ctrl+O` | Parcourir |
| `Ctrl+F` | Focus sur la recherche d'historique |
