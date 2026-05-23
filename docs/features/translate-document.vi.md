---
description: Dịch PDF, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT và 30+ định dạng khác trong khi giữ nguyên định dạng và bố cục.
---

# Dịch tài liệu

Dịch toàn bộ file — Office, PDF, EPUB, văn bản thuần, phụ đề, định
dạng localization và nhiều hơn — với định dạng được giữ nguyên.

## Định dạng hỗ trợ

| Loại | Phần mở rộng |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Văn bản & web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eBook | `.epub` |
| Phụ đề | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Localization | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Hướng dẫn từng bước

1. Nhấp **Dịch tài liệu** ở thanh bên.
2. Kéo file vào (hoặc nhấp **Duyệt**). Thư mục cũng được — file hỗ trợ
   bên trong được nhận đệ quy.
3. Chọn **Nguồn** (hoặc để `Tự động phát hiện`) và **Đích**.
4. Nhấp **Dịch** — hoặc nhấn `Ctrl+Enter`.
5. Bảng lịch sử bên dưới hiển thị tiến trình từng file (Pending →
   Translating → Done / Failed). Thanh bên hiện spinner khi có tác vụ
   đang chạy.
6. Nhấp **Mở** ở dòng để mở file đã dịch. Nhấp chuột phải để có tùy
   chọn: dịch lại, tạm dừng, retry, xóa.

## File được lưu ở đâu

Mặc định, file đã dịch được lưu cạnh file gốc với hậu tố
`_translated_<src>_<tgt>`:

```
~/Documents/report.docx
~/Documents/report_translated_en_fr.docx     ← ở đây
```

Đổi trong **Cài đặt → Chung → Đường dẫn lưu trữ bản dịch** sang thư mục tùy chỉnh.

## Giới hạn và bảo vệ

- **Giới hạn 100 file mỗi lần thả** — thả nhiều hơn bạn sẽ nhận thông báo.
  Dịch theo batch.
- **Phát hiện trùng** — thả file đã có trong hàng đợi và bạn sẽ nhận
  thông báo (file trùng bị bỏ, không thêm hai lần).
- **Tự resume** — thoát ứng dụng khi đang dịch, lần khởi động sau sẽ
  resume (tác vụ Pending / Translating).

## Tùy chọn riêng cho Office

Tab Bản dịch trong **Cài đặt** expose các toggle này cho file Office:

| Tùy chọn | Làm gì |
|---|---|
| **Dịch ảnh nhúng** | Chạy OCR + Vision LLM trên ảnh trong `.docx` / `.xlsx` / `.pptx` và chèn lại ảnh đã dịch. Cần OCR đã cấu hình. |
| **Dịch bình luận** | Bình luận / ghi chú review được dịch cùng với text body. |
| **Dịch shape & text box** | Bắt text nằm trong shape, callout và text box nổi. |
| **Dịch ghi chú diễn giả** | Ghi chú diễn giả của PowerPoint được dịch. |
| **Dịch tên sheet** | Nhãn tab sheet của Excel được dịch. |
| **Tự động chuyển định dạng cũ (Auto-convert legacy)** | `.doc` / `.xls` / `.ppt` được chuyển sang OOXML hiện đại trước khi dịch (chính xác hơn). |
| **Tự động chuyển ODF (Auto-convert ODF)** | `.odt` / `.ods` / `.odp` được chuyển sang OOXML trước khi dịch. |

Mọi bản dịch Office đều giữ định dạng từng run: đậm, nghiêng, gạch
chân, gạch ngang, cỡ font, màu, hyperlink, header, footer, footnote,
endnote, tất cả.

### Dịch ảnh nhúng: Bỏ qua kèm cảnh báo và lưu cache

Khi **Dịch ảnh nhúng** được bật, mỗi hình ảnh nhúng đi
qua OCR → thị giác LLM → tái-chèn đã render. Hai hành vi
đáng biết:

- **Bỏ qua kèm cảnh báo**: nếu một hình ảnh không dịch
  được (quá lớn, hỏng, mô hình thị giác từ chối định
  dạng, v.v.) tài liệu vẫn hoàn thành — hình ảnh hỏng giữ
  nguyên ngôn ngữ gốc, một cảnh báo được ghi vào
  `app.log`, và vòng lặp tiếp tục với hình ảnh tiếp theo.
  Chỉ các lỗi LLM nghiêm trọng (`AUTH_ERROR`,
  `QUOTA_ERROR`, `VISION_NOT_SUPPORTED`) mới dừng pipeline
  ngay lập tức vì chúng cũng chặn mọi hình ảnh còn lại.
  Băng-rôn thông tin phía trên ô **Dịch ảnh nhúng**
  ghi lại chính sách ngay tại chỗ.
- **Lưu cache theo hình ảnh**: các bản dịch hình ảnh
  thành công được giữ lại dưới thư mục lưu trữ nội bộ của
  tác vụ, sử dụng khóa SHA256 của byte nguồn. Khi thử
  lại, các hình ảnh đã dịch trúng bộ nhớ đệm thay vì
  chạy lại OCR + LLM — công việc đã trả phí không bị làm
  lại. Các hình ảnh trùng lặp (logo công ty trên mọi
  trang chiếu) được dịch một lần và tái sử dụng N − 1
  lần.

Tệp đầu ra chỉ xuất hiện trong thư mục đầu ra bạn chọn
khi **thành công** — các bản dịch một phần từ các lần
chạy bị hủy hoặc thất bại vẫn nằm trong thư mục lưu trữ
nội bộ của tác vụ, nên thư mục đầu ra của bạn không bao
giờ tích lũy tài liệu mồ côi được dịch một nửa.

## Đặc thù PDF

PDF dùng engine extract-overlay: text gốc bị redact tại chỗ và text dịch
được overlay vào cùng các ô, giữ bố cục thị giác. Checkpoint từng trang
nghĩa là tác vụ tạm dừng / crash resume từ chỗ dừng, không phải từ trang 1.

Cái gì được dịch:

- Văn bản body (với phát hiện căn chỉnh — trái / giữa / phải / justify)
- Bookmark / outline (mục TOC)
- Form field (input text, dropdown, list box)
- Hyperlink (rect link cập nhật để bao text mới)
- Ảnh nhúng (khi **Dịch ảnh nhúng** bật)
- Bình luận / chú thích PDF

Với PDF scan (không có lớp text nhúng), OCR chạy tự động cho từng
trang. Cấu hình engine OCR ở **Cài đặt → OCR**.

## Đầu ra phải-sang-trái

Bản dịch sang **Tiếng Ả Rập**, **Tiếng Hebrew** hoặc **Tiếng Ba Tư**
hiển thị nguyên bản RTL trên mọi định dạng đầu ra — `dir="rtl"` được
chèn vào PDF overlay, HTML và chương EPUB (với
`page-progression-direction="rtl"` trong OPF EPUB để Apple Books và
Kindle lật trang đúng chiều); DOCX `<w:bidi/>` + `<w:rtl/>`, PPTX
`rtl="1"`, XLSX sheet view phải-sang-trái, ODT/ODS/ODP
`style:writing-mode="rl-tb"`, RTF `\rtldoc`, và mã căn chỉnh ASS/SSA
được phản chiếu (`\an1` ↔ `\an3`, `\an4` ↔ `\an6`, v.v.). Căn giữa
không bị động đến.

## Phím tắt

| Phím tắt | Hành động |
|---|---|
| `Ctrl+Enter` | Bắt đầu dịch |
| `Ctrl+O` | Duyệt file |
| `Ctrl+F` | Focus tìm kiếm lịch sử |
| `Ctrl+P` | Tạm dừng hàng đợi đang chạy |
| `Ctrl+G` | Tiếp tục hàng đợi đang chạy |
| `Delete` | Xóa các mục lịch sử đã chọn |

`Ctrl+P` / `Ctrl+G` bị tạm tắt khi ô nhập text đang focus, nên không
xung đột với gõ phím.

## Khi xảy ra lỗi

Tác vụ thất bại hiện trạng thái đỏ với mã lỗi và thông báo bản địa
hóa — xem [hướng dẫn khắc phục sự cố](../troubleshooting.md) cho các
lỗi phổ biến (`AUTH_ERROR`, `QUOTA_ERROR`, `FFMPEG_NOT_FOUND`, v.v.).
