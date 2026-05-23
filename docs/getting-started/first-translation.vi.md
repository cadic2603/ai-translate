---
description: Dịch tài liệu đầu tiên với AI Translate trong 5 phút — kéo thả PDF, chọn ngôn ngữ đích và tải về bản đã dịch.
---

# Bản dịch đầu tiên của bạn

Một lần chạy nhanh từ đầu đến cuối — dưới 5 phút sau khi đã cài xong.

!!! abstract "Trước khi bắt đầu"
    Bạn cần hoàn tất [cài đặt](installation.md) và đã cấu hình một
    LLM API key. Gói miễn phí Google Gemini là đủ cho lần thử đầu.

## Dịch một tài liệu Word

1. Khởi chạy ứng dụng desktop:

    ```bash
    uv run python -m src.main
    ```

2. Nhấp **Dịch tài liệu** ở thanh bên trái.

3. Kéo bất kỳ file `.docx` nào vào vùng thả — hoặc nhấp **Duyệt** để chọn.

4. File xuất hiện trong hàng đợi. Chọn ngôn ngữ đích ở phía trên:

    - Nguồn: `Tự động phát hiện` (mặc định — thường chính xác)
    - Đích: ví dụ `Tiếng Pháp`, `Tiếng Việt`, `Tiếng Nhật`, `Tiếng Trung (Giản thể)`

5. Nhấp **Dịch** (hoặc nhấn `Ctrl+Enter`).

6. Theo dõi thanh tiến trình trong bảng lịch sử ở cuối trang.
   Khi đạt 100%, nhấp **Mở** ở dòng đó để mở file đã dịch — được lưu
   cạnh file gốc với hậu tố `_translated_<src>_<tgt>`.

## Vừa rồi đã xảy ra điều gì

- File `.docx` của bạn được sao chép vào thư mục lưu trữ riêng cho từng
  tác vụ, bản gốc không bị động đến.
- Văn bản được trích xuất, gom thành các đoạn phù hợp với LLM, dịch,
  rồi chèn lại vào tài liệu với toàn bộ định dạng được giữ nguyên (đậm,
  nghiêng, font, màu, header, footnote, hyperlink…).
- Một dòng lịch sử được ghi vào cơ sở dữ liệu SQLite để bạn có thể mở
  lại, chạy lại, hoặc dịch lại file sau này.

## Một số tác vụ có thể thử tiếp theo

=== "Dịch văn bản thuần"

    Vào **Dịch văn bản** ở thanh bên. Dán bất kỳ nội dung nào, chọn
    ngôn ngữ đích, nhấn Enter. Đầu ra stream trực tiếp, đổi ngôn ngữ (`Ctrl+L`),
    chế độ chỉnh sửa, phát TTS.

=== "Tạo phụ đề"

    **Tạo phụ đề** — thả một file `.mp4` vào. Bạn sẽ nhận được file `.srt`
    bằng ngôn ngữ gốc. (Để dịch _và_ lồng tiếng cho video, dùng trang
    Lồng tiếng thay thế.)

=== "Dịch micro trực tiếp"

    **Dịch trực tiếp** — chọn microphone hoặc âm thanh hệ thống, chọn
    ngôn ngữ đích, Bắt đầu. Cửa sổ overlay nổi hiển thị phụ đề theo
    thời gian thực.

## Bước tiếp theo

- Xem [danh sách tính năng](../index.md#headline-features) để biết mỗi trang làm gì.
- Kết nối [thêm nhà cung cấp](../setup/llm-providers.md) (endpoint tùy chỉnh, ElevenLabs, Soniox, Google Cloud).
- Thử [CLI](../cli.md) cho batch / chạy theo script.
