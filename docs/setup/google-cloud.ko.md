---
description: Vision OCR, Speech-to-Text 및 Text-to-Speech를 위해 AI Translate에 Google Cloud 연결 — API 키 설정 및 관련 서비스 활성화.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

단일 Google Cloud API 키가 세 가지 선택적 백엔드를 구동합니다:

- **Vision OCR** — 유료 OCR 엔진(월 1,000회 무료)
- **Speech-to-Text v1** — 유료 STT(월 60분 무료)
- **Text-to-Speech v1** — 유료 TTS(WaveNet의 경우 월 1M 문자 무료)

실제로 사용하는 API만 활성화하면 됩니다.

## API 키 받기

1. [Google Cloud 프로젝트 생성](https://console.cloud.google.com/projectcreate)
2. API 라이브러리 열기: <https://console.cloud.google.com/apis/library>
3. 다음 중 하나 활성화:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [API 키 생성](https://console.cloud.google.com/apis/credentials):
   **+ Create Credentials → API key** 클릭
5. 키 복사(`AIza...`처럼 보임).

!!! tip "키 제한"
    API 키 세부 정보 페이지의 **API restrictions** 아래에서, 활성화한
    API로만 키를 제한합니다. 그러면 유출된 키가 의도하지 않은
    서비스에서 청구서를 쌓을 수 없습니다.

## 앱에서 구성

**설정 → 서비스**에서:

1. **Google Cloud API 키**에 붙여넣기 → **저장**

이 단일 키는 이제 세 가지 Google 서비스 모두에 사용 가능합니다.

## 각 서비스 활성화

### Vision OCR

**설정 → OCR → OCR 방법 = Google Cloud OCR**에서.

그게 다입니다 — 서비스에서 동일한 키를 사용합니다.

### Speech-to-Text

**설정 → 자막 → STT 방법 = Google Cloud**(자막 / 음성 페이지용) 또는
**설정 → Live → STT 방법 = Google Cloud**(Live 페이지용)에서.

**설정 → 자막 → Google STT 모델**에서 인식 모델을 선택:

| 모델 | 최적 |
|---|---|
| `latest_long`(기본) | 긴 형식 오디오(인터뷰, 강의) |
| `latest_short` | 음성 명령, 짧은 구절 |
| `phone_call` | 전화 오디오(8 kHz) |
| `medical_dictation` / `medical_conversation` | 의료 분야 오디오 |

### Text-to-Speech

**설정 → 음성 → TTS 방법 = Google Cloud TTS**에서.

기본적으로 서버는 언어와 성별을 기반으로 음성을 선택합니다 — 대부분의
사용자에게 필요한 전부입니다. 특정 Google 음성(예:
`en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`)을 고정하는 것은 엔진
에서 지원되지만 아직 설정 필드로 노출되지 않았습니다;
`voice/google_tts_voice_name`을 `settings.ini`에서 직접 편집하여
설정할 수 있습니다. 음성 ID는
<https://cloud.google.com/text-to-speech/docs/voices>에 나열되어
있습니다.

## 일반적인 오류

| 오류 | 가능한 원인 |
|---|---|
| `AUTH_ERROR` | 잘못된 / 만료된 키. 설정 → 서비스에서 다시 붙여넣기. |
| `API not enabled` | 이 Cloud 프로젝트에서 특정 API(Vision / Speech / TTS)를 활성화하지 않았습니다. |
| `QUOTA_ERROR` | 이 API의 무료 티어 한도 도달. 대기하거나 청구 업그레이드. |
| `INVALID_ARGUMENT_ERROR` | 선택한 언어에 음성 이름이 존재하지 않습니다. |

## 비용 보호

!!! warning
    세 가지 Google API 모두 후불입니다 — 무료 티어를 초과하면 중지
    없이 청구가 시작됩니다. 대용량 작업을 수행하기 전에 Cloud 프로
    젝트에 [예산 알림](https://console.cloud.google.com/billing/budgets)
    을 설정하세요.
