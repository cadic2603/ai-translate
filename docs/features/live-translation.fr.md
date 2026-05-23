---
description: "Traduction de la parole en temps réel : transcrivez et traduisez le micro ou l'audio système en direct avec les backends Whisper ou Soniox."
---

# Traduction en direct

Sous-titres et traductions en temps réel depuis le micro, l'audio
système, ou les deux — avec une fenêtre overlay always-on-top
optionnelle pour que les sous-titres se trouvent au-dessus de ce que
vous regardez.

## Ce que vous pouvez en faire

- **Sous-titres de réunions en direct** — sous-titrez un appel Zoom
  / Meet / Teams dans une autre langue sans rejoindre comme bot de traduction.
- **Apprentissage de langue en temps réel** — sous-titrez du contenu
  en langue étrangère (films, podcasts, conférences) avec votre
  langue maternelle comme piste de traduction.
- **Sous-titres système** — capturez l'audio système pour sous-titrer
  YouTube / Netflix / tout ce qui joue sur vos haut-parleurs.

## Ce qu'il vous faut

- **FFmpeg** dans `PATH` — voir [Configuration FFmpeg](../setup/ffmpeg.md).
- Un backend STT, l'un de :
    - **faster-whisper** — local, hors ligne, gratuit, par défaut
    - **Soniox** — cloud, payant, diarisation des locuteurs en temps réel. Voir [Configuration Soniox](../setup/soniox.md).

- Pour la **capture audio système**, le bon backend par OS est
  auto-sélectionné : Linux utilise `parec` (PulseAudio / PipeWire),
  Windows utilise WASAPI loopback natif (pas de logiciel
  supplémentaire dans la plupart des cas), macOS utilise
  `ffmpeg -f avfoundation` contre un périphérique loopback virtuel
  (BlackHole / Loopback / etc.). Une bannière d'avertissement inline
  avec des liens d'installation cliquables apparaît si quelque chose
  manque. Voir [Configuration → Audio système](../setup/system-audio.md)
  pour les instructions d'installation complètes par OS.

## Pas à pas

1. Cliquez sur **Traduction en direct** dans la barre latérale.
2. Configurez une fois dans **Paramètres → Live** :

    - **Langue source** (langue parlée)
    - **Langue cible** (ou laissez vide pour transcription seule)
    - **Source audio** : Micro / Audio système / Les deux
    - **Méthode STT** : Whisper / Soniox

3. Sur la page Live, cliquez sur **Démarrer l'écoute** (`Ctrl+Entrée`).
4. La transcription remplit le panneau principal carte par carte. La
   fenêtre **Overlay** flottante affiche aussi les sous-titres
   (faites-la glisser où vous voulez).
5. Cliquez sur **Stop** pour terminer la session.

## La vue transcription

Choisissez une mise en page dans la barre d'outils :

- **Empilé** — original + traduction, l'un au-dessus de l'autre
- **Côte à côte** — original à gauche, traduction à droite
- **Original seul** / **Traduction seule**

Les boutons de la barre d'outils utilisent les suffixes **`ON`** / **`OFF`**
pour un état lisible d'un coup d'œil — par ex. `TTS ON`, `TTS OFF`,
`Timestamps ON`, `Overlay OFF`.

Activez/désactivez les **horodatages** avec l'icône horloge.
Activez/désactivez la **lecture TTS** des lignes traduites avec
l'icône haut-parleur. Honore votre choix dans
**Paramètres → Voix → Méthode TTS** — Edge TTS (par défaut),
ElevenLabs, Google Cloud TTS, Gemini TTS, ou **Piper TTS**
(entièrement hors ligne). Avec Piper sélectionné, les voix par langue
manquantes **retombent silencieusement sur Edge TTS** en cours de
flux — il n'y a pas de pre-flight modal sur cette page, car bloquer
le flux live sur une boîte de dialogue de téléchargement serait
pire que le repli.

## La fenêtre overlay

Une fenêtre outil draggable, redimensionnable et always-on-top.
Raccourcis :

| Raccourci | Action |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Diminuer / augmenter l'opacité |
| `Ctrl+Flèche` | Déplacer l'overlay |
| `Ctrl+0` / `Ctrl+9` | Agrandir / réduire |

Position, taille, opacité et taille de police persistent entre les sessions.

### Synchronisation en direct avec les paramètres

Les commandes de taille de police et d'opacité fonctionnent dans
les deux sens : faire glisser le curseur **Taille de police** ou
**Opacité** dans **Paramètres → Traduction en direct →
Configuration de la superposition** met à jour la superposition
ouverte en temps réel, et inversement, appuyer sur `+` / `-` /
`Ctrl+[` / `Ctrl+]` à l'intérieur de la superposition met à jour
les curseurs dans Paramètres. Aucun redémarrage de la
superposition n'est requis.

### Espace réservé pour l'état vide

Avant qu'un son ne soit capturé, la superposition affiche un
espace réservé (« Appuyez sur Démarrer... » inactif / « En
écoute... » une fois Démarrer cliqué) qui reflète l'état vide de
la fenêtre principale — le basculement reste synchronisé avec la
pastille d'état en cours. L'espace réservé s'adapte à la largeur
× hauteur actuelle de la superposition pour rester lisible à
n'importe quelle taille de fenêtre.

### Mode sous-titres minimaux

La case **Afficher des sous-titres minimaux** dans Paramètres →
Traduction en direct → Configuration de la superposition masque
les puces d'horodatage et de locuteur sur la superposition tout
en les laissant visibles sur la fenêtre principale. Utile quand
la superposition est partagée avec un public (mode présentateur
/ partage d'écran) mais que vous souhaitez conserver toutes les
métadonnées dans votre vue de travail. La bascule ne s'applique
qu'à la superposition — elle ne modifie pas votre préférence
« Étiquettes de locuteur » pour la fenêtre principale.

## Sauvegarder la transcription

Cliquez sur **Sauvegarder la transcription** pour exporter la session
vers un fichier `.txt` avec horodatages, locuteurs, lignes originales
et lignes traduites.

## Choisir un backend STT

| Backend | Idéal pour | Coût | Latence |
|---|---|---|---|
| **Whisper** (local) | Hors ligne, sensible à la confidentialité | Gratuit | Moyenne (~1 s après fin de phrase) |
| **Soniox** | Réunions multi-locuteurs | Payant (~0,005 $ / min) | Faible (temps réel) |

## Mises en garde

!!! warning "Sélection du micro"
    L'entrée micro utilise toujours le **périphérique par défaut de l'OS** —
    il n'y a pas de sélecteur dans l'app (sounddevice fait remonter
    trop de plugins ALSA virtuels pour être utile, et l'OS possède
    déjà l'UI du micro par défaut). Réglez votre micro préféré dans
    les paramètres son de votre OS avant de démarrer.

!!! warning "Backpressure TTS"
    La file TTS est limitée aux 3 phrases les plus récentes — l'audio
    plus ancien en file est abandonné si la synthèse prend du retard.
    Cela maintient la lecture parlée près des sous-titres à l'écran.

!!! tip "ElevenLabs sans clé"
    Si vous avez réglé la méthode TTS sur ElevenLabs mais qu'aucune
    clé d'API n'est configurée, la page Live retombe automatiquement
    sur Edge TTS et annonce le repli dans le label de statut.

## Raccourcis

| Raccourci | Action |
|---|---|
| `Ctrl+Entrée` | Démarrer / Arrêter |
| `Ctrl+K` | Effacer le journal (avec confirmation) |
| `Ctrl+[` / `Ctrl+]` | Ajuster l'opacité de l'overlay |
