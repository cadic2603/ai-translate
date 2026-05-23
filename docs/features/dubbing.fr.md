---
description: "Doublez les vidéos de bout en bout : transcrivez l'audio, traduisez les sous-titres, synthétisez la parole dans la langue cible et remixez-la dans la vidéo originale."
---

# Doublage vidéo

Pipeline complet **STT → Traduire → TTS → Mix** qui produit un fichier
vidéo dans une autre langue avec la piste vocale remplacée. L'audio
original est supprimé ; la nouvelle piste de doublage est calée sur
les sous-titres.

## Ce qu'il vous faut

- **FFmpeg** dans `PATH` — voir [Configuration FFmpeg](../setup/ffmpeg.md).
- Un backend STT (par défaut Whisper local, aucune configuration nécessaire)
- Un backend TTS — Edge TTS (par défaut), ElevenLabs, Google Cloud TTS,
  Gemini TTS, ou **Piper TTS** (entièrement hors ligne ; voix par
  langue téléchargées une fois via **Paramètres → Voix → Piper TTS →
  Télécharger les voix maintenant**)
- Un **LLM** configuré pour l'étape de traduction

## Pas à pas

1. Cliquez sur **Doublage** dans la barre latérale.
2. Déposez un ou plusieurs fichiers vidéo (`.mp4`, `.webm`, `.mkv`,
   `.avi`, `.mov`, `.wmv`).
3. Choisissez la **Langue source** (la langue *parlée* dans la vidéo)
   et la **Langue cible** vers laquelle doubler.
4. Cliquez sur **Démarrer le doublage** (`Ctrl+Entrée`).
5. Surveillez la progression par tâche dans la table d'historique.
   Elle passe par quatre phases :

| Phase | Plage | Que se passe-t-il |
|---|---|---|
| **STT** | 5–25% | Transcription de l'audio source |
| **Traduire** | 25–50% | LLM traduisant chaque ligne de sous-titre |
| **TTS** | 50–90% | Synthèse de la voix langue-cible pour chaque ligne |
| **Mix** | 90–100% | FFmpeg remplace la piste audio |

6. Une fois terminé, **Ouvrez** la ligne pour lire la vidéo doublée.

## Sorties

Pour chaque vidéo d'entrée, vous obtenez quatre fichiers dans le
répertoire de sortie :

```
movie.mp4
movie_dubbed_en_fr.mp4              ← vidéo doublée
movie_subtitle_en.srt               ← sous-titre langue originale
movie_subtitle_fr.srt               ← sous-titre traduit
movie_voice_fr.mp3                  ← piste vocale synthétisée
```

## Reprendre une exécution mise en pause / crashée

Le pipeline checkpoint après chaque phase. Si vous appuyez sur
**Stop**, quittez l'app, ou crashez, appuyer sur **Continuer** sur
la ligne reprend à partir de la dernière phase complétée — vous ne
repayez pas pour le STT ou la traduction s'ils étaient déjà faits.

Clic droit sur une entrée Done / Failed pour ces options :

- **Continuer** — reprend depuis le dernier checkpoint sans re-prompter.
- **Re-doubler** — rouvre le sélecteur de langue ; si vous choisissez
  une nouvelle cible, les checkpoints traduire et TTS sont supprimés
  (vous ne repayez pas pour le STT). Choisir la même cible relance
  effectivement depuis le dernier checkpoint, comme Continuer.
- **Ouvrir** — lit la vidéo doublée.

## Mises en garde

!!! warning "Synchronisation labiale"
    Le doublage correspond aux *timestamps* de l'audio source, pas
    aux mouvements des lèvres. Les lignes traduites beaucoup plus
    longues que l'original sembleront pressées ; les lignes beaucoup
    plus courtes laisseront du silence. Pour le doublage professionnel,
    on re-time généralement manuellement après cette passe — c'est
    une fonctionnalité future.

!!! tip "Vérifications pre-flight"
    La page valide FFmpeg + les clés de votre backend TTS avant de
    démarrer. Clé manquante → boîte de dialogue amicale, pas de
    doublage à moitié exécuté. Avec **Piper TTS** sélectionné, elle
    vérifie aussi que la voix Piper par langue est sur le disque ;
    voix manquante → boîte de dialogue modale avec un bouton
    **Ouvrir les paramètres** qui vous emmène dans la bibliothèque
    de voix, donc vous ne brûlez pas de temps STT + traduction pour
    échouer à l'étape TTS.

!!! tip "Changer de langue cible"
    Sur un re-target, le pipeline supprime les checkpoints traduire
    + TTS (leur contenu n'est plus valide pour la nouvelle langue)
    mais conserve le checkpoint STT — vous économisez le coût de
    transcription.

## Raccourcis

| Raccourci | Action |
|---|---|
| `Ctrl+Entrée` | Démarrer le doublage |
| `Ctrl+O` | Parcourir |
| `Ctrl+F` | Focus sur la recherche d'historique |
| `Ctrl+P` | Pause de la file active |
| `Ctrl+G` | Continuer (reprendre) la file active |

`Ctrl+P` / `Ctrl+G` sont supprimés quand un champ texte a le focus,
donc ils n'entrent pas en collision avec la frappe.
