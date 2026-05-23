---
description: AI Translate의 번역 기능을 Model Context Protocol(MCP) 도구로 제공하여, Claude Desktop, Claude Code 및 기타 MCP 클라이언트에서 텍스트, 파일, 오디오 번역을 수행할 수 있도록 합니다.
---

# MCP 서버 (`ait-mcp`)

번역 파이프라인을 **Model Context Protocol** 도구로 제공하여 Claude Desktop이나 Claude Code 같은 AI 에이전트가 직접 실행할 수 있게 합니다. 이제 텍스트를 복사해서 붙여넣는 대신, 에이전트에게 "이 PDF 파일을 프랑스어로 번역해 줘"라고 지시하기만 하면 됩니다.

## 제공되는 도구

총 9개의 도구가 제공됩니다:

| 도구 | 목적 |
|---|---|
| `translate_text` | 문자열 목록 일괄 번역 |
| `translate_document` | 파일 번역 작업 대기열 추가 (작업 ID 반환) |
| `get_task_status` | 진행 상태 폴링(Polling) |
| `cancel_task` | 진행 중인 작업 안전 취소 |
| `extract_image_text` | 이미지 내 텍스트 추출 (OCR / LLM 비전) |
| `transcribe_audio` | 오디오 자막 생성 (음성 → SRT) |
| `synthesize_speech` | 음성 합성 (텍스트 → MP3 / WAV) |
| `query_glossary` | 용어집 데이터 조회 |
| `list_languages` | 지원되는 전체 언어 목록 조회 |

## 서버 실행 방법

```bash
ait-mcp                       # stdio 전송 방식 (데스크톱 에이전트의 기본값)
ait-mcp --transport sse       # 웹 클라이언트용 Server-Sent Events 방식
ait-mcp --transport sse --port 9000
```

`stdio`는 SSE 방식을 명시적으로 지정하지 않은 대부분의 MCP 클라이언트가 기본적으로 사용하는 통신 방식입니다.

## Claude Desktop에 추가하기

1. Claude Desktop 열기 → **Settings → Developer → Edit Config**
2. `mcpServers` 아래에 다음 항목을 추가합니다:

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    `/absolute/path/to/ai-translate` 부분을 실제 클론(Clone)한 저장소 경로로 변경하세요.

3. Claude Desktop을 완전히 종료하고 다시 실행합니다. 이제 Claude Desktop의 망치(도구) 아이콘을 누르면 "ai-translate"와 함께 9개의 도구가 표시됩니다. 다음과 같이 입력해 보세요:

    > "이 PDF (`/home/me/report.pdf`)를 프랑스어로 번역해 — 출력 파일은 원본 옆에 저장해 줘."

## Claude Code에 추가하기

`~/.config/claude-code/mcp_servers.json` 파일을 수정하거나 (Claude Code 내부에서 `claude mcp add` 명령 사용):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Claude Code를 다시 시작하면 위와 동일한 9개 도구를 호출할 수 있습니다.

## 다른 MCP 클라이언트에 추가하기

모든 MCP 호환 클라이언트는 비슷한 형태의 설정 값을 가집니다:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — `stdio` (기본값)

HTTP / SSE 기반 클라이언트의 경우, 서버를 `ait-mcp --transport sse --port 9000` 명령어로 먼저 실행한 뒤 클라이언트가 `http://localhost:9000` 주소를 바라보도록 설정하세요.

## 오류 처리 규약 (Contract)

모든 도구는 오류가 발생했을 때 동일한 형태의 메시지를 반환하도록 설계되어, 에이전트가 실패 상황을 일관되게 처리할 수 있습니다:

| 잘못된 입력 상황 | 도구 응답 (오류 메시지) |
|---|---|
| 알 수 없는 언어 | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM 환경 미구성 | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| 지원되지 않는 파일 형식 | 지원되는 확장자를 나열하는 `ValueError` |
| 형식이 틀린 `model="..."` (`:` 기호 누락) | 기본 모델을 암묵적으로 쓰는 대신 `ValueError` 반환 |
| `cancel_task`에서 알 수 없는 작업 ID | `unknown` 상태가 담긴 배열 반환 — (오류 발생시키지 않음) |
| `transcribe_audio`에서 FFmpeg 누락 | `RuntimeError: FFmpeg is required…` (엔진의 원시 `FFMPEG_NOT_FOUND` 태그 대신 사람이 읽기 편하게 가공) |

따라서 도구를 호출하는 에이전트는 이러한 오류 처리 규약(Contract)을 신뢰하고 견고한 호출 로직을 작성할 수 있습니다.

## 동시성 (Concurrency)

`translate_document`는 데몬 스레드에서 백그라운드로 파이프라인을 실행합니다. 각 배치 작업은 개별적인 취소 이벤트를 관리하므로, 하나의 배치 작업을 취소하더라도 다른 작업에 영향을 주지 않습니다. MCP 서버는 실행 중인 파이프라인을 내부 로컬 맵에서 추적하며, 작업이 끝나면 자동으로 맵에서 정리(Clean-up)합니다.

## 활용 사례

- **"이 코드베이스의 문서를 베트남어로 번역해 줘"** — 에이전트가 `docs` 폴더를 대상으로 `translate_document` 도구를 호출하고, `get_task_status`로 각 작업의 완료 여부를 폴링합니다.
- **"어떤 언어들을 지원해?"** — 에이전트가 `list_languages`를 호출하여 응답을 읽어옵니다.
- **"이 일본어 영수증 이미지를 번역해 줘"** — 에이전트가 영수증 사진 파일 경로를 `extract_image_text`에 넘겨 텍스트를 추출한 다음, 결과 값을 다시 `translate_text`에 넘겨 번역합니다.
- **"이 Zoom 녹화 영상의 베트남어 자막을 만들어 줘"** — 에이전트가 먼저 `transcribe_audio`를 호출해 원본 언어 SRT 자막을 추출합니다. 이후 각 자막 라인(Cue)마다 `translate_text`를 호출해 베트남어로 번역한 뒤 새로운 SRT 자막으로 재조립합니다.

!!! note "비디오 더빙은 단일 MCP 도구로 제공되지 않습니다"
    전체 파이프라인(STT → 번역 → TTS → 원본 영상에 오디오 병합)을 수행하는 데스크톱 앱의 **비디오 더빙** 기능은 현재 GUI에서만 바로 사용할 수 있습니다. MCP 클라이언트는 `transcribe_audio` + `translate_text` + `synthesize_speech` 도구를 순차적으로 호출하여 동일한 결과를 구성할 수는 있지만, 타이밍 정보(Mux)를 동기화하여 영상을 합치는 FFmpeg 병합 작업은 에이전트나 외부 스크립트가 직접 처리해야 합니다.

## 팁 (Tips)

!!! tip "한 번의 설정으로 모든 에이전트 호환"
    MCP 서버는 API 키 및 환경 설정을 데스크톱 앱, CLI와 공유합니다. GUI 화면에서 LLM, OCR, TTS 설정을 한 번만 마치면, `ait-mcp` 서버와 연동된 모든 AI 에이전트가 해당 설정을 그대로 상속받습니다.

!!! tip "콜드 스타트 엔드포인트 캐시 최적화"
    각 `(엔드포인트, 모델)` 쌍에 대한 API 방식(Chat vs Responses) 및 작동하는 페이로드(Payload) 구성이 OS 캐시 디렉터리의 `llm_endpoint_cache.json`에 영구적으로 저장됩니다. (경로: Linux `~/.cache/ai-translate/`, macOS `~/Library/Caches/ai-translate/`, Windows `%LOCALAPPDATA%\ai-translate\cache\`)
    따라서 새로운 `ait-mcp` 프로세스가 실행되더라도, 이미 한 번 검증을 마친 호출에 대해서는 불필요한 자동 감지 검사 과정(Round Trip)을 건너뛰어 호출 속도가 크게 향상됩니다. 해당 캐시는 멀티 프로세스 및 멀티 스레드 환경에서도 안전하게 동작합니다(원자적 이름 변경(Atomic Rename) 기반의 Read-Merge-Write 방식 사용).

!!! tip "도구(요청)별 맞춤형 모델 선택"
    `translate_text`와 `translate_document` 도구는 선택적 파라미터로 `model`을 받습니다. 이를 통해 에이전트는 사용자가 GUI 설정을 일일이 바꿀 필요 없이, 즉각적인 응답이 필요할 땐 가벼운 모델을, 최종 산출물이 필요할 땐 강력하고 무거운 모델을 동적으로 선택해 호출할 수 있습니다.

!!! warning "오래 걸리는 파이프라인 작업 주의"
    `translate_document`는 파이프라인 실행 완료를 기다리지 않고 작업 ID를 즉시 반환합니다. 에이전트는 각 작업이 `Done` 또는 `Failed` 상태에 도달할 때까지 `get_task_status` 도구를 반복 호출(Polling)해야 합니다. MCP 클라이언트의 타임아웃 오류를 방지하기 위해 도구 호출 내부에서 작업이 끝날 때까지 동기적으로 대기(Wait)해서는 안 됩니다.
