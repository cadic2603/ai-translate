---
description: วินิจฉัยปัญหา AI Translate — ฟอนต์ที่ขาดหายไป, ข้อผิดพลาด FFmpeg, ปัญหาตัวแปลง LibreOffice, ความล้มเหลวในการตั้งค่า OCR และการรับรองความถูกต้อง LLM API
---

# การแก้ไขปัญหา

ข้อผิดพลาดทั่วไป ความหมาย และวิธีแก้ไข

## ข้อผิดพลาดในการตั้งค่า

### "LLM is not configured"

คุณยังไม่ได้เพิ่มคีย์ API เปิดแอปเดสก์ท็อป → **Settings → LLM**
→ วางคีย์ ดู[ผู้ให้บริการ LLM](setup/llm-providers.md)สำหรับคำแนะนำ
ครบถ้วน

### `AUTH_ERROR`

คีย์ LLM API ผิดหรือหมดอายุ

- **Gemini** — สร้างคีย์ใหม่ที่ <https://aistudio.google.com/apikey>
  วางใหม่ใน **Settings → LLM**
- **ผู้ให้บริการแบบกำหนดเอง** — ตรวจสอบว่าคีย์ใช้งานได้ (curl
  endpoint ด้วยตนเองด้วย header `Authorization: Bearer …`
  เดียวกัน) ถ้า endpoint ย้าย ให้อัปเดตฟิลด์ **API endpoint** ด้วย

### `QUOTA_ERROR`

คุณได้ถึงขีดจำกัดของ tier ฟรีหรือแผนแบบชำระเงิน

- **Gemini free tier** — โควต้าคำขอรายวันแตกต่างกันไปต่อโมเดล (ดู
  <https://ai.google.dev/gemini-api/docs/rate-limits>)
  รอหนึ่งวันหรืออัปเกรดเป็นแบบชำระเงิน
- **OpenAI / อื่นๆ** — ตรวจสอบแดชบอร์ดการเรียกเก็บเงินของคุณ ผู้
  ให้บริการหลายรายมี "spend caps" ที่หยุดคำขอเมื่อคุณถึงพวกมัน

### `MODEL_NOT_FOUND`

ชื่อโมเดลที่คุณเลือกไม่พร้อมใช้งาน

- ผู้ให้บริการแบบกำหนดเอง — ตรวจสอบว่าโมเดลอยู่ในรายการ **Models**
  ที่คั่นด้วยเครื่องหมายจุลภาคใน **Settings → LLM**
- รายการ Gemini ในตัว — สลับเป็นโมเดลที่บันทึกไว้ใน **Settings →
  LLM → Default Gemini model**

### `VISION_NOT_SUPPORTED`

คุณเลือกโมเดลที่ไม่ใช่ vision และพยายามแปลรูปภาพ / PDF ที่สแกน
สลับเป็นโมเดลที่ชื่อมี `flash`, `pro` หรือ `vision` (เช่น
`gpt-4o` สำหรับ OpenAI, Gemini Flash หรือ Pro variant ปัจจุบันใดๆ
สำหรับ Gemini)

## ข้อผิดพลาด audio / video

### `FFMPEG_NOT_FOUND`

FFmpeg ไม่อยู่บน PATH ดู[การตั้งค่า FFmpeg](setup/ffmpeg.md)
สำหรับคำสั่งติดตั้งสำหรับ OS ของคุณ

เซิร์ฟเวอร์ MCP wrap ใหม่เป็น: *"FFmpeg is required to decode this
audio/video file but is not installed or not on PATH."*

### หน้า Live ไม่แสดงคำบรรยาย

- **แหล่งเสียงผิด** — เปิด **Settings → Live → Audio source** และ
  ตรวจสอบให้ตรงกับสิ่งที่คุณต้องการจริงๆ (Microphone / System / Both)
- **ไมค์ปิดเสียง** — ตรวจสอบการตั้งค่าเสียง OS แอปใช้อุปกรณ์อินพุต
  เริ่มต้น
- **เสียงระบบยังไม่ได้ตั้งค่า** — ดู[การจับเสียงระบบ](setup/system-audio.md)
  สำหรับขั้นตอน loopback ของ macOS / Windows

### เอาต์พุตเสียงเงียบ / ว่างเปล่า

- **ElevenLabs ไม่มีคีย์** — หน้าเสียงแสดง dialog pre-flight ที่
  เป็นมิตร; หากผ่านพ้นไป ไฟล์อาจมีไบต์ว่างเปล่า ตรวจสอบ
  **Settings → Service → ElevenLabs API key**
- **ข้อผิดพลาดเครือข่าย Edge TTS** — Edge TTS ต้องใช้อินเทอร์เน็ต;
  ถ้า firewall ของคุณบล็อก `speech.platform.bing.com` ให้สลับเป็น
  ElevenLabs, Google Cloud TTS หรือ **Piper TTS** (offline เต็ม
  รูปแบบ)

### Dialog "Piper voice not installed"

หน้าเสียง / พากย์ / แปลข้อความ pre-flight ว่าเสียง Piper สำหรับ
ภาษาเป้าหมายของคุณอยู่บนดิสก์ก่อนที่ worker จะเริ่ม หากไม่มี
คุณจะเห็น modal พร้อมปุ่ม **Open Settings**

ในการดาวน์โหลดเสียง:

1. คลิก **Open Settings** ใน dialog (หรือเปิด **Settings → Voice**
   ด้วยตนเอง)
2. ตรวจสอบว่า **TTS method** ตั้งเป็น **Piper TTS**
3. คลิก **Download voices now** เพื่อเปิด dialog ห้องสมุดเสียง
4. ค้นหาแถวภาษาเป้าหมายของคุณ จากนั้นคลิก **Female voice** หรือ
   **Male voice** ข้างๆ เสียงเป็นไฟล์ ONNX ขนาด ~25–60 MB ดาวน์
   โหลดจาก HuggingFace ครั้งเดียวต่อภาษา
5. ปิด dialog และรันงานแปล / เสียง / dub ใหม่

หากภาษาเป้าหมายของคุณไม่อยู่ในรายการ ก็ไม่มี Piper coverage —
เอนจินจะ fall back เป็น Edge TTS เงียบๆ ในเวลาสังเคราะห์ ดังนั้น
คุณไม่จำเป็นต้องดาวน์โหลดอะไรจริงๆ 13 ภาษาที่ไม่มีเสียง Piper
วันนี้: เบลารุส, เบงกาลี, จีน (ดั้งเดิม), โครเอเชีย, เอสโตเนีย,
ฮีบรู, ญี่ปุ่น, เขมร, เกาหลี, ลิทัวเนีย, มาเลย์, มองโกเลีย, ไทย

หน้า **แปลสด** เป็นที่เดียวที่ *จะไม่* แสดง dialog นี้ — การขัด
จังหวะสตรีมสดด้วย modal จะเลวร้ายกว่า fallback ดังนั้นกรณีเสียง
ที่หายไปที่นั่นจะ route เงียบๆ ไปยัง Edge TTS

## ข้อผิดพลาดการแปลเอกสาร

### การแปล PDF ล้มเหลวในหน้าเฉพาะ

PDF ใช้ checkpoint ต่อหน้า — หน้าที่สำเร็จไม่ทำซ้ำ หน้าที่ล้มเหลว
log stack ไปที่ `app.log`; สาเหตุทั่วไป:

- หน้าเป็น **scan โดยไม่มี text layer** และ OCR ไม่ได้กำหนดค่า
  ตั้งค่า **Settings → OCR** (ดู[เอนจิน OCR](setup/ocr-engines.md))
- หน้ามี **เลย์เอาต์คณิตซับซ้อน** ที่ LLM ทำลาย ลองโมเดลที่แข็ง
  แกร่งกว่า (Pro variant แทน Flash)

### การแปล Office ทำลายการจัดรูปแบบ

- **รูปแบบสมัยใหม่** (`.docx`, `.xlsx`, `.pptx`) — การจัดรูปแบบ
  ถูกรักษาไว้ต่อ run ผ่าน HTML round-trip ถ้าคุณเห็น tag `<b>`
  ที่หลงเหลือในเอาต์พุต LLM ไม่ปิดมัน — รันใหม่ด้วยโมเดลที่แข็ง
  แกร่งกว่า
- **รูปแบบเก่า** (`.doc`, `.xls`, `.ppt`) — เปิด **Settings →
  Translation → Auto-convert legacy** สำหรับความเที่ยงตรงที่ดี
  กว่ามาก ไปป์ไลน์แปลงเป็น `.docx` ก่อน แปล แปลงกลับ

### คิวแปลหยุดกลาง batch

ออกจากแอปและตรวจสอบฐานข้อมูล:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

แถว `Translating` ที่ไม่ได้ถูกแตะมาเป็นนาทีหมายความว่า worker
crash เงียบๆ เปิดแอปเดสก์ท็อปอีกครั้ง — มันจะกลับมาทำงาน Pending
/ Translating tasks อัตโนมัติเมื่อเริ่มต้น

## ปัญหาข้ามฟังก์ชัน

### หลายไฟล์พร้อมกันแปลเงียบๆ เป็นไฟล์เดียว

drop ทีละไฟล์ หรือตรวจสอบคอลัมน์ **Files** ในส่วนหัวคิว — ควร
แสดงจำนวนที่คุณ drop ขีดจำกัด 100 ไฟล์แสดง notification เมื่อ
เกิน

### Sidebar แสดง spinner ตลอดไป

บ่งชี้ว่า worker ยังคงถูก flag ว่ากำลังทำงาน ออกจากแอปอย่างหมดจด
(ไม่มี SIGKILL) — autouse cleanup hooks รีเซ็ต flags หาก SIGKILL
ทิ้งสถานะไว้ ให้ล้าง DB workers ด้วยตนเอง:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Logs อยู่ที่ไหน? {: #where-are-the-logs }

| OS | Path |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Logs จับ DEBUG+ เสมอไม่ว่าจะมี console verbosity เท่าใด เอาต์พุต
console เป็น INFO+ ตามค่าเริ่มต้น; pass `--verbose` ไปยัง CLI
เพื่อ mirror ไฟล์ log เต็มไปยัง stdout

## ยังติดอยู่?

- ดู [FAQ](faq.md) สำหรับคำถามระดับการออกแบบ
- ยื่น issue ที่ <https://github.com/cadic2603/ai-translate/issues>
  พร้อมด้วย: OS, รุ่น Python, คำสั่งที่ล้มเหลว, ส่วนที่เกี่ยวข้อง
  ของ `app.log` และคำอธิบายสิ่งที่คุณคาดหวัง
