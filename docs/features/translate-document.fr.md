---
description: Traduisez des PDF, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT et 30+ autres formats de fichiers en préservant la mise en forme et la mise en page.
---

# Traduire un document

Traduisez des fichiers complets — Office, PDF, EPUB, texte brut,
sous-titres, formats de localisation, et plus — avec la mise en forme
préservée.

## Formats pris en charge

| Catégorie | Extensions |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Texte & web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eBooks | `.epub` |
| Sous-titres | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Localisation | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Pas à pas

1. Cliquez sur **Traduire un document** dans la barre latérale.
2. Glissez-déposez des fichiers (ou cliquez sur **Parcourir**). Les
   dossiers fonctionnent aussi — les fichiers pris en charge à
   l'intérieur sont récupérés récursivement.
3. Choisissez la **Source** (ou laissez sur `Détection automatique`)
   et la **Cible**.
4. Cliquez sur **Traduire** — ou appuyez sur `Ctrl+Entrée`.
5. La table d'historique en dessous affiche la progression par fichier
   (En attente → Traduction → Terminé / Échec). La barre latérale
   affiche un spinner tant qu'une tâche est active.
6. Cliquez sur **Ouvrir** sur une ligne pour ouvrir le fichier traduit.
   Clic droit pour les options : retraduire, mettre en pause, réessayer,
   supprimer.

## Où finissent les fichiers

Par défaut, les fichiers traduits sont enregistrés à côté de l'original
avec un suffixe `_translated_<src>_<tgt>` :

```
~/Documents/rapport.docx
~/Documents/rapport_translated_en_fr.docx     ← ici
```

Modifiez cela dans **Paramètres → Général → Chemin de stockage des
traductions** vers un répertoire personnalisé.

## Limites et garde-fous

- **Plafond de 100 fichiers déposés** — déposez-en plus et vous
  recevrez une notification. Traduisez par lots.
- **Détection des doublons** — déposez un fichier déjà dans la file et
  vous verrez une notification (le doublon est rejeté, pas ajouté deux
  fois).
- **Reprise automatique** — quittez l'app pendant que des traductions
  s'exécutent et elles reprendront au prochain lancement (tâches En
  attente / En cours).

## Options spécifiques à Office

L'onglet Traduction dans **Paramètres** expose ces bascules pour les
fichiers Office :

| Option | Ce qu'elle fait |
|---|---|
| **Traduire les images intégrées** | Exécute OCR + LLM vision sur les images dans `.docx` / `.xlsx` / `.pptx` et réinsère l'image traduite. Nécessite OCR configuré. |
| **Traduire les commentaires** | Les commentaires / notes de relecture sont traduits en même temps que le texte du corps. |
| **Traduire les formes & zones de texte** | Capture le texte qui réside dans les formes, légendes et zones de texte flottantes. |
| **Traduire les notes de présentation** | Les notes de présentation PowerPoint sont traduites. |
| **Traduire les noms de feuilles** | Les libellés des onglets de feuilles Excel sont traduits. |
| **Convertir auto. legacy** | Les `.doc` / `.xls` / `.ppt` sont convertis en OOXML moderne avant la traduction (meilleure fidélité). |
| **Convertir auto. ODF** | Les `.odt` / `.ods` / `.odp` sont convertis en OOXML avant la traduction. |

Toute la traduction Office préserve la mise en forme par run : gras,
italique, souligné, barré, taille de police, couleur, hyperliens,
en-têtes, pieds de page, notes de bas de page, notes de fin, tout.

### Traduction des images intégrées : ignorer-avec-avertissement + cache

Lorsque **Traduire les images intégrées** est activé, chaque
image intégrée passe par OCR → vision LLM → réinjection
rendue. Deux comportements à connaître :

- **Ignorer-avec-avertissement** : si une image ne peut pas
  être traduite (trop grande, corrompue, le modèle de vision
  rejette le format, etc.) le document se termine quand même
  — l'image cassée reste dans la langue d'origine, un
  avertissement est enregistré dans `app.log` et la boucle
  continue avec l'image suivante. Seules les erreurs LLM
  fatales (`AUTH_ERROR`, `QUOTA_ERROR`,
  `VISION_NOT_SUPPORTED`) arrêtent le pipeline immédiatement
  car elles bloquent également toutes les images restantes.
  La bannière d'information au-dessus de la case **Traduire
  les images intégrées** documente la politique en ligne.
- **Cache par image** : les traductions d'image réussies sont
  conservées sous le répertoire de stockage interne de la
  tâche, clé SHA256 des octets source. En cas de nouvelle
  tentative, les images déjà traduites accèdent au cache au
  lieu de relancer OCR + LLM — le travail payé n'est pas
  refait. Les images dupliquées (un logo d'entreprise sur
  chaque diapositive) sont traduites une fois et réutilisées
  N − 1 fois.

Le fichier de sortie n'apparaît dans votre dossier de sortie
qu'en cas de **succès** — les traductions partielles
provenant d'exécutions annulées ou échouées restent confinées
dans le répertoire de stockage interne de la tâche, de sorte
que votre dossier de sortie ne collecte jamais de documents
orphelins à moitié traduits.

## Spécificités PDF

Les PDF utilisent un moteur extraction-superposition : le texte
d'origine est rédacté sur place et le texte traduit superposé dans les
mêmes boîtes, conservant la mise en page visuelle. Le checkpoint par
page signifie qu'une exécution en pause / plantée reprend là où elle
s'est arrêtée, pas à la page 1.

Ce qui est traduit :

- Texte du corps (avec détection d'alignement — gauche / centre /
  droite / justifié)
- Signets / plans (entrées de TOC)
- Champs de formulaire (saisies texte, listes déroulantes, listes)
- Hyperliens (rectangle de lien mis à jour pour englober le nouveau
  texte)
- Images intégrées (quand **Traduire les images intégrées** est activé)
- Commentaires / annotations PDF

Pour les PDF scannés (sans couche de texte intégrée), l'OCR s'exécute
automatiquement par page. Configurez votre moteur OCR dans
**Paramètres → OCR**.

## Sortie de droite à gauche

Les traductions vers l'**arabe**, l'**hébreu** ou le **persan**
s'affichent en RTL nativement dans tous les formats de sortie —
`dir="rtl"` injecté dans les superpositions PDF, HTML, et chapitres
EPUB (avec `page-progression-direction="rtl"` dans l'OPF de l'EPUB
pour qu'Apple Books et Kindle tournent les pages dans le bon sens) ;
DOCX `<w:bidi/>` + `<w:rtl/>`, PPTX `rtl="1"`, vue de feuille XLSX
de droite à gauche, ODT/ODS/ODP `style:writing-mode="rl-tb"`, RTF
`\rtldoc`, et miroitage des codes d'alignement ASS/SSA (`\an1` ↔
`\an3`, `\an4` ↔ `\an6`, etc.). Les alignements centraux ne sont pas
touchés.

## Raccourcis

| Raccourci | Action |
|---|---|
| `Ctrl+Entrée` | Démarrer la traduction |
| `Ctrl+O` | Parcourir des fichiers |
| `Ctrl+F` | Focaliser la recherche d'historique |
| `Ctrl+P` | Mettre en pause la file active |
| `Ctrl+G` | Continuer (reprendre) la file active |
| `Suppr` | Supprimer les entrées d'historique sélectionnées |

`Ctrl+P` / `Ctrl+G` sont supprimés quand un champ texte a le focus,
pour ne pas entrer en collision avec la frappe.

## Quand ça échoue

Une tâche échouée affiche un statut rouge avec un code d'erreur et un
message localisé — voir le [guide de dépannage](../troubleshooting.md)
pour les courants (`AUTH_ERROR`, `QUOTA_ERROR`, `FFMPEG_NOT_FOUND`,
etc.).
