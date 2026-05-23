---
description: Capture audio du microphone multiplateforme pour la traduction en direct.
---

# Configuration de PortAudio (Microphone)

La fonctionnalité de [Traduction en direct](../features/live-translation.md) utilise le paquet Python `sounddevice`, qui repose sur la bibliothèque C PortAudio pour accéder aux périphériques de microphone sur tous les systèmes d'exploitation. La plupart des utilisateurs doivent installer cette dépendance au niveau du système.

## Windows
Les roues précompilées (wheels) pour `sounddevice` et `PyAudio` incluent généralement le binaire PortAudio sous Windows. L'installation manuelle à l'échelle du système n'est généralement pas nécessaire. Si vous rencontrez des erreurs, assurez-vous que vos pilotes audio sont à jour.

## macOS
Utilisez Homebrew pour installer PortAudio :

```bash
brew install portaudio
```

## Linux
Le nom du paquet dépend de votre distribution. Le paquet de développement (se terminant généralement par `-dev` ou `-devel`) doit être installé pour que Python puisse construire les liaisons C si aucune roue précompilée n'est disponible.

=== "Ubuntu / Debian / Mint"

    ```bash
    sudo apt-get install portaudio19-dev
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install portaudio-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S portaudio
    ```

## Dépannage

Si l'application continue de signaler qu'elle ne peut pas accéder au microphone après l'installation :

1. Assurez-vous que votre application de terminal (ou environnement de bureau) est autorisée à accéder au microphone (en particulier sur macOS).
2. Redémarrez l'application (ou le terminal/serveur MCP) pour qu'elle prenne en compte le nouveau chemin de la bibliothèque.
