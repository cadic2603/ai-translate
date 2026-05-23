---
description: "Dịch lời nói thời gian thực: phiên âm và dịch microphone hoặc âm thanh hệ thống live với backend Whisper hoặc Soniox."
---

# Dịch trực tiếp

Phụ đề và bản dịch theo thời gian thực từ microphone, âm thanh hệ thống,
hoặc cả hai — kèm cửa sổ overlay luôn-trên-cùng tùy chọn để phụ đề
nằm trên thứ bạn đang xem.

## Bạn có thể làm gì

- **Phụ đề cuộc họp trực tiếp** — phụ đề cuộc gọi Zoom / Meet / Teams
  ở ngôn ngữ khác mà không cần tham gia với tư cách bot phiên dịch.
- **Học ngôn ngữ thời gian thực** — phụ đề nội dung tiếng nước ngoài
  (phim, podcast, bài giảng) với ngôn ngữ mẹ đẻ làm track dịch.
- **Phụ đề toàn hệ thống** — bắt âm thanh hệ thống để phụ đề YouTube /
  Netflix / bất cứ thứ gì phát qua loa.

## Bạn cần gì

- **FFmpeg** trên `PATH` — xem [Cài FFmpeg](../setup/ffmpeg.md).
- Một backend STT, một trong:
    - **faster-whisper** — local, offline, miễn phí, mặc định
    - **Soniox** — cloud, có phí, phân biệt người nói thời gian thực.
      Xem [Cài Soniox](../setup/soniox.md).

- Cho **bắt âm thanh hệ thống**, backend phù hợp cho từng OS được tự
  chọn: Linux dùng `parec` (PulseAudio / PipeWire), Windows dùng WASAPI
  loopback nguyên bản (không cần phần mềm ngoài trong hầu hết trường
  hợp), macOS dùng `ffmpeg -f avfoundation` với thiết bị loopback ảo
  (BlackHole / Loopback / v.v.). Một banner cảnh báo inline với link
  cài đặt có thể nhấp xuất hiện nếu thiếu thứ gì đó. Xem
  [Cài đặt → Âm thanh hệ thống](../setup/system-audio.md) để có hướng
  dẫn cài đặt đầy đủ theo OS.

## Hướng dẫn từng bước

1. Nhấp **Dịch trực tiếp** ở thanh bên.
2. Cấu hình một lần trong **Cài đặt → Trực tiếp**:

    - **Ngôn ngữ nguồn** (ngôn ngữ được nói)
    - **Ngôn ngữ đích** (hoặc để trống nếu chỉ phiên âm)
    - **Nguồn âm thanh**: Microphone / Âm thanh hệ thống / Cả hai
    - **Phương thức STT**: Whisper / Soniox

3. Quay lại trang Live, nhấp **Bắt đầu nghe** (`Ctrl+Enter`).
4. Bản phiên âm điền vào ô chính theo từng card. Cửa sổ **Overlay** nổi
   cũng hiển thị phụ đề (kéo nó tới đâu cũng được).
5. Nhấp **Dừng** để kết thúc phiên.

## Khu vực hiển thị transcript

Chọn bố cục ở thanh công cụ:

- **Xếp chồng lên nhau** — gốc + dịch, một trên một dưới
- **Hiển thị cạnh nhau** — gốc bên trái, dịch bên phải
- **Chỉ nguồn** / **Chỉ bản dịch**

Các nút thanh công cụ dùng hậu tố **`ON`** / **`OFF`** để liếc qua biết
trạng thái — ví dụ `TTS ON`, `TTS OFF`, `Timestamps ON`, `Overlay OFF`.

Bật/tắt **timestamps** với icon đồng hồ. Bật/tắt **phát TTS** của các
dòng đã dịch với icon loa. Tuân theo lựa chọn **Cài đặt → Giọng →
Phương thức TTS** — Edge TTS (mặc định), ElevenLabs, Google Cloud TTS,
Gemini TTS, hoặc **Piper TTS** (hoàn toàn offline). Khi chọn Piper,
voice theo ngôn ngữ bị thiếu sẽ **âm thầm fallback về Edge TTS** giữa
chừng — không có pre-flight modal trên trang này, vì chặn luồng live
bằng hộp thoại tải về sẽ tệ hơn fallback.

## Cửa sổ overlay

Cửa sổ công cụ kéo được, đổi kích thước được, luôn-trên-cùng. Phím tắt:

| Phím tắt | Hành động |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Giảm / tăng độ trong suốt |
| `Ctrl+Arrow` | Di chuyển overlay |
| `Ctrl+0` / `Ctrl+9` | To ra / nhỏ lại |

Vị trí, kích thước, độ trong suốt và cỡ font được giữ giữa các phiên.

### Đồng bộ trực tiếp với Cài đặt

Điều khiển kích thước phông và độ trong suốt hoạt động hai chiều:
kéo thanh trượt **Kích thước phông** hoặc **Độ trong suốt** trong
**Cài đặt → Dịch trực tiếp → Cấu hình lớp phủ** sẽ cập nhật lớp
phủ đang mở theo thời gian thực; và ngược lại, nhấn `+` / `-` /
`Ctrl+[` / `Ctrl+]` bên trong lớp phủ sẽ cập nhật các thanh
trượt trong Cài đặt. Không cần khởi động lại lớp phủ.

### Trạng thái rỗng (placeholder)

Trước khi có bất kỳ âm thanh nào được ghi, lớp phủ hiển thị một
placeholder ("Nhấn Bắt đầu..." khi nhàn rỗi / "Đang nghe..."
sau khi nhấn Bắt đầu) phản chiếu trạng thái rỗng của cửa sổ
chính — chuyển đổi đồng bộ với pill trạng thái đang chạy.
Placeholder co giãn theo chiều rộng × chiều cao hiện tại của
lớp phủ để vẫn dễ đọc ở mọi kích thước cửa sổ.

### Chế độ phụ đề tối giản

Hộp kiểm **Hiển thị phụ đề tối giản** trong Cài đặt → Dịch
trực tiếp → Cấu hình lớp phủ ẩn nhãn thời gian và người nói
trên lớp phủ nhưng vẫn giữ chúng hiển thị trên cửa sổ chính.
Hữu ích khi lớp phủ được chia sẻ với khán giả (chế độ thuyết
trình / chia sẻ màn hình) nhưng bạn vẫn muốn xem đầy đủ
metadata trong góc làm việc. Tùy chọn này chỉ áp dụng cho lớp
phủ — không thay đổi tùy chỉnh "Nhãn người nói" cho cửa sổ
chính.

## Lưu transcript

Nhấp **Lưu transcript** để xuất phiên thành file `.txt` với timestamp,
người nói, dòng gốc và dòng dịch.

## Chọn backend STT

| Backend | Phù hợp với | Chi phí | Độ trễ |
|---|---|---|---|
| **Whisper** (local) | Offline, nhạy cảm về quyền riêng tư | Miễn phí | Trung bình (~1 giây sau khi hết câu) |
| **Soniox** | Cuộc họp nhiều người nói | Có phí (~$0.005 / phút) | Thấp (thời gian thực) |

## Lưu ý

!!! warning "Chọn microphone"
    Đầu vào mic luôn dùng **thiết bị mặc định của OS** — không có bộ
    chọn trong ứng dụng (sounddevice expose quá nhiều plugin ảo ALSA
    vô dụng, và OS đã sở hữu UI chọn mic mặc định). Đặt mic ưa thích
    trong cài đặt âm thanh OS trước khi bắt đầu.

!!! warning "Giới hạn hàng đợi TTS (Backpressure)"
    Hàng đợi TTS bị giới hạn ở 3 câu gần nhất — audio cũ trong hàng đợi
    bị bỏ nếu tổng hợp không kịp. Cách này giữ phát giọng gần với phụ
    đề trên màn hình.

!!! tip "ElevenLabs không có key"
    Nếu đặt phương thức TTS là ElevenLabs nhưng không cấu hình API key,
    trang Live tự động fallback về Edge TTS và thông báo fallback ở
    dòng trạng thái.

## Phím tắt

| Phím tắt | Hành động |
|---|---|
| `Ctrl+Enter` | Bắt đầu / Dừng |
| `Ctrl+K` | Xóa log (có xác nhận) |
| `Ctrl+[` / `Ctrl+]` | Điều chỉnh độ trong suốt overlay |
