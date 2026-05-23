---
description: Trích xuất văn bản từ ảnh và ảnh chụp màn hình bằng OCR (Tesseract, EasyOCR, Google Vision) hoặc vision LLM — xuất ra TXT hoặc DOCX.
---

# Trích xuất văn bản

Lấy văn bản ra khỏi ảnh — hóa đơn, ảnh chụp màn hình, tài liệu chụp lại,
trang scan, bất cứ thứ gì. Xuất ra `.txt` (thuần) hoặc `.docx`
(đoạn văn có định dạng).

Trang này **không dịch** — chỉ trích xuất. Đẩy kết quả sang Dịch tài liệu
nếu bạn muốn dịch luôn.

## Hai phương thức trích xuất

| Phương thức | Phù hợp với |
|---|---|
| **OCR** | Khối lượng lớn / batch / nhạy cảm về chi phí (miễn phí hoặc gần như miễn phí mỗi ảnh) |
| **Vision LLM** | Giữ bố cục, chữ viết hỗn hợp ngôn ngữ, ảnh chất lượng thấp, chữ viết tay |

Chọn mặc định ở **Cài đặt → Trích xuất văn bản → Phương thức trích xuất**.

## Engine OCR (phương thức OCR)

| Engine | Chi phí | Offline | Ngôn ngữ | Ghi chú |
|---|---|---|---|---|
| **Tesseract** | Miễn phí | Có | 100+ | Mặc định. Cần cài đặt trên hệ thống. |
| **EasyOCR** | Miễn phí | Có (sau khi tải model) | 80+ | Tốt nhất cho chữ không thuộc Latin. Model ~1 GB. |
| **Google Cloud Vision** | Có phí (1.000 ảnh miễn phí / tháng) | Không | 60+ | Độ chính xác cao nhất. |

Cấu hình tại **Cài đặt → OCR**.

## Hướng dẫn từng bước

1. Nhấp **Trích xuất văn bản** ở thanh bên.
2. Thả một hoặc nhiều file ảnh (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`,
   `.tiff`, `.tif`).
3. Chọn **Ngôn ngữ nguồn** (giúp OCR chọn đúng model).
4. Chọn **Định dạng xuất** — `.txt` hoặc `.docx`.
5. Nhấp **Trích xuất** (hoặc `Ctrl+Enter`).
6. Nhấp **Mở** ở dòng tương ứng khi hoàn tất.

## Gợi ý sử dụng

- **Hóa đơn / biên lai nhiều chữ** → Tesseract nhanh và chính xác.
- **Ghi chú viết tay chụp ảnh** → Vision LLM thắng đáng kể.
- **Khung manga / truyện tranh** → EasyOCR (xử lý tốt chữ CJK dọc).
- **Form có nhiều ô nhỏ** → Google Cloud Vision thường giữ ranh giới
  trường tốt hơn các engine khác.

## Mẹo

!!! tip "OCR hoặc LLM, không cả hai"
    Trang sẽ chọn một phương thức và chạy. Để so sánh kết quả, chạy
    cùng một ảnh hai lần với các phương thức khác nhau.

!!! tip "Hộp thoại Yêu cầu cài đặt"
    Nếu bạn chọn OCR nhưng chưa cấu hình engine OCR nào (hoặc chọn LLM
    nhưng chưa có LLM key), trang sẽ hiện một hộp thoại "Yêu cầu cài đặt"
    liên kết thẳng đến tab Cài đặt phù hợp.

## Phím tắt

| Phím tắt | Hành động |
|---|---|
| `Ctrl+Enter` | Trích xuất |
| `Ctrl+O` | Duyệt |
| `Ctrl+F` | Focus tìm kiếm lịch sử |
