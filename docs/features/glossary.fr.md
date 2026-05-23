---
description: Gérez des ensembles de glossaires personnalisés pour appliquer une terminologie cohérente dans les traductions — import/export CSV, portée par paire de langues, priorisation par projet.
---

# Glossaire

Verrouillez des termes spécifiques à des traductions spécifiques pour
chaque tâche de traduction. Utile pour les noms de marque, la
terminologie produit, le jargon technique ou les noms de personnages
que vous voulez garder cohérents.

## Comment ça marche

Un glossaire est une liste de paires (terme source, terme cible)
regroupées dans un **ensemble**. Quand vous activez un ensemble,
chaque appel LLM dans l'app reçoit les entrées pertinentes injectées
dans le prompt — donc le LLM voit « utiliser 'OpenAI' pour 'OpenAI',
pas '开放AI' » avant de traduire.

Plusieurs ensembles peuvent être actifs en même temps. Seules les
entrées dont la source ou la cible apparaît dans le texte du batch
sont ajoutées au prompt (compression par appel), donc un glossaire
de 5 000 entrées reste léger en tokens.

## Pas à pas

1. Cliquez sur **Glossaire** dans la barre latérale.
2. Cliquez sur **Nouvel ensemble** (`Ctrl+N`) et donnez-lui un nom (ex. « Projet Acme »).
3. Avec l'ensemble sélectionné à gauche, le panneau droit montre ses entrées.
4. Cliquez sur **Ajouter** pour créer une nouvelle entrée. Remplissez :
    - **Source** — le terme original
    - **Cible** — la traduction à imposer
    - Optionnellement un commentaire / note
5. Répétez pour chaque terme.
6. Cochez la case **Actif** sur le nom de l'ensemble pour l'activer.

## Activer / désactiver les ensembles

La case **Actif** à côté de chaque nom d'ensemble contrôle si ses
entrées sont injectées dans les prompts LLM. Vous pouvez laisser 50
ensembles inactifs en stockage et n'activer que les 2 dont vous avez
besoin pour le projet courant.

## Import / Export (CSV)

- **Export** — sélectionnez un ensemble, cliquez sur **Exporter** →
  sauvegardez en `.csv`. Deux colonnes : `source`, `target` (UTF-8,
  séparé par virgules, échappement RFC 4180).
- **Import** — cliquez sur **Importer** → choisissez un `.csv` →
  choisissez un ensemble de destination (existant ou nouveau). Sur une
  source dupliquée vous obtiendrez une invite remplacer-ou-ignorer.

Le format CSV fait round-trip, donc un Export → édition dans Excel →
Import est sûr.

## Recherche et filtrage

`Ctrl+F` met le focus sur la barre de recherche. Tapez n'importe quelle
sous-chaîne et les entrées (et la liste des ensembles) sont filtrées
sur les correspondances ; la sous-chaîne correspondante est mise en
surbrillance. Effacer la recherche restaure la liste complète.

La recherche est **insensible aux accents et insensible à la casse** —
`cafe` trouve `café` et vice versa.

## Édition sur place

Cliquez sur n'importe quelle cellule pour éditer. Appuyez sur `Tab`
pour passer à la cellule suivante. Appuyez sur `Esc` pour annuler.
Une auto-sauvegarde se déclenche quand vous cliquez en dehors de la
ligne. Source ou cible vide annule la ligne au lieu de sauvegarder
une entrée invalide.

## Suppression

- **Supprimer une entrée** — sélectionnez-la, appuyez sur `Suppr`.
  Vous verrez une boîte de confirmation.
- **Supprimer tout un ensemble** — sélectionnez l'ensemble, appuyez
  sur `Suppr`. La boîte de dialogue affiche le nombre d'entrées en
  cascade pour que vous sachiez ce que vous supprimez.

## Raccourcis

| Raccourci | Action |
|---|---|
| `Ctrl+N` | Nouvel ensemble |
| `Ctrl+F` | Focus sur la recherche |
| `Suppr` | Supprimer l'entrée / l'ensemble sélectionné |

## Astuces

!!! tip "Portée par ensemble"
    Un ensemble est un groupement *logique*. Groupez par projet, par
    client, par domaine (médical / juridique / gaming) — ce qui a du
    sens. N'activez que les ensembles pertinents au travail courant.

!!! tip "Le glossaire ne remplace pas la traduction"
    Le LLM est instruit d'utiliser les entrées du glossaire, mais cela
    reste un indice — des traductions forcées extrêmement maladroites
    peuvent toujours apparaître. Utilisez de simples paires
    `terme → traduction` plutôt que des phrases complètes.
