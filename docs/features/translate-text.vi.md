---
description: Dịch nhanh đoạn văn bản sang 45+ ngôn ngữ với AI Translate — dán, gõ hoặc nói; hỗ trợ chế độ chỉnh sửa, phát TTS và đổi ngôn ngữ.
---

# Dịch văn bản

Dịch tức thì bằng LLM với tự phát hiện, đổi ngôn ngữ, đầu ra streaming
và phát TTS. Phù hợp nhất cho đoạn văn ngắn, dùng kiểu chat, và kiểm
tra cấu hình LLM.

## Hướng dẫn từng bước

1. Nhấp **Dịch văn bản** ở thanh bên.
2. Gõ hoặc dán văn bản nguồn vào ô bên trái.
3. Ngôn ngữ **Nguồn** tự phát hiện khi bạn gõ (dùng `langdetect`).
4. Chọn ngôn ngữ **Đích** từ menu thả bên phải.
5. Nhấp **Dịch** (hoặc nhấn `Ctrl+Enter`).
6. Bản dịch hiển thị từng token vào ô bên phải.

## Bạn nhận được

- **Đầu ra streaming** — bản dịch hiện ra ngay khi LLM sinh, không cần
  chờ toàn bộ phản hồi.
- **Tự phát hiện nguồn** — bộ chọn nguồn cập nhật theo thời gian thực.
  Nhấp để ghi đè thủ công.
- **Chế độ chỉnh sửa** — nhấp ô bên phải để sửa bản dịch thủ công.
  Nhấn `Escape` để hủy bản dịch đang chạy; nhấn lần nữa để thoát chế
  độ chỉnh sửa.
- **Tái sử dụng lịch sử** — mọi bản dịch đều được lưu. Nhấp một mục
  trong bảng Lịch sử dịch văn bản bên dưới để nạp lại cả hai ô; chỉnh
  sửa cập nhật mục gốc thay vì tạo bản trùng.
- **Phát TTS** — nhấp nút **Nghe** cạnh từng ô để nghe đọc to. Tuân theo
  lựa chọn **Cài đặt → Giọng → Phương thức TTS** — Edge TTS (mặc định),
  ElevenLabs, Google Cloud TTS, Gemini TTS, hoặc **Piper TTS** (hoàn
  toàn offline). Khi chọn Piper, nút Nghe chạy cùng pre-flight như trang
  Tạo giọng nói: nếu thiếu voice cho ngôn ngữ đó sẽ hiện hộp thoại với
  nút **Mở cài đặt** để bạn tải về. Cache hit bỏ qua pre-flight hoàn toàn.
- **Chọn model theo trang** — khi có nhiều LLM được cấu hình, dropdown
  cho phép chọn model Flash nhanh hoặc model Pro nặng hơn cho chất
  lượng, chỉ riêng trang này.

## Phím tắt

| Phím tắt | Hành động |
|---|---|
| `Ctrl+Enter` | Dịch |
| `Ctrl+L` | Đổi nguồn ↔ đích |
| `Escape` | Hủy bản dịch đang chạy, hoặc thoát chế độ chỉnh sửa |
| `Ctrl+F` | Focus tìm kiếm lịch sử |

## Mẹo

!!! tip "Ngôn ngữ RTL"
    Bản dịch sang **Tiếng Ả Rập**, **Tiếng Hebrew** hoặc **Tiếng Ba Tư**
    tự động hiển thị phải-sang-trái trong ô đầu ra. Cùng cách xử lý RTL
    áp dụng cho file xuất ở mọi định dạng trên trang
    [Dịch tài liệu](translate-document.md) (PDF, DOCX, PPTX, XLSX, ODF,
    RTF, HTML, EPUB, ASS/SSA), và Tiếng Ba Tư có giọng `fa-IR` bản địa
    cho phát Edge TTS.

!!! tip "Cache nút Nghe"
    Lần đầu nhấn Nghe cho một cặp (văn bản, ngôn ngữ), audio được tổng
    hợp và lưu vào ổ đĩa. Các lần phát sau là tức thì. Cache được xóa
    khi khởi động ứng dụng, mỗi phiên bắt đầu lại từ đầu.

!!! tip "Key được lưu ở đâu"
    Trang Dịch văn bản đọc cùng các mục keychain như phần còn lại của
    ứng dụng — xem [Nhà cung cấp LLM](../setup/llm-providers.md).
