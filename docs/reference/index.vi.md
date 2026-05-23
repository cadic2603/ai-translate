---
description: Tài liệu tham khảo cho lập trình viên về Python API của AI Translate — tự động tạo từ docstring; bao gồm core, utils, constants, CLI và MCP server.
---

# Tài liệu tham khảo cho lập trình viên

Người dùng cuối có thể muốn xem [trang tính năng](../index.md#headline-features)
hoặc [hướng dẫn cài đặt](../setup/llm-providers.md), không phải mục này.

Đây là **tham khảo API tự động sinh** — mỗi trang ứng với một module Python
trong `src/`, được tạo từ docstring của dự án. Nó dành cho người đóng góp
và người tích hợp muốn gọi các hàm bên dưới từ code Python của riêng họ.

## Mục tiêu build

`uv run mkdocs build` tái tạo các trang này từ `src/` mỗi lần build,
nên chúng luôn phản ánh đúng những gì đang có trong code.

## Bắt đầu từ đâu

Điểm vào dịch không cần GUI là
[`run_translation_pipeline`](api/core/translator.md) — mọi tính năng
trong ứng dụng desktop, CLI và MCP server cuối cùng đều đi qua đây.
Đọc hàm này và `TranslationConfig` đi kèm là cách nhanh nhất để hiểu
toàn bộ pipeline.

## Cấu trúc

- **[Constants](api/constants/index.md)** — khóa cài đặt, mã lỗi, bảng ngôn ngữ, engine i18n / theme.
- **[Core](api/core/index.md)** — pipeline dịch, điều phối LLM, processor theo định dạng, engine OCR / STT / TTS, checkpoint, cơ sở dữ liệu.
- **[Utils](api/utils/index.md)** — các tiện ích dùng chung.
- **[CLI](api/cli.md)** — điểm vào `ait`.
- **[MCP Server](api/mcp_server.md)** — điểm vào `ait-mcp`.
