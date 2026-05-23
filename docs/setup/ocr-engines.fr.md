---
description: Configurez les moteurs OCR pour l'extraction de texte d'images et de PDF — choisissez entre Tesseract ou EasyOCR hors ligne, ou Google Vision OCR basé sur le cloud.
---

# Moteurs OCR

L'OCR est utilisé pour lire le texte des images — à la fois sur la
page [Extraire du texte](../features/extract-text.md) et comme repli
dans la traduction de Document quand une page est scannée (pas de
couche texte) ou quand vous activez **Traduire les images intégrées**.

Vous pouvez choisir parmi trois moteurs OCR.

## Tesseract (recommandé par défaut)

Gratuit, rapide, hors ligne. Nécessite une installation système.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` apporte toutes les langues prises en charge.
    Pour économiser du disque, n'installez que ce dont vous avez
    besoin (par ex. `tesseract-ocr-fra` pour le français).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    Téléchargez l'installateur depuis les
    [versions Tesseract de UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
    Lancez-le, acceptez les valeurs par défaut — les packs de langue
    sont fournis.

Vérifier :

```bash
tesseract --version
tesseract --list-langs
```

Dans l'app desktop : **Paramètres → OCR → Méthode OCR = Tesseract**.
Terminé.

## EasyOCR

Gratuit, hors ligne. Idéal pour les écritures non-latines (chinois,
coréen, japonais, thaï). Les modèles se téléchargent à la première
utilisation (~1 Go au total).

```bash
uv sync --extra easyocr
```

Dans l'app desktop : **Paramètres → OCR → Méthode OCR = EasyOCR**.

La première fois que vous l'utilisez pour une langue, le modèle
pertinent se télécharge dans `~/.EasyOCR/`. Les exécutions suivantes
sont instantanées.

## Google Cloud Vision

Cloud, payant (1 000 requêtes gratuites / mois). Précision maximale,
particulièrement sur du contenu bruité / manuscrit / multi-écriture.

1. [Créez un projet Google Cloud](https://console.cloud.google.com/projectcreate)
2. Activez la [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [Créez une clé API](https://console.cloud.google.com/apis/credentials)
4. Dans l'app desktop : **Paramètres → Service → Clé API Google Cloud** → coller
5. **Paramètres → OCR → Méthode OCR = Google Cloud OCR**

La même clé API Google Cloud alimente Vision OCR, Speech-to-Text et
Text-to-Speech si vous activez aussi ces API.

## Comparaison de précision

L'onglet **Paramètres → OCR** comporte un petit tableau de
comparaison intégré — couverture linguistique, en ligne/hors ligne,
coût, précision. Relisez-le chaque fois que vous êtes tenté de
changer.

## Quand l'OCR est utilisé

| Endroit | Comportement |
|---|---|
| **Page Extraire du texte** (quand méthode = OCR) | OCR direct sur les images déposées |
| **Traduire un document → PDF** | Repli OCR sur les pages scannées uniquement (pas de couche texte) |
| **Traduire un document → Office** avec **Traduire les images intégrées** activé | OCR + LLM vision sur chaque image intégrée |

## Astuces

!!! tip "Choisir la langue source"
    La plupart des moteurs OCR sont beaucoup plus précis quand vous
    leur dites quelle langue attendre. Les pages Sous-titre /
    Document / Extraire du texte transmettent toutes votre sélecteur
    **Langue source** au moteur OCR.

!!! tip "Tesseract suffit pour le texte imprimé propre"
    Ne courez pas vers l'OCR cloud avant que Tesseract / EasyOCR
    n'ait réellement échoué sur votre contenu. Ils sont gratuits,
    rapides et étonnamment bons.
