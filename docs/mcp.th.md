---
description: เปิดเผย AI Translate เป็นเครื่องมือ Model Context Protocol เพื่อให้ Claude Desktop, Claude Code และไคลเอนต์ MCP อื่นๆ สามารถแปลข้อความ ไฟล์ และเสียงได้
---

# เซิร์ฟเวอร์ MCP (`ait-mcp`)

เปิดเผยไปป์ไลน์การแปลเป็นเครื่องมือ **Model Context Protocol** เพื่อ
ให้ AI agents เช่น Claude Desktop และ Claude Code สามารถขับเคลื่อน
มันได้โดยตรง — "แปล PDF นี้เป็นภาษาฝรั่งเศส" กลายเป็นการเรียก
เครื่องมือ ไม่ใช่การคัดลอก-วาง

## สิ่งที่เปิดเผย

เก้าเครื่องมือ:

| เครื่องมือ | วัตถุประสงค์ |
|---|---|
| `translate_text` | แปลรายการของสตริง |
| `translate_document` | จัดคิวงานแปลไฟล์ (ส่งคืนรหัสงาน) |
| `get_task_status` | ตรวจสอบสถานะงาน |
| `cancel_task` | ยกเลิกแบบร่วมมือสำหรับงานที่กำลังทำงาน |
| `extract_image_text` | OCR หรือ LLM vision |
| `transcribe_audio` | เสียง → SRT |
| `synthesize_speech` | ข้อความ → MP3 / WAV |
| `query_glossary` | แสดงรายการชุด / รายการคำศัพท์ |
| `list_languages` | ภาษาที่รองรับทั้ง 45 ภาษา |

## รันเซิร์ฟเวอร์

```bash
ait-mcp                       # การส่งข้อมูล stdio (ค่าเริ่มต้นสำหรับ desktop agents)
ait-mcp --transport sse       # Server-Sent Events สำหรับไคลเอนต์เว็บ
ait-mcp --transport sse --port 9000
```

`stdio` คือสิ่งที่ไคลเอนต์ MCP ทุกตัวคาดหวัง เว้นแต่คุณจะเชื่อมต่อ SSE
อย่างชัดเจน

## เพิ่มไปยัง Claude Desktop

1. เปิด Claude Desktop → **Settings → Developer → Edit Config**
2. เพิ่มรายการนี้ใต้ `mcpServers`:

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

    แทนที่ `/absolute/path/to/ai-translate` ด้วย path repo ที่
    cloned

3. ออกและเปิด Claude Desktop ใหม่ ไอคอนค้อนควรแสดง "ai-translate"
   พร้อมเครื่องมือทั้ง 9 รายการแล้ว ลอง:

    > "แปล PDF นี้ (`/home/me/report.pdf`) เป็นภาษาฝรั่งเศส — บันทึก
    > เอาต์พุตข้างต้นทาง"

## เพิ่มไปยัง Claude Code

`~/.config/claude-code/mcp_servers.json` (หรือ `claude mcp add` จาก
ภายใน Claude Code):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

รีสตาร์ท Claude Code เครื่องมือทั้ง 9 รายการเดียวกันสามารถเรียกได้

## เพิ่มไปยังไคลเอนต์ MCP อื่นๆ

ไคลเอนต์ที่เข้ากันได้กับ MCP ใดๆ มีรูปร่างคล้ายกัน:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (ค่าเริ่มต้น)

สำหรับไคลเอนต์ที่ใช้ HTTP / SSE ให้รัน
`ait-mcp --transport sse --port 9000` และชี้ไคลเอนต์ไปที่
`http://localhost:9000`

## การรับประกันการตรวจสอบ

ทุกเครื่องมือส่งคืนรูปร่างเดียวกันในข้อผิดพลาด เพื่อให้ agents สามารถ
จัดการกับความล้มเหลวอย่างสม่ำเสมอ:

| อินพุตที่ไม่ดี | การตอบสนองของเครื่องมือ |
|---|---|
| ภาษาที่ไม่รู้จัก | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM ไม่ได้กำหนดค่า | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| ประเภทไฟล์ที่ไม่รองรับ | `ValueError` แสดงรายการนามสกุลที่อนุญาต |
| `model="…"` ผิดรูปแบบ (ไม่มี `:`) | `ValueError` แทนที่จะใช้ค่าเริ่มต้นอย่างเงียบๆ |
| Task ID ที่ไม่รู้จักใน `cancel_task` | ส่งคืนในอาร์เรย์ `unknown` — ไม่มีข้อผิดพลาด |
| FFmpeg หายไปบน `transcribe_audio` | `RuntimeError: FFmpeg is required…` (re-wrapped จาก tag `FFMPEG_NOT_FOUND` เปล่าของเอนจิน) |

Agents ที่เรียกเครื่องมือเหล่านี้สามารถพึ่งพาสัญญาเหล่านี้ได้

## การทำงานพร้อมกัน

`translate_document` รันไปป์ไลน์ใน daemon thread แต่ละ batch ได้รับ
cancel event ของตัวเอง ดังนั้นการยกเลิก batch หนึ่งจะไม่รบกวนอีก
batch หนึ่ง MCP server ติดตามไปป์ไลน์ที่ใช้งานอยู่ใน map ที่อยู่ใน
process (ทำความสะอาดอัตโนมัติเมื่อไปป์ไลน์เสร็จสิ้น)

## กรณีการใช้งาน

- **"แปลเอกสารของ codebase นี้เป็นภาษาเวียดนาม"** — ชี้ agent ไปที่
  โฟลเดอร์เอกสาร มันจะ batch การเรียก `translate_document` และ poll
  `get_task_status` จนกว่าแต่ละรายการจะเสร็จ
- **"คุณรองรับภาษาอะไรบ้าง?"** — agent เรียก `list_languages` อ่าน
  การตอบสนอง
- **"แปลใบเสร็จญี่ปุ่นนี้"** — agent เรียก `extract_image_text` ใน
  ภาพถ่าย จากนั้น `translate_text` กับผลลัพธ์
- **"สร้างคำบรรยายภาษาเวียดนามสำหรับการบันทึก Zoom นี้"** — agent
  เรียก `transcribe_audio` เพื่อรับ SRT ในภาษาต้นทาง จากนั้น
  `translate_text` กับแต่ละ cue เพื่อ localize และประกอบ SRT ใหม่

!!! note "การพากย์เสียงวิดีโอไม่ใช่เครื่องมือ MCP"
    ไปป์ไลน์ STT เต็ม → translate → TTS → mux (หน้า **พากย์เสียง**
    ของแอปเดสก์ท็อป) ใช้ได้เฉพาะผ่าน GUI เท่านั้นในตอนนี้ จาก MCP
    คุณสามารถประกอบสิ่งเทียบเท่าได้ด้วย `transcribe_audio` +
    `translate_text` + `synthesize_speech` แต่คุณจะต้องจัดการกับ
    ขั้นตอน mux ที่รับรู้จังหวะเวลา (FFmpeg) นอกระบบ

## เคล็ดลับ

!!! tip "ตั้งค่าครั้งเดียว agents ทำงานทุกที่"
    เซิร์ฟเวอร์ MCP แชร์คีย์ API และการตั้งค่ากับแอปเดสก์ท็อปและ CLI
    กำหนดค่า LLM / OCR / TTS ครั้งเดียวใน GUI จากนั้น agent ใดๆ ที่
    พูดคุยกับ `ait-mcp` จะสืบทอดการตั้งค่าเดียวกัน

!!! tip "Cold-start endpoint cache"
    สำหรับแต่ละคู่ `(endpoint, model)` การเลือก chat-vs-responses-API
    และ working payload variant จะถูกเก็บไว้ใน
    `llm_endpoint_cache.json` ใน OS cache directory
    (`~/.cache/ai-translate/` บน Linux,
    `~/Library/Caches/ai-translate/` บน macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` บน Windows) Process
    `ait-mcp` ใหม่จะข้ามการสำรวจการตรวจจับอัตโนมัติทั้งหมดหลังจาก
    การเรียกที่สำเร็จครั้งแรก — agents ที่ spawn เซิร์ฟเวอร์ตามต้องการ
    จะไม่จ่าย round-trips การตรวจจับ variant ในทุกการเรียก Cache
    ปลอดภัยสำหรับ multi-process และ multi-thread (read-merge-write
    ภายใต้ RLock พร้อมการเปลี่ยนชื่อแบบ atomic)

!!! tip "Per-tool model picker"
    เครื่องมือ `translate_text` และ `translate_document` ยอมรับ
    parameter `model` เสริม — agents สามารถเลือกโมเดลที่รวดเร็วสำหรับ
    การหมุนเร็วและโมเดลที่หนักกว่าสำหรับเอาต์พุตการผลิตโดยไม่ต้องให้
    ผู้ใช้กำหนดค่าแอปเดสก์ท็อปใหม่

!!! warning "ไปป์ไลน์ที่ทำงานยาวนาน"
    `translate_document` ส่งคืน task IDs ทันที คาดหวังให้ agent poll
    `get_task_status` จนกว่าแต่ละ task จะถึง `Done` หรือ `Failed`
    อย่ารอแบบ synchronous ภายในการเรียกเครื่องมือ; การทำเช่นนั้น
    เสี่ยงต่อการที่ timeout ของไคลเอนต์ MCP จะทำงาน
