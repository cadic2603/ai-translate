---
description: Cài FFmpeg để AI Translate có thể giải mã âm thanh và video cho tạo phụ đề, tổng hợp giọng nói và lồng tiếng video — bắt buộc cho tính năng media.
---

# FFmpeg

FFmpeg cần thiết cho mọi luồng làm việc với âm thanh / video:

- **Tạo phụ đề** — giải mã âm thanh nguồn cho STT
- **Tạo giọng nói** — ghép các clip TTS theo thời điểm thành một file
- **Lồng tiếng** — STT → TTS → mux ngược vào video
- **Dịch trực tiếp** — khi bắt âm thanh hệ thống đi qua `parec`

Nó không được đóng gói sẵn — cài một lần trên hệ thống của bạn.

## Cài đặt

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    Hoặc, nếu muốn bản build đầy đủ hơn, bật [RPM Fusion](https://rpmfusion.org/Configuration)
    trước.

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    Tải bản static build từ <https://www.gyan.dev/ffmpeg/builds/>
    (bản "release essentials" là đủ), giải nén, rồi thêm thư mục `bin/`
    vào PATH:

    1. Nhấn **Win + R**, gõ `sysdm.cpl`, nhấn **Enter**
    2. **Advanced → Environment Variables → System variables → Path → Edit**
    3. **New** → dán đường dẫn tuyệt đối tới thư mục `bin` của FFmpeg
    4. **OK** thoát ra, khởi động lại các terminal đang mở

## Xác minh

```bash
ffmpeg -version
```

Bạn nên thấy banner phiên bản kèm `--enable-libx264 --enable-libvpx`
trong dòng cấu hình. Nếu thấy "command not found", việc cài đặt chưa
nằm trên PATH.

## Kiểm tra pre-flight trong ứng dụng

Trang Tạo giọng nói / Lồng tiếng gọi `shutil.which("ffmpeg")` trước
khi bắt đầu. Nếu không tìm thấy FFmpeg, bạn sẽ thấy hộp thoại lỗi thân
thiện với link quay về đây, không phải tác vụ chạy giữa chừng rồi hỏng.

## Lỗi thường gặp

| Lỗi | Ý nghĩa |
|---|---|
| `FFMPEG_NOT_FOUND` | `ffmpeg` không có trên PATH lúc trang cố chạy. Cài (như trên) rồi khởi động lại ứng dụng. |

Trong MCP server (`ait-mcp`), cùng lỗi này được bọc lại thành thông
điệp dễ đọc:

> *"FFmpeg is required to decode this audio/video file but is not
> installed or not on PATH. Install FFmpeg and try again."*
