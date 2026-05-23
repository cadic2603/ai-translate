---
description: "번역을 위한 LLM 공급자 구성: Google Gemini(권장), OpenAI 호환 엔드포인트 또는 API 키가 있는 모든 사용자 정의 공급자."
---

# LLM 공급자

번역 파이프라인은 실제 번역을 위해 Large Language Model을 호출합니다.
하나 또는 여러 개를 구성할 수 있습니다; 기능별 모델 선택기는 각
페이지가 다른 것을 사용할 수 있도록 합니다.

## Google Gemini(처음 설정에 권장) {: #google-gemini-recommended-for-first-time-setup }

무료 티어가 관대하고 대부분의 개인 사용에 충분히 좋습니다.

1. <https://aistudio.google.com/apikey>로 이동
2. **Create API key** 클릭(Google 계정으로 로그인)
3. 키 복사(`AIza...`처럼 보임)
4. 데스크톱 앱에서: **설정 → LLM → Gemini API 키** → 붙여넣기 →
   **저장**
5. **기본 Gemini 모델** 드롭다운에서 기본 모델 선택. Google의
   라인업은 다음과 같이 보이는 경향이 있습니다:

    - **Flash** 변형(예: `gemini-2.5-flash`) — 빠름, 관대한 무료
      티어, 좋은 품질. 권장 시작점.
    - **Pro** 변형 — 느림, 더 높은 품질, 더 비쌈.
    - **Flash-lite** — 가장 빠름, 가장 저렴, 더 낮은 품질.

    사용 가능한 정확한 모델 이름은 Google이 귀하의 계정에 배포한
    것에 따라 다릅니다; 균형 잡힌 기본값을 위해 이름에 `flash`를
    포함하는 것을 선택하세요.

완료. 키는 OS 키체인에 저장되며 일반 텍스트가 아닙니다.

### Vertex AI 모드(엔터프라이즈)

Gemini 구성 블록 내에서 라디오 쌍이 **Developer API**에서 **Vertex
AI**로 전환할 수 있게 해줍니다 — 동일한 Gemini 모델, GCP 계정을
통해 청구, 조직 수준 제어(VPC-SC, 감사 로그, 지역 데이터 거주).

1. **설정 → LLM**에서 Gemini 라디오를 **Developer API**에서
   **Vertex AI**로 전환
2. 채우기:
    - **Project** — GCP 프로젝트 ID
    - **Location** — Vertex 지역(기본값 `us-central1`)
    - **Credentials path** *(선택사항)* — 서비스 계정 JSON 키 파일
      에 대한 경로. Application Default Credentials를 사용하려면
      비워두세요(`gcloud auth application-default login`)
3. **저장**. 프로젝트가 설정되면 모델 드롭다운이 Vertex에서 다시
   채워집니다.

OAuth 새로 고침은 `google-genai`에 의해 자동으로 처리됩니다. 서비스
계정 JSON 경로는 의도적으로 일반 텍스트로 저장됩니다(*경로*는
비밀이 아닙니다 — 파일의 내용은 그러하며, Google의 문서화된 모범
사례가 그것들을 보관하는 디스크에 남아 있습니다).

## OpenAI / OpenAI 호환

OpenAI 호환 REST API를 노출하는 모든 것이 작동합니다 — OpenAI 자체,
[LiteLLM 프록시](https://docs.litellm.ai)를 통한 Anthropic, 로컬
Ollama, LM Studio, vLLM, Together.ai, Groq 등.

**설정 → LLM**에서:

1. **Add Custom Provider** 클릭
2. 채우기:
    - **Name** — "OpenAI" / "Local Ollama" / "Anthropic"과 같은
      레이블
    - **API endpoint** — 기본 URL(예: `https://api.openai.com/v1`
      또는 Ollama용 `http://localhost:11434/v1`)
    - **API key** — 인증되지 않은 로컬 엔드포인트의 경우 비워두기
    - **Models** — 쉼표로 구분된 목록(예: `gpt-4o-mini, gpt-4o,
      gpt-3.5-turbo`)
3. **Save** 클릭.

사용자 정의 공급자는 OS 키체인에 JSON blob으로 저장됩니다(API 키
포함).

## 기본 모델 전환

**설정 → LLM**의 **기본 Gemini 모델** 드롭다운은 자체 선택기가 없는
모든 기능 페이지에서 사용되는 폴백을 설정합니다.

자체 모델 선택기가 있는 페이지:

- **텍스트 번역** — `텍스트 번역 설정 탭 → 기본 모델`
- **문서 번역** — 작업별로 선택; 기본값으로 폴백
- **자막 / 음성 / 더빙 / Live / 텍스트 추출** — 각각 설정 탭에 자체
  기능별 기본값이 있습니다

이를 통해 혼합 및 매칭이 가능합니다: live용 무료 Flash, 큰 문서용
Pro, 민감한 데이터용 로컬 Ollama.

## 키가 저장되는 위치

| OS | 저장소 |
|---|---|
| **macOS** | 키체인(로그인 키체인) |
| **Windows** | 자격 증명 관리자 |
| **Linux (GNOME)** | Secret Service(gnome-keyring / KWallet) |
| **Linux(데몬 없음)** | `~/.config/ai-translate/settings.ini`의 일반 텍스트 INI로 폴백 |

폴백 INI 값은 키체인이 사용 가능해질 때마다 첫 번째 읽기에서
키체인으로 마이그레이션됩니다 — 수동 단계 없음.

## 헤드리스 / 서버 설치

데스크톱 세션 없이도 Python의 `keyring` CLI(`uv sync` 후)를 통해
키를 설정할 수 있습니다:

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# 사용자 정의 공급자(JSON blob 붙여넣기 — 스키마는 설정 UI 참조)
uv run keyring set ai-translate llm/custom_providers
```

또는 동일한 INI 키를 `settings.ini`에 직접 설정 — 앱은 첫 번째
읽기에서 그것들을 키체인으로 마이그레이션합니다. 파일은 다음
위치에 있습니다:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## 설정 테스트

가장 빠른 정상 작동 확인:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Korean --quiet
cat /tmp/x_translated__ko.txt
```

"안녕하세요 세상."이 보이면 — 완료된 것입니다.

## 일반적인 오류

| 오류 | 가능한 원인 |
|---|---|
| `AUTH_ERROR` | 잘못된 / 만료된 API 키. 설정에서 다시 붙여넣기. |
| `QUOTA_ERROR` | 무료 티어 일일 요청 초과. 대기하거나 비용 지불. |
| `MODEL_NOT_FOUND` | 사용자 정의 공급자의 `models` 목록에 요청된 모델이 포함되지 않음. |
| `VISION_NOT_SUPPORTED` | 선택한 모델은 이미지 입력을 할 수 없습니다. `flash` / `pro` / `vision` 변형을 사용하세요. |

자세한 내용은 [문제 해결](../troubleshooting.md) 참조.
