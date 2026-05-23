---
description: Connectez ElevenLabs à AI Translate pour du TTS neuronal de haute qualité — générez des voix off dans 30+ langues avec une parole réaliste et expressive.
---

# ElevenLabs (TTS)

Synthèse vocale neuronale premium. Utilisé par les pages
**[Générer la voix](../features/generate-voice.md)**,
**[Doublage](../features/dubbing.md)** et
**[Traduction en direct](../features/live-translation.md)** lorsque
vous choisissez ElevenLabs comme méthode TTS.

## Obtenir une clé API

1. Inscrivez-vous sur <https://elevenlabs.io>
2. Ouvrez <https://elevenlabs.io/app/settings/api-keys>
3. Cliquez sur **+ Create New Key**, nommez-la (par ex. "ai-translate"),
   copiez la clé (ressemble à `sk_...`)

Le palier gratuit donne ~10 000 caractères / mois, suffisant pour
tester. L'utilisation en production commence autour de 5 $/mois.

## Configurer dans l'app

Dans **Paramètres → Service** :

1. Collez la clé dans **Clé API ElevenLabs** → **Enregistrer**
2. Entrez votre **ID de voix** préféré dans **ID de voix** (trouvez
   les IDs sur <https://elevenlabs.io/app/voice-lab> ; copiez l'ID
   depuis l'URL d'une voix). Laissez vide pour qu'ElevenLabs en
   choisisse une par défaut.

Dans **Paramètres → Voix** :

1. Définissez **Méthode TTS** sur **ElevenLabs**
2. Choisissez le **Modèle ElevenLabs** :

    | Modèle | Idéal pour |
    |---|---|
    | `eleven_multilingual_v2` (par défaut) | Usage général, latence/qualité équilibrées |
    | `eleven_v3` | Qualité maximale (à utiliser pour les doublages de production) |
    | `eleven_flash_v2_5` | Latence la plus basse (à utiliser pour la traduction en direct) |

## Ce qu'il alimente

| Page | Utilisez ElevenLabs quand |
|---|---|
| **Générer la voix** | Vous voulez des voix off de qualité premium à partir de fichiers de sous-titres |
| **Doublage** | Vous voulez une piste de doublage de haute qualité sur une vidéo traduite |
| **Traduction en direct** | Vous voulez la lecture parlée des sous-titres traduits en temps réel |

## Clonage de voix

ElevenLabs prend en charge le clonage de voix personnalisé (plan
payant). Une fois que vous avez cloné une voix sur le site
ElevenLabs, collez son ID de voix dans **Paramètres → Service → ID
de voix** et le pipeline de doublage / génération vocale l'utilisera.

## Avertissements

!!! warning "Vérification pre-flight"
    Les pages Voix / Doublage vérifient que votre clé API ElevenLabs
    est définie *avant* de démarrer le travail. Si elle manque, vous
    obtiendrez une boîte de dialogue conviviale vous renvoyant aux
    Paramètres, pas une tâche à moitié exécutée.

!!! tip "Le mode Live retombe automatiquement"
    Sur la page **Traduction en direct**, si vous avez sélectionné
    ElevenLabs mais n'avez pas configuré de clé, l'app retombe sur
    **Edge TTS** (gratuit) et annonce le repli dans le label de statut
    pour que vous puissiez le corriger plus tard.

!!! info "FFmpeg toujours requis"
    ElevenLabs renvoie des octets audio ; l'app utilise toujours
    FFmpeg pour convertir entre formats et combiner des clips minutés
    en un fichier. Voir [Configuration FFmpeg](ffmpeg.md).

## Erreurs courantes

| Erreur | Cause probable |
|---|---|
| `AUTH_ERROR` | Clé API erronée / expirée. Recollez dans Paramètres → Service. |
| `QUOTA_ERROR` | Limite de caractères du palier gratuit atteinte, ou plan payant épuisé. |
| `MODEL_NOT_FOUND` | Le modèle ElevenLabs sélectionné n'est plus disponible ; choisissez-en un autre dans Paramètres → Voix. |
