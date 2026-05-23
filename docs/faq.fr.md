---
description: "Questions fréquentes sur AI Translate : formats de fichiers supportés, fonctionnalités gratuites vs payantes, utilisation hors ligne, choix de fournisseurs LLM, et sélection du moteur OCR."
---

# Foire aux questions

## Général

### Fonctionne-t-il hors ligne ?

Principalement oui. Spécifiquement :

- **La traduction** nécessite un LLM. L'API Gemini gratuite est en
  ligne ; **Ollama / LM Studio local** via les paramètres de
  fournisseur personnalisé est entièrement hors ligne.
- **L'OCR** avec **Tesseract** ou **EasyOCR** est hors ligne.
- **Le STT** avec **Whisper** (par défaut) est hors ligne.
- **Le TTS** avec **Edge TTS** (par défaut) est en ligne ; **ElevenLabs**
  / **Google Cloud TTS** / **Gemini TTS** sont en ligne (gratuit ou
  payant) ; **Piper TTS** est un TTS neuronal entièrement hors ligne —
  pas de clé, pas d'appel réseau une fois la voix par langue téléchargée
  (fichier ONNX d'environ 25–60 Mo) via **Paramètres → Voix → Piper TTS
  → Télécharger les voix maintenant**.

Pour une configuration totalement air-gapped : Fournisseur personnalisé →
LLM local, Tesseract ou EasyOCR pour l'OCR, Whisper pour le STT, et
Piper TTS pour la sortie vocale.

### Où sont sauvegardés mes fichiers traduits ?

À côté de l'original par défaut, avec un suffixe
`_translated_<src>_<tgt>` (par ex. `report_translated_en_fr.docx`).
Surchargez par fonctionnalité dans **Paramètres → Général → Chemin de
stockage des traductions**.

### Où sont stockés mes paramètres ?

Fichier INI à :

| OS | Chemin |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

Les clés d'API vivent dans le trousseau de l'OS (pas dans l'INI).
L'historique de traduction vit dans une base SQLite dans le répertoire
de données.

### Comment mes données sont-elles gérées ?

- **Local-first** — le texte ne quitte jamais votre machine sauf si
  vous appelez un service LLM / OCR / STT / TTS cloud.
- **Pas de télémétrie** — l'application ne contacte pas l'extérieur.
  La seule requête sortante que l'application elle-même fait est la
  vérification optionnelle de mise à jour GitHub Releases (toggle
  dans **Paramètres → Général**) ; les backends cloud n'appellent
  que leurs vendeurs respectifs.
- **Clés d'API** — stockées dans le trousseau de votre OS. Le fallback
  trousseau de l'application desktop est un INI en clair quand aucun
  démon trousseau n'est disponible.

### Puis-je traduire un Google Doc / une page Notion ?

Pas directement. Exportez d'abord en `.docx`, traduisez, puis importez
le fichier traduit. Idem pour Notion (export Markdown / HTML),
Confluence (export `.docx`), etc.

## Choisir des modèles / moteurs

### Quel modèle LLM dois-je utiliser ?

Pour la plupart des utilisateurs :

- **Toute variante Gemini Flash** — palier gratuit, rapide,
  étonnamment bon. À utiliser pour les traductions quotidiennes. Les
  noms ressemblent à `gemini-2.5-flash`, `gemini-3-flash-preview`,
  etc., selon ce qui est disponible.
- **Toute variante Gemini Pro** — paiement par token, qualité
  supérieure. À utiliser pour les documents importants (juridique,
  technique, face client).
- **Ollama local** avec un modèle 7B-13B — quand vous avez besoin
  d'hors ligne / confidentialité.

Le sélecteur de modèle par fonctionnalité signifie que vous pouvez
utiliser un modèle rapide pour la traduction de style chat et réserver
le coûteux pour les documents.

### Quel moteur OCR dois-je utiliser ?

- **Tesseract** pour le texte imprimé propre dans les principaux
  scripts. Gratuit, hors ligne, rapide.
- **EasyOCR** pour les scripts non latins (CJK surtout) et les images
  plus bruitées.
- **Google Cloud Vision** pour l'écriture manuscrite, les scripts
  mixtes, et la précision la plus élevée quand vous pouvez payer.

### Quelle méthode STT dois-je utiliser ?

- **Whisper local** pour hors ligne / confidentialité.
- **Soniox** pour les enregistrements multi-locuteurs — les étiquettes
  de locuteur font le round-trip dans votre SRT.
- **Google Cloud STT** pour audio téléphonique / médical (leurs modèles
  de domaine sont bons).
- **Gemini Live** pour la traduction speech-to-speech en temps réel.

### Quel backend TTS ?

- **Edge TTS** pour des voix gratuites de haute qualité.
- **ElevenLabs** pour des voix premium / brandées / clonées.
- **Google Cloud TTS** pour des voix WaveNet dans des langues à longue
  traîne où Edge a une couverture limitée.
- **Gemini TTS** pour des voix prébuilt naturelles gratuites
  réutilisant votre clé d'API Gemini existante.
- **Piper TTS** quand vous avez besoin d'une sortie vocale **hors
  ligne / air-gapped**. Compromis : chaque langue nécessite un
  téléchargement unique de voix d'environ 25–60 Mo via
  **Paramètres → Voix → Piper TTS → Télécharger les voix maintenant**,
  et 13 des 45 langues de l'application n'ont pas de voix Piper
  (celles-ci se replient silencieusement sur Edge TTS).

## Workflow

### Comment traduire un dossier entier ?

Déposez le dossier dans la zone de dépôt **Traduire un document**. Les
fichiers supportés à l'intérieur (récursivement) sont mis en file ;
tout le reste est silencieusement ignoré. Il y a un plafond de
100 fichiers par dépôt ; les batchs plus grands → divisez en plusieurs
dépôts.

### Puis-je mettre en pause et reprendre des traductions ?

Oui. Quittez l'application à tout moment — les tâches Pending /
Translating reprennent au prochain lancement. Le checkpointing par
tâche signifie que la page 47 sur 100 d'un PDF n'est pas refaite quand
vous reprenez.

### Puis-je éditer une traduction à la main ?

Pour **Traduire le texte** — oui, cliquez sur le panneau de droite et
tapez. L'édition se sauvegarde automatiquement dans l'enregistrement
historique de l'entrée.

Pour **Traduire un document** — ouvrez le fichier traduit dans votre
éditeur habituel (Word, LibreOffice, etc.) et éditez là. L'application
ne fait pas le round-trip des éditions de retour dans l'historique.

### Puis-je traduire en bloc une liste de chaînes ?

Utilisez le CLI :

```bash
ait *.txt --target French
```

Ou pour des chaînes in-process (par ex. chaînes UI extraites du code),
appelez l'outil MCP `translate_text` avec une liste, ou utilisez l'API
Python directement :

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## Glossaire

### Pourquoi le LLM n'utilise pas mon glossaire ?

Trois choses à vérifier :

1. L'ensemble est **actif** (case cochée).
2. Le terme source dans votre glossaire apparaît effectivement dans
   le texte source (la compression par appel n'envoie au LLM que les
   entrées qui correspondent au texte du batch — économise des tokens,
   mais signifie qu'un terme source mal orthographié est invisible).
3. Le modèle est assez fort — `flash-lite` ignore parfois les indices
   que `flash` et `pro` honorent.

### Les termes du glossaire sont-ils appariés indifféremment aux accents ?

Oui. La recherche du glossaire et la barre de recherche dans la page
Glossaire utilisent toutes deux une fonction de normalisation qui
supprime les accents et la casse. Donc `cafe`, `Café` et `CAFE`
correspondent tous à une entrée dont la source est `Café`.

## Confidentialité

### Collectez-vous des données d'usage ?

Non. L'application n'a pas de SDK d'analytics. La vérification de
mise à jour optionnelle interroge un seul endpoint GitHub Releases au
démarrage ; elle est togglable dans **Paramètres → Général**.

### Mes clés d'API sont-elles en sécurité ?

Elles sont stockées dans votre trousseau OS (Keychain sur macOS,
Credential Manager sur Windows, Secret Service sur Linux). D'autres
processus ne peuvent pas les lire sans votre permission explicite. Le
fallback (quand aucun démon trousseau n'est disponible — généralement
serveurs Linux headless) est un INI en clair sous le répertoire de
configuration de votre utilisateur ; dans ce mode les clés sont
protégées par les permissions de fichier mais pas chiffrées
cryptographiquement.
