---
description: Installez FFmpeg pour qu'AI Translate puisse décoder l'audio et la vidéo pour la génération de sous-titres, la synthèse vocale et le doublage vidéo — requis pour les fonctionnalités multimédia.
---

# FFmpeg

FFmpeg est requis pour tout flux audio / vidéo :

- **Générer un sous-titre** — décodage audio source pour STT
- **Générer la voix** — combinaison de clips TTS minutés en un fichier
- **Doublage** — STT → TTS → mux dans la vidéo
- **Traduction en direct** — quand la capture audio système passe par
  `parec`

Il n'est pas inclus — installez-le une fois sur votre système.

## Installer

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    Ou, pour une compilation plus complète, activez d'abord
    [RPM Fusion](https://rpmfusion.org/Configuration).

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    Téléchargez une compilation statique depuis <https://www.gyan.dev/ffmpeg/builds/>
    (la build "release essentials" suffit), dézippez, puis ajoutez le
    dossier `bin/` à votre PATH :

    1. Appuyez sur **Win + R**, tapez `sysdm.cpl`, appuyez sur **Entrée**
    2. **Avancé → Variables d'environnement → Variables système → Path → Modifier**
    3. **Nouveau** → collez le chemin absolu du dossier `bin` de FFmpeg
    4. **OK** partout, redémarrez les terminaux ouverts

## Vérifier

```bash
ffmpeg -version
```

Vous devriez voir une bannière de version avec `--enable-libx264 --enable-libvpx`
dans la ligne de configuration. Si vous voyez "command not found",
l'installation n'a pas atteri sur PATH.

## Vérification pre-flight dans l'app

Les pages Voix / Doublage appellent `shutil.which("ffmpeg")` avant de
démarrer le travail. Si FFmpeg n'est pas trouvé, vous verrez une boîte
de dialogue d'erreur conviviale avec un lien vers ici, pas une tâche
à moitié exécutée.

## Erreur courante

| Erreur | Signification |
|---|---|
| `FFMPEG_NOT_FOUND` | `ffmpeg` n'est pas sur PATH au moment où la page a essayé de l'exécuter. Installez-le (ci-dessus) et redémarrez l'app. |

Dans le serveur MCP (`ait-mcp`), la même erreur est ré-enveloppée en
un message lisible :

> *« FFmpeg est requis pour décoder ce fichier audio/vidéo mais n'est
> pas installé ou n'est pas sur PATH. Installez FFmpeg et réessayez. »*
