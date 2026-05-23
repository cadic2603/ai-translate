---
description: Chẩn đoán sự cố AI Translate — thiếu font, lỗi FFmpeg, sự cố converter LibreOffice, lỗi cài OCR và xác thực API LLM.
---

# Khắc phục sự cố

Lỗi thường gặp, ý nghĩa và cách khắc phục.

## Lỗi cài đặt

### "LLM is not configured"

Bạn chưa thêm API key. Mở ứng dụng desktop → **Cài đặt → LLM** → dán
một key. Xem [Nhà cung cấp LLM](setup/llm-providers.md) để có hướng
dẫn đầy đủ.

### `AUTH_ERROR`

API key LLM sai hoặc hết hạn.

- **Gemini** — tạo key mới tại <https://aistudio.google.com/apikey>,
  dán lại trong **Cài đặt → LLM**.
- **Nhà cung cấp tùy chỉnh** — xác thực key còn hợp lệ (curl endpoint
  thủ công với cùng header `Authorization: Bearer …`). Nếu endpoint đã
  chuyển, cập nhật trường **Endpoint API** luôn.

### `QUOTA_ERROR`

Bạn đã chạm giới hạn gói miễn phí hoặc gói trả phí.

- **Gemini gói miễn phí** — quota request mỗi ngày khác nhau theo model
  (xem <https://ai.google.dev/gemini-api/docs/rate-limits>). Chờ một
  ngày, hoặc nâng cấp trả phí.
- **OpenAI / khác** — kiểm tra dashboard billing. Nhiều nhà cung cấp có
  "spend cap" tạm dừng request khi bạn đạt mức.

### `MODEL_NOT_FOUND`

Tên model bạn chọn không có sẵn.

- Nhà cung cấp tùy chỉnh — đảm bảo model có trong danh sách **Models**
  phân tách bằng dấu phẩy ở **Cài đặt → LLM**.
- Danh sách Gemini tích hợp — chuyển sang model có tài liệu trong
  **Cài đặt → LLM → Model Gemini mặc định**.

### `VISION_NOT_SUPPORTED`

Bạn chọn model không hỗ trợ vision và cố dịch ảnh / PDF scan. Chuyển
sang model có tên chứa `flash`, `pro` hoặc `vision` (ví dụ `gpt-4o`
cho OpenAI, bất kỳ biến thể Gemini Flash hoặc Pro hiện tại cho Gemini).

## Lỗi audio / video

### `FFMPEG_NOT_FOUND`

FFmpeg không có trên PATH. Xem [Cài FFmpeg](setup/ffmpeg.md) để có
lệnh cài cho OS của bạn.

MCP server bọc lại lỗi này thành: *"FFmpeg is required to decode this
audio/video file but is not installed or not on PATH."*

### Trang Live không hiện phụ đề

- **Sai nguồn audio** — mở **Cài đặt → Trực tiếp → Nguồn âm thanh** và
  đảm bảo khớp cái bạn thực sự muốn (Microphone / System / Cả hai).
- **Mic bị mute** — kiểm tra cài đặt âm thanh OS; ứng dụng dùng thiết
  bị input mặc định.
- **Âm thanh hệ thống chưa cài** — xem
  [Bắt âm thanh hệ thống](setup/system-audio.md) cho các bước loopback
  trên macOS / Windows.

### Đầu ra giọng im lặng / trống

- **ElevenLabs không có key** — trang Voice hiện hộp thoại pre-flight
  thân thiện; nếu lọt qua, file có thể là byte trống. Kiểm tra
  **Cài đặt → Dịch vụ → ElevenLabs API key**.
- **Lỗi mạng Edge TTS** — Edge TTS cần internet; nếu firewall chặn
  `speech.platform.bing.com`, chuyển sang ElevenLabs, Google Cloud TTS,
  hoặc **Piper TTS** (hoàn toàn offline).

### Hộp thoại "Piper voice not installed"

Trang Voice / Dubbing / Translate Text pre-flight rằng voice Piper cho
ngôn ngữ đích của bạn có trên ổ đĩa trước khi worker bắt đầu. Nếu không,
bạn sẽ thấy modal với nút **Mở cài đặt**.

Để tải voice:

1. Nhấp **Mở cài đặt** trong hộp thoại (hoặc mở **Cài đặt → Giọng** thủ công).
2. Đảm bảo **Phương thức TTS** đặt thành **Piper TTS**.
3. Nhấp **Tải voice ngay** để mở hộp thoại thư viện voice.
4. Tìm dòng ngôn ngữ đích của bạn, rồi nhấp **Female voice** hoặc
   **Male voice** kế bên. Voice là file ONNX ~25–60 MB tải từ
   HuggingFace; một lần cho mỗi ngôn ngữ.
5. Đóng hộp thoại và chạy lại tác vụ dịch / voice / dub của bạn.

Nếu ngôn ngữ đích không có trong danh sách, nó không có Piper hỗ trợ —
engine âm thầm fallback về Edge TTS lúc tổng hợp, nên bạn không cần
tải gì cả. 13 ngôn ngữ không có voice Piper hôm nay: Belarusian,
Bengali, Tiếng Trung (Phồn thể), Tiếng Croatia, Tiếng Estonia, Tiếng
Hebrew, Tiếng Nhật, Tiếng Khmer, Tiếng Hàn, Tiếng Lithuania, Tiếng Mã
Lai, Tiếng Mông Cổ, Tiếng Thái.

Trang **Dịch trực tiếp** là nơi *không* hiển thị hộp thoại này — gián
đoạn live stream với modal sẽ tệ hơn fallback, nên các trường hợp
thiếu voice ở đây âm thầm đi sang Edge TTS.

## Lỗi dịch tài liệu

### Dịch PDF fail ở trang cụ thể

PDF dùng checkpoint từng trang — trang thành công không bị làm lại.
Trang fail log stack vào `app.log`; thủ phạm thường gặp:

- Trang là **scan không có lớp text** và OCR chưa cấu hình. Cài
  **Cài đặt → OCR** (xem [Engine OCR](setup/ocr-engines.md)).
- Trang chứa **bố cục toán phức tạp** mà LLM làm hỏng. Thử model mạnh
  hơn (biến thể Pro thay vì Flash).

### Dịch Office làm hỏng định dạng

- **Định dạng hiện đại** (`.docx`, `.xlsx`, `.pptx`) — định dạng được
  giữ nguyên từng run qua HTML round-trip. Nếu bạn thấy thẻ `<b>` lạc
  trong output, LLM chưa đóng chúng — chạy lại với model mạnh hơn.
- **Định dạng cũ** (`.doc`, `.xls`, `.ppt`) — bật **Cài đặt → Bản dịch
  → Auto-convert legacy** để có độ chính xác tốt hơn nhiều. Pipeline
  chuyển sang `.docx` trước, dịch, rồi chuyển ngược.

### Hàng đợi dịch dừng giữa batch

Thoát ứng dụng và kiểm tra cơ sở dữ liệu:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

Các dòng `Translating` không được động đến trong vài phút có nghĩa
worker crash âm thầm. Khởi chạy lại ứng dụng desktop — nó tự resume
các tác vụ Pending / Translating khi khởi động.

## Vấn đề dùng chung

### Kéo thả nhiều file nhưng có vẻ chỉ dịch 1 file

Thả từng file một, HOẶC kiểm tra cột **Files** trong header hàng đợi —
nó nên hiển thị đúng số lượng file bạn đã thả. Giới hạn 100 file hiện thông báo khi vượt quá.

### Sidebar hiện spinner mãi mãi

Cho thấy worker vẫn được đánh dấu là đang chạy. Thoát ứng dụng sạch
(không SIGKILL) — hook autouse cleanup reset cờ. Nếu SIGKILL để lại
state kẹt, xóa worker DB thủ công:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Log nằm ở đâu {: #where-are-the-logs }

| OS | Đường dẫn |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Log luôn ghi DEBUG+ bất kể độ verbose console. Output console mặc định
là INFO+; truyền `--verbose` cho CLI để mirror toàn bộ file log lên stdout.

## Vẫn bị kẹt?

- Xem [FAQ](faq.md) cho các câu hỏi cấp thiết kế.
- Báo cáo vấn đề tại <https://github.com/cadic2603/ai-translate/issues>
  với: OS, phiên bản Python, lệnh fail, phần liên quan của `app.log`,
  và mô tả những gì bạn đã mong đợi.
