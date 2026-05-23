---
description: Connectez Google Cloud à AI Translate pour Vision OCR, Speech-to-Text et Text-to-Speech — créez une clé API et activez les services pertinents.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

Une seule clé API Google Cloud alimente trois backends optionnels :

- **Vision OCR** — moteur OCR payant (1 000 gratuits / mois)
- **Speech-to-Text v1** — STT payant (60 minutes / mois gratuites)
- **Text-to-Speech v1** — TTS payant (1 M caractères / mois gratuits
  pour WaveNet)

Vous n'avez besoin d'activer que les API que vous utilisez réellement.

## Obtenir une clé API

1. [Créez un projet Google Cloud](https://console.cloud.google.com/projectcreate)
2. Ouvrez la bibliothèque API : <https://console.cloud.google.com/apis/library>
3. Activez l'une de :
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [Créez une clé API](https://console.cloud.google.com/apis/credentials) :
   cliquez sur **+ Create Credentials → API key**
5. Copiez la clé (ressemble à `AIza...`).

!!! tip "Restreindre la clé"
    Sur la page de détail de la clé API, sous **API restrictions**,
    restreignez la clé aux seules API que vous avez activées. De
    cette manière, une clé fuitée ne peut pas accumuler de factures
    sur des services que vous n'aviez pas l'intention d'utiliser.

## Configurer dans l'app

Dans **Paramètres → Service** :

1. Collez dans **Clé API Google Cloud** → **Enregistrer**

Cette clé unique est maintenant disponible pour les trois services
Google.

## Activer chaque service

### Vision OCR

Dans **Paramètres → OCR → Méthode OCR = Google Cloud OCR**.

C'est tout — il utilisera la même clé du Service.

### Speech-to-Text

Dans **Paramètres → Sous-titre → Méthode STT = Google Cloud** (pour
les pages Sous-titre / Voix) ou **Paramètres → Live → Méthode STT =
Google Cloud** (pour la page Live).

Dans **Paramètres → Sous-titre → Modèle STT Google**, choisissez le
modèle de reconnaissance :

| Modèle | Idéal pour |
|---|---|
| `latest_long` (par défaut) | Audio long format (interviews, conférences) |
| `latest_short` | Commandes vocales, phrases courtes |
| `phone_call` | Audio téléphonique (8 kHz) |
| `medical_dictation` / `medical_conversation` | Audio du domaine médical |

### Text-to-Speech

Dans **Paramètres → Voix → Méthode TTS = Google Cloud TTS**.

Par défaut, le serveur choisit une voix selon la langue et le genre
— c'est tout ce dont la plupart des utilisateurs ont besoin. Épingler
une voix Google spécifique (par ex. `en-US-Chirp3-HD-Charon`,
`vi-VN-Wavenet-A`) est pris en charge par le moteur mais pas encore
exposé comme champ de Paramètres ; cela peut être défini en éditant
`voice/google_tts_voice_name` directement dans `settings.ini`. Les
IDs de voix sont listés sur
<https://cloud.google.com/text-to-speech/docs/voices>.

## Erreurs courantes

| Erreur | Cause probable |
|---|---|
| `AUTH_ERROR` | Clé erronée / expirée. Recollez dans Paramètres → Service. |
| `API not enabled` | Vous n'avez pas activé l'API spécifique (Vision / Speech / TTS) sur ce projet Cloud. |
| `QUOTA_ERROR` | Limite du palier gratuit atteinte pour cette API. Attendez ou mettez à niveau la facturation. |
| `INVALID_ARGUMENT_ERROR` | Le nom de voix n'existe pas dans la langue choisie. |

## Garde-coût

!!! warning
    Les trois API Google sont post-payées — une fois que vous
    dépassez le palier gratuit, vous commencez à être facturé sans
    arrêt. Définissez une [alerte budgétaire](https://console.cloud.google.com/billing/budgets)
    sur le projet Cloud avant de faire un travail à grand volume.
