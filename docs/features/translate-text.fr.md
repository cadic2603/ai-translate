---
description: Traduisez instantanément des extraits de texte dans plus de 45 langues avec AI Translate — collez, tapez ou parlez ; supporte le mode édition, la lecture TTS et l'inversion de langues.
---

# Traduire le texte

Traduction LLM instantanée avec auto-détection, échange de langues,
sortie en streaming et lecture TTS. Idéal pour les extraits courts,
l'usage type chat et le test de votre configuration LLM.

## Pas à pas

1. Cliquez sur **Traduire le texte** dans la barre latérale.
2. Tapez ou collez votre texte source dans le panneau gauche.
3. La langue **Source** s'auto-détecte pendant que vous tapez (alimenté par `langdetect`).
4. Choisissez une langue **Cible** dans le menu déroulant de droite.
5. Cliquez sur **Traduire** (ou appuyez sur `Ctrl+Entrée`).
6. La traduction stream dans le panneau droit token par token.

## Ce que vous obtenez

- **Sortie en streaming** — la traduction apparaît au fur et à mesure
  que le LLM la génère, pas d'attente pour la réponse complète.
- **Auto-détection de la source** — le sélecteur source se met à jour
  en temps réel. Cliquez pour outrepasser.
- **Mode édition** — cliquez sur le panneau droit pour modifier la
  traduction manuellement. Appuyez sur `Échap` pour annuler une
  traduction en cours ; appuyez à nouveau pour quitter le mode édition.
- **Réutilisation de l'historique** — chaque traduction est sauvegardée.
  Cliquez sur une entrée dans le panneau Historique des traductions de
  texte ci-dessous pour recharger les deux panneaux ; les modifications
  mettent à jour l'entrée originale au lieu de créer un doublon.
- **Lecture TTS** — cliquez sur **Écouter** à côté de l'un ou l'autre
  panneau pour l'entendre lu à haute voix. Honore votre choix dans
  **Paramètres → Voix → Méthode TTS** — Edge TTS (par défaut),
  ElevenLabs, Google Cloud TTS, Gemini TTS ou **Piper TTS**
  (entièrement hors ligne). Avec Piper sélectionné, le bouton Écouter
  effectue le même pre-flight que la page Voix : une voix manquante
  par langue affiche un dialogue modal avec un bouton **Ouvrir les
  paramètres** pour la télécharger. Les hits de cache sautent
  entièrement le pre-flight.
- **Sélecteur de modèle par fonctionnalité** — quand plus d'un LLM
  est configuré, un menu déroulant vous laisse choisir un modèle
  Flash rapide pour la vitesse ou un modèle Pro plus lourd pour la
  qualité, juste pour cette page.

## Raccourcis

| Raccourci | Action |
|---|---|
| `Ctrl+Entrée` | Traduire |
| `Ctrl+L` | Échanger source ↔ cible |
| `Échap` | Annuler la traduction en cours, ou quitter le mode édition |
| `Ctrl+F` | Focus sur la recherche d'historique |

## Astuces

!!! tip "Langues RTL"
    Les traductions vers l'**arabe**, l'**hébreu** ou le **persan**
    s'affichent automatiquement de droite à gauche dans le panneau
    de sortie. La même gestion RTL se transmet à la sortie de fichier
    sur tous les formats de la page
    [Traduire un document](translate-document.md) (PDF, DOCX, PPTX,
    XLSX, ODF, RTF, HTML, EPUB, ASS/SSA), et le persan obtient une
    voix `fa-IR` native pour la lecture Edge TTS.

!!! tip "Cache du bouton Écouter"
    La première fois que vous cliquez sur Écouter pour une paire
    (texte, langue) donnée, l'audio est synthétisé et mis en cache
    sur disque. Les lectures suivantes sont instantanées. Le cache
    est effacé au démarrage de l'application, donc chaque session
    démarre à neuf.

!!! tip "Où vont les clés"
    La page Traduire le texte lit les mêmes entrées de keychain que
    le reste de l'application — voir
    [Fournisseurs LLM](../setup/llm-providers.md).
