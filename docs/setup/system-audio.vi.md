---
description: Bắt âm thanh hệ thống trên Linux, macOS và Windows cho trang Dịch trực tiếp của AI Translate — dịch mọi âm thanh đang phát trên máy bạn theo thời gian thực.
---

# Bắt âm thanh hệ thống (Live)

Trang **[Dịch trực tiếp](../features/live-translation.md)** có thể bắt
**âm thanh hệ thống** (mọi thứ đang phát qua loa) để bạn phụ đề / dịch
mọi media — cuộc gọi Zoom, YouTube, Netflix, game, âm thanh hệ thống.

Trong **Cài đặt → Trực tiếp → Nguồn âm thanh** (hoặc combo ở đầu trang
Dịch trực tiếp), chọn:

- **Microphone** — chỉ mic của bạn
- **Âm thanh hệ thống** — chỉ những gì đang phát qua loa
- **Cả hai** — trộn cả hai (tốt khi tường thuật trên media hoặc bắt cuộc
  họp lai)

Khi chọn **Âm thanh hệ thống** hoặc **Cả hai**, ứng dụng điều phối tới
backend bắt âm phù hợp cho OS. Một banner cảnh báo inline với link cài
đặt có thể nhấp xuất hiện nếu OS chưa đáp ứng điều kiện, nên bạn không
cần bắt đầu phiên mới biết thiếu gì đó.

## Linux (PulseAudio / PipeWire)

Chạy được ngay trên mọi distro hiện đại.

Ứng dụng dùng `parec` (PulseAudio Recorder) để tap **monitor source**
của default sink. Lớp tương thích PulseAudio của PipeWire làm việc này
trong suốt — bạn không cần PulseAudio thuần.

```bash
parec --version    # nên in ra phiên bản
```

Nếu thiếu `parec`, banner cảnh báo phát hiện package manager của distro
và in trực tiếp lệnh cài đặt — ví dụ:

> System audio capture needs PulseAudio or PipeWire — run `sudo apt-get install pulseaudio`.

Phát hiện trên apt-get / dnf / pacman / zypper / apk; bạn có thể
copy-paste lệnh trực tiếp vào terminal.

## macOS

CoreAudio không expose âm thanh hệ thống nguyên bản, nên bạn cần một
**thiết bị loopback ảo** — cài một trong:

- **[BlackHole](https://existential.audio/blackhole/)** — miễn phí, mã nguồn mở
- **[Loopback](https://rogueamoeba.com/loopback/)** — có phí, GUI bóng bẩy
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — tùy chọn miễn phí cũ
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — có phí

Ứng dụng tự phát hiện bất kỳ thiết bị nào qua `ffmpeg -f avfoundation -list_devices`
và dùng cái đầu tiên khớp. Không cần đặt loopback làm output / input mặc
định — việc bắt âm xảy ra trực tiếp qua backend avfoundation của `ffmpeg`.

Sau khi cài, chỉ cần chọn **Âm thanh hệ thống** trong combo trang
Live và banner cảnh báo biến mất.

## Windows

Nguyên bản — **không cần phần mềm ngoài** trong hầu hết trường hợp.

Ứng dụng nói chuyện trực tiếp với **WASAPI loopback** qua package Python
[`soundcard`](https://github.com/bastibe/SoundCard) (cài tự động với
ứng dụng trên Windows). Đây là cùng API loopback nguyên bản mà các app
desktop Tauri / Rust dùng; nó bắt output của loa mặc định không cần
cable ảo.

Nếu vì lý do nào đó WASAPI loopback không khả dụng (Windows phiên bản
cũ, driver audio bất thường), ứng dụng fallback về `ffmpeg -f dshow`
với một thiết bị DirectShow loopback ảo. Chọn một trong:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — miễn phí, cung cấp `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — miễn phí, xuất hiện dưới dạng `CABLE Output (VB-Audio Virtual Cable)`
- **Stereo Mix (Realtek Audio)** — tùy chọn cũ trên bo mạch, thường bị tắt mặc định

Ứng dụng dò các tùy chọn này theo thứ tự và dùng cái đầu tiên có sẵn.

## Tại sao "Cả hai" bắt cả giọng bạn VÀ âm thanh hệ thống

Ở chế độ **Cả hai**, ứng dụng mở HAI luồng bắt âm song song — mic của
bạn qua `sounddevice`, âm thanh hệ thống qua backend OS-specific ở trên —
và trộn ở mức từng block sample. Đây là chế độ phù hợp khi tường thuật
trên video, hoặc bắt cả hai phía của cuộc họp lai (giọng bạn cộng với
người tham dự qua loa).

> **Mẹo:** nếu bạn nghe echo hoặc nhận phụ đề trùng, có nghĩa âm thanh
> hệ thống đang lọt qua microphone (loa to → mic bắt được). Chuyển sang
> **chỉ Âm thanh hệ thống**, hoặc dùng tai nghe.

## Khắc phục sự cố

| Triệu chứng | Nguyên nhân có thể |
|---|---|
| Trang Live khởi động nhưng không có phụ đề | Sai nguồn âm thanh, hoặc mic mặc định bị mute |
| Có phụ đề cho giọng bạn nhưng không có cho video YouTube | Điều kiện âm thanh hệ thống chưa cài (banner sẽ hiện hướng dẫn cài) |
| Phụ đề bị nhân đôi (echo) | Chế độ "Cả hai" bắt âm thanh hệ thống hai lần — một lần từ loa qua mic, một lần qua loopback. Chuyển sang chỉ Âm thanh hệ thống hoặc dùng tai nghe |
| Banner vẫn hiện sau khi cài phần mềm thiếu | Đổi tab rồi quay lại — banner check lại khi trang hiện |
| macOS: đã cài BlackHole nhưng banner vẫn còn | Xác nhận BlackHole có trong danh sách thiết bị âm thanh `ffmpeg -f avfoundation -list_devices true -i ""`; ứng dụng cần thấy nó ở đó |
| Windows: WASAPI loopback fail mà không có lỗi | Thử cài VB-Audio Virtual Cable làm fallback; Windows phiên bản cũ hoặc một số driver audio không expose loopback qua `soundcard` |
