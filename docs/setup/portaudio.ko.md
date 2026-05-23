---
description: 실시간 번역을 위한 크로스 플랫폼 마이크 오디오 캡처.
---

# PortAudio 설정 (마이크)

[실시간 번역](../features/live-translation.md) 기능은 `sounddevice` 파이썬 패키지를 사용하며, 이는 모든 운영 체제에서 마이크 장치에 액세스하기 위해 PortAudio C 라이브러리에 의존합니다. 대부분의 사용자는 이 시스템 수준 종속성을 설치해야 합니다.

## Windows
`sounddevice` 및 `PyAudio`용 사전 컴파일된 휠(wheel)은 일반적으로 Windows에서 PortAudio 바이너리를 번들로 제공합니다. 일반적으로 수동 시스템 전체 설치는 필요하지 않습니다. 오류가 발생하는 경우 오디오 드라이버가 최신 상태인지 확인하십시오.

## macOS
Homebrew를 사용하여 PortAudio를 설치합니다:

```bash
brew install portaudio
```

## Linux
패키지 이름은 배포판에 따라 다릅니다. 사전 컴파일된 휠을 사용할 수 없는 경우 Python이 C 바인딩을 빌드할 수 있도록 개발 패키지(일반적으로 `-dev` 또는 `-devel`로 끝남)를 설치해야 합니다.

=== "Ubuntu / Debian / Mint"

    ```bash
    sudo apt-get install portaudio19-dev
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install portaudio-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S portaudio
    ```

## 문제 해결

설치 후에도 애플리케이션에서 마이크에 액세스할 수 없다고 계속 보고하는 경우:

1. 터미널 애플리케이션(또는 데스크톱 환경)에 마이크에 액세스할 수 있는 권한이 있는지 확인합니다(특히 macOS에서).
2. 새 라이브러리 경로를 가져오도록 애플리케이션(또는 터미널/MCP 서버)을 다시 시작합니다.
