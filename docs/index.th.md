---
description: AI Translate เป็นโปรแกรมแปลภาษาเดสก์ท็อปฟรีข้ามแพลตฟอร์มสำหรับเอกสาร, PDF, คำบรรยาย, เสียง และคำพูดสดในกว่า 45 ภาษา
---

# AI Translate

โปรแกรมแปลภาษาเดสก์ท็อปฟรีข้ามแพลตฟอร์มที่จัดการ **45 ภาษา** และไป
ไกลเกินกว่าข้อความธรรมดา — มันแปลเอกสาร, เสียง, วิดีโอ, คำพูดสด,
ภาพหน้าจอ และอีกมากมาย ทั้งหมดด้วยไปป์ไลน์เดียวที่ขับเคลื่อนด้วย LLM

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **แอปเดสก์ท็อป**

    ---

    ลากไฟล์เข้ามา เลือกภาษาเป้าหมาย รับสำเนาที่แปลแล้วกลับมา
    ลากแล้ววาง, ประวัติ, คำศัพท์ และอื่นๆ

    [:octicons-arrow-right-24: คำแนะนำ 5 นาที](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **บรรทัดคำสั่ง**

    ---

    `ait report.docx --target French` — ไปป์ไลน์เดียวกัน เขียนสคริปต์
    ได้และไม่ต้องมี GUI มีประโยชน์สำหรับ CI, งาน batch, เซิร์ฟเวอร์

    [:octicons-arrow-right-24: คู่มือ CLI](cli.md)

-   :material-robot-outline:{ .lg .middle } **AI agents (MCP)**

    ---

    เปิดเผยการแปลเป็นเครื่องมือ Model Context Protocol เพื่อให้ Claude
    Desktop, Claude Code และไคลเอนต์ MCP อื่นๆ สามารถเรียกใช้ได้
    โดยตรง

    [:octicons-arrow-right-24: ตั้งค่า MCP](mcp.md)

</div>

## คุณสามารถแปลอะไรได้บ้าง

| ประเภท | รูปแบบ |
|---|---|
| **เอกสาร Office** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, รวมถึง `.doc` / `.xls` / `.ppt` รุ่นเก่า |
| **ไฟล์ PDF** | การแปลแบบ extract-overlay พร้อมการรักษาเลย์เอาต์, การแปลบุ๊กมาร์ก / ฟอร์ม / ลิงก์, OCR fallback สำหรับการสแกน |
| **ข้อความและเว็บ** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **คำบรรยาย** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **โลคัลไลเซชัน** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **รูปภาพ** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR หรือ LLM vision) |
| **เสียง** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **วิดีโอ** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (ไปป์ไลน์พากย์เสียงเต็มรูปแบบ) |

## ฟีเจอร์เด่น {: #headline-features }

- **[แปลข้อความ](features/translate-text.md)** — การแปล LLM ทันทีพร้อมการตรวจจับอัตโนมัติ, แก้ไขในที่ และเล่น TTS ภาษาจากขวาไปซ้าย (อาหรับ, ฮีบรู, เปอร์เซีย) เรนเดอร์แบบ native
- **[แปลเอกสาร](features/translate-document.md)** — drop ไฟล์ ดูสปินเนอร์ความคืบหน้าต่อ task รับสำเนาที่แปลแล้วเคียงข้างกัน เป้าหมาย RTL ได้รับ bidi markup ที่เหมาะสม; `Ctrl+P` / `Ctrl+G` หยุดและดำเนินคิวต่อ
- **[สร้างคำบรรยาย (STT)](features/generate-subtitle.md)** — ถอดเสียงเสียง / วิดีโอเป็น SRT / VTT / ASS / SSA
- **[สร้างเสียง (TTS)](features/generate-voice.md)** — สังเคราะห์คำบรรยายเป็น MP3 / WAV พร้อมจังหวะเวลา
- **[พากย์เสียงวิดีโอ](features/dubbing.md)** — STT เต็มรูปแบบ → แปล → TTS → ผสมกลับเข้าวิดีโอต้นทาง
- **[แปลสด](features/live-translation.md)** — overlay คำบรรยายไมโครโฟนหรือเสียงระบบแบบเรียลไทม์
- **[ดึงข้อความ](features/extract-text.md)** — OCR หรือ LLM vision → `.txt` / `.docx`
- **[คำศัพท์](features/glossary.md)** — บังคับใช้คำศัพท์ที่สอดคล้องกันในทุกการแปล

!!! tip "โหมด Vertex AI สำหรับ Gemini"
    ผู้ใช้ระดับองค์กรสามารถสลับการเรียก Gemini จาก Developer API เป็น
    **Vertex AI** ใน **การตั้งค่า → LLM** — ชี้ไปที่โครงการและภูมิภาค
    GCP ของคุณ ใส่ JSON path บัญชีบริการเป็นทางเลือก ดู
    [ผู้ให้บริการ LLM](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup)

!!! tip "ครั้งแรกที่นี่?"
    เริ่มต้นด้วย[การติดตั้ง](getting-started/installation.md) แล้ว
    [คำแนะนำการแปลครั้งแรกใน 5 นาที](getting-started/first-translation.md)
    คุณจะมีเอกสารที่แปลแล้วในเวลาน้อยกว่า 10 นาทีจาก clone ใหม่
