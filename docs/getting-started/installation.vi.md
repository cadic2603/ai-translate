---
description: Hướng dẫn cài đặt AI Translate trên Windows, macOS và Linux — bao gồm Python, FFmpeg và thiết lập LibreOffice tùy chọn.
---

# Cài đặt

## Cần chuẩn bị

- **Python 3.12 trở lên** ([tải về](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — trình quản lý gói Python tốc độ cao. Cài bằng:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **Một API key LLM** — chọn một trong:
    - [Google Gemini](https://aistudio.google.com/apikey) (có gói miễn phí — khuyến nghị cho người mới bắt đầu)
    - Bất kỳ endpoint tương thích OpenAI nào (OpenAI, Anthropic qua proxy, Ollama / LM Studio chạy local, v.v.)

## Tuỳ chọn, mở khoá thêm tính năng

| Công cụ | Dùng cho | Khi nào cần |
|---|---|---|
| **FFmpeg** ([tải](https://ffmpeg.org/download.html)) | Phụ đề, Giọng nói, Lồng tiếng, Trực tiếp | Bất kỳ tác vụ âm thanh / video nào |
| **LibreOffice** ([tải](https://www.libreoffice.org/download/)) | Định dạng Office trên Linux/macOS | Dịch định dạng cũ `.doc` / `.xls` / `.ppt`, hoặc bất kỳ tệp Office nào khi không có MS Office |
| **Tesseract** ([hướng dẫn](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | Engine OCR (mặc định) | Trang Trích xuất Văn bản, dịch PDF scan, dịch ảnh nhúng |
| **MS Office** + **pywin32** | Office trên Windows | Chất lượng cao nhất khi dịch Office trên Windows |

Bạn có thể cài AI Translate mà không có cái nào ở trên — các tính năng cần
chúng sẽ thông báo trước khi gặp lỗi.

## Cài đặt

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

Lệnh trên cài mọi thứ cần để chạy ứng dụng desktop, CLI, và máy chủ MCP.

## Chạy thử

=== "Ứng dụng desktop"
    ```bash
    uv run python -m src.main
    ```

=== "Dòng lệnh"
    ```bash
    uv run ait --version
    ```

=== "Máy chủ MCP"
    ```bash
    uv run ait-mcp           # transport stdio (cho Claude Desktop / Code)
    ```

## Thêm API key

Khi mở ứng dụng desktop lần đầu:

1. Bấm **Settings** trên thanh bên
2. Mở tab **LLM**
3. Dán **Google Gemini API key** (hoặc cấu hình một custom OpenAI-compatible
   provider). Người dùng doanh nghiệp có thể chuyển Gemini sang **chế độ
   Vertex AI** — trỏ đến project và region GCP, tuỳ chọn thêm đường dẫn
   JSON của service account; xem [Nhà cung cấp LLM](../setup/llm-providers.md)
   để biết chi tiết.
4. Chọn model mặc định — bất kỳ biến thể Flash hiện hành nào (ví dụ
   `gemini-2.5-flash`) là điểm khởi đầu miễn phí ổn. Biến thể Pro cho chất
   lượng cao hơn với chi phí cao hơn.
5. Đóng Settings — xong

Key được lưu trong **OS keychain** (macOS Keychain, Windows Credential Manager,
GNOME / KDE Secret Service trên Linux), không phải dạng plaintext trên ổ.

!!! tip "Cài đặt headless / server"
    Nếu bạn không thể chạy desktop app để cấu hình key, xem
    [LLM Providers](../setup/llm-providers.md) cho các lệnh keychain CLI.

## Tiếp theo: thử ngay

[Lần dịch đầu tiên trong 5 phút →](first-translation.md){ .md-button .md-button--primary }
