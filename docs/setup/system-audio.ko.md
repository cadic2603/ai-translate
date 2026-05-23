---
description: AI Translate의 Live 페이지를 위해 Linux, macOS 및 Windows에서 시스템 오디오 캡처 — 컴퓨터에서 재생되는 모든 소리를 실시간으로 번역.
---

# 시스템 오디오 캡처(Live)

**[라이브 번역](../features/live-translation.md)** 페이지는 **시스템
오디오**(스피커에서 재생되는 모든 것)를 캡처할 수 있어 모든 미디어를
자막 / 번역할 수 있습니다 — Zoom 통화, YouTube, Netflix, 게임,
시스템 사운드.

**설정 → Live → 오디오 소스**(또는 Live 페이지 상단의 콤보)에서 선택:

- **마이크** — 마이크만
- **시스템 오디오** — 스피커에서 재생되는 것만
- **둘 다** — 둘 다 혼합(미디어 위에 내레이션하거나 하이브리드 회의를
  캡처하는 데 좋음)

**시스템 오디오** 또는 **둘 다**를 선택하면, 앱이 OS에 맞는 올바른
캡처 백엔드로 디스패치합니다. OS 전제 조건이 충족되지 않으면 클릭
가능한 설치 링크가 있는 인라인 경고 배너가 나타나므로, 무언가가
누락되었다는 것을 알기 위해 세션을 시작할 필요가 없습니다.

## Linux (PulseAudio / PipeWire)

모든 현대적인 배포판에서 즉시 작동합니다.

앱은 기본 싱크의 **모니터 소스**를 탭하기 위해 `parec`(PulseAudio
Recorder)를 사용합니다. PipeWire의 PulseAudio 호환성 shim이 이를
투명하게 만들어 줍니다 — 원시 PulseAudio가 필요하지 않습니다.

```bash
parec --version    # 무언가를 출력해야 함
```

`parec`가 없으면 경고 배너가 배포판의 패키지 관리자를 감지하고 정확한
설치 명령을 인라인합니다 — 예를 들어:

> 시스템 오디오 캡처에는 PulseAudio 또는 PipeWire가 필요합니다 — `sudo apt-get install pulseaudio` 실행.

apt-get / dnf / pacman / zypper / apk에서 감지됩니다; 명령을 직접
터미널로 복사-붙여넣기 할 수 있습니다.

## macOS

CoreAudio는 시스템 오디오를 기본적으로 노출하지 않으므로, **가상
루프백 장치**가 필요합니다 — 다음 중 하나를 설치:

- **[BlackHole](https://existential.audio/blackhole/)** — 무료, 오픈 소스
- **[Loopback](https://rogueamoeba.com/loopback/)** — 유료, 세련된 GUI
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — 레거시 무료 옵션
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — 유료

앱은 `ffmpeg -f avfoundation -list_devices`를 통해 이들 중 하나를
자동 감지하고 첫 번째 일치를 사용합니다. 루프백을 기본 출력 / 입력
으로 설정할 필요가 없습니다 — 캡처는 `ffmpeg`의 avfoundation 백엔드
를 통해 직접 발생합니다.

설치 후 Live 페이지 콤보에서 **시스템 오디오**를 선택하기만 하면
경고 배너가 사라집니다.

## Windows

기본 — 대부분의 경우 **추가 소프트웨어가 필요하지 않음**.

앱은 Python 패키지
[`soundcard`](https://github.com/bastibe/SoundCard)(Windows에서 앱과
함께 자동 설치)를 통해 **WASAPI 루프백**과 직접 통신합니다. 이는
Tauri / Rust 데스크톱 앱이 사용하는 동일한 네이티브 루프백 API입니다;
가상 케이블 없이 기본 스피커 출력을 캡처합니다.

어떤 이유로 WASAPI 루프백을 사용할 수 없는 경우(오래된 Windows
버전, 비정상적인 오디오 드라이버), 앱은 가상-루프백 DirectShow 장치에
대해 `ffmpeg -f dshow`로 폴백합니다. 다음 중 하나를 선택:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — 무료, `virtual-audio-capturer` 제공
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — 무료, `CABLE Output (VB-Audio Virtual Cable)`로 제공
- **Stereo Mix (Realtek Audio)** — 레거시 온보드 옵션, 종종 기본적으로 비활성화됨

앱은 이들을 순서대로 검사하고 처음 존재하는 것을 사용합니다.

## "둘 다"가 음성 AND 시스템 오디오를 모두 받는 이유

**둘 다** 모드에서 앱은 두 개의 캡처 스트림을 병렬로 엽니다 —
`sounddevice`를 통한 마이크, 위의 OS별 백엔드를 통한 시스템 오디오 —
그리고 샘플 블록 단위로 혼합합니다. 이것은 비디오 위에 내레이션하거나
하이브리드 회의의 양쪽 모두(목소리와 스피커의 참여자)를 캡처하기에
적합한 모드입니다.

> **팁:** 에코가 들리거나 자막이 중복되면, 마이크를 통해 시스템
> 오디오가 들어오는 것입니다(큰 스피커 → 마이크가 그것들을 잡음).
> **시스템 오디오**만으로 전환하거나 헤드폰을 사용하세요.

## 문제 해결

| 증상 | 가능한 원인 |
|---|---|
| Live 페이지가 시작되지만 자막 없음 | 잘못된 오디오 소스가 선택되었거나, 기본 마이크가 음소거됨 |
| 음성에 대한 자막은 있지만 YouTube 비디오에는 없음 | 시스템 오디오 전제 조건이 설치되지 않음(배너가 설치 지침을 표시해야 함) |
| 자막이 두 번(에코) | "둘 다" 모드는 시스템 오디오를 두 번 캡처 — 한 번은 스피커에서 마이크를 통해, 한 번은 루프백을 통해. 시스템 오디오만으로 전환하거나 헤드폰 사용 |
| 누락된 소프트웨어를 설치한 후 배너가 계속 표시됨 | 탭을 전환하고 돌아오기 — 배너는 페이지 표시 시 다시 확인 |
| macOS: BlackHole 설치되었지만 배너가 여전히 위에 있음 | BlackHole이 `ffmpeg -f avfoundation -list_devices true -i ""` 오디오 장치 목록에 있는지 확인; 앱이 거기서 봐야 함 |
| Windows: 오류 없이 WASAPI 루프백 실패 | 폴백으로 VB-Audio Virtual Cable 설치 시도; 오래된 Windows 버전이나 일부 오디오 드라이버는 `soundcard`를 통해 루프백을 노출하지 않음 |
