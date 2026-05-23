---
description: AI Translate가 자막 생성, 음성 합성 및 비디오 더빙을 위해 오디오 및 비디오를 디코딩할 수 있도록 FFmpeg 설치 — 미디어 기능에 필요합니다.
---

# FFmpeg

FFmpeg는 모든 오디오 / 비디오 워크플로에 필요합니다:

- **자막 생성** — STT를 위한 소스 오디오 디코딩
- **음성 생성** — 타이밍이 있는 TTS 클립을 하나의 파일로 결합
- **더빙** — STT → TTS → 비디오로 다시 mux
- **라이브 번역** — 시스템 오디오 캡처가 `parec`를 통과할 때

번들로 제공되지 않습니다 — 시스템에 한 번 설치하세요.

## 설치

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    또는 더 완전한 빌드의 경우, 먼저
    [RPM Fusion](https://rpmfusion.org/Configuration)을 활성화하세요.

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    <https://www.gyan.dev/ffmpeg/builds/>에서 정적 빌드를 다운로드
    ("release essentials" 빌드면 충분), 압축 해제, 그런 다음 `bin/`
    폴더를 PATH에 추가:

    1. **Win + R** 누름, `sysdm.cpl` 입력, **Enter** 누름
    2. **고급 → 환경 변수 → 시스템 변수 → Path → 편집**
    3. **새로 만들기** → FFmpeg의 `bin` 폴더의 절대 경로 붙여넣기
    4. 모두 **확인**, 열린 모든 터미널 재시작

## 확인

```bash
ffmpeg -version
```

구성 줄에 `--enable-libx264 --enable-libvpx`가 있는 버전 배너를
보아야 합니다. "command not found"가 보이면, 설치가 PATH에 도달하지
않은 것입니다.

## 앱 내 사전 검사

음성 / 더빙 페이지는 작업을 시작하기 전에
`shutil.which("ffmpeg")`를 호출합니다. FFmpeg를 찾을 수 없으면 반쯤
실행된 작업 대신 여기로 돌아오는 링크가 있는 친근한 오류 대화상자가
표시됩니다.

## 일반적인 오류

| 오류 | 의미 |
|---|---|
| `FFMPEG_NOT_FOUND` | 페이지가 실행하려고 시도한 시점에 `ffmpeg`가 PATH에 없습니다. 설치(위)하고 앱을 다시 시작하세요. |

MCP 서버(`ait-mcp`)에서 동일한 오류가 사람이 읽을 수 있는 메시지로
다시 래핑됩니다:

> *"이 오디오/비디오 파일을 디코딩하려면 FFmpeg가 필요하지만 설치
> 되지 않았거나 PATH에 없습니다. FFmpeg를 설치하고 다시 시도하세요."*
