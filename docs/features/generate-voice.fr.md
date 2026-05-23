---
description: Convertissez des sous-titres en audio parlé avec Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS ou Piper TTS hors ligne — préserve la synchronisation SRT pour la génération vocale de qualité doublage.
---

# Générer la voix (TTS)

Synthétisez des fichiers de sous-titres (avec timing) ou du texte
arbitraire en audio MP3 / WAV. Cinq backends TTS : Edge TTS (gratuit),
ElevenLabs (haute qualité), Google Cloud TTS, Gemini TTS (palier
gratuit) et Piper TTS (hors ligne).

## Ce qu'il vous faut

- **FFmpeg** dans le `PATH` — voir [Configuration FFmpeg](../setup/ffmpeg.md).
- Un backend TTS, l'un de :
    - **Edge TTS** — gratuit, pas de clé, par défaut. Utilise les voix
      cloud de Microsoft Edge.
    - **ElevenLabs** — payant, qualité maximale. Voir [Configuration ElevenLabs](../setup/elevenlabs.md).
    - **Google Cloud TTS** — payant, très bon. Voir [Configuration Google Cloud](../setup/google-cloud.md).
    - **Gemini TTS** — palier gratuit, voix prédéfinies naturelles.
      Réutilise votre clé API Gemini existante de l'onglet LLM —
      aucune configuration supplémentaire.
    - **Piper TTS** — TTS neuronal entièrement hors ligne. Pas de clé
      API, pas d'appels réseau — les voix sont des fichiers ONNX de
      ~25–60 Mo téléchargés une fois via **Paramètres → Voix → Piper
      TTS → Télécharger les voix maintenant**. 32 des 45 langues de
      l'app ont une voix Piper aujourd'hui ; les langues sans
      couverture Piper retombent silencieusement sur Edge TTS au
      moment de la synthèse.

## Pas à pas

1. Cliquez sur **Générer la voix** dans la barre latérale.
2. Déposez un ou plusieurs fichiers de sous-titres `.srt` / `.vtt` /
   `.ass` / `.ssa`.
3. Choisissez la **Langue** (auto-détectée depuis le nom de fichier
   du sous-titre quand possible — par ex. `_translated_en_fr.srt` est
   détecté comme français).
4. Choisissez le **Genre de voix** — `Féminin` ou `Masculin`.
5. Choisissez le **Format de sortie** — `.mp3` (par défaut) ou `.wav`.
6. Cliquez sur **Générer** (ou `Ctrl+Entrée`).
7. **Ouvrez** la ligne quand c'est terminé — elle se lit dans votre
   application audio par défaut.

## Sortie

Vous obtenez un fichier audio unique avec les pistes vocales placées
à l'horodatage de chaque sous-titre. Des silences remplissent le temps
entre les indices pour que l'audio reste synchronisé avec le timing
d'origine.

## Choisir un backend TTS

| Backend | Coût | Voix | Notes |
|---|---|---|---|
| **Edge TTS** | Gratuit | Centaines, toutes les langues majeures | Par défaut. Pas de configuration. |
| **ElevenLabs** | Payant (~5 $/mois palier d'entrée) | Voix neuronales premium, clonage de voix | Qualité maximale. L'ID de voix est défini dans Paramètres → Service. |
| **Google Cloud TTS** | Payant (~4 $/M caractères ; 1 M gratuit / mois) | Voix WaveNet / Studio dans 50+ langues | Voix WaveNet fortes pour les langues européennes. Par défaut, le serveur choisit une voix selon la langue + le genre. |
| **Gemini TTS** | Palier gratuit (les quotas Developer API s'appliquent) | Voix prédéfinies naturelles dans 24+ langues — `Kore` (féminin par défaut) / `Puck` (masculin par défaut) | Réutilise votre clé API Gemini de l'onglet LLM. Sortie par appel plafonnée à ~30 s ; les longs textes se découpent automatiquement aux frontières de phrase. |
| **Piper TTS** | Gratuit, **hors ligne** | Voix neuronales dans 32 des 45 langues de l'app | Pas de clé, pas de réseau. Voix par langue téléchargée à la demande via **Paramètres → Voix → Piper TTS → Télécharger les voix maintenant** (~25–60 Mo chacune). Le pre-flight attrape une voix manquante avant que le travail ne commence. |

Basculez dans **Paramètres → Voix → Méthode TTS**.

## Spécificités Piper TTS

Piper est le seul backend TTS entièrement hors ligne dans l'app.
Quelques choses à savoir :

- **Boîte de dialogue de la bibliothèque de voix** — ouvrez via
  **Paramètres → Voix → Piper TTS → Télécharger les voix maintenant**.
  Chaque ligne de langue affiche un bouton de téléchargement
  `Voix féminine` et / ou `Voix masculine` (certaines langues sont
  mono-genre). Les voix proviennent du catalogue HuggingFace
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).
- **Couverture** — 32 des 45 langues de l'app ont une voix Piper.
  Les 13 sans couverture (biélorusse, bengali, chinois (traditionnel),
  croate, estonien, hébreu, japonais, khmer, coréen, lituanien,
  malais, mongol, thaï) retombent silencieusement sur Edge TTS au
  moment de la synthèse, donc la synthèse n'échoue jamais durement
  sur une voix manquante.
- **Résolution du genre** — quand vous choisissez `Féminin`, le moteur
  essaie d'abord la voix féminine pour cette langue ; si seule une voix
  masculine existe, il l'utilise à la place (et vice versa). Journalisé
  au niveau INFO.
- **Garde pre-flight** — avant qu'une exécution Voix ne commence, la
  page vérifie que la voix Piper par langue est sur le disque. Si
  manquante, vous obtenez une boîte de dialogue modale avec un bouton
  **Ouvrir les paramètres** qui vous emmène directement à la
  bibliothèque de voix pour la télécharger sans perdre votre file.

## Spécificités Gemini TTS

Gemini TTS utilise `gemini-2.5-flash-preview-tts` via la Developer API.
Quelques choses à savoir :

- **Sélection de voix** est par genre aujourd'hui — Féminin mappe à
  `Kore`, Masculin à `Puck`. Les deux sont des voix claires et
  neutres qui fonctionnent à travers les langues sans sonner trop
  caractérielles.
- **Plafond de longueur de sortie** — chaque appel API Gemini renvoie
  au maximum ~30 s de parole. L'app découpe le texte d'entrée sous
  `_GEMINI_TTS_MAX_BYTES` (~2000 octets ≈ 30 s) aux frontières de
  phrase, puis concatène les morceaux via FFmpeg. Vous ne rencontrerez
  pas de troncature sur du texte de sous-titre normal.
- **Format audio** — Gemini émet du PCM brut à 24 kHz mono s16le ;
  l'app transcode par morceau en MP3 (ou WAV si vous l'avez choisi)
  pour que le fichier final corresponde à votre format de sortie
  sélectionné.
- **Vertex AI n'est pas encore pris en charge pour TTS** — même si
  votre onglet LLM est configuré pour Vertex, Gemini TTS a toujours
  besoin d'une clé API Developer. L'app lève `AUTH_ERROR` à l'avance
  si elle est manquante.

## Modèles ElevenLabs

Trois modèles sont exposés :

| Modèle | Latence | Qualité | À utiliser pour |
|---|---|---|---|
| `eleven_multilingual_v2` (par défaut) | Moyenne | Élevée | TTS général |
| `eleven_v3` | Moyenne | Maximale | Studio / production |
| `eleven_flash_v2_5` | Faible | Bonne | Temps réel / mode Live |

Configurez dans **Paramètres → Voix → Modèle ElevenLabs**.

## Astuces

!!! tip "Régénérer"
    Clic droit sur une ligne → **Régénérer** pour permuter le genre de
    voix / la méthode TTS / le format sans relancer la traduction.

!!! tip "Vérifications pre-flight"
    La page valide la clé API ElevenLabs (lorsqu'elle est sélectionnée)
    et la disponibilité de FFmpeg avant de commencer. Vous verrez une
    boîte de dialogue conviviale si quelque chose manque.

!!! warning "Stop est atomique"
    Cliquez sur **Stop** pendant la synthèse et vous n'obtiendrez pas
    un MP3 à moitié écrit dans le répertoire de sortie — le fichier
    est écrit dans un emplacement temporaire d'abord, puis déplacé en
    place uniquement en cas de succès.

## Raccourcis

| Raccourci | Action |
|---|---|
| `Ctrl+Entrée` | Générer |
| `Ctrl+O` | Parcourir |
| `Ctrl+F` | Focaliser la recherche d'historique |
