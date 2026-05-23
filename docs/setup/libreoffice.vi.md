---
description: Cài LibreOffice để AI Translate có thể dịch định dạng Office cũ (.doc, .xls, .ppt) và file ODF (.odt, .ods, .odp) trên macOS và Linux.
---

# LibreOffice (định dạng Office)

Pipeline dịch Office chọn backend tốt nhất hiện có theo thứ tự:

1. **win32com** (Windows + MS Office đã cài) — độ chính xác cao nhất
2. **LibreOffice UNO** (đa nền tảng) — fallback khi không có win32com
3. **python-docx / openpyxl / python-pptx** (chỉ định dạng hiện đại) —
   fallback Python thuần khi không có cả hai phương thức trên

LibreOffice là **con đường duy nhất** cho `.doc` / `.xls` / `.ppt` cũ
trên Linux và macOS, và là con đường được khuyến nghị trên các nền tảng
đó cho cả Office hiện đại (độ chính xác tốt hơn backend Python thuần,
đặc biệt với bảng và đối tượng nhúng).

## Cài đặt

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    Hoặc tải từ <https://www.libreoffice.org/download/download/>.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    Ứng dụng desktop trên Windows thường dùng **win32com** với MS Office
    đã cài — LibreOffice là *fallback* khi thiếu MS Office. Cài từ
    <https://www.libreoffice.org/download/download/>.

## Xác minh

```bash
soffice --version
```

Nếu nhận "command not found" trên macOS, binary nằm ở
`/Applications/LibreOffice.app/Contents/MacOS/soffice`. Ứng dụng tự
phát hiện qua các đường dẫn cài đặt phổ biến, nhưng bạn có thể ghi
đè trong **Cài đặt → Chung → Đường dẫn LibreOffice** nếu cần.

## LibreOffice hỗ trợ gì

Khi LibreOffice là backend đang hoạt động:

| Tính năng | Ghi chú |
|---|---|
| **Office hiện đại** (`.docx`, `.xlsx`, `.pptx`) | Dùng làm fallback khi không có win32com |
| **Office cũ** (`.doc`, `.xls`, `.ppt`) | Bắt buộc — Python thuần không đọc được |
| **ODF** (`.odt`, `.ods`, `.odp`) | Dùng cho chuyển đổi round-trip khi **Auto-convert ODF** bật |
| **Auto-convert cũ / ODF → OOXML** | Bắt buộc |

## Tiến trình nền

Lần đầu cần LibreOffice, ứng dụng spawn một tiến trình `soffice` ở chế
độ headless và giữ sống xuyên suốt các lần dịch (`office_lifecycle.py`).
Nó tự tắt khi ứng dụng thoát.

## Lưu ý

!!! warning "Thời gian khởi động lần đầu"
    Lần dịch đầu tiên dùng LibreOffice phải chờ ~5-10 giây để `soffice`
    khởi tạo. Các lần dịch sau dùng lại tiến trình đó và nhanh.

!!! info "Log crash JVM"
    Thành phần Java của LibreOffice thỉnh thoảng tạo file `hs_err_pid*.log`
    khi segfault. Ứng dụng định tuyến chúng vào thư mục tạm để không làm
    bẩn thư mục dự án của bạn.

!!! tip "Tự chuyển đổi cũ / ODF"
    Bật **Cài đặt → Bản dịch → Auto-convert legacy** nếu bạn thường
    xuyên dịch `.doc` / `.xls` / `.ppt`. Pipeline sẽ chuyển sang `.docx`
    / `.xlsx` / `.pptx` trước (qua `convert_to_modern_format`), dịch
    bản hiện đại, rồi chuyển ngược. Độ chính xác cao hơn nhiều so với
    dịch trực tiếp định dạng cũ.
