---
description: AI Translate là phần mềm dịch thuật miễn phí trên máy tính, hỗ trợ tài liệu, PDF, phụ đề, âm thanh và lời nói trực tiếp với hơn 45 ngôn ngữ.
---

# AI Translate

Trình dịch desktop miễn phí, đa nền tảng, hỗ trợ **45 ngôn ngữ** và làm
được nhiều hơn dịch văn bản — nó dịch tài liệu, âm thanh, video, lời
nói trực tiếp, ảnh chụp màn hình, tất cả qua một pipeline LLM duy nhất.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Ứng dụng desktop**

    ---

    Kéo thả tệp vào, chọn ngôn ngữ đích, nhận về bản dịch. Có drag-and-drop,
    lịch sử, bảng thuật ngữ, đầy đủ.

    [:octicons-arrow-right-24: Hướng dẫn 5 phút](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Dòng lệnh**

    ---

    `ait report.docx --target French` — cùng pipeline, có thể script và
    chạy không giao diện. Hữu ích cho CI, batch job, máy chủ.

    [:octicons-arrow-right-24: Hướng dẫn CLI](cli.md)

-   :material-robot-outline:{ .lg .middle } **AI agent (MCP)**

    ---

    Cung cấp tính năng dịch thuật dưới dạng các công cụ Model Context Protocol để
    Claude Desktop, Claude Code, và các MCP client khác có thể gọi trực
    tiếp.

    [:octicons-arrow-right-24: Cài đặt MCP](mcp.md)

</div>

## Bạn có thể dịch những gì

| Loại | Định dạng |
|---|---|
| **Tài liệu Office** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, cùng định dạng cũ `.doc` / `.xls` / `.ppt` |
| **PDF** | Dịch theo kiểu trích xuất–phủ đè giữ nguyên bố cục, dịch bookmark / form / link, có OCR dự phòng cho bản scan |
| **Văn bản & web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Phụ đề** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Bản địa hoá** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Hình ảnh** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR hoặc LLM vision) |
| **Âm thanh** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Video** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (pipeline lồng tiếng đầy đủ) |

## Tính năng nổi bật {: #headline-features }

- **[Dịch Văn bản](features/translate-text.md)** — dịch tức thì qua LLM với tự nhận diện ngôn ngữ, chỉnh sửa tại chỗ, phát giọng nói (TTS). Các ngôn ngữ phải-trái (Ả Rập, Do Thái, Ba Tư) hiển thị đúng hướng tự nhiên.
- **[Dịch Tài liệu](features/translate-document.md)** — kéo thả tệp, theo dõi spinner tiến trình từng tệp, nhận bản sao đã dịch nằm cạnh bản gốc. Đích RTL được chèn markup bidi đúng chuẩn; `Ctrl+P` / `Ctrl+G` tạm dừng và tiếp tục hàng đợi.
- **[Tạo Phụ đề (STT)](features/generate-subtitle.md)** — phiên âm âm thanh / video thành SRT / VTT / ASS / SSA.
- **[Tạo Giọng nói (TTS)](features/generate-voice.md)** — tổng hợp phụ đề thành MP3 / WAV với timing chính xác.
- **[Lồng tiếng Video](features/dubbing.md)** — pipeline đầy đủ STT → dịch → TTS → mix lại video gốc.
- **[Dịch Trực tiếp](features/live-translation.md)** — phụ đề thời gian thực từ micro hoặc âm thanh hệ thống.
- **[Trích xuất Văn bản](features/extract-text.md)** — OCR hoặc LLM vision → `.txt` / `.docx`.
- **[Bảng thuật ngữ](features/glossary.md)** — đảm bảo thuật ngữ nhất quán xuyên suốt các bản dịch.

!!! tip "Chế độ Vertex AI cho Gemini"
    Người dùng doanh nghiệp có thể chuyển các lời gọi Gemini từ Developer
    API sang **Vertex AI** trong **Cài đặt → LLM** — trỏ đến project và
    region GCP của bạn, tuỳ chọn thêm đường dẫn JSON của service account.
    Xem [Nhà cung cấp LLM](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "Lần đầu sử dụng?"
    Bắt đầu với [Cài đặt](getting-started/installation.md), sau đó là
    [hướng dẫn 5 phút cho lần dịch đầu tiên](getting-started/first-translation.md).
    Bạn sẽ có một tài liệu đã dịch trong vòng 10 phút từ lúc clone repo.
