---
description: Capturez l'audio système sur Linux, macOS et Windows pour la page Live d'AI Translate — traduisez n'importe quel son joué sur votre ordinateur en temps réel.
---

# Capture audio système (Live)

La page **[Traduction en direct](../features/live-translation.md)**
peut capturer l'**audio système** (tout ce qui joue sur vos
haut-parleurs) pour que vous puissiez sous-titrer / traduire
n'importe quel média — appels Zoom, YouTube, Netflix, jeux, sons
système.

Dans **Paramètres → Live → Source audio** (ou la combo en haut de la
page Live), choisissez :

- **Microphone** — uniquement votre micro
- **Audio système** — uniquement ce qui joue sur vos haut-parleurs
- **Les deux** — les deux mixés (idéal pour narrer par-dessus un
  média ou capturer des réunions hybrides)

Quand vous choisissez **Audio système** ou **Les deux**, l'app
dispatche vers le bon backend de capture pour votre OS. Une bannière
d'avertissement en ligne avec des liens d'installation cliquables
apparaît si les prérequis OS ne sont pas remplis, pour que vous
n'ayez pas à démarrer une session pour découvrir qu'il manque
quelque chose.

## Linux (PulseAudio / PipeWire)

Fonctionne de base sur toute distro moderne.

L'app utilise `parec` (PulseAudio Recorder) pour exploiter la
**source moniteur** de votre sink par défaut. Le shim de
compatibilité PulseAudio de PipeWire rend cela transparent — vous
n'avez pas besoin de PulseAudio brut.

```bash
parec --version    # devrait afficher quelque chose
```

Si `parec` est manquant, la bannière d'avertissement détecte le
gestionnaire de paquets de votre distro et inclut la commande
d'installation exacte — par exemple :

> La capture audio système nécessite PulseAudio ou PipeWire — exécutez `sudo apt-get install pulseaudio`.

Détecté sur apt-get / dnf / pacman / zypper / apk ; vous pouvez
copier-coller la commande directement dans un terminal.

## macOS

CoreAudio n'expose pas l'audio système nativement, donc vous avez
besoin d'un **périphérique loopback virtuel** — installez l'un de :

- **[BlackHole](https://existential.audio/blackhole/)** — gratuit, open source
- **[Loopback](https://rogueamoeba.com/loopback/)** — payant, GUI soigné
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — option libre legacy
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — payant

L'app les détecte automatiquement via
`ffmpeg -f avfoundation -list_devices` et utilise le premier match.
Pas besoin de définir le loopback comme votre sortie / entrée par
défaut — la capture se fait directement via le backend avfoundation
de `ffmpeg`.

Après installation, choisissez simplement **Audio système** dans la
combo de la page Live et la bannière d'avertissement disparaît.

## Windows

Natif — **aucun logiciel supplémentaire nécessaire** dans la plupart
des cas.

L'app communique directement avec **WASAPI loopback** via le package
Python [`soundcard`](https://github.com/bastibe/SoundCard) (installé
automatiquement avec l'app sur Windows). C'est la même API loopback
native que les apps desktop Tauri / Rust utilisent ; elle capture la
sortie haut-parleur par défaut sans câble virtuel.

Si pour une raison quelconque WASAPI loopback n'est pas disponible
(versions Windows plus anciennes, pilote audio inhabituel), l'app
retombe sur `ffmpeg -f dshow` contre un périphérique DirectShow
loopback virtuel. Choisissez l'un de :

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — gratuit, fournit `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — gratuit, livré comme `CABLE Output (VB-Audio Virtual Cable)`
- **Stereo Mix (Realtek Audio)** — option intégrée legacy, souvent désactivée par défaut

L'app les sonde dans l'ordre et utilise le premier présent.

## Pourquoi « Les deux » capte votre voix ET l'audio système

En mode **Les deux**, l'app ouvre DEUX flux de capture en parallèle —
votre micro via `sounddevice`, l'audio système via le backend
spécifique à l'OS ci-dessus — et les mixe à la granularité du bloc
d'échantillon. C'est le bon mode pour narrer par-dessus une vidéo,
ou pour capturer les deux côtés d'une réunion hybride (votre voix
plus les participants sur les haut-parleurs).

> **Astuce :** si vous entendez un écho ou obtenez des sous-titres
> dupliqués, vous avez de l'audio système qui passe par votre
> microphone (haut-parleurs forts → micro les capte). Passez à
> **Audio système** seulement, ou utilisez des écouteurs.

## Dépannage

| Symptôme | Cause probable |
|---|---|
| La page Live démarre mais pas de sous-titres | Mauvaise source audio sélectionnée, ou votre micro par défaut est muté |
| Sous-titres pour votre voix mais pas pour la vidéo YouTube | Le prérequis audio système n'est pas installé (la bannière devrait afficher les instructions d'installation) |
| Sous-titres en double (écho) | Le mode « Les deux » capte l'audio système deux fois — une fois depuis les haut-parleurs via micro, une fois via loopback. Passez à Audio système seulement ou utilisez des écouteurs |
| La bannière reste visible après installation du logiciel manquant | Changez d'onglet et revenez — la bannière re-vérifie au show de la page |
| macOS : BlackHole installé mais bannière toujours présente | Confirmez que BlackHole est dans la liste des périphériques audio de `ffmpeg -f avfoundation -list_devices true -i ""` ; l'app a besoin de le voir là |
| Windows : WASAPI loopback échoue malgré aucune erreur | Essayez d'installer VB-Audio Virtual Cable comme repli ; les versions Windows plus anciennes ou certains pilotes audio n'exposent pas le loopback via `soundcard` |
