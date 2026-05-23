---
description: Dùng CLI ait để dịch file ở chế độ headless — hỗ trợ PDF, tài liệu Office, phụ đề và 45+ ngôn ngữ từ script hoặc CI job.
---

# Dòng lệnh (`ait`)

Dịch headless — cùng pipeline với ứng dụng desktop, không cần màn hình.
Hữu ích cho CI, batch job, server và workflow bằng script.

## Bắt đầu nhanh

```bash
ait report.docx --target French
```

Output xuất cạnh nguồn dưới dạng `report_translated_<src>_<tgt>.docx`.

## Công thức thường dùng

### Nhiều file

```bash
ait *.pdf --target Japanese
```

Mở rộng glob là việc của shell (Unix). Trên Windows / `cmd.exe`, liệt
kê file rõ ràng hoặc dùng PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Thư mục đầu ra tùy chỉnh

```bash
ait report.docx --target French --output ./translated/
```

Thư mục được tạo nếu chưa có. Nếu không thể tạo (permission denied,
v.v.) bạn nhận lỗi rõ ràng và exit code 2 — không chạy nửa chừng.

### Chỉ định ngôn ngữ nguồn

```bash
ait letter.txt --target German --source "English (US)"
```

Khớp nguồn không phân biệt hoa thường. "Chinese" trần in gợi ý:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Chọn model cụ thể

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# Hoặc bất kỳ Provider:model_name nào đã đăng ký trong tab LLM của ứng dụng desktop.
```

Định dạng nghiêm ngặt là `Provider:model_name`. Thiếu dấu hai chấm →
exit 2 với thông báo rõ ràng thay vì âm thầm fallback về model Gemini
mặc định.

### Tùy chọn Office

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` cần OCR đã cấu hình (xem
[Engine OCR](setup/ocr-engines.md)).

### Tự chuyển đổi định dạng cũ

```bash
ait old-doc.doc --target French --convert-legacy
```

Pipeline chuyển `.doc` → `.docx` trước (chính xác hơn), dịch bản hiện
đại, rồi chuyển ngược. Tương tự cho `--convert-odf` và `.odt` / `.ods`
/ `.odp`.

### Yên tĩnh / verbose

```bash
ait report.docx --target French --quiet      # chỉ lỗi
ait report.docx --target French --verbose    # toàn bộ DEBUG
```

Chế độ mặc định in banner và tiến trình từng tác vụ ra stderr; chi tiết
đầy đủ (HTTP body dump, log retry) đi vào thư mục log ứng dụng của
nền tảng bất kể độ verbose console (xem
[Khắc phục sự cố → Log nằm ở đâu](troubleshooting.md#where-are-the-logs)
để biết đường dẫn trên OS của bạn).

### Liệt kê ngôn ngữ hỗ trợ

```bash
ait --list-languages
```

In ra cả 45 ngôn ngữ hỗ trợ. Hữu ích để pipe vào vòng lặp shell.

### Phiên bản

```bash
ait --version
# ait 0.1.0
```

## Exit code

| Code | Ý nghĩa |
|---|---|
| `0` | Mọi tác vụ thành công |
| `2` | Lỗi tham số (ngôn ngữ không xác định, thiếu đích, model sai định dạng, output không ghi được, phần mở rộng file không hỗ trợ) |
| `3` | LLM chưa cấu hình |
| `4` | Thất bại một phần (một số thành công, một số không) |
| `5` | Tất cả thất bại |
| `130` | Bị gián đoạn (`Ctrl+C`) |

## Hủy

`Ctrl+C` một lần — hủy hợp tác. Checkpoint của tác vụ hiện tại được
lưu, pipeline thoát sạch ở ranh giới polling tiếp theo.

`Ctrl+C` lần nữa — gián đoạn cứng. Dùng tiết kiệm; file dở dang có
thể bị bỏ trong trạng thái viết nửa chừng.

## Tham chiếu cờ đầy đủ

```bash
ait --help
```

Hiển thị mọi cờ với mặc định. Cùng nội dung được tóm tắt ở đây:

| Cờ | Mặc định | Ghi chú |
|---|---|---|
| `--target / -t LANG` | _bắt buộc_ | Không phân biệt hoa thường |
| `--source / -s LANG` | tự phát hiện | Không phân biệt hoa thường |
| `--output / -o DIR` | thư mục cha của nguồn | Tạo nếu thiếu |
| `--model / -m PROVIDER:MODEL` | mặc định desktop | Định dạng nghiêm ngặt |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | tắt | Cần OCR đã cấu hình |
| `--translate-comments` | tắt | Bình luận Office |
| `--translate-shapes` | tắt | Shape / text box |
| `--translate-notes` | tắt | Ghi chú diễn giả PowerPoint |
| `--translate-sheet-names` | tắt | Tab sheet Excel |
| `--convert-legacy` | tắt | `.doc`/`.xls`/`.ppt` → định dạng hiện đại |
| `--convert-odf` | tắt | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | tắt | Giữ mục lịch sử sau khi hoàn tất |
| `--quiet / -q` | tắt | Chỉ lỗi trên console |
| `--verbose / -v` | tắt | DEBUG đầy đủ |
| `--list-languages` | — | In 45 ngôn ngữ và thoát |
| `--version` | — | In phiên bản và thoát |

## Mẹo

!!! tip "Cài một lần, dùng ở mọi nơi"
    CLI chia sẻ API key và cài đặt với ứng dụng desktop — cài mọi thứ
    một lần trong GUI, rồi tự động hóa với `ait` từ đó.

!!! tip "Cache endpoint cold-start"
    Với mỗi cặp `(endpoint, model)`, lựa chọn chat-vs-responses-API và
    biến thể payload đang chạy được lưu vào `llm_endpoint_cache.json`
    trong thư mục cache OS (`~/.cache/ai-translate/` trên Linux,
    `~/Library/Caches/ai-translate/` trên macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` trên Windows). Lời gọi CLI
    cold-start hoàn toàn bỏ qua bước probe auto-detection sau lần gọi
    thành công đầu tiên — hữu ích khi script làm việc với các deployment
    Azure / vLLM / OpenRouter / Anthropic / DeepSeek cần điều chỉnh
    payload riêng. Cache an toàn đa tiến trình và đa thread
    (read-merge-write dưới RLock với rename nguyên tử).

!!! tip "Luồng đầu ra"
    Chế độ mặc định in banner, danh sách tác vụ xếp hàng và tiến trình
    từng tác vụ vào **stdout** (line-buffered nên xen kẽ đúng với lỗi);
    thông báo lỗi và bản ghi log đi vào **stderr**. Kết hợp với
    `--quiet` để bỏ stdout hoàn toàn cho pipe sạch:

    ```bash
    ait --list-languages | grep -i japanese    # dữ liệu trên stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
