---
description: Traduisez votre premier document avec AI Translate en 5 minutes — glissez-déposez un PDF, choisissez une langue cible et téléchargez la copie traduite.
---

# Votre première traduction

Un parcours rapide de bout en bout — moins de 5 minutes une fois la
configuration faite.

!!! abstract "Avant de commencer"
    Vous devez avoir terminé l'[installation](installation.md) et
    configuré une clé d'API LLM. Le palier gratuit de Google Gemini
    suffit pour un premier essai.

## Traduire un document Word

1. Lancez l'application desktop :

    ```bash
    uv run python -m src.main
    ```

2. Cliquez sur **Traduire un document** dans la barre latérale gauche.

3. Glissez n'importe quel fichier `.docx` dans la zone de dépôt — ou
   cliquez sur **Parcourir** pour en choisir un.

4. Le fichier apparaît dans la file. Choisissez une langue cible en haut :

    - Source : `Détection automatique` (par défaut — généralement correct)
    - Cible : ex. `Français`, `Vietnamien`, `Japonais`, `Chinois (Simplifié)`

5. Cliquez sur **Traduire** (ou appuyez sur `Ctrl+Entrée`).

6. Regardez la barre de progression dans le tableau d'historique en bas
   de la page. Lorsqu'elle atteint 100%, cliquez sur **Ouvrir** sur la
   ligne pour ouvrir le fichier traduit — sauvegardé à côté de l'original
   avec le suffixe `_translated_<src>_<tgt>`.

## Ce qui vient de se passer

- Votre `.docx` a été cloné dans un dossier de stockage par tâche pour
  que l'original ne soit pas touché.
- Le texte a été extrait, regroupé en chunks adaptés au LLM, traduit,
  puis ré-injecté dans le document avec toute la mise en forme préservée
  (gras, italique, polices, couleurs, en-têtes, notes de bas de page,
  hyperliens…).
- Une entrée d'historique a été écrite dans une base SQLite pour que
  vous puissiez ré-ouvrir, ré-exécuter ou re-traduire le fichier plus tard.

## Essayez ensuite les gains rapides

=== "Traduire du texte brut"

    Allez dans **Traduire le texte** dans la barre latérale. Collez
    n'importe quoi, choisissez une cible, appuyez sur Entrée. Sortie en
    streaming, échange de langues (`Ctrl+L`), mode édition, lecture TTS.

=== "Générer des sous-titres"

    **Générer un sous-titre** — déposez un `.mp4`. Vous obtenez un
    `.srt` dans la langue source. (Pour traduire _et_ doubler la vidéo,
    utilisez plutôt la page Doublage.)

=== "Traduction micro en direct"

    **Traduction en direct** — choisissez microphone ou audio système,
    choisissez une cible, Démarrer. Une fenêtre overlay flottante
    affiche les sous-titres en temps réel.

## Et après ?

- Voir l'[index des fonctionnalités](../index.md#headline-features) pour ce que fait chaque page.
- Brancher [d'autres fournisseurs](../setup/llm-providers.md) (endpoints personnalisés, ElevenLabs, Soniox, Google Cloud).
- Essayer le [CLI](../cli.md) pour les exécutions batch / scriptées.
