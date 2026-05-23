---
description: Windows, macOS 또는 Linux에서 사전 빌드된 바이너리 또는 소스로부터 AI Translate를 설치 — Python, FFmpeg 및 선택적 LibreOffice 설정 포함.
---

# 설치

## 필요한 것

- **Python 3.12 이상** ([다운로드](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — 빠른 Python 패키지 매니저. 설치:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **LLM API 키** — 다음 중 하나:
    - [Google Gemini](https://aistudio.google.com/apikey) (무료 티어 사용 가능 — 시작용으로 추천)
    - 모든 OpenAI 호환 엔드포인트 (OpenAI, 프록시를 통한 Anthropic, 로컬 Ollama / LM Studio 등)

## 선택적이지만 더 많은 기능을 잠금 해제

| 도구 | 사용처 | 필요한 시점 |
|---|---|---|
| **FFmpeg** ([다운로드](https://ffmpeg.org/download.html)) | 자막, 음성, 더빙, 라이브 | 모든 오디오/비디오 워크플로 |
| **LibreOffice** ([다운로드](https://www.libreoffice.org/download/)) | Linux/macOS의 Office 형식 | 레거시 `.doc` / `.xls` / `.ppt` 번역, 또는 MS Office가 설치되지 않았을 때 모든 Office 파일 |
| **Tesseract** ([설치 가이드](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | OCR 엔진 (기본) | 텍스트 추출 페이지, 스캔된 PDF 번역, 임베디드 이미지 번역 |
| **MS Office** + **pywin32** | Windows의 Office | Windows에서 최고 충실도 Office 번역 |

이들 중 어느 것도 없이 AI Translate를 설치할 수 있습니다 — 필요한
기능은 실패하기 전에 알려줍니다.

## 설정

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

이는 데스크톱 앱, CLI, MCP 서버를 실행하는 데 필요한 모든 것을 설치합니다.

## 실행

=== "데스크톱 앱"
    ```bash
    uv run python -m src.main
    ```

=== "명령줄"
    ```bash
    uv run ait --version
    ```

=== "MCP 서버"
    ```bash
    uv run ait-mcp           # stdio 전송 (Claude Desktop / Code용)
    ```

## API 키 추가

데스크톱 앱을 처음 열 때:

1. 사이드바에서 **설정** 클릭
2. **LLM** 탭 열기
3. **Google Gemini API 키**를 붙여넣기 (또는 OpenAI 호환 사용자
   지정 제공자 구성). 엔터프라이즈 사용자는 Gemini를
   **Vertex AI 모드**로 전환할 수 있습니다 — GCP 프로젝트와
   리전을 가리키고, 선택적으로 service-account JSON 경로 제공;
   세부 사항은 [LLM 제공자](../setup/llm-providers.md) 참조.
4. 기본 모델 선택 — 모든 현재 Flash 변형 (예: `gemini-2.5-flash`)이
   견고한 무료 시작점입니다. Pro 변형은 더 높은 비용으로 더 나은
   품질을 제공.
5. 설정 닫기 — 완료

키는 디스크의 일반 텍스트가 아닌 **OS 키체인**(macOS Keychain,
Windows Credential Manager, Linux의 GNOME / KDE Secret Service)에
저장됩니다.

!!! tip "헤드리스 / 서버 설치"
    키를 설정하기 위해 데스크톱 앱을 실행할 수 없는 경우, keychain
    CLI 명령에 대해서는 [LLM 제공자](../setup/llm-providers.md)를 참조.

## 다음: 시도해보세요

[5분 첫 번역 →](first-translation.md){ .md-button .md-button--primary }
