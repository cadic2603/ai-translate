---
description: AI Translate 문제 진단 — 폰트 누락, FFmpeg 오류, LibreOffice 변환기 문제, OCR 설정 실패, LLM API 인증 등 해결 방법.
---

# 문제 해결 (Troubleshooting)

일반적으로 발생하는 오류의 의미와 해결 방법을 안내합니다.

## 환경 설정 관련 오류

### LLM이 구성되지 않음 (`LLM is not configured`)

아직 API 키를 입력하지 않은 상태입니다. 데스크톱 앱을 열고 **설정 → LLM** 메뉴에서 발급받은 API 키를 붙여넣으세요. 전체 가이드는 [LLM 제공자](setup/llm-providers.md) 문서를 참조하세요.

### 인증 오류 (`AUTH_ERROR`)

LLM API 키가 잘못되었거나 만료되었습니다.

- **Gemini:** [Google AI Studio](https://aistudio.google.com/apikey)에서 새 키를 생성한 뒤 **설정 → LLM**에 다시 입력하세요.
- **Custom Provider:** API 키가 유효한지 확인하세요(`Authorization: Bearer …` 헤더를 사용해 터미널에서 `curl` 명령어로 테스트). API 주소(엔드포인트)가 변경되었다면 **API Endpoint** 필드도 알맞게 수정해야 합니다.

### 사용량 초과 오류 (`QUOTA_ERROR`)

무료 제공량(Tier) 또는 유료 요금제 한도를 초과했습니다.

- **Gemini 무료 계정:** 모델별 일일 요청 할당량 한도에 도달했습니다([요금제 안내 참조](https://ai.google.dev/gemini-api/docs/rate-limits)). 하루를 기다려 할당량이 초기화되게 하거나 유료 요금제로 업그레이드하세요.
- **OpenAI 및 기타:** 서비스의 결제 대시보드를 확인하세요. 많은 제공업체에서 지출 한도(Spend Cap)에 도달하면 요청을 일시 중지합니다.

### 모델을 찾을 수 없음 (`MODEL_NOT_FOUND`)

선택한 모델 이름을 사용할 수 없거나 잘못 입력했습니다.

- **Custom Provider:** **설정 → LLM**의 쉼표(`,`)로 구분된 **Models** 목록에 해당 모델이 제대로 입력되어 있는지 확인하세요.
- **Gemini:** **설정 → LLM → 기본 Gemini 모델** 메뉴에서 공식 지원되는 모델 목록 중 하나로 다시 선택하세요.

### 비전 모델 미지원 (`VISION_NOT_SUPPORTED`)

텍스트 전용 모델을 선택한 상태에서 이미지나 스캔된 PDF를 번역하려고 시도했습니다. 이름에 `flash`, `pro`, `vision`, `omni` 등이 포함된 멀티모달(비전) 지원 모델로 전환하세요. (예: OpenAI의 `gpt-4o`, Gemini Flash 및 Pro 최신 모델).

## 오디오 및 비디오 오류

### FFmpeg 누락 (`FFMPEG_NOT_FOUND`)

FFmpeg가 시스템 PATH에 등록되어 있지 않거나 설치되지 않았습니다. 운영체제별 설치 명령어는 [FFmpeg 설정](setup/ffmpeg.md) 문서를 참조하세요.

MCP 서버를 사용 중인 경우 이 오류는 다음과 같이 알아보기 쉽게 가공되어 반환됩니다: *"FFmpeg is required to decode this audio/video file but is not installed or not on PATH."*

### 실시간(Live) 번역 화면에 자막이 표시되지 않음

- **오디오 소스 설정 오류:** **설정 → Live → 오디오 소스** 메뉴를 열고 실제로 인식하려는 대상(마이크 / 시스템 오디오 / 둘 다)과 일치하는지 확인하세요.
- **마이크 문제/음소거:** 운영체제의 사운드 설정을 확인하세요. 앱은 OS에 설정된 기본 입력(마이크) 장치를 사용합니다.
- **시스템 오디오 미설정:** macOS 및 Windows에서 컴퓨터 소리(시스템 오디오)를 캡처하려면 루프백 설정이 필요할 수 있습니다. [시스템 오디오 캡처](setup/system-audio.md) 가이드를 참조하세요.

### TTS 음성 출력이 나오지 않거나 파일이 비어 있음

- **ElevenLabs API 키 누락:** 음성(Voice) 페이지에서 시작 전 안내 대화 상자가 떴음에도 이를 무시하고 넘어갔다면, 생성된 파일이 0바이트(빈 파일)일 수 있습니다. **설정 → Service → ElevenLabs API Key**가 정상적으로 입력되었는지 확인하세요.
- **Edge TTS 네트워크 차단:** Edge TTS는 마이크로소프트 서버 연결이 필요합니다. 방화벽이나 네트워크 환경에서 `speech.platform.bing.com`을 차단하고 있다면, 다른 온라인 엔진(ElevenLabs, Google Cloud TTS)이나 완전 오프라인 엔진인 **Piper TTS**로 전환하세요.

### `Piper voice not installed` 알림창이 뜹니다

음성 변환(Voice) / 더빙(Dubbing) / 텍스트 번역 화면에서는 실제 번역 작업을 시작하기 전에, 대상 언어의 Piper 음성 파일이 컴퓨터에 다운로드되어 있는지 사전 검사(Pre-flight)를 수행합니다. 파일이 없다면 **설정 열기** 버튼이 포함된 알림창이 뜹니다.

**해결 방법 (음성 모델 다운로드):**

1. 알림창에서 **설정 열기**를 클릭하거나, 직접 **설정 → 음성** 탭으로 이동합니다.
2. **TTS 엔진**이 **Piper TTS**로 선택되어 있는지 확인합니다.
3. **지금 음성 다운로드** 버튼을 클릭해 음성 라이브러리 목록을 엽니다.
4. 대상 언어를 찾아 우측의 **Female voice(여성 음성)** 또는 **Male voice(남성 음성)** 버튼을 클릭합니다. (HuggingFace에서 약 25~60MB 크기의 ONNX 파일을 한 번만 다운로드하면 됩니다.)
5. 다운로드가 완료되면 대화 상자를 닫고 다시 작업을 실행합니다.

※ 만약 대상 언어가 다운로드 목록에 아예 없다면, 해당 언어는 Piper TTS가 공식 지원하지 않는 언어입니다. 이 경우 엔진은 음성 생성 시 자동으로 `Edge TTS`를 대신 사용하므로 사용자가 따로 다운로드할 필요가 없습니다. (Piper 음성이 없는 언어 13개: 벨라루스어, 벵골어, 중국어(번체), 크로아티아어, 에스토니아어, 히브리어, 일본어, 크메르어, 한국어, 리투아니아어, 말레이어, 몽골어, 태국어)

※ **참고:** 실시간 번역(Live) 화면에서는 스트리밍 흐름을 방해하지 않기 위해 음성이 없더라도 이 알림창을 띄우지 않습니다. 대신 조용히 Edge TTS로 우회(Fallback)하여 음성을 출력합니다.

## 문서 번역 관련 오류

### PDF 번역 중 특정 페이지에서 실패함

PDF 번역은 페이지별로 중간 저장(체크포인트)을 수행하므로, 번역에 성공한 페이지는 재시작 시 다시 번역하지 않습니다. 특정 페이지에서 실패하는 일반적인 원인은 다음과 같으며, 상세 오류 내역은 `app.log` 파일에 기록됩니다:

- 페이지가 텍스트를 드래그할 수 없는 스캔 이미지인데 OCR 엔진이 설정되어 있지 않은 경우. **설정 → OCR**에서 엔진을 켜주세요. ([OCR 엔진](setup/ocr-engines.md) 참조)
- 복잡한 수식이나 레이아웃이 포함되어 있어 가벼운 모델(Flash)이 처리하지 못한 경우. 성능이 더 뛰어난 Pro 모델로 변경하여 다시 시도해 보세요.

### Office 문서 번역 후 서식(양식)이 깨짐

- **최신 형식(`.docx`, `.xlsx`, `.pptx`)**: 내부적으로 서식을 HTML 태그로 임시 치환하여 번역 후 복원합니다. 번역 결과물에 `<b>`, `<i>` 같은 HTML 태그가 그대로 노출되어 있다면, LLM이 문장을 번역하면서 태그를 올바르게 닫아주지 못한 것입니다. 더 성능이 좋은 모델로 다시 번역해 보세요.
- **구버전 형식(`.doc`, `.xls`, `.ppt`)**: 구버전 문서는 구조적 한계로 서식이 잘 깨집니다. **설정 → 번역 → Auto-convert legacy(구버전 자동 변환)** 옵션을 켜면, 원본을 임시로 최신 형식(`.docx` 등)으로 변환해 번역한 뒤 다시 원래 포맷으로 돌려주어 번역 품질이 크게 향상됩니다.

### 번역 대기열(Queue)이 일괄 작업 중간에 멈춤

작업자 스레드가 알 수 없는 이유로 죽었을 수 있습니다. 앱을 종료하고 터미널에서 데이터베이스 상태를 확인하세요:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

상태가 `Translating`인 채로 몇 분 이상 방치된 항목이 있다면 작업자가 충돌(Crash)한 것입니다. 데스크톱 앱을 다시 시작하기만 하면 됩니다. 앱 시작 시 `Pending` 또는 멈춰 있던 `Translating` 작업을 자동으로 인식해 이어서 진행합니다.

## 기타 시스템 / 공통 오류

### 여러 파일을 끌어다 놓았는데 1개만 번역되는 것 같음

목록 헤더의 **Files** 열에 끌어다 놓은 파일 개수가 제대로 인식되었는지 확인하세요. 참고로, 한 번에 최대 100개의 파일까지만 추가할 수 있으며 100개를 초과할 경우 알림창이 뜹니다.

### 사이드바의 진행 스피너가 영원히 돌아감

작업자 스레드가 실행 중이라는 신호가 UI에 갇힌 상태입니다. `SIGKILL(강제 종료)`을 피하고 앱을 정상적으로 종료하세요. 앱이 종료되면서 정리 프로세스가 상태를 바로잡습니다. 만약 이미 비정상 종료하여 상태가 꼬였다면, 다음 명령어로 DB를 초기화해 주세요:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### 로그 파일은 어디에 있나요? {: #where-are-the-logs }

| OS | 경로 |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

로그 파일에는 콘솔의 출력 수준과 무관하게 언제나 가장 상세한 내용(`DEBUG` 레벨)이 모두 기록됩니다. CLI 사용 시 로그 전체를 화면(stdout)에도 함께 띄우려면 `--verbose` 옵션을 추가하세요.

## 여전히 문제가 해결되지 않나요?

- 기능이나 구조적인 질문은 [자주 묻는 질문(FAQ)](faq.md) 문서를 참조하세요.
- 문제가 계속된다면 [GitHub 이슈 게시판](https://github.com/cadic2603/ai-translate/issues)에 버그를 등록해 주세요. 등록 시 **운영체제(OS), Python 버전, 실패한 명령어 또는 상황, `app.log` 파일 내 오류 관련 부분, 기대했던 동작 결과**를 함께 적어주시면 빠르게 파악할 수 있습니다.
