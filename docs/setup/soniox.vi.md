---
description: Cấu hình Soniox cho speech-to-text thời gian thực trong trang Dịch trực tiếp của AI Translate — hỗ trợ phân biệt người nói, thuật ngữ và dịch trực tiếp.
---

# Soniox (STT)

Speech-to-text thời gian thực qua API WebSocket của Soniox. Được dùng bởi
trang **[Phụ đề](../features/generate-subtitle.md)** và **[Dịch trực tiếp](../features/live-translation.md)**
khi bạn chọn Soniox làm phương thức STT.

## Tại sao chọn Soniox

- **Thời gian thực** — các token đến trong khi người nói vẫn đang nói.
- **Phân biệt người nói** — nhãn người nói trên từng token (ví dụ _Người 1: Xin chào…_).
- **Dịch tích hợp** — Soniox có thể dịch trong lúc nhận dạng,
  giúp bỏ qua một lần gọi LLM bổ sung.
- **Đa ngôn ngữ** — tự phát hiện ngôn ngữ nguồn ngay cả khi đang ở giữa stream.

## Lấy API key

1. Đăng ký tại <https://console.soniox.com>
2. Mở **API keys** → **Create new API key**
3. Sao chép key (dạng `Bearer ...`; chỉ sao chép token, không bao gồm
   tiền tố `Bearer `).

Giá tính theo phút âm thanh (~$0.005 / phút tại thời điểm viết tài liệu) —
xem <https://soniox.com/pricing>.

## Cấu hình trong ứng dụng

Trong **Cài đặt → Dịch vụ**:

1. Dán key vào **Soniox API key** → **Lưu**

Trong **Cài đặt → Trực tiếp** *(cho dịch trực tiếp)* hoặc **Cài đặt → Phụ đề**
*(cho tạo phụ đề)*:

1. Đặt **Phương thức STT** thành **Soniox**

## Soniox hỗ trợ gì

| Trang | Dùng Soniox khi |
|---|---|
| **Phụ đề** | Bản ghi nhiều người nói (phỏng vấn, thảo luận, họp) khi bạn muốn có nhãn người nói trong file SRT |
| **Dịch trực tiếp** | Tạo phụ đề họp theo thời gian thực, đặc biệt khi có nhiều người nói |

## Thuật ngữ glossary

WebSocket Soniox chấp nhận danh sách thuật ngữ để ưu tiên khi nhận dạng.
Ứng dụng tự động chuyển các mục glossary đang kích hoạt — tên thương hiệu /
danh từ riêng / thuật ngữ chuyên ngành được nhận dạng đáng tin cậy hơn.

## Lưu ý

!!! warning "Chỉ online"
    Soniox chỉ chạy trên cloud; nếu âm thanh của bạn nhạy cảm (y tế,
    pháp lý), hãy dùng Whisper (local) thay thế.

!!! info "Tự kết nối lại"
    WebSocket tự kết nối lại khi gặp lỗi tạm thời với exponential backoff.
    Phiên dài vẫn duy trì kết nối qua các lần mạng chập chờn ngắn.

## Lỗi thường gặp

| Lỗi | Nguyên nhân có thể |
|---|---|
| `AUTH_ERROR` | API key sai / hết hạn. Dán lại trong Cài đặt → Dịch vụ. |
| `QUOTA_ERROR` | Vượt giới hạn gói. |
| `CONNECTION_ERROR` | Mạng bị chặn / firewall. Thử lại từ mạng khác. |
