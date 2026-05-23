---
description: Cài đặt các engine OCR để trích xuất văn bản từ ảnh và PDF — chọn Tesseract hoặc EasyOCR offline, hoặc Google Vision OCR trên cloud.
---

# Engine OCR

OCR được dùng để đọc văn bản từ ảnh — cả trên trang [Trích xuất văn bản](../features/extract-text.md)
và làm fallback bên trong dịch tài liệu khi một trang được scan (không
có layer text) hoặc khi bạn bật **Dịch ảnh nhúng**.

Bạn có thể chọn từ ba engine OCR.

## Tesseract (mặc định khuyến nghị)

Miễn phí, nhanh, offline. Cần cài đặt trên hệ thống.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` bao gồm mọi ngôn ngữ hỗ trợ. Để tiết kiệm ổ đĩa,
    chỉ cài những gì bạn cần (ví dụ `tesseract-ocr-fra` cho tiếng Pháp).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    Tải installer từ
    [bản phát hành Tesseract của UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
    Chạy nó, chấp nhận mặc định — gói ngôn ngữ đã được gộp sẵn.

Xác minh:

```bash
tesseract --version
tesseract --list-langs
```

Trong ứng dụng desktop: **Cài đặt → OCR → Phương thức OCR = Tesseract**. Xong.

## EasyOCR

Miễn phí, offline. Tốt cho chữ không thuộc Latin (Trung, Hàn, Nhật, Thái).
Model tải khi dùng lần đầu (~1 GB tổng).

```bash
uv sync --extra easyocr
```

Trong ứng dụng desktop: **Cài đặt → OCR → Phương thức OCR = EasyOCR**.

Lần đầu dùng cho một ngôn ngữ, model tương ứng tải về `~/.EasyOCR/`.
Các lần sau là tức thì.

## Google Cloud Vision

Cloud, có phí (1.000 yêu cầu miễn phí / tháng). Chính xác nhất, đặc
biệt với nội dung nhiễu / viết tay / đa script.

1. [Tạo dự án Google Cloud](https://console.cloud.google.com/projectcreate)
2. Bật [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [Tạo API key](https://console.cloud.google.com/apis/credentials)
4. Trong ứng dụng desktop: **Cài đặt → Dịch vụ → Google Cloud API key** → dán
5. **Cài đặt → OCR → Phương thức OCR = Google Cloud OCR**

Cùng một Google Cloud API key này cấp nguồn cho Vision OCR, Speech-to-Text
và Text-to-Speech nếu bạn cũng bật các API đó.

## So sánh độ chính xác

Tab **Cài đặt → OCR** có sẵn một bảng so sánh nhỏ — phạm vi ngôn ngữ,
online/offline, chi phí, độ chính xác. Đọc lại bất cứ khi nào bạn định
chuyển engine.

## Khi nào OCR được dùng

| Nơi | Hành vi |
|---|---|
| **Trang Trích xuất văn bản** (khi phương thức = OCR) | OCR trực tiếp trên ảnh thả vào |
| **Dịch tài liệu → PDF** | OCR fallback trên trang chỉ-scan (không có layer text) |
| **Dịch tài liệu → Office** với **Dịch ảnh nhúng** bật | OCR + Vision LLM trên từng ảnh nhúng |

## Mẹo

!!! tip "Chọn ngôn ngữ nguồn"
    Hầu hết engine OCR chính xác hơn nhiều khi bạn cho biết ngôn ngữ
    cần chờ đợi. Trang Phụ đề / Tài liệu / Trích xuất văn bản đều
    chuyển bộ chọn **Ngôn ngữ nguồn** của bạn cho engine OCR.

!!! tip "Tesseract đủ cho text in sạch"
    Đừng vội với cloud OCR cho đến khi Tesseract / EasyOCR thực sự thất
    bại trên nội dung của bạn. Chúng miễn phí, nhanh và bất ngờ tốt.
