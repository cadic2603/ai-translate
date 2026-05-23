---
description: Utilisez l'interface en ligne de commande ait pour traduire des fichiers sans interface — supporte PDF, documents Office, sous-titres et 45+ langues depuis un script ou un job CI.
---

# Ligne de commande (`ait`)

Traduction headless — même pipeline que l'application desktop, sans
écran requis. Utile pour la CI, les jobs batch, les serveurs et les
flux scriptés.

## Démarrage rapide

```bash
ait report.docx --target French
```

La sortie atterrit à côté de la source sous le nom
`report_translated_<src>_<tgt>.docx`.

## Recettes courantes

### Plusieurs fichiers

```bash
ait *.pdf --target Japanese
```

L'expansion glob est le travail du shell (Unix). Sur Windows / `cmd.exe`,
listez les fichiers explicitement ou utilisez PowerShell :

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Répertoire de sortie personnalisé

```bash
ait report.docx --target French --output ./translated/
```

Le répertoire est créé s'il n'existe pas. S'il ne peut pas être créé
(permission refusée, etc.) vous obtenez une erreur claire et le code de
sortie 2 — pas d'exécution partielle.

### Spécifier la langue source

```bash
ait letter.txt --target German --source "English (US)"
```

La correspondance source est insensible à la casse. "Chinese" tout seul
imprime un indice :

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Choisir un modèle spécifique

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# Ou tout autre Provider:model_name enregistré dans l'onglet LLM de l'application desktop.
```

Le format est strictement `Provider:model_name`. Deux-points manquants
→ sortie 2 avec un message clair au lieu de retomber silencieusement
sur le modèle Gemini par défaut.

### Options Office

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` requiert qu'un OCR soit configuré (voir
[Moteurs OCR](setup/ocr-engines.md)).

### Auto-conversion des formats anciens

```bash
ait old-doc.doc --target French --convert-legacy
```

Le pipeline convertit `.doc` → `.docx` d'abord (meilleure fidélité),
traduit la copie moderne, reconvertit. Idem pour `--convert-odf` et
`.odt` / `.ods` / `.odp`.

### Silencieux / verbeux

```bash
ait report.docx --target French --quiet      # erreurs uniquement
ait report.docx --target French --verbose    # DEBUG firehose complet
```

Le mode par défaut imprime une bannière et la progression par tâche sur
stderr ; le détail complet (dumps body HTTP, logs de retry) atterrit
dans le répertoire des logs de l'application de la plateforme quel que
soit le verbeux console (voir
[Dépannage → Où sont les logs ?](troubleshooting.md#where-are-the-logs)
pour le chemin sur votre OS).

### Lister les langues supportées

```bash
ait --list-languages
```

Imprime les 45 langues supportées. Utile pour piper dans des boucles shell.

### Version

```bash
ait --version
# ait 0.1.0
```

## Codes de sortie

| Code | Signification |
|---|---|
| `0` | Toutes les tâches ont réussi |
| `2` | Erreur d'argument (langue inconnue, cible manquante, modèle malformé, sortie non inscriptible, extension de fichier non supportée) |
| `3` | LLM non configuré |
| `4` | Échec partiel (certaines réussies, d'autres non) |
| `5` | Toutes échouées |
| `130` | Interrompu (`Ctrl+C`) |

## Annulation

`Ctrl+C` une fois — annulation coopérative. Le checkpoint de la tâche
courante est sauvegardé, le pipeline sort proprement à la prochaine
limite de polling.

`Ctrl+C` encore — interruption dure. À utiliser avec parcimonie ; des
fichiers partiels peuvent rester dans un état à moitié écrit.

## Référence complète des drapeaux

```bash
ait --help
```

Affiche chaque drapeau avec sa valeur par défaut. Le même contenu
résumé ici :

| Drapeau | Défaut | Notes |
|---|---|---|
| `--target / -t LANG` | _requis_ | Insensible à la casse |
| `--source / -s LANG` | détection auto | Insensible à la casse |
| `--output / -o DIR` | parent de la source | Créé si manquant |
| `--model / -m PROVIDER:MODEL` | défaut desktop | Format strict |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | off | Requiert OCR configuré |
| `--translate-comments` | off | Commentaires Office |
| `--translate-shapes` | off | Formes / boîtes de texte |
| `--translate-notes` | off | Notes du présentateur PowerPoint |
| `--translate-sheet-names` | off | Onglets de feuille Excel |
| `--convert-legacy` | off | `.doc`/`.xls`/`.ppt` → format moderne |
| `--convert-odf` | off | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | off | Garder les entrées d'historique après complétion |
| `--quiet / -q` | off | Erreurs uniquement sur la console |
| `--verbose / -v` | off | DEBUG firehose |
| `--list-languages` | — | Imprime les 45 langues et sort |
| `--version` | — | Imprime la version et sort |

## Astuces

!!! tip "Configurez une fois, utilisez partout"
    Le CLI partage ses clés d'API et paramètres avec l'application
    desktop — configurez tout une fois dans la GUI, puis automatisez
    avec `ait` ensuite.

!!! tip "Cache d'endpoint cold-start"
    Pour chaque paire `(endpoint, modèle)`, le choix chat-vs-responses-API
    et la variante de payload qui marche sont persistés dans
    `llm_endpoint_cache.json` du répertoire cache OS
    (`~/.cache/ai-translate/` sur Linux,
    `~/Library/Caches/ai-translate/` sur macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` sur Windows). Les invocations
    CLI cold-start sautent entièrement le probe d'auto-détection après
    le premier appel réussi — utile pour scripter contre des
    déploiements Azure / vLLM / OpenRouter / Anthropic / DeepSeek qui
    nécessitent un tuning de payload spécifique au fournisseur. Le cache
    est sûr multi-processus et multi-thread (read-merge-write sous RLock
    avec rename atomique).

!!! tip "Flux de sortie"
    Le mode par défaut imprime la bannière, la liste des tâches en
    file, et la progression par tâche sur **stdout** (line-buffered
    pour s'entrelacer correctement avec les erreurs) ; les messages
    d'erreur et les enregistrements de log vont sur **stderr**. Combinez
    avec `--quiet` pour supprimer entièrement stdout pour un piping
    propre :

    ```bash
    ait --list-languages | grep -i japanese    # données sur stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
