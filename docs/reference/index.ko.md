---
description: AI Translate Python API에 대한 개발자 참조 — docstring에서 자동 생성됨; core, utils, constants, CLI, MCP 서버 모듈을 다룸.
---

# 개발자 참조

최종 사용자는 이 섹션이 아니라 [기능 페이지](../index.md#headline-features)나
[설정 가이드](../setup/llm-providers.md)를 원할 것입니다.

이것은 **자동 생성된 API 참조**입니다 — `src/` 내 각 Python 모듈마다
한 페이지씩, 프로젝트의 docstring으로부터 렌더링됩니다. 자체 Python
코드에서 기반 함수를 호출하려는 기여자와 통합 개발자를 위한 것입니다.

## 빌드 대상

`uv run mkdocs build`는 빌드할 때마다 이 페이지들을 `src/`에서 재생성
하므로, 항상 현재 코드 상태를 반영합니다.

## 어디서 시작할까

헤드리스 번역 진입점은
[`run_translation_pipeline`](api/core/translator.md)입니다 — 데스크톱
앱의 모든 기능, CLI, MCP 서버가 결국 이를 거칩니다. 이 함수와 옆의
`TranslationConfig`를 읽는 것이 파이프라인을 이해하는 가장 빠른 방법입니다.

## 구성

- **[Constants](api/constants/index.md)** — 설정 키, 오류 코드, 언어 테이블, i18n / 테마 엔진.
- **[Core](api/core/index.md)** — 번역 파이프라인, LLM 디스패치, 포맷별 프로세서, OCR / STT / TTS 엔진, 체크포인트, 데이터베이스.
- **[Utils](api/utils/index.md)** — 횡단적 헬퍼.
- **[CLI](api/cli.md)** — `ait` 진입점.
- **[MCP Server](api/mcp_server.md)** — `ait-mcp` 진입점.
