---
description: Kết nối ElevenLabs vào AI Translate cho TTS neural chất lượng cao — tạo voiceover trên 30+ ngôn ngữ với giọng nói tự nhiên, biểu cảm.
---

# ElevenLabs (TTS)

Text-to-speech neural cao cấp. Được dùng bởi trang **[Tạo giọng nói](../features/generate-voice.md)**,
**[Lồng tiếng](../features/dubbing.md)**, và **[Dịch trực tiếp](../features/live-translation.md)**
khi bạn chọn ElevenLabs làm phương thức TTS.

## Lấy API key

1. Đăng ký tại <https://elevenlabs.io>
2. Mở <https://elevenlabs.io/app/settings/api-keys>
3. Nhấp **+ Create New Key**, đặt tên (ví dụ "ai-translate"), sao chép
   key (dạng `sk_...`)

Gói miễn phí cho bạn ~10.000 ký tự / tháng, đủ để dùng thử. Sử dụng
cho production bắt đầu từ ~$5/tháng.

## Cấu hình trong ứng dụng

Trong **Cài đặt → Dịch vụ**:

1. Dán key vào **ElevenLabs API key** → **Lưu**
2. Nhập **Voice ID** ưa thích vào **Voice ID** (tìm ID tại
   <https://elevenlabs.io/app/voice-lab>; sao chép ID từ URL của giọng).
   Để trống để ElevenLabs chọn mặc định.

Trong **Cài đặt → Giọng**:

1. Đặt **Phương thức TTS** thành **ElevenLabs**
2. Chọn **Model ElevenLabs**:

    | Model | Phù hợp với |
    |---|---|
    | `eleven_multilingual_v2` (mặc định) | Dùng chung, cân bằng độ trễ/chất lượng |
    | `eleven_v3` | Chất lượng cao nhất (dùng cho lồng tiếng production) |
    | `eleven_flash_v2_5` | Độ trễ thấp nhất (dùng cho Dịch trực tiếp) |

## ElevenLabs hỗ trợ gì

| Trang | Dùng ElevenLabs khi |
|---|---|
| **Tạo giọng nói** | Bạn muốn voiceover chất lượng cao từ file phụ đề |
| **Lồng tiếng** | Bạn muốn track lồng tiếng chất lượng cao trên video đã dịch |
| **Dịch trực tiếp** | Bạn muốn nghe phụ đề đã dịch theo thời gian thực |

## Voice cloning

ElevenLabs hỗ trợ clone giọng tùy chỉnh (gói trả phí). Khi đã clone giọng
trên trang ElevenLabs, dán Voice ID vào **Cài đặt → Dịch vụ → Voice ID**
và pipeline lồng tiếng / tạo giọng sẽ dùng nó.

## Lưu ý

!!! warning "Kiểm tra pre-flight"
    Trang Tạo giọng nói / Lồng tiếng kiểm tra ElevenLabs API key đã
    được đặt *trước* khi bắt đầu. Nếu thiếu, bạn sẽ nhận hộp thoại
    thân thiện chỉ về Cài đặt, không phải tác vụ chạy nửa chừng rồi hỏng.

!!! tip "Chế độ Live tự động fallback"
    Trên trang **Dịch trực tiếp**, nếu đã chọn ElevenLabs nhưng chưa
    cấu hình key, ứng dụng sẽ fallback về **Edge TTS** (miễn phí) và
    thông báo ở dòng trạng thái để bạn sửa khi tiện.

!!! info "FFmpeg vẫn bắt buộc"
    ElevenLabs trả về byte audio; ứng dụng vẫn dùng FFmpeg để chuyển
    đổi định dạng và ghép các clip có thời điểm thành một file. Xem
    [Cài FFmpeg](ffmpeg.md).

## Lỗi thường gặp

| Lỗi | Nguyên nhân có thể |
|---|---|
| `AUTH_ERROR` | API key sai / hết hạn. Dán lại trong Cài đặt → Dịch vụ. |
| `QUOTA_ERROR` | Hết giới hạn ký tự gói miễn phí, hoặc cạn gói trả phí. |
| `MODEL_NOT_FOUND` | Model ElevenLabs đã chọn không còn khả dụng; chọn cái khác trong Cài đặt → Giọng. |
