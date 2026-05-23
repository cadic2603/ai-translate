---
description: "Configurez les fournisseurs LLM pour la traduction : Google Gemini (recommandé), endpoints compatibles OpenAI, ou tout fournisseur personnalisé avec une clé API."
---

# Fournisseurs LLM

Le pipeline de traduction appelle un Large Language Model pour la
traduction réelle. Vous pouvez en configurer un ou plusieurs ; le
sélecteur de modèle par fonctionnalité permet à chaque page d'en
utiliser un différent.

## Google Gemini (recommandé pour une première configuration) {: #google-gemini-recommended-for-first-time-setup }

Le palier gratuit est généreux et suffisant pour la plupart des
usages personnels.

1. Allez sur <https://aistudio.google.com/apikey>
2. Cliquez sur **Create API key** (connectez-vous avec votre compte
   Google)
3. Copiez la clé (ressemble à `AIza...`)
4. Dans l'app desktop : **Paramètres → LLM → Clé API Gemini** →
   coller → **Enregistrer**
5. Choisissez un modèle par défaut dans le menu déroulant **Modèle
   Gemini par défaut**. La gamme de Google a tendance à ressembler à :

    - Variantes **Flash** (par ex. `gemini-2.5-flash`) — rapide,
      palier gratuit généreux, bonne qualité. Point de départ
      recommandé.
    - Variantes **Pro** — plus lent, qualité supérieure, plus cher.
    - **Flash-lite** — le plus rapide, le moins cher, qualité
      inférieure.

    Les noms de modèles exacts disponibles dépendent de ce que Google
    a déployé sur votre compte ; choisissez-en un dont le nom contient
    `flash` pour un défaut équilibré.

Terminé. La clé est stockée dans le trousseau de votre OS, pas en
texte brut.

### Mode Vertex AI (entreprise)

À l'intérieur du bloc de configuration Gemini, une paire de boutons
radio vous permet de basculer de **Developer API** à **Vertex AI** —
mêmes modèles Gemini, facturés via votre compte GCP, avec contrôles
au niveau de l'organisation (VPC-SC, journaux d'audit, résidence
régionale des données).

1. Dans **Paramètres → LLM**, basculez le radio Gemini de
   **Developer API** à **Vertex AI**
2. Remplissez :
    - **Project** — votre ID de projet GCP
    - **Location** — une région Vertex (par défaut `us-central1`)
    - **Credentials path** *(optionnel)* — chemin vers un fichier de
      clé JSON de compte de service. Laissez vide pour utiliser les
      Application Default Credentials
      (`gcloud auth application-default login`)
3. **Enregistrer**. Le menu déroulant des modèles se re-remplit
   depuis Vertex une fois le projet défini.

Le rafraîchissement OAuth est géré automatiquement par
`google-genai`. Le chemin JSON du compte de service est stocké en
clair par exprès (le *chemin* n'est pas un secret — le contenu du
fichier l'est, et il reste sur disque où la pratique recommandée
documentée par Google le maintient).

## OpenAI / Compatible OpenAI

Tout ce qui expose une API REST compatible OpenAI fonctionne — OpenAI
lui-même, Anthropic via [proxy LiteLLM](https://docs.litellm.ai),
Ollama local, LM Studio, vLLM, Together.ai, Groq, et ainsi de suite.

Dans **Paramètres → LLM** :

1. Cliquez sur **Add Custom Provider**
2. Remplissez :
    - **Name** — une étiquette comme « OpenAI » / « Local Ollama » /
      « Anthropic »
    - **API endpoint** — l'URL de base (par ex.
      `https://api.openai.com/v1` ou `http://localhost:11434/v1` pour
      Ollama)
    - **API key** — laissez vide pour les endpoints locaux non
      authentifiés
    - **Models** — liste séparée par virgules (par ex.
      `gpt-4o-mini, gpt-4o, gpt-3.5-turbo`)
3. Cliquez sur **Save**.

Les fournisseurs personnalisés sont stockés sous forme de blob JSON
dans le trousseau de l'OS (clés API incluses).

## Changer le modèle par défaut

Le menu déroulant **Modèle Gemini par défaut** dans **Paramètres →
LLM** définit un repli utilisé par chaque page de fonctionnalité qui
n'a pas son propre sélecteur.

Pages avec leur propre sélecteur de modèle :

- **Traduire le texte** — `onglet de paramètres Traduire le texte → Modèle par défaut`
- **Traduire un document** — choisit par tâche ; retombe sur le défaut
- **Sous-titre / Voix / Doublage / Live / Extraire du texte** —
  chacun a son propre défaut par fonctionnalité dans son onglet de
  Paramètres

Cela vous permet de mixer-et-matcher : Flash gratuit pour le live,
Pro pour les gros documents, Ollama local pour les données sensibles.

## Où les clés sont stockées

| OS | Stockage |
|---|---|
| **macOS** | Trousseau (login keychain) |
| **Windows** | Gestionnaire d'identifiants |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (sans daemon)** | Retombe sur INI en clair dans `~/.config/ai-translate/settings.ini` |

La valeur INI de repli est migrée vers le trousseau à la première
lecture chaque fois qu'un trousseau devient disponible — pas d'étape
manuelle.

## Installation headless / serveur

Sans session desktop, vous pouvez toujours définir des clés via le
CLI `keyring` de Python (après `uv sync`) :

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Fournisseurs personnalisés (collez le blob JSON — voir l'UI Paramètres pour le schéma)
uv run keyring set ai-translate llm/custom_providers
```

Ou définissez directement les mêmes clés INI dans `settings.ini` —
l'app les migre vers le trousseau à la première lecture. Le fichier
se trouve à :

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## Tester votre configuration

Vérification rapide :

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target French --quiet
cat /tmp/x_translated__fr.txt
```

Si vous voyez « Bonjour le monde. » — vous avez terminé.

## Erreurs courantes

| Erreur | Cause probable |
|---|---|
| `AUTH_ERROR` | Clé API erronée / expirée. Recollez dans Paramètres. |
| `QUOTA_ERROR` | Requêtes-par-jour du palier gratuit dépassées. Attendez ou payez. |
| `MODEL_NOT_FOUND` | La liste `models` du fournisseur personnalisé n'inclut pas le modèle demandé. |
| `VISION_NOT_SUPPORTED` | Le modèle que vous avez choisi ne peut pas faire d'entrée d'image. Utilisez une variante `flash` / `pro` / `vision`. |

Voir [Dépannage](../troubleshooting.md) pour plus.
