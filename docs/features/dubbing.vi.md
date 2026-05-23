---
description: "Lồng tiếng video toàn bộ: phiên âm âm thanh, dịch phụ đề, tổng hợp giọng nói ở ngôn ngữ đích và mix vào video gốc."
---

# Lồng tiếng video

Pipeline đầy đủ **STT → Dịch → TTS → Mix** tạo ra file video ở ngôn ngữ
khác với track giọng được thay thế. Audio gốc bị bỏ; track lồng tiếng
mới được canh theo phụ đề.

## Bạn cần gì

- **FFmpeg** trên `PATH` — xem [Cài FFmpeg](../setup/ffmpeg.md).
- Backend STT (mặc định Whisper local, không cần cài đặt thêm)
- Backend TTS — Edge TTS (mặc định), ElevenLabs, Google Cloud TTS,
  Gemini TTS, hoặc **Piper TTS** (hoàn toàn offline; voice theo ngôn
  ngữ tải một lần qua **Cài đặt → Giọng → Piper TTS → Tải voice ngay**)
- Một **LLM** đã cấu hình cho bước dịch

## Hướng dẫn từng bước

1. Nhấp **Lồng tiếng** ở thanh bên.
2. Thả một hoặc nhiều file video (`.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`,
   `.wmv`).
3. Chọn **Ngôn ngữ nguồn** (ngôn ngữ *được nói* trong video) và
   **Ngôn ngữ đích** muốn lồng tiếng sang.
4. Nhấp **Bắt đầu lồng tiếng** (`Ctrl+Enter`).
5. Theo dõi tiến trình từng tác vụ trong bảng lịch sử. Nó đi qua bốn pha:

| Pha | Phạm vi | Đang làm gì |
|---|---|---|
| **STT** | 5–25% | Phiên âm audio nguồn |
| **Dịch** | 25–50% | LLM dịch từng dòng phụ đề |
| **TTS** | 50–90% | Tổng hợp giọng ngôn ngữ đích cho từng dòng |
| **Mix** | 90–100% | FFmpeg thay thế track audio |

6. Khi xong, nhấp **Mở** ở dòng để phát video đã lồng tiếng.

## File xuất

Với mỗi video đầu vào, bạn nhận bốn file trong thư mục xuất:

```
movie.mp4
movie_dubbed_en_fr.mp4              ← video đã lồng tiếng
movie_subtitle_en.srt               ← phụ đề ngôn ngữ gốc
movie_subtitle_fr.srt               ← phụ đề đã dịch
movie_voice_fr.mp3                  ← track giọng tổng hợp
```

## Tiếp tục từ lần dừng / crash

Pipeline checkpoint sau mỗi pha. Nếu bạn nhấp **Dừng**, thoát ứng dụng,
hoặc crash, nhấp **Tiếp tục** ở dòng đó sẽ resume từ pha hoàn tất gần
nhất — bạn không tốn lại cho STT hay dịch nếu đã xong.

Nhấp chuột phải vào mục Done / Failed để có các tùy chọn:

- **Tiếp tục** — resume từ checkpoint cuối, không hỏi lại.
- **Lồng tiếng lại** — mở lại bộ chọn ngôn ngữ; nếu bạn chọn target mới,
  checkpoint dịch và TTS bị bỏ (bạn không tốn lại cho STT). Chọn cùng
  target tương đương chạy lại từ checkpoint cuối, giống như Tiếp tục.
- **Mở** — phát video đã lồng tiếng.

## Lưu ý

!!! warning "Đồng bộ môi"
    Lồng tiếng khớp *thời điểm* của audio nguồn, không phải chuyển động
    môi. Các dòng dịch dài hơn nhiều so với gốc sẽ nghe vội; ngắn hơn
    nhiều sẽ để lại khoảng lặng. Để lồng tiếng chuyên nghiệp, thường
    cần re-time thủ công sau lần này — đó là tính năng tương lai.

!!! tip "Kiểm tra pre-flight"
    Trang xác thực FFmpeg + key của backend TTS trước khi bắt đầu. Thiếu
    key → hộp thoại thân thiện, không có dub chạy nửa chừng. Khi chọn
    **Piper TTS**, nó cũng kiểm tra voice Piper theo ngôn ngữ có trên ổ
    đĩa không; thiếu voice → hộp thoại với nút **Mở cài đặt** đưa bạn
    vào thư viện voice, để không tốn thời gian STT + dịch rồi fail ở bước TTS.

!!! tip "Đổi ngôn ngữ đích"
    Khi đổi target, pipeline bỏ checkpoint dịch + TTS (nội dung của chúng
    không còn hợp lệ với ngôn ngữ mới) nhưng giữ checkpoint STT — bạn
    tiết kiệm chi phí phiên âm.

## Phím tắt

| Phím tắt | Hành động |
|---|---|
| `Ctrl+Enter` | Bắt đầu lồng tiếng |
| `Ctrl+O` | Duyệt |
| `Ctrl+F` | Focus tìm kiếm lịch sử |
| `Ctrl+P` | Tạm dừng hàng đợi đang chạy |
| `Ctrl+G` | Tiếp tục hàng đợi đang chạy |

`Ctrl+P` / `Ctrl+G` bị tạm tắt khi ô nhập text đang focus, nên không
xung đột với gõ phím.
