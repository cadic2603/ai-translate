---
description: ติดตั้ง AI Translate บน Windows, macOS หรือ Linux จากไบนารีที่สร้างไว้ล่วงหน้าหรือจากซอร์ส — ครอบคลุม Python, FFmpeg และการตั้งค่า LibreOffice เสริม
---

# การติดตั้ง

## สิ่งที่คุณต้องมี

- **Python 3.12 หรือใหม่กว่า** ([ดาวน์โหลด](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — ตัวจัดการแพ็คเกจ Python ที่รวดเร็ว ติดตั้งด้วย:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **คีย์ LLM API** — สิ่งใดสิ่งหนึ่งจาก:
    - [Google Gemini](https://aistudio.google.com/apikey) (มี tier ฟรี — แนะนำสำหรับการเริ่มต้น)
    - endpoint ที่เข้ากันได้กับ OpenAI ใดๆ (OpenAI, Anthropic ผ่าน proxy, Ollama / LM Studio ในเครื่อง ฯลฯ)

## ทางเลือก แต่ปลดล็อกฟีเจอร์เพิ่มเติม

| เครื่องมือ | ใช้โดย | เมื่อใดที่คุณต้องการ |
|---|---|---|
| **FFmpeg** ([ดาวน์โหลด](https://ffmpeg.org/download.html)) | คำบรรยาย, เสียง, พากย์, Live | เวิร์กโฟลว์ audio/video ใดๆ |
| **LibreOffice** ([ดาวน์โหลด](https://www.libreoffice.org/download/)) | รูปแบบ Office บน Linux/macOS | การแปล `.doc` / `.xls` / `.ppt` รุ่นเก่า หรือไฟล์ Office ใดๆ เมื่อไม่ได้ติดตั้ง MS Office |
| **Tesseract** ([คู่มือการติดตั้ง](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | เอนจิน OCR (ค่าเริ่มต้น) | หน้าดึงข้อความ, การแปล PDF ที่สแกน, การแปลภาพที่ฝัง |
| **MS Office** + **pywin32** | Office บน Windows | การแปล Office ความเที่ยงตรงสูงสุดบน Windows |

คุณสามารถติดตั้ง AI Translate ได้โดยไม่มีสิ่งเหล่านี้ — ฟีเจอร์ที่
ต้องการสิ่งเหล่านี้จะแจ้งคุณก่อนที่จะล้มเหลว

## ตั้งค่า

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

การกระทำนี้ติดตั้งทุกสิ่งที่จำเป็นในการรันแอปเดสก์ท็อป, CLI และ
เซิร์ฟเวอร์ MCP

## รัน

=== "แอปเดสก์ท็อป"
    ```bash
    uv run python -m src.main
    ```

=== "บรรทัดคำสั่ง"
    ```bash
    uv run ait --version
    ```

=== "เซิร์ฟเวอร์ MCP"
    ```bash
    uv run ait-mcp           # การส่งข้อมูล stdio (สำหรับ Claude Desktop / Code)
    ```

## เพิ่มคีย์ API ของคุณ

ครั้งแรกที่คุณเปิดแอปเดสก์ท็อป:

1. คลิก **การตั้งค่า** ในแถบด้านข้าง
2. เปิดแท็บ **LLM**
3. วาง **คีย์ Google Gemini API** ของคุณ (หรือกำหนดค่าผู้ให้บริการที่
   เข้ากันได้กับ OpenAI แบบกำหนดเอง) ผู้ใช้ระดับองค์กรสามารถสลับ
   Gemini เป็น **โหมด Vertex AI** แทน — ชี้ไปที่โครงการ GCP และ
   ภูมิภาค เลือกใส่ JSON path บัญชีบริการเป็นทางเลือก ดู
   [ผู้ให้บริการ LLM](../setup/llm-providers.md) สำหรับรายละเอียด
4. เลือกโมเดลเริ่มต้น — Flash variant ปัจจุบันใดๆ (เช่น
   `gemini-2.5-flash`) เป็นจุดเริ่มต้นฟรีที่ดี Pro variants ให้
   คุณภาพที่ดีกว่าด้วยค่าใช้จ่ายที่สูงกว่า
5. ปิดการตั้งค่า — เสร็จแล้ว

คีย์ถูกจัดเก็บใน **OS keychain** ของคุณ (macOS Keychain, Windows
Credential Manager, GNOME / KDE Secret Service บน Linux) ไม่ใช่ใน
ข้อความธรรมดาบนดิสก์

!!! tip "ติดตั้งแบบ headless / เซิร์ฟเวอร์"
    หากคุณไม่สามารถรันแอปเดสก์ท็อปเพื่อตั้งค่าคีย์ ดู
    [ผู้ให้บริการ LLM](../setup/llm-providers.md) สำหรับคำสั่ง CLI
    ของ keychain

## ถัดไป: ลองใช้

[การแปลครั้งแรกใน 5 นาที →](first-translation.md){ .md-button .md-button--primary }
