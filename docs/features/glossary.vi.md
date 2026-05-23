---
description: Quản lý các bộ glossary tùy chỉnh để giữ thuật ngữ nhất quán giữa các bản dịch — nhập/xuất CSV, phạm vi theo cặp ngôn ngữ, ưu tiên theo dự án.
---

# Bảng thuật ngữ (Glossary)

Khóa các thuật ngữ cụ thể với bản dịch cụ thể trong mọi tác vụ dịch.
Hữu ích cho tên thương hiệu, thuật ngữ sản phẩm, jargon kỹ thuật, hoặc
tên nhân vật mà bạn muốn giữ nhất quán.

## Cách hoạt động

Một glossary là danh sách các cặp (thuật ngữ nguồn, thuật ngữ đích)
được nhóm thành một **bộ**. Khi bạn bật một bộ, mọi lần gọi LLM trong
ứng dụng sẽ được nhúng các mục liên quan vào prompt — nên LLM thấy
"dùng 'OpenAI' cho 'OpenAI', không phải '开放AI'" trước khi dịch.

Có thể bật nhiều bộ cùng lúc. Chỉ những mục có nguồn hoặc đích xuất
hiện trong batch text mới được thêm vào prompt (nén theo lần gọi),
nên một glossary 5.000 mục vẫn rẻ về token.

## Hướng dẫn từng bước

1. Nhấp **Glossary** ở thanh bên.
2. Nhấp **Bộ mới** (`Ctrl+N`) và đặt tên (ví dụ "Dự án Acme").
3. Khi bộ được chọn ở bên trái, ô bên phải hiện các mục của nó.
4. Nhấp **Thêm** để tạo mục mới. Điền:
    - **Nguồn** — thuật ngữ gốc
    - **Đích** — bản dịch cần ép
    - Tùy chọn ghi chú
5. Lặp lại cho từng thuật ngữ.
6. Đánh dấu hộp **Hoạt động** trên tên bộ để bật cho các bản dịch.

## Bật / tắt các bộ

Hộp **Hoạt động** cạnh tên mỗi bộ điều khiển việc các mục có được nhúng
vào prompt LLM hay không. Bạn có thể để 50 bộ không hoạt động trong kho
và chỉ bật 2 bộ cần cho dự án hiện tại.

## Nhập / Xuất (CSV)

- **Xuất** — chọn một bộ, nhấp **Xuất** → lưu thành `.csv`. Hai cột:
  `source`, `target` (UTF-8, phân tách bằng dấu phẩy, escape theo RFC 4180).
- **Nhập** — nhấp **Nhập** → chọn `.csv` → chọn bộ đích (đang có hoặc
  tạo mới). Khi trùng nguồn, bạn sẽ nhận lời nhắc thay thế hoặc bỏ qua.

Định dạng CSV round-trip, nên Xuất → chỉnh trong Excel → Nhập là an toàn.

## Tìm kiếm và lọc

`Ctrl+F` focus ô tìm kiếm. Gõ bất kỳ chuỗi con nào và các mục (và danh
sách bộ) sẽ lọc theo kết quả khớp; chuỗi khớp được highlight. Xóa tìm
kiếm khôi phục danh sách đầy đủ.

Tìm kiếm **không phân biệt dấu và không phân biệt hoa thường** — `cafe`
tìm thấy `café` và ngược lại.

## Chỉnh tại chỗ

Nhấp bất kỳ ô nào để chỉnh. Nhấn `Tab` để sang ô kế tiếp. Nhấn `Esc`
để hoàn tác. Auto-save kích hoạt khi bạn nhấp ra khỏi dòng. Nguồn hoặc
đích trống sẽ revert dòng thay vì lưu mục không hợp lệ.

## Xóa

- **Xóa một mục** — chọn nó, nhấn `Delete`. Bạn sẽ thấy hộp thoại xác nhận.
- **Xóa cả bộ** — chọn bộ, nhấn `Delete`. Hộp thoại hiển thị số mục con
  bị cascade để bạn biết mình đang xóa gì.

## Phím tắt

| Phím tắt | Hành động |
|---|---|
| `Ctrl+N` | Bộ mới |
| `Ctrl+F` | Focus tìm kiếm |
| `Delete` | Xóa mục / bộ đã chọn |

## Mẹo

!!! tip "Phạm vi theo bộ"
    Một bộ là gom *logic*. Gom theo dự án, theo khách hàng, theo lĩnh
    vực (y tế / pháp lý / gaming) — bất cứ gì hợp lý. Chỉ bật những
    bộ liên quan đến công việc hiện tại.

!!! tip "Glossary không override bản dịch"
    LLM được yêu cầu dùng các mục glossary, nhưng đó vẫn chỉ là gợi
    ý — các bản dịch ép cứng rất khó chịu vẫn có thể xuất hiện. Dùng
    cặp `thuật ngữ → bản dịch` đơn giản chứ không phải cả câu.
