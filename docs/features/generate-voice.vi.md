---
description: Chuyển phụ đề thành audio nói với Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS hoặc Piper TTS offline — giữ timing SRT để tạo giọng chất lượng lồng tiếng.
---

# Tạo giọng nói (TTS)

Tổng hợp file phụ đề (có timing) hoặc văn bản tùy ý thành audio MP3 / WAV.
Năm backend TTS: Edge TTS (miễn phí), ElevenLabs (chất lượng cao),
Google Cloud TTS, Gemini TTS (gói miễn phí), và Piper TTS (offline).

## Bạn cần gì

- **FFmpeg** trên `PATH` — xem [Cài FFmpeg](../setup/ffmpeg.md).
- Một backend TTS, một trong:
    - **Edge TTS** — miễn phí, không cần key, mặc định. Dùng voice cloud
      của Microsoft Edge.
    - **ElevenLabs** — có phí, chất lượng cao nhất. Xem
      [Cài ElevenLabs](../setup/elevenlabs.md).
    - **Google Cloud TTS** — có phí, rất tốt. Xem
      [Cài Google Cloud](../setup/google-cloud.md).
    - **Gemini TTS** — gói miễn phí, voice prebuilt tự nhiên. Tái sử
      dụng Gemini API key có sẵn từ tab LLM — không cần cài đặt thêm.
    - **Piper TTS** — TTS neural hoàn toàn offline. Không API key, không
      gọi mạng — voice là file ONNX ~25–60 MB tải một lần qua
      **Cài đặt → Giọng → Piper TTS → Tải voice ngay**. 32 trong 45 ngôn
      ngữ của ứng dụng có voice Piper hôm nay; ngôn ngữ không có Piper
      sẽ âm thầm fallback về Edge TTS lúc tổng hợp.

## Hướng dẫn từng bước

1. Nhấp **Tạo giọng nói** ở thanh bên.
2. Thả một hoặc nhiều file phụ đề `.srt` / `.vtt` / `.ass` / `.ssa`.
3. Chọn **Ngôn ngữ** (tự phát hiện từ tên file phụ đề khi có thể —
   ví dụ `_translated_en_fr.srt` được phát hiện là Tiếng Pháp).
4. Chọn **Giới tính giọng** — `Nữ` hoặc `Nam`.
5. Chọn **Định dạng xuất** — `.mp3` (mặc định) hoặc `.wav`.
6. Nhấp **Tạo** (hoặc `Ctrl+Enter`).
7. Nhấp **Mở** ở dòng khi xong — file phát ở ứng dụng audio mặc định.

## File xuất

Bạn nhận một file audio đơn với các track giọng đặt tại timestamp của
mỗi phụ đề. Khoảng lặng được điền vào giữa các cue để audio đồng bộ
với timing gốc.

## Chọn backend TTS

| Backend | Chi phí | Voice | Ghi chú |
|---|---|---|---|
| **Edge TTS** | Miễn phí | Hàng trăm, mọi ngôn ngữ chính | Mặc định. Không cần cài. |
| **ElevenLabs** | Có phí (~$5/tháng gói thấp nhất) | Voice neural cao cấp, clone giọng | Chất lượng cao nhất. Voice ID đặt ở Cài đặt → Dịch vụ. |
| **Google Cloud TTS** | Có phí (~$4/M ký tự; 1 M miễn phí / tháng) | Voice WaveNet / Studio cho 50+ ngôn ngữ | Voice WaveNet tốt cho ngôn ngữ châu Âu. Mặc định server tự chọn voice dựa trên ngôn ngữ + giới tính. |
| **Gemini TTS** | Gói miễn phí (áp dụng quota Developer API) | Voice prebuilt tự nhiên cho 24+ ngôn ngữ — `Kore` (mặc định nữ) / `Puck` (mặc định nam) | Tái sử dụng Gemini API key từ tab LLM. Đầu ra mỗi lần gọi giới hạn ~30 giây; văn bản dài tự chunk theo ranh giới câu. |
| **Piper TTS** | Miễn phí, **offline** | Voice neural cho 32 trong 45 ngôn ngữ của ứng dụng | Không key, không mạng. Voice theo ngôn ngữ tải theo nhu cầu từ **Cài đặt → Giọng → Piper TTS → Tải voice ngay** (~25–60 MB mỗi voice). Pre-flight bắt voice thiếu trước khi bắt đầu. |

Chuyển trong **Cài đặt → Giọng → Phương thức TTS**.

## Đặc thù Piper TTS

Piper là backend TTS hoàn toàn offline duy nhất trong ứng dụng. Vài
điều cần biết:

- **Hộp thoại thư viện voice** — mở qua **Cài đặt → Giọng → Piper TTS
  → Tải voice ngay**. Mỗi dòng ngôn ngữ hiển thị nút tải `Female voice`
  và / hoặc `Male voice` (một số ngôn ngữ chỉ có một giới tính). Voice
  đến từ catalog
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
  trên HuggingFace.
- **Phạm vi** — 32 trong 45 ngôn ngữ của ứng dụng có voice Piper. 13
  ngôn ngữ không có (Belarusian, Bengali, Tiếng Trung (Phồn thể),
  Tiếng Croatia, Tiếng Estonia, Tiếng Hebrew, Tiếng Nhật, Tiếng Khmer,
  Tiếng Hàn, Tiếng Lithuania, Tiếng Mã Lai, Tiếng Mông Cổ, Tiếng Thái)
  âm thầm fallback về Edge TTS lúc tổng hợp để tổng hợp không bao giờ
  hard-fail vì thiếu voice.
- **Phân giải giới tính** — khi bạn chọn `Nữ`, engine thử voice nữ cho
  ngôn ngữ đó trước; nếu chỉ có voice nam, nó dùng nam thay (và ngược
  lại). Log ở mức INFO.
- **Cổng pre-flight** — trước khi tác vụ Voice bắt đầu, trang kiểm tra
  voice Piper theo ngôn ngữ có trên ổ đĩa. Nếu thiếu, bạn nhận hộp
  thoại modal với nút **Mở cài đặt** đưa bạn thẳng đến thư viện voice
  để tải mà không mất hàng đợi.

## Đặc thù Gemini TTS

Gemini TTS dùng `gemini-2.5-flash-preview-tts` qua Developer API. Vài
điều cần biết:

- **Chọn voice** theo giới tính hôm nay — Nữ ánh xạ `Kore`, Nam ánh xạ
  `Puck`. Cả hai đều là voice rõ, trung tính dùng được cho mọi ngôn
  ngữ mà không nghe quá đặc trưng.
- **Giới hạn độ dài đầu ra** — mỗi lần gọi API Gemini trả về tối đa
  ~30 giây speech. Ứng dụng chunk văn bản đầu vào dưới
  `_GEMINI_TTS_MAX_BYTES` (~2000 byte ≈ 30 giây) theo ranh giới câu,
  rồi nối các chunk qua FFmpeg. Bạn không gặp truncation với text phụ
  đề bình thường.
- **Định dạng audio** — Gemini xuất raw PCM 24 kHz mono s16le; ứng dụng
  transcode từng chunk sang MP3 (hoặc WAV nếu bạn chọn) nên file cuối
  khớp định dạng đầu ra đã chọn.
- **Vertex AI chưa được hỗ trợ cho TTS** — kể cả khi tab LLM của bạn
  được cấu hình cho Vertex, Gemini TTS vẫn cần Developer API key. Ứng
  dụng raise `AUTH_ERROR` ngay nếu thiếu.

## Model ElevenLabs

Ba model được expose:

| Model | Độ trễ | Chất lượng | Dùng cho |
|---|---|---|---|
| `eleven_multilingual_v2` (mặc định) | Trung bình | Cao | TTS chung |
| `eleven_v3` | Trung bình | Cao nhất | Studio / production |
| `eleven_flash_v2_5` | Thấp | Tốt | Thời gian thực / chế độ Live |

Cấu hình trong **Cài đặt → Giọng → Model ElevenLabs**.

## Mẹo

!!! tip "Tạo lại"
    Nhấp chuột phải vào dòng → **Tạo lại** để đổi giới tính giọng /
    phương thức TTS / định dạng mà không cần chạy lại bản dịch.

!!! tip "Kiểm tra pre-flight"
    Trang xác thực ElevenLabs API key (khi đã chọn) và sự sẵn sàng
    của FFmpeg trước khi bắt đầu. Bạn sẽ thấy hộp thoại thân thiện
    nếu thiếu thứ gì đó.

!!! warning "Dừng là nguyên tử"
    Nhấn **Dừng** giữa lúc tổng hợp và bạn sẽ không nhận MP3 viết dở
    trong thư mục xuất — file được viết vào vị trí tạm trước, rồi mới
    di chuyển về đích chỉ khi thành công.

## Phím tắt

| Phím tắt | Hành động |
|---|---|
| `Ctrl+Enter` | Tạo |
| `Ctrl+O` | Duyệt |
| `Ctrl+F` | Focus tìm kiếm lịch sử |
