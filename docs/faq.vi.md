---
description: "Câu hỏi thường gặp về AI Translate: định dạng file hỗ trợ, miễn phí so với trả phí, dùng offline, lựa chọn nhà cung cấp LLM và chọn engine OCR."
---

# Câu hỏi thường gặp

## Tổng quan

### Có hoạt động offline không?

Phần lớn là có. Cụ thể:

- **Dịch** cần LLM. Gemini API miễn phí là online; **Ollama / LM Studio
  local** qua Cài đặt Nhà cung cấp tùy chỉnh hoàn toàn offline.
- **OCR** với **Tesseract** hoặc **EasyOCR** là offline.
- **STT** với **Whisper** (mặc định) là offline.
- **TTS** với **Edge TTS** (mặc định) là online; **ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** là online (miễn phí hoặc trả
  phí); **Piper TTS** là TTS neural hoàn toàn offline — không key,
  không gọi mạng sau khi bạn đã tải voice theo ngôn ngữ (file ONNX
  ~25–60 MB) qua **Cài đặt → Giọng → Piper TTS → Tải voice ngay**.

Để có cài đặt hoàn toàn air-gapped: Nhà cung cấp tùy chỉnh → LLM local,
Tesseract hoặc EasyOCR cho OCR, Whisper cho STT, và Piper TTS cho đầu
ra giọng nói.

### File đã dịch của tôi được lưu ở đâu?

Mặc định cạnh file gốc, với hậu tố `_translated_<src>_<tgt>` (ví dụ
`report_translated_en_fr.docx`). Ghi đè theo từng tính năng trong
**Cài đặt → Chung → Đường dẫn lưu trữ bản dịch**.

### Cài đặt của tôi được lưu ở đâu?

File INI ở:

| OS | Đường dẫn |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

API key sống trong keychain OS (không phải trong INI). Lịch sử dịch
sống trong DB SQLite ở thư mục dữ liệu.

### Dữ liệu của tôi được xử lý như thế nào?

- **Local-first** — văn bản không bao giờ rời máy bạn trừ khi bạn đang
  gọi dịch vụ LLM / OCR / STT / TTS cloud.
- **Không telemetry** — ứng dụng không phone home. Yêu cầu outbound
  duy nhất ứng dụng tự thực hiện là kiểm tra cập nhật GitHub-Releases
  tùy chọn (toggle trong **Cài đặt → Chung**); backend cloud chỉ gọi
  vendor tương ứng.
- **API key** — lưu trong keychain OS. Fallback của ứng dụng desktop là
  INI plaintext khi không có daemon keychain.

### Tôi có thể dịch Google Doc / trang Notion?

Không trực tiếp. Xuất sang `.docx` trước, dịch, rồi import file đã dịch
trở lại. Tương tự cho Notion (xuất Markdown / HTML), Confluence (xuất
`.docx`), v.v.

## Chọn model / engine

### Tôi nên dùng model LLM nào?

Cho hầu hết người dùng:

- **Bất kỳ biến thể Gemini Flash** — gói miễn phí, nhanh, tốt bất ngờ.
  Dùng cho dịch hàng ngày. Tên dạng `gemini-2.5-flash`,
  `gemini-3-flash-preview`, v.v., tùy theo cái gì hiện có.
- **Bất kỳ biến thể Gemini Pro** — trả theo token, chất lượng cao hơn.
  Dùng cho tài liệu quan trọng (pháp lý, kỹ thuật, khách hàng).
- **Ollama local** với model 7B-13B — khi bạn cần offline / quyền riêng tư.

Bộ chọn model theo trang nghĩa là bạn có thể dùng model nhanh cho dịch
kiểu chat và dành cái đắt tiền cho tài liệu.

### Tôi nên dùng engine OCR nào?

- **Tesseract** cho text in sạch ở các script chính. Miễn phí, offline,
  nhanh.
- **EasyOCR** cho script không thuộc Latin (đặc biệt CJK) và ảnh nhiễu hơn.
- **Google Cloud Vision** cho chữ viết tay, script hỗn hợp và độ chính
  xác cao nhất khi bạn có thể trả tiền.

### Tôi nên dùng phương thức STT nào?

- **Whisper local** cho offline / quyền riêng tư.
- **Soniox** cho bản ghi nhiều người nói — nhãn người nói round-trip
  vào SRT.
- **Google Cloud STT** cho audio điện thoại / y tế (model lĩnh vực
  của họ rất tốt).
- **Gemini Live** cho dịch speech-to-speech thời gian thực.

### Backend TTS nào?

- **Edge TTS** cho voice miễn phí, chất lượng cao.
- **ElevenLabs** cho voice cao cấp / branded / clone.
- **Google Cloud TTS** cho voice WaveNet ở các ngôn ngữ ít phổ biến nơi
  Edge phủ thưa.
- **Gemini TTS** cho voice prebuilt tự nhiên miễn phí tái sử dụng
  Gemini API key có sẵn của bạn.
- **Piper TTS** khi bạn cần đầu ra giọng **offline / air-gapped**.
  Đánh đổi: mỗi ngôn ngữ cần tải voice ~25–60 MB một lần qua
  **Cài đặt → Giọng → Piper TTS → Tải voice ngay**, và 13 trong 45
  ngôn ngữ của ứng dụng không có voice Piper (những cái đó âm thầm
  fallback về Edge TTS).

## Quy trình làm việc

### Tôi dịch cả thư mục thế nào?

Thả thư mục vào vùng thả của **Dịch tài liệu**. File hỗ trợ bên trong
(đệ quy) được xếp hàng; mọi thứ khác âm thầm bị bỏ qua. Có giới hạn
100 file mỗi lần thả; batch lớn hơn → chia thành nhiều lần thả.

### Tôi có thể tạm dừng và tiếp tục bản dịch?

Có. Thoát ứng dụng bất cứ lúc nào — tác vụ Pending / Translating resume
ở lần khởi động sau. Checkpoint từng tác vụ nghĩa là trang 47/100 của
PDF không bị làm lại khi bạn resume.

### Tôi có thể chỉnh bản dịch thủ công?

Cho **Dịch văn bản** — có, nhấp ô bên phải và gõ. Chỉnh sửa tự lưu
vào bản ghi lịch sử của mục.

Cho **Dịch tài liệu** — mở file đã dịch trong editor thông thường
(Word, LibreOffice, v.v.) và chỉnh ở đó. Ứng dụng không round-trip
chỉnh sửa trở lại lịch sử.

### Tôi có thể dịch hàng loạt một danh sách chuỗi?

Dùng CLI:

```bash
ait *.txt --target French
```

Hoặc cho chuỗi in-process (ví dụ chuỗi UI trích từ code), gọi tool MCP
`translate_text` với một danh sách, hoặc dùng Python API trực tiếp:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## Glossary

### Tại sao LLM không dùng glossary của tôi?

Ba thứ cần kiểm tra:

1. Bộ từ vựng đang được **kích hoạt** (checkbox đã tích).
2. Thuật ngữ nguồn trong glossary thực sự xuất hiện trong văn bản nguồn
   (nén theo lần gọi chỉ gửi LLM các mục khớp text batch — tiết kiệm
   token, nhưng nghĩa là thuật ngữ nguồn gõ sai sẽ vô hình).
3. Model đủ mạnh — `flash-lite` đôi khi bỏ qua hint mà `flash` và `pro`
   tôn trọng.

### Thuật ngữ glossary được khớp không phân biệt dấu?

Có. Cả tra cứu glossary và ô tìm kiếm trong trang Glossary đều dùng
hàm chuẩn hóa loại bỏ dấu và phân biệt hoa thường. Nên `cafe`, `Café`
và `CAFE` đều khớp một mục có nguồn là `Café`.

## Quyền riêng tư

### Bạn có thu thập dữ liệu sử dụng không?

Không. Ứng dụng không có analytics SDK. Kiểm tra cập nhật tùy chọn
poll một endpoint GitHub Releases duy nhất khi khởi động; nó toggle
được trong **Cài đặt → Chung**.

### API key của tôi có an toàn không?

Chúng được lưu trong keychain OS (Keychain trên macOS, Credential
Manager trên Windows, Secret Service trên Linux). Các tiến trình khác
không đọc được mà không có sự cho phép rõ ràng của bạn. Fallback (khi
không có daemon keychain — thường là server Linux headless) là INI
plaintext dưới thư mục cấu hình người dùng; ở chế độ đó key được bảo
vệ bằng quyền file nhưng không được mã hóa cryptographically.
