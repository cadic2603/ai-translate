---
description: Ghi âm micrô đa nền tảng cho dịch trực tiếp.
---

# Thiết lập PortAudio (Micrô)

Tính năng [Dịch Trực tiếp](../features/live-translation.md) sử dụng gói Python `sounddevice`, gói này dựa vào thư viện C PortAudio để truy cập thiết bị micrô trên tất cả các hệ điều hành. Hầu hết người dùng cần cài đặt phụ thuộc cấp hệ thống này.

## Windows
Các tệp wheel được biên dịch sẵn cho `sounddevice` và `PyAudio` thường đóng gói sẵn mã nhị phân PortAudio trên Windows. Thường không cần cài đặt thủ công toàn hệ thống. Nếu bạn gặp lỗi, hãy đảm bảo trình điều khiển âm thanh của bạn đã được cập nhật.

## macOS
Sử dụng Homebrew để cài đặt PortAudio:

```bash
brew install portaudio
```

## Linux
Tên gói phụ thuộc vào bản phân phối của bạn. Phải cài đặt gói phát triển (thường kết thúc bằng `-dev` hoặc `-devel`) để Python có thể xây dựng các ràng buộc C nếu không có tệp wheel biên dịch sẵn.

=== "Ubuntu / Debian / Mint"

    ```bash
    sudo apt-get install portaudio19-dev
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install portaudio-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S portaudio
    ```

## Khắc phục sự cố

Nếu ứng dụng tiếp tục báo cáo không thể truy cập micrô sau khi cài đặt:

1. Đảm bảo ứng dụng dòng lệnh (hoặc môi trường màn hình) của bạn có quyền truy cập micrô (đặc biệt là trên macOS).
2. Khởi động lại ứng dụng (hoặc dòng lệnh/máy chủ MCP) để nó nhận diện đường dẫn thư viện mới.
