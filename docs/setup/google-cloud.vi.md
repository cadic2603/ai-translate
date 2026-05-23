---
description: Kết nối Google Cloud vào AI Translate cho Vision OCR, Speech-to-Text và Text-to-Speech — tạo API key và bật các dịch vụ liên quan.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

Một API key Google Cloud duy nhất cấp nguồn cho ba backend tùy chọn:

- **Vision OCR** — engine OCR có phí (miễn phí 1.000 ảnh / tháng)
- **Speech-to-Text v1** — STT có phí (miễn phí 60 phút / tháng)
- **Text-to-Speech v1** — TTS có phí (miễn phí 1 triệu ký tự / tháng cho WaveNet)

Bạn chỉ cần bật những API thực sự sử dụng.

## Lấy API key

1. [Tạo dự án Google Cloud](https://console.cloud.google.com/projectcreate)
2. Mở thư viện API: <https://console.cloud.google.com/apis/library>
3. Bật bất kỳ trong số:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [Tạo API key](https://console.cloud.google.com/apis/credentials):
   nhấp **+ Create Credentials → API key**
5. Sao chép key (dạng `AIza...`).

!!! tip "Hạn chế key"
    Trên trang chi tiết API key, ở mục **API restrictions**, hạn chế key
    chỉ cho những API bạn đã bật. Như vậy key bị rò rỉ không thể tạo
    chi phí trên dịch vụ bạn không định dùng.

## Cấu hình trong ứng dụng

Trong **Cài đặt → Dịch vụ**:

1. Dán vào **Google Cloud API key** → **Lưu**

Một key này giờ có sẵn cho cả ba dịch vụ Google.

## Bật từng dịch vụ

### Vision OCR

Trong **Cài đặt → OCR → Phương thức OCR = Google Cloud OCR**.

Vậy là xong — nó sẽ dùng cùng key từ Dịch vụ.

### Speech-to-Text

Trong **Cài đặt → Phụ đề → Phương thức STT = Google Cloud** (cho trang
Phụ đề / Giọng nói) hoặc **Cài đặt → Trực tiếp → Phương thức STT =
Google Cloud** (cho trang Dịch trực tiếp).

Trong **Cài đặt → Phụ đề → Model Google STT**, chọn model nhận dạng:

| Model | Phù hợp với |
|---|---|
| `latest_long` (mặc định) | Audio dài (phỏng vấn, bài giảng) |
| `latest_short` | Lệnh thoại, cụm từ ngắn |
| `phone_call` | Audio điện thoại (8 kHz) |
| `medical_dictation` / `medical_conversation` | Audio lĩnh vực y tế |

### Text-to-Speech

Trong **Cài đặt → Giọng → Phương thức TTS = Google Cloud TTS**.

Mặc định server tự chọn voice dựa trên ngôn ngữ và giới tính — đa số
người dùng chỉ cần vậy. Engine có hỗ trợ ghim một voice Google cụ thể
(ví dụ `en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`) nhưng chưa expose
ra UI Cài đặt; có thể đặt bằng cách sửa `voice/google_tts_voice_name`
trong `settings.ini` trực tiếp. Danh sách voice ID xem tại
<https://cloud.google.com/text-to-speech/docs/voices>.

## Lỗi thường gặp

| Lỗi | Nguyên nhân có thể |
|---|---|
| `AUTH_ERROR` | Key sai / hết hạn. Dán lại trong Cài đặt → Dịch vụ. |
| `API not enabled` | Bạn chưa bật API cụ thể (Vision / Speech / TTS) trên dự án Cloud này. |
| `QUOTA_ERROR` | Đã đạt giới hạn miễn phí cho API này. Chờ, hoặc nâng cấp billing. |
| `INVALID_ARGUMENT_ERROR` | Tên voice không tồn tại trong ngôn ngữ bạn đã chọn. |

## Cảnh giác chi phí

!!! warning
    Cả ba API Google đều thanh toán sau — khi bạn vượt mức miễn phí là
    bắt đầu bị tính phí mà không có giới hạn cứng. Đặt
    [cảnh báo budget](https://console.cloud.google.com/billing/budgets)
    trên dự án Cloud trước khi dùng khối lượng lớn.
