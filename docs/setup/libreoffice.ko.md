---
description: macOS 및 Linux에서 AI Translate가 레거시 Office 형식(.doc, .xls, .ppt) 및 ODF 파일(.odt, .ods, .odp)을 번역할 수 있도록 LibreOffice 설치.
---

# LibreOffice (Office 형식)

Office 번역 파이프라인은 다음 순서로 사용 가능한 최상의 백엔드를
선택합니다:

1. **win32com**(Windows + MS Office 설치) — 최고 충실도
2. **LibreOffice UNO**(크로스 플랫폼) — win32com이 없을 때의 폴백
3. **python-docx / openpyxl / python-pptx**(현대 형식만) — 위의
   둘 모두 사용할 수 없을 때의 순수 Python 폴백

LibreOffice는 Linux와 macOS에서 레거시 `.doc` / `.xls` / `.ppt`에
대한 **유일한 경로**이며, 해당 플랫폼에서 현대 Office 형식에 대해서도
권장되는 경로입니다(순수 Python 백엔드보다 더 나은 충실도, 특히
테이블 및 임베디드 객체에).

## 설치

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    또는 <https://www.libreoffice.org/download/download/>에서 다운로드.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    Windows의 데스크톱 앱은 일반적으로 MS Office가 설치된 상태에서
    **win32com**을 사용합니다 — LibreOffice는 MS Office가 누락된 경우
    *폴백*입니다. <https://www.libreoffice.org/download/download/>
    에서 설치.

## 확인

```bash
soffice --version
```

macOS에서 "command not found"가 표시되면, 바이너리는
`/Applications/LibreOffice.app/Contents/MacOS/soffice`에 있습니다.
앱은 일반적인 설치 경로를 통해 자동 검색하지만, 필요한 경우 **설정 →
일반 → LibreOffice 경로**에서 재정의할 수 있습니다.

## 무엇을 강화하는지

LibreOffice가 활성 백엔드일 때:

| 기능 | 메모 |
|---|---|
| **현대 Office**(`.docx`, `.xlsx`, `.pptx`) | win32com을 사용할 수 없을 때 폴백으로 사용 |
| **레거시 Office**(`.doc`, `.xls`, `.ppt`) | 필요 — 순수 Python은 이것들을 읽을 수 없음 |
| **ODF**(`.odt`, `.ods`, `.odp`) | **ODF 자동 변환**이 켜져 있을 때 라운드트립 변환에 사용 |
| **레거시 / ODF → OOXML 자동 변환** | 필요 |

## 백그라운드 프로세스

LibreOffice가 처음 필요할 때, 앱은 헤드리스 모드에서 `soffice`
프로세스를 생성하고 번역 전반에 걸쳐 살려둡니다(`office_lifecycle.py`).
앱 종료 시 자동으로 종료됩니다.

## 주의사항

!!! warning "최초 실행 시작 시간"
    LibreOffice에 도달하는 첫 번째 번역은 `soffice`가 시작되기까지
    ~5-10초 기다립니다. 이후 번역은 동일한 프로세스를 재사용하고
    빠릅니다.

!!! info "JVM 충돌 로그"
    LibreOffice의 Java 구성 요소는 가끔 segfault 시 `hs_err_pid*.log`
    파일을 생성합니다. 앱은 그것들을 임시 디렉토리로 라우팅하여
    프로젝트 폴더를 오염시키지 않도록 합니다.

!!! tip "레거시 / ODF 자동 변환"
    `.doc` / `.xls` / `.ppt`를 일상적으로 번역하는 경우 **설정 →
    번역 → 레거시 자동 변환**을 활성화하세요. 파이프라인은 먼저 그것
    들을 `.docx` / `.xlsx` / `.pptx`로 변환하고(`convert_to_modern_format`
    경유), 현대 복사본을 번역한 다음 다시 변환합니다. 충실도는 레거시
    형식을 직접 번역하는 것보다 훨씬 높습니다.
