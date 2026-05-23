---
description: ait 명령줄 인터페이스를 사용하여 헤드리스로 파일 번역 — 스크립트 또는 CI 작업에서 PDF, Office 문서, 자막 및 45개 이상의 언어 지원.
---

# 명령줄 인터페이스 (`ait`)

디스플레이 없이 헤드리스(headless)로 번역할 수 있습니다. 데스크톱 앱과 동일한 파이프라인을 사용하며 CI, 일괄 처리(batch) 작업, 서버 및 스크립트 워크플로우에 유용합니다.

## 빠른 시작

```bash
ait report.docx --target French
```

출력 파일은 원본 파일과 같은 위치에 `report_translated_<src>_<tgt>.docx` 이름으로 생성됩니다.

## 자주 사용하는 명령어

### 여러 파일 번역

```bash
ait *.pdf --target Japanese
```

Glob 패턴 확장(`*.pdf`)은 유닉스 셸에서 처리됩니다. Windows `cmd.exe`에서는 파일 이름을 명시적으로 나열하거나 PowerShell을 사용하세요:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### 사용자 정의 출력 디렉터리

```bash
ait report.docx --target French --output ./translated/
```

지정한 디렉터리가 없으면 새로 생성합니다. 권한 문제 등으로 생성할 수 없는 경우, 부분 실행 없이 즉시 명확한 오류 메시지와 함께 종료 코드 2를 반환합니다.

### 원본 언어 지정

```bash
ait letter.txt --target German --source "English (US)"
```

원본 언어 지정 시 대소문자를 구분하지 않습니다. 단순하게 "Chinese"라고 입력하면 다음과 같은 힌트 메시지가 출력됩니다:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### 특정 모델 선택

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# 또는 데스크톱 앱의 LLM 탭에 등록된 다른 Provider:model_name을 사용할 수도 있습니다.
```

형식은 반드시 `Provider:model_name`이어야 합니다. 콜론(`:`)이 누락되면 기본 Gemini 모델로 자동 전환되는 대신, 명확한 에러 메시지와 함께 종료 코드 2를 반환합니다.

### Office 옵션 적용

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` 옵션을 사용하려면 OCR 설정이 필요합니다. ([OCR 엔진](setup/ocr-engines.md) 참조)

### 구버전 형식 자동 변환

```bash
ait old-doc.doc --target French --convert-legacy
```

이 파이프라인은 번역 품질(충실도)을 높이기 위해 구버전(`.doc`) 형식을 최신 형식(`.docx`)으로 먼저 변환하여 번역한 다음, 다시 원래 형식으로 되돌립니다. `--convert-odf` 옵션과 `.odt` / `.ods` / `.odp` 포맷도 동일한 방식으로 동작합니다.

### 출력 제어 (조용히 / 자세히)

```bash
ait report.docx --target French --quiet      # 오류 메시지만 출력
ait report.docx --target French --verbose    # 전체 DEBUG 스트림 출력
```

기본 모드에서는 배너와 작업 진행 상태를 콘솔에 출력합니다. 전체 세부 정보(HTTP 본문 덤프, 재시도 로그 등)는 콘솔 출력 수준과 상관없이 운영체제별 앱 로그 디렉터리에 저장됩니다(로그 경로 확인 방법은 [문제 해결 → 로그 위치](troubleshooting.md#where-are-the-logs) 참조).

### 지원 언어 목록 확인

```bash
ait --list-languages
```

지원되는 45개 언어 목록 전체를 출력합니다. 셸 스크립트에서 파이프라인(`|`)으로 전달해 루프를 돌릴 때 유용합니다.

### 버전 확인

```bash
ait --version
# ait 0.1.0
```

## 종료 코드 (Exit Codes)

| 코드 | 의미 |
|---|---|
| `0` | 모든 작업 성공 |
| `2` | 인수 오류 (알 수 없는 언어, 누락된 대상, 잘못된 형식의 모델, 쓸 수 없는 출력 경로, 지원되지 않는 파일 확장자) |
| `3` | LLM 환경 미구성 |
| `4` | 일부 실패 (일부는 성공, 일부는 실패) |
| `5` | 모두 실패 |
| `130` | 중단됨 (`Ctrl+C`) |

## 작업 취소

`Ctrl+C` 한 번 입력: 안전한 취소(Cooperative Cancel). 현재 작업의 체크포인트를 저장하고 파이프라인이 진행 중인 단계를 마친 후 안전하게 종료됩니다.

`Ctrl+C` 두 번 입력: 강제 종료(Strong Interrupt). 주의해서 사용하세요. 작성 중이던 임시 파일이 불완전한 상태로 남을 수 있습니다.

## 전체 옵션(Flag) 참조

```bash
ait --help
```

각 플래그와 기본값을 표시합니다. 동일한 내용을 아래 표에 요약했습니다.

| 플래그 | 기본값 | 설명 |
|---|---|---|
| `--target / -t LANG` | _필수_ | 대상 언어 (대소문자 구분 없음) |
| `--source / -s LANG` | 자동 감지 | 원본 언어 (대소문자 구분 없음) |
| `--output / -o DIR` | 원본 파일 위치 | 디렉터리가 없으면 자동 생성 |
| `--model / -m PROVIDER:MODEL` | 데스크톱 앱 기본값 | 형식 엄격 검사 (`Provider:model`) |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` 지원 |
| `--translate-images` | 사용 안 함 | 구성된 OCR 필요 |
| `--translate-comments` | 사용 안 함 | Office 주석 번역 |
| `--translate-shapes` | 사용 안 함 | Office 도형 / 텍스트 상자 번역 |
| `--translate-notes` | 사용 안 함 | PowerPoint 발표자 노트 번역 |
| `--translate-sheet-names` | 사용 안 함 | Excel 시트 탭(이름) 번역 |
| `--convert-legacy` | 사용 안 함 | `.doc`/`.xls`/`.ppt` → 최신 형식으로 임시 변환 |
| `--convert-odf` | 사용 안 함 | `.odt`/`.ods`/`.odp` → OOXML로 임시 변환 |
| `--keep-history` | 사용 안 함 | 완료 후 데스크톱 앱 히스토리 항목 유지 |
| `--quiet / -q` | 사용 안 함 | 콘솔에 오류 메시지만 출력 |
| `--verbose / -v` | 사용 안 함 | 디버그 수준(DEBUG) 전체 로그 출력 |
| `--list-languages` | — | 45개 언어 목록 출력 후 종료 |
| `--version` | — | 버전 정보 출력 후 종료 |

## 팁 (Tips)

!!! tip "한 번의 설정으로 모든 곳에서 사용"
    CLI는 데스크톱 앱과 API 키 및 환경 설정을 공유합니다. GUI 앱에서 한 번만 설정을 마치면 `ait` 명령어를 통해 바로 자동화할 수 있습니다.

!!! tip "콜드 스타트 엔드포인트 캐시 최적화"
    각 `(엔드포인트, 모델)` 쌍에 대한 API 방식(Chat vs Responses) 및 작동하는 페이로드(Payload) 구성이 OS 캐시 디렉터리의 `llm_endpoint_cache.json`에 영구적으로 저장됩니다. (경로: Linux `~/.cache/ai-translate/`, macOS `~/Library/Caches/ai-translate/`, Windows `%LOCALAPPDATA%\ai-translate\cache\`)
    첫 호출이 성공하고 나면, 이후의 콜드 스타트(Cold Start) CLI 호출에서는 자동 감지 검사 과정을 건너뛰어 속도가 크게 향상됩니다. 이는 제공자별 맞춤형 페이로드 설정이 필요한 Azure, vLLM, OpenRouter, Anthropic, DeepSeek 환경에서 스크립트를 작성할 때 매우 유용합니다. 해당 캐시는 멀티 프로세스 및 멀티 스레드 환경에서도 안전하게 동작합니다(원자적 이름 변경(Atomic Rename) 기반의 Read-Merge-Write 방식 사용).

!!! tip "출력 스트림(Stream) 제어"
    기본적으로 배너, 대기열(Queue) 작업 목록, 개별 작업 진행률은 **stdout**으로 출력됩니다(오류 메시지와 겹치지 않게 라인 버퍼링 적용). 오류 메시지와 로그 기록은 **stderr**로 출력됩니다. 파이프라인 연결을 깔끔하게 유지하기 위해 stdout 출력을 완전히 숨기고 싶다면 `--quiet` 옵션을 함께 사용하세요:

    ```bash
    ait --list-languages | grep -i japanese    # stdout의 데이터 필터링
    ait file.txt --target French --quiet 2> errors.log
    ```
