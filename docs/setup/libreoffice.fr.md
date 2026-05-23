---
description: Installez LibreOffice pour qu'AI Translate puisse traduire les formats Office hérités (.doc, .xls, .ppt) et les fichiers ODF (.odt, .ods, .odp) sur macOS et Linux.
---

# LibreOffice (formats Office)

Le pipeline de traduction Office choisit le meilleur backend
disponible dans cet ordre :

1. **win32com** (Windows + MS Office installé) — fidélité maximale
2. **LibreOffice UNO** (multiplateforme) — repli quand win32com est
   absent
3. **python-docx / openpyxl / python-pptx** (formats modernes
   uniquement) — repli pure-Python quand aucun des deux ci-dessus
   n'est disponible

LibreOffice est **la seule voie** pour les fichiers `.doc` / `.xls`
/ `.ppt` hérités sur Linux et macOS, et la voie recommandée sur
ces plateformes pour les formats Office modernes aussi (meilleure
fidélité que le backend pure-Python, surtout pour les tableaux et
les objets intégrés).

## Installer

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    Ou téléchargez depuis <https://www.libreoffice.org/download/download/>.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    L'app desktop sur Windows utilise généralement **win32com** avec
    MS Office installé — LibreOffice est le *repli* si MS Office est
    manquant. Installez depuis <https://www.libreoffice.org/download/download/>.

## Vérifier

```bash
soffice --version
```

Si vous obtenez "command not found" sur macOS, le binaire est à
`/Applications/LibreOffice.app/Contents/MacOS/soffice`. L'app le
découvre automatiquement à travers les chemins d'installation
courants, mais vous pouvez surcharger dans **Paramètres → Général →
Chemin LibreOffice** si nécessaire.

## Ce qu'il alimente

Quand LibreOffice est le backend actif :

| Fonctionnalité | Note |
|---|---|
| **Office moderne** (`.docx`, `.xlsx`, `.pptx`) | Utilisé comme repli quand win32com n'est pas disponible |
| **Office hérité** (`.doc`, `.xls`, `.ppt`) | Requis — Python pur ne peut pas les lire |
| **ODF** (`.odt`, `.ods`, `.odp`) | Utilisé pour la conversion aller-retour quand **Convertir auto. ODF** est activé |
| **Convertir auto. legacy / ODF → OOXML** | Requis |

## Processus en arrière-plan

La première fois que LibreOffice est nécessaire, l'app lance un
processus `soffice` en mode headless et le maintient en vie à travers
les traductions (`office_lifecycle.py`). Il s'arrête automatiquement
à la fermeture de l'app.

## Avertissements

!!! warning "Temps de démarrage au premier lancement"
    La première traduction qui touche LibreOffice attend ~5-10 secondes
    pour que `soffice` démarre. Les traductions suivantes réutilisent
    le même processus et sont rapides.

!!! info "Logs de plantage JVM"
    Le composant Java de LibreOffice produit occasionnellement des
    fichiers `hs_err_pid*.log` lorsqu'il segfault. L'app les achemine
    vers un répertoire temporaire pour qu'ils ne polluent pas votre
    dossier de projet.

!!! tip "Convertir auto. legacy / ODF"
    Activez **Paramètres → Traduction → Convertir auto. legacy** si
    vous traduisez régulièrement des `.doc` / `.xls` / `.ppt`. Le
    pipeline les convertit en `.docx` / `.xlsx` / `.pptx` d'abord
    (via `convert_to_modern_format`), traduit la copie moderne, puis
    reconvertit. La fidélité est bien plus élevée qu'en traduisant
    le format hérité directement.
