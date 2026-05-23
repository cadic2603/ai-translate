---
description: AI Translate는 45개 이상의 언어로 문서, PDF, 자막, 오디오, 실시간 음성을 위한 무료 크로스 플랫폼 데스크톱 번역기입니다.
---

# AI Translate

**45개 언어**를 처리하고 일반 텍스트를 훨씬 뛰어넘는 무료 크로스 플랫폼 데스크톱 번역기 — 단일 LLM 기반 파이프라인을 통해 문서, 오디오, 비디오, 실시간 음성, 화면 캡처 등을 모두 번역할 수 있습니다.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **데스크톱 앱**

    ---

    파일을 끌어다 놓고 대상 언어를 선택하기만 하면 번역된 결과물을 받을 수 있습니다. 드래그 앤 드롭, 히스토리 관리, 용어집 기능이 모두 포함되어 있습니다.

    [:octicons-arrow-right-24: 5분 워크스루](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **명령줄 (CLI)**

    ---

    `ait report.docx --target French` — 동일한 파이프라인을 사용하며 스크립트 작성 및 헤드리스 환경을 지원합니다. CI, 배치 작업, 서버 환경에 유용합니다.

    [:octicons-arrow-right-24: CLI 가이드](cli.md)

-   :material-robot-outline:{ .lg .middle } **AI 에이전트 (MCP)**

    ---

    번역 기능을 Model Context Protocol 도구로 제공하여 Claude Desktop, Claude Code 및 기타 MCP 클라이언트에서 직접 호출할 수 있습니다.

    [:octicons-arrow-right-24: MCP 설정](mcp.md)

</div>

## 지원하는 형식

| 종류 | 형식 |
|---|---|
| **Office 문서** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, 그리고 레거시 `.doc` / `.xls` / `.ppt` |
| **PDF** | 레이아웃을 보존하는 추출-오버레이(extract-overlay) 방식의 번역, 북마크/양식(폼)/링크 번역, 스캔된 문서를 위한 OCR 대체(fallback) 기능 |
| **텍스트 & 웹** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **자막** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **로컬라이제이션** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **이미지** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR 또는 LLM 비전 활용) |
| **오디오** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **비디오** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (전체 더빙 파이프라인 지원) |

## 주요 기능 {: #headline-features }

- **[텍스트 번역](features/translate-text.md)** — 언어 자동 감지, 즉각적인 인플레이스 수정, TTS 재생 기능을 지원하는 실시간 LLM 번역. 우에서 좌로 읽는(RTL) 언어(아랍어, 히브리어, 페르시아어)도 자연스럽게 렌더링됩니다.
- **[문서 번역](features/translate-document.md)** — 파일을 끌어다 놓고 항목별 진행 상태를 확인하며 번역된 파일을 원본과 나란히 받을 수 있습니다. RTL 언어로 번역 시 적절한 양방향(bidi) 마크업이 적용되며, `Ctrl+P` / `Ctrl+G` 키로 작업 대기열을 일시 정지하거나 다시 시작할 수 있습니다.
- **[자막 생성 (STT)](features/generate-subtitle.md)** — 오디오 및 비디오를 SRT / VTT / ASS / SSA 자막 파일로 변환(전사)합니다.
- **[음성 생성 (TTS)](features/generate-voice.md)** — 자막의 시간 정보에 맞춰 MP3 / WAV 음성으로 합성합니다.
- **[비디오 더빙](features/dubbing.md)** — STT → 번역 → TTS의 전체 과정을 거쳐 원본 비디오에 더빙 음성을 믹싱합니다.
- **[실시간 번역](features/live-translation.md)** — 마이크 또는 시스템 오디오를 인식해 실시간으로 자막을 화면에 겹쳐 보여줍니다(오버레이).
- **[텍스트 추출](features/extract-text.md)** — OCR 또는 LLM 비전을 사용해 이미지에서 텍스트를 추출하여 `.txt` / `.docx` 파일로 저장합니다.
- **[용어집](features/glossary.md)** — 모든 번역 과정에서 일관된 용어가 사용되도록 적용합니다.

!!! tip "Gemini용 Vertex AI 모드"
    엔터프라이즈 사용자는 **설정 → LLM** 메뉴에서 Gemini API 호출 방식을 Developer API에서 **Vertex AI**로 전환할 수 있습니다. GCP 프로젝트와 리전을 지정하고, 필요에 따라 서비스 계정(service-account) JSON 경로를 추가로 제공할 수 있습니다.
    [LLM 제공자](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup) 섹션을 참조하세요.

!!! tip "처음 오셨나요?"
    먼저 [설치](getting-started/installation.md) 가이드를 확인한 후 [5분 첫 번역 워크스루](getting-started/first-translation.md)를 따라해 보세요. 프로젝트를 클론한 뒤 10분 안에 번역된 문서를 얻을 수 있습니다.
