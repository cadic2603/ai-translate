---
description: Configurez Soniox pour la transcription vocale en temps réel sur la page Live d'AI Translate — prend en charge la diarisation des locuteurs, les termes de glossaire et la traduction en direct.
---

# Soniox (STT)

Transcription vocale en temps réel via l'API WebSocket de Soniox.
Utilisé par les pages **[Sous-titre](../features/generate-subtitle.md)** et
**[Traduction en direct](../features/live-translation.md)** lorsque vous
choisissez Soniox comme méthode STT.

## Pourquoi Soniox

- **Temps réel** — les tokens arrivent pendant que le locuteur parle.
- **Diarisation des locuteurs** — étiquettes de locuteur par token
  (par ex. _Locuteur 1 : Bonjour…_).
- **Traduction en flux** — Soniox peut traduire pendant la
  transcription, économisant un aller-retour LLM supplémentaire.
- **Multi-langue** — détecte automatiquement la langue source même
  en plein flux.

## Obtenir une clé API

1. Inscrivez-vous sur <https://console.soniox.com>
2. Ouvrez **API keys** → **Create new API key**
3. Copiez-la (ressemble à `Bearer ...` ; copiez juste le token sans
   le préfixe `Bearer `).

La tarification est facturée par minute d'audio (~0,005 $ / minute au
moment de l'écriture) — voir <https://soniox.com/pricing>.

## Configurer dans l'app

Dans **Paramètres → Service** :

1. Collez la clé dans **Clé API Soniox** → **Enregistrer**

Dans **Paramètres → Live** *(pour la traduction en direct)* ou
**Paramètres → Sous-titre** *(pour la génération de sous-titres)* :

1. Définissez **Méthode STT** sur **Soniox**

## Ce qu'il alimente

| Page | Utilisez Soniox quand |
|---|---|
| **Sous-titre** | Enregistrements multi-locuteurs (interviews, panels, réunions) où vous voulez les étiquettes de locuteurs dans le SRT |
| **Traduction en direct** | Sous-titrage de réunions en temps réel, surtout avec plusieurs locuteurs |

## Termes de glossaire

Le WebSocket Soniox accepte un glossaire de termes pour biaiser la
reconnaissance. L'app transmet automatiquement vos entrées de
glossaire actives — les noms de marques / noms propres / jargon sont
reconnus plus fiablement.

## Avertissements

!!! warning "En ligne uniquement"
    Soniox est uniquement cloud ; si votre audio est sensible
    (médical, juridique), utilisez Whisper (local) à la place.

!!! info "Reconnexion"
    Le WebSocket se reconnecte automatiquement sur les échecs
    transitoires avec un backoff exponentiel. Les longues sessions
    restent connectées à travers de brèves coupures réseau.

## Erreurs courantes

| Erreur | Cause probable |
|---|---|
| `AUTH_ERROR` | Clé API erronée / expirée. Recollez dans Paramètres → Service. |
| `QUOTA_ERROR` | Limite de plan dépassée. |
| `CONNECTION_ERROR` | Réseau bloqué / pare-feu. Réessayez depuis un autre réseau. |
