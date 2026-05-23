---
description: Tạo phụ đề SRT, VTT, ASS hoặc SSA từ bất kỳ âm thanh hay video nào — dùng Whisper hoặc Google Cloud Speech-to-Text cho phiên âm chất lượng cao.
---

# Tạo phụ đề (STT)

Phiên âm âm thanh hoặc video thành phụ đề có thời điểm. Bắt giọng nói
và xuất ra SRT / VTT / ASS / SSA — kèm tùy chọn dịch trong cùng một
lần chạy.

## Bạn cần gì

- **FFmpeg** trên `PATH` để giải mã âm thanh/video — xem [Cài FFmpeg](../setup/ffmpeg.md).
- Một backend phiên âm, một trong:
    - **faster-whisper** — local, offline, miễn phí (mặc định; không cần cài đặt thêm)
    - **Google Cloud Speech-to-Text** — cloud, có phí, chính xác hơn với
      âm thanh nhiễu. Xem [Cài Google Cloud](../setup/google-cloud.md).
    - **Soniox** — cloud, có phí, thời gian thực và phân biệt người nói.
      Xem [Cài Soniox](../setup/soniox.md).

## Hướng dẫn từng bước

1. Nhấp **Tạo phụ đề** ở thanh bên.
2. Thả một hoặc nhiều file âm thanh / video (`.mp3`, `.wav`, `.m4a`, `.flac`,
   `.ogg`, `.aac`, `.wma`, `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv`).
3. Chọn **Ngôn ngữ nguồn** (ngôn ngữ *được nói* trong âm thanh) — để
   `Tự động phát hiện` cho Whisper tự xác định.
4. Chọn **Ngôn ngữ đích** — chọn `Không dịch` để lấy bản phiên âm thuần,
   hoặc bất kỳ ngôn ngữ nào trong 45 ngôn ngữ hỗ trợ để dịch luôn trong
   cùng lần chạy.
5. Chọn **Định dạng xuất** (SRT / VTT / ASS / SSA).
6. Nhấp **Tạo** (hoặc `Ctrl+Enter`).
7. Theo dõi hàng đợi. Nhấp **Mở** khi hoàn tất.

## Chọn định dạng

| Định dạng | Phù hợp với |
|---|---|
| **SRT** | Phổ biến — gần như mọi trình phát đều hỗ trợ |
| **VTT** | HTML5 `<video>` với phần tử `<track>` |
| **ASS / SSA** | Karaoke, phụ đề có style, luồng fansub |

Bốn định dạng đều round-trip qua cùng parser, nên bạn có thể chuyển định
dạng xuất khi dịch lại mà không mất timing.

## Kích thước model Whisper

Chọn trong **Cài đặt → Phụ đề**:

| Model | Kích thước | Tốc độ | Độ chính xác |
|---|---|---|---|
| `tiny` | ~75 MB | rất nhanh | thấp |
| `base` (mặc định) | ~150 MB | nhanh | tạm ổn |
| `small` | ~500 MB | trung bình | tốt |
| `medium` | ~1.5 GB | chậm | cao |
| `large` | ~3 GB | rất chậm | tốt nhất |

Model tải khi dùng lần đầu và cache cục bộ. Trên kết nối chậm, lần chạy
đầu cảm giác lâu; các lần sau rất nhanh.

## So sánh phương thức STT

| Backend | Chi phí | Online? | Phân biệt người nói | Ngôn ngữ |
|---|---|---|---|---|
| **Whisper** (local) | Miễn phí | Không | Không | 99 |
| **Google Cloud STT** | Có phí | Có | Có (model `latest_long`) | 125+ |
| **Soniox** | Có phí | Có | Có (nhãn người nói trên từng token) | 60+ |

Chuyển trong **Cài đặt → Phụ đề → Phương thức STT**.

## Mẹo

- **Nút Dừng** — gián đoạn batch đang chạy. File còn xếp hàng phía sau
  giữ nguyên; bạn có thể resume sau.
- **Tạo lại** — nhấp chuột phải vào mục đã Done để chạy lại với định
  dạng / ngôn ngữ / phương thức STT khác.
- **Audio dài** — Whisper xử lý audio hàng giờ ổn; ước tính ~1 phút xử
  lý cho mỗi phút audio trên CPU với model `base`.

## Phím tắt

| Phím tắt | Hành động |
|---|---|
| `Ctrl+Enter` | Tạo |
| `Ctrl+O` | Duyệt |
| `Ctrl+F` | Focus tìm kiếm lịch sử |
