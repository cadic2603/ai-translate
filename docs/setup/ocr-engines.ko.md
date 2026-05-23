---
description: 이미지 및 PDF 텍스트 추출을 위한 OCR 엔진 설정 — 오프라인 Tesseract 또는 EasyOCR, 또는 클라우드 기반 Google Vision OCR 중에서 선택.
---

# OCR 엔진

OCR은 이미지에서 텍스트를 읽는 데 사용됩니다 — [텍스트 추출](../features/extract-text.md)
페이지에서 그리고 페이지가 스캔되었거나(텍스트 레이어 없음) **포함된
이미지 번역**을 켤 때 문서 번역 내의 폴백으로.

세 가지 OCR 엔진 중에서 선택할 수 있습니다.

## Tesseract(권장 기본)

무료, 빠름, 오프라인. 시스템 설치가 필요합니다.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all`은 지원되는 모든 언어를 가져옵니다. 디스크
    를 절약하려면 필요한 것만 설치하세요(예: 프랑스어용
    `tesseract-ocr-fra`).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    [UB Mannheim의 Tesseract 릴리스](https://github.com/UB-Mannheim/tesseract/wiki)
    에서 설치 프로그램을 다운로드합니다. 실행하고 기본값을 수락하세요
    — 언어 팩이 번들되어 있습니다.

확인:

```bash
tesseract --version
tesseract --list-langs
```

데스크톱 앱에서: **설정 → OCR → OCR 방법 = Tesseract**. 완료.

## EasyOCR

무료, 오프라인. 비라틴 스크립트(중국어, 한국어, 일본어, 태국어)에
훌륭합니다. 모델은 첫 사용 시 다운로드됩니다(총 ~1 GB).

```bash
uv sync --extra easyocr
```

데스크톱 앱에서: **설정 → OCR → OCR 방법 = EasyOCR**.

언어에 처음 사용할 때, 관련 모델이 `~/.EasyOCR/`로 다운로드됩니다.
이후 실행은 즉시입니다.

## Google Cloud Vision

클라우드, 유료(월 1,000건의 무료 요청). 최고의 정확도, 특히 시끄러운
/ 손글씨 / 다중 스크립트 콘텐츠에서.

1. [Google Cloud 프로젝트 생성](https://console.cloud.google.com/projectcreate)
2. [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com) 활성화
3. [API 키 생성](https://console.cloud.google.com/apis/credentials)
4. 데스크톱 앱에서: **설정 → 서비스 → Google Cloud API 키** → 붙여넣기
5. **설정 → OCR → OCR 방법 = Google Cloud OCR**

해당 API도 활성화하면 동일한 Google Cloud API 키가 Vision OCR,
Speech-to-Text 및 Text-to-Speech를 강화합니다.

## 정확도 비교

**설정 → OCR** 탭에는 작은 비교 테이블이 내장되어 있습니다 — 언어
커버리지, 온라인/오프라인, 비용, 정확도. 전환하고 싶을 때마다 다시
읽으세요.

## OCR이 사용되는 때

| 장소 | 동작 |
|---|---|
| **텍스트 추출 페이지**(방법 = OCR일 때) | 드롭된 이미지에 직접 OCR |
| **문서 번역 → PDF** | 스캔 전용 페이지(텍스트 레이어 없음)에 OCR 폴백 |
| **문서 번역 → Office** + **포함된 이미지 번역** 켜짐 | 모든 포함된 이미지에 OCR + LLM 비전 |

## 팁

!!! tip "소스 언어 선택"
    대부분의 OCR 엔진은 어떤 언어를 기대해야 하는지 알려줄 때 훨씬
    더 정확합니다. 자막 / 문서 / 텍스트 추출 페이지 모두 **소스
    언어** 선택기를 OCR 엔진에 전달합니다.

!!! tip "Tesseract는 깨끗한 인쇄 텍스트에 충분"
    Tesseract / EasyOCR이 실제로 콘텐츠에서 실패할 때까지 클라우드
    OCR에 손을 뻗지 마세요. 그것들은 무료, 빠르며 놀라울 정도로
    좋습니다.
