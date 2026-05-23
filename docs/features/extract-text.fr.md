---
description: Extrait du texte d'images et de captures d'écran à l'aide de moteurs OCR (Tesseract, EasyOCR, Google Vision) ou de LLM vision — sortie en TXT ou DOCX.
---

# Extraire le texte

Sortez le texte des images — reçus, captures d'écran, documents
photographiés, pages scannées, n'importe quoi. Sortie en `.txt`
(brut) ou `.docx` (paragraphes formatés).

Cette page **ne traduit pas** — elle ne fait qu'extraire. Envoyez la
sortie vers Traduire un document si vous voulez aussi traduire.

## Deux méthodes d'extraction

| Méthode | Idéal pour |
|---|---|
| **OCR** | Volume élevé / batch / sensible aux coûts (gratuit ou quasi-gratuit par image) |
| **LLM vision** | Préservation de la mise en page, scripts mixtes, images de mauvaise qualité, écriture manuscrite |

Choisissez le défaut dans **Paramètres → Extraire le texte → Méthode d'extraction**.

## Moteurs OCR (méthode OCR)

| Moteur | Coût | Hors ligne | Langues | Notes |
|---|---|---|---|---|
| **Tesseract** | Gratuit | Oui | 100+ | Par défaut. Nécessite une installation système. |
| **EasyOCR** | Gratuit | Oui (après téléchargement du modèle) | 80+ | Idéal pour les scripts non latins. ~1 Go de modèles. |
| **Google Cloud Vision** | Payant (1 000 gratuits / mois) | Non | 60+ | Précision la plus élevée. |

Configurez dans **Paramètres → OCR**.

## Pas à pas

1. Cliquez sur **Extraire le texte** dans la barre latérale.
2. Déposez un ou plusieurs fichiers image (`.png`, `.jpg`, `.jpeg`,
   `.bmp`, `.webp`, `.tiff`, `.tif`).
3. Choisissez la **Langue source** (aide l'OCR à choisir le bon modèle).
4. Choisissez le **Format de sortie** — `.txt` ou `.docx`.
5. Cliquez sur **Extraire** (ou `Ctrl+Entrée`).
6. **Ouvrez** la ligne quand c'est fini.

## Quand utiliser quoi

- **Reçu / facture chargé en texte** → Tesseract est rapide et précis.
- **Notes manuscrites photographiées** → la vision LLM gagne nettement.
- **Panneaux manga / BD** → EasyOCR (gère bien le texte CJK vertical).
- **Formulaire avec beaucoup de petits champs** → Google Cloud Vision
  préserve mieux les frontières des champs que les autres.

## Astuces

!!! tip "OCR ou LLM, pas les deux"
    La page choisit une méthode et la lance. Pour comparer les sorties,
    relancez la même image deux fois avec des méthodes différentes.

!!! tip "Boîte de dialogue Configuration requise"
    Si vous choisissez OCR mais qu'aucun moteur OCR n'est configuré
    (ou LLM mais aucune clé LLM n'est configurée), la page affiche
    une seule boîte de dialogue « Configuration requise » qui mène
    directement à l'onglet Paramètres pertinent.

## Raccourcis

| Raccourci | Action |
|---|---|
| `Ctrl+Entrée` | Extraire |
| `Ctrl+O` | Parcourir |
| `Ctrl+F` | Focus sur la recherche d'historique |
