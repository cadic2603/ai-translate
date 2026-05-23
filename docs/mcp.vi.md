---
description: Expose AI Translate dưới dạng tools Model Context Protocol để Claude Desktop, Claude Code và các MCP client khác có thể dịch văn bản, file và âm thanh.
---

# Server MCP (`ait-mcp`)

Expose pipeline dịch dưới dạng **Model Context Protocol** tools để các
agent AI như Claude Desktop và Claude Code có thể điều khiển trực tiếp —
"Dịch PDF này sang tiếng Pháp" trở thành một lời gọi tool, không phải
copy-paste.

## Những gì được expose

Chín tool:

| Tool | Mục đích |
|---|---|
| `translate_text` | Dịch một danh sách chuỗi |
| `translate_document` | Xếp hàng các tác vụ dịch file (trả về task ID) |
| `get_task_status` | Poll trạng thái tác vụ |
| `cancel_task` | Hủy hợp tác các tác vụ đang chạy |
| `extract_image_text` | OCR hoặc Vision LLM |
| `transcribe_audio` | Audio → SRT |
| `synthesize_speech` | Văn bản → MP3 / WAV |
| `query_glossary` | Liệt kê các bộ / mục glossary |
| `list_languages` | Tất cả 45 ngôn ngữ hỗ trợ |

## Chạy server

```bash
ait-mcp                       # transport stdio (mặc định cho desktop agent)
ait-mcp --transport sse       # Server-Sent Events cho web client
ait-mcp --transport sse --port 9000
```

`stdio` là cái mọi MCP client mong đợi trừ khi bạn đã đấu nối SSE
một cách rõ ràng.

## Thêm vào Claude Desktop

1. Mở Claude Desktop → **Settings → Developer → Edit Config**
2. Thêm mục này dưới `mcpServers`:

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    Thay `/absolute/path/to/ai-translate` bằng đường dẫn repo đã clone.

3. Thoát và mở lại Claude Desktop. Icon hammer giờ nên hiển thị
   "ai-translate" với cả 9 tool. Thử:

    > "Dịch PDF này (`/home/me/report.pdf`) sang tiếng Pháp — lưu kết
    > quả cạnh file gốc."

## Thêm vào Claude Code

`~/.config/claude-code/mcp_servers.json` (hoặc `claude mcp add` từ bên
trong Claude Code):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Khởi động lại Claude Code. Cùng 9 tool giờ có thể gọi.

## Thêm vào MCP client khác

Mọi client tương thích MCP có cấu hình tương tự:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (mặc định)

Cho client dựa trên HTTP / SSE, chạy `ait-mcp --transport sse --port 9000`
và trỏ client đến `http://localhost:9000`.

## Quy ước xử lý lỗi (Contract)

Mọi tool trả về cùng shape khi lỗi để agent có thể xử lý nhất quán:

| Đầu vào sai | Phản hồi tool |
|---|---|
| Ngôn ngữ không xác định | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| Chưa cấu hình LLM | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Loại file không hỗ trợ | `ValueError` liệt kê các phần mở rộng được phép |
| `model="…"` sai định dạng (không có `:`) | `ValueError` thay vì âm thầm dùng mặc định |
| Task ID không xác định trong `cancel_task` | Trả về trong mảng `unknown` — không lỗi |
| Thiếu FFmpeg ở `transcribe_audio` | `RuntimeError: FFmpeg is required…` (bọc lại từ tag `FFMPEG_NOT_FOUND` của engine) |

Agent gọi các tool này có thể tin các hợp đồng này.

## Đồng thời

`translate_document` chạy pipeline trong daemon thread. Mỗi batch nhận
cancel event riêng, nên hủy một batch không làm phiền batch khác. MCP
server theo dõi các pipeline đang chạy trong map process-local (tự dọn
khi pipeline kết thúc).

## Use case

- **"Dịch tài liệu của codebase này sang tiếng Việt"** — trỏ agent vào
  thư mục docs, nó batch các lời gọi `translate_document` và poll
  `get_task_status` đến khi mỗi cái xong.
- **"Bạn hỗ trợ ngôn ngữ nào?"** — agent gọi `list_languages`, đọc phản hồi.
- **"Dịch hóa đơn tiếng Nhật này"** — agent gọi `extract_image_text`
  trên ảnh, rồi `translate_text` trên kết quả.
- **"Tạo phụ đề tiếng Việt cho bản ghi Zoom này"** — agent gọi
  `transcribe_audio` để lấy SRT ở ngôn ngữ gốc, rồi `translate_text`
  trên từng cue để localize, và lắp lại SRT.

!!! note "Lồng tiếng video không phải MCP tool"
    Pipeline đầy đủ STT → dịch → TTS → mux (trang **Lồng tiếng** của
    ứng dụng desktop) chỉ có sẵn qua GUI hiện tại. Từ MCP bạn có thể
    tự ghép tương đương với `transcribe_audio` + `translate_text` +
    `synthesize_speech`, nhưng bạn cần xử lý bước mux nhận biết timing
    (FFmpeg) bên ngoài.

## Mẹo

!!! tip "Cài một lần, agent hoạt động ở mọi nơi"
    MCP server chia sẻ API key và cài đặt với ứng dụng desktop và CLI.
    Cấu hình LLM / OCR / TTS một lần trong GUI, rồi mọi agent giao tiếp
    với `ait-mcp` đều kế thừa cùng cài đặt.

!!! tip "Cache endpoint cold-start"
    Với mỗi cặp `(endpoint, model)`, lựa chọn chat-vs-responses-API và
    biến thể payload đang chạy được lưu vào `llm_endpoint_cache.json`
    trong thư mục cache OS (`~/.cache/ai-translate/` trên Linux,
    `~/Library/Caches/ai-translate/` trên macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` trên Windows). Tiến trình
    `ait-mcp` mới hoàn toàn bỏ qua bước probe auto-detection sau lần
    gọi thành công đầu tiên — agent spawn server theo nhu cầu không
    phải trả round-trip phát hiện biến thể trên mỗi lần gọi. Cache an
    toàn đa tiến trình và đa thread (read-merge-write dưới RLock với
    rename nguyên tử).

!!! tip "Bộ chọn model theo tool"
    Tool `translate_text` và `translate_document` chấp nhận tham số
    `model` tùy chọn — agent có thể chọn model nhanh cho lượt nhanh và
    model nặng hơn cho đầu ra production mà không cần người dùng cấu
    hình lại ứng dụng desktop.

!!! warning "Pipeline dài"
    `translate_document` trả về ngay lập tức với task ID. Agent được
    kỳ vọng poll `get_task_status` đến khi mỗi tác vụ đạt `Done` hoặc
    `Failed`. Đừng chờ đồng bộ trong lời gọi tool; điều đó risk làm
    timeout MCP client.
