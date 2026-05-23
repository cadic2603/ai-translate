---
description: 고품질 신경망 TTS를 위해 AI Translate에 ElevenLabs 연결 — 사실적이고 표현력이 풍부한 음성으로 30개 이상의 언어로 보이스오버 생성.
---

# ElevenLabs (TTS)

프리미엄 신경망 텍스트 음성 변환. TTS 방법으로 ElevenLabs를 선택할
때 **[음성 생성](../features/generate-voice.md)**,
**[더빙](../features/dubbing.md)**, **[라이브 번역](../features/live-translation.md)**
페이지에서 사용.

## API 키 받기

1. <https://elevenlabs.io>에서 가입
2. <https://elevenlabs.io/app/settings/api-keys> 열기
3. **+ Create New Key** 클릭, 이름 지정(예: "ai-translate"), 키
   복사(`sk_...`처럼 보임)

무료 티어는 월 ~10,000자를 제공하며, 테스트에 충분합니다. 프로덕션
사용은 월 약 $5부터 시작됩니다.

## 앱에서 구성

**설정 → 서비스**에서:

1. 키를 **ElevenLabs API 키**에 붙여넣기 → **저장**
2. 선호하는 **음성 ID**를 **음성 ID**에 입력
   (<https://elevenlabs.io/app/voice-lab>에서 ID 찾기; 음성의 URL
   에서 ID 복사). ElevenLabs가 기본값을 선택하도록 비워두세요.

**설정 → 음성**에서:

1. **TTS 방법**을 **ElevenLabs**로 설정
2. **ElevenLabs 모델** 선택:

    | 모델 | 최적 |
    |---|---|
    | `eleven_multilingual_v2`(기본) | 일반 사용, 균형 잡힌 지연 시간/품질 |
    | `eleven_v3` | 최고 품질(프로덕션 더빙에 사용) |
    | `eleven_flash_v2_5` | 가장 낮은 지연 시간(라이브 번역에 사용) |

## 무엇을 강화하는지

| 페이지 | 다음 경우 ElevenLabs 사용 |
|---|---|
| **음성 생성** | 자막 파일에서 프리미엄 품질의 보이스오버를 원할 때 |
| **더빙** | 번역된 비디오에 고품질 더빙 트랙을 원할 때 |
| **라이브 번역** | 번역된 자막의 실시간 음성 재생을 원할 때 |

## 음성 클로닝

ElevenLabs는 사용자 정의 음성 클로닝(유료 플랜)을 지원합니다.
ElevenLabs 사이트에서 음성을 복제한 후, 그 음성 ID를 **설정 →
서비스 → 음성 ID**에 붙여넣으면 더빙 / 음성 생성 파이프라인이 그것을
사용합니다.

## 주의사항

!!! warning "사전 검사"
    음성 / 더빙 페이지는 작업을 시작하기 *전에* ElevenLabs API 키가
    설정되어 있는지 확인합니다. 누락된 경우, 반쯤 실행된 작업 대신
    설정을 가리키는 친근한 대화상자를 받게 됩니다.

!!! tip "Live 모드는 자동으로 폴백"
    **라이브 번역** 페이지에서, ElevenLabs를 선택했지만 키를 구성
    하지 않은 경우, 앱은 자동으로 **Edge TTS**(무료)로 폴백하고
    상태 레이블에서 폴백을 알려 편할 때 수정할 수 있도록 합니다.

!!! info "FFmpeg는 여전히 필요"
    ElevenLabs는 오디오 바이트를 반환합니다; 앱은 여전히 형식 간
    변환과 타이밍이 있는 클립을 하나의 파일로 결합하는 데 FFmpeg를
    사용합니다. [FFmpeg 설정](ffmpeg.md) 참조.

## 일반적인 오류

| 오류 | 가능한 원인 |
|---|---|
| `AUTH_ERROR` | 잘못된 / 만료된 API 키. 설정 → 서비스에서 다시 붙여넣기. |
| `QUOTA_ERROR` | 무료 티어 문자 한도 도달, 또는 유료 플랜 소진. |
| `MODEL_NOT_FOUND` | 선택한 ElevenLabs 모델을 더 이상 사용할 수 없음; 설정 → 음성에서 다른 것 선택. |
