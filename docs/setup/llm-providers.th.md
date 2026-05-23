---
description: "กำหนดค่าผู้ให้บริการ LLM สำหรับการแปล: Google Gemini (แนะนำ), endpoints ที่เข้ากันได้กับ OpenAI หรือผู้ให้บริการแบบกำหนดเองที่มีคีย์ API"
---

# ผู้ให้บริการ LLM

Pipeline การแปลเรียก Large Language Model สำหรับการแปลจริง คุณ
สามารถกำหนดค่าหนึ่งหรือหลาย; ตัวเลือกโมเดลต่อฟีเจอร์ให้แต่ละหน้าใช้
ตัวที่แตกต่างกัน

## Google Gemini (แนะนำสำหรับการตั้งค่าครั้งแรก) {: #google-gemini-recommended-for-first-time-setup }

Tier ฟรีใจกว้างและดีพอสำหรับการใช้งานส่วนตัวส่วนใหญ่

1. ไปที่ <https://aistudio.google.com/apikey>
2. คลิก **Create API key** (ลงชื่อเข้าใช้ด้วยบัญชี Google ของคุณ)
3. คัดลอกคีย์ (ดูเหมือน `AIza...`)
4. ในแอปเดสก์ท็อป: **Settings → LLM → Gemini API key** → วาง →
   **Save**
5. เลือกโมเดลค่าเริ่มต้นใน dropdown **Default Gemini model**
   ลายไลน์ของ Google มักจะดูเหมือน:

    - **Flash** variants (เช่น `gemini-2.5-flash`) — เร็ว, tier
      ฟรีใจกว้าง, คุณภาพดี จุดเริ่มต้นที่แนะนำ
    - **Pro** variants — ช้ากว่า, คุณภาพสูงกว่า, แพงกว่า
    - **Flash-lite** — เร็วที่สุด, ถูกที่สุด, คุณภาพต่ำกว่า

    ชื่อโมเดลที่แม่นยำขึ้นอยู่กับสิ่งที่ Google ปล่อยให้บัญชีของ
    คุณ; เลือกอันที่มี `flash` ในชื่อสำหรับค่าเริ่มต้นที่สมดุล

เสร็จ คีย์เก็บใน OS keychain ของคุณ ไม่ใช่ในข้อความธรรมดา

### โหมด Vertex AI (สำหรับองค์กร)

ภายในบล็อกการตั้งค่า Gemini คู่ radio ให้คุณสลับจาก **Developer
API** ไปยัง **Vertex AI** — โมเดล Gemini เดียวกัน เรียกเก็บเงิน
ผ่านบัญชี GCP ของคุณ พร้อมการควบคุมระดับองค์กร (VPC-SC, audit
logs, การพักข้อมูลระดับภูมิภาค)

1. ใน **Settings → LLM** สลับ Gemini radio จาก **Developer API**
   เป็น **Vertex AI**
2. กรอก:
    - **Project** — ID โครงการ GCP ของคุณ
    - **Location** — region ของ Vertex (ค่าเริ่มต้น `us-central1`)
    - **Credentials path** *(ตัวเลือก)* — path ไปยังไฟล์คีย์ JSON
      ของ service account ปล่อยว่างเพื่อใช้ Application Default
      Credentials (`gcloud auth application-default login`)
3. **Save** dropdown โมเดลจะถูก repopulate จาก Vertex เมื่อตั้ง
   project แล้ว

การรีเฟรช OAuth จัดการโดย `google-genai` อัตโนมัติ Path JSON ของ
service-account ถูกเก็บเป็น plaintext โดยตั้งใจ (*path* ไม่ใช่
ความลับ — เนื้อหาของไฟล์เป็น และพวกมันอยู่บนดิสก์ตามแนวทางปฏิบัติ
ที่ดีที่สุดที่ Google จัดทำเอกสาร)

## OpenAI / เข้ากันได้กับ OpenAI

อะไรก็ตามที่เปิดเผย REST API ที่เข้ากันได้กับ OpenAI ทำงานได้ —
OpenAI เอง, Anthropic ผ่าน [LiteLLM proxy](https://docs.litellm.ai),
Ollama ในเครื่อง, LM Studio, vLLM, Together.ai, Groq และอื่นๆ

ใน **Settings → LLM**:

1. คลิก **Add Custom Provider**
2. กรอก:
    - **Name** — ป้ายชื่อเช่น "OpenAI" / "Local Ollama" / "Anthropic"
    - **API endpoint** — URL ฐาน (เช่น `https://api.openai.com/v1`
      หรือ `http://localhost:11434/v1` สำหรับ Ollama)
    - **API key** — ปล่อยว่างสำหรับ endpoint ในเครื่องที่ไม่
      ต้องการการรับรองความถูกต้อง
    - **Models** — รายการคั่นด้วยจุลภาค (เช่น `gpt-4o-mini,
      gpt-4o, gpt-3.5-turbo`)
3. คลิก **Save**

ผู้ให้บริการแบบกำหนดเองถูกเก็บเป็น JSON blob ใน OS keychain
(รวมคีย์ API)

## การสลับโมเดลค่าเริ่มต้น

dropdown **Default Gemini model** ใน **Settings → LLM** ตั้ง
fallback ที่ใช้โดยทุกหน้าฟีเจอร์ที่ไม่มีตัวเลือกของตัวเอง

หน้าที่มีตัวเลือกโมเดลของตัวเอง:

- **Translate Text** — `Translate Text settings tab → Default model`
- **Translate Document** — เลือกต่องาน; fall back ไปยังค่าเริ่มต้น
- **Subtitle / Voice / Dubbing / Live / Extract Text** — แต่ละ
  อันมีค่าเริ่มต้นต่อฟีเจอร์ของตัวเองในแท็บ Settings ของมัน

นี่ให้คุณผสมและจับคู่: Flash ฟรีสำหรับ live, Pro สำหรับเอกสารใหญ่,
Ollama ในเครื่องสำหรับข้อมูลที่ละเอียดอ่อน

## คีย์ถูกเก็บที่ไหน

| OS | การเก็บ |
|---|---|
| **macOS** | Keychain (login keychain) |
| **Windows** | Credential Manager |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (ไม่มี daemon)** | fall back ไปยัง plaintext INI ใน `~/.config/ai-translate/settings.ini` |

ค่า INI fallback ถูก migrate ไปยัง keychain ในการอ่านครั้งแรก
เมื่อใดก็ตามที่ keychain พร้อมใช้งาน — ไม่มีขั้นตอนด้วยตนเอง

## การติดตั้งแบบ headless / เซิร์ฟเวอร์

โดยไม่มีเซสชันเดสก์ท็อป คุณยังสามารถตั้งคีย์ผ่าน `keyring` CLI
ของ Python (หลัง `uv sync`):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# ผู้ให้บริการแบบกำหนดเอง (วาง JSON blob — ดู Settings UI สำหรับ schema)
uv run keyring set ai-translate llm/custom_providers
```

หรือตั้งคีย์ INI เดียวกันโดยตรงใน `settings.ini` — แอปจะ migrate
ไปยัง keychain ในการอ่านครั้งแรก ไฟล์อยู่ที่:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## ทดสอบการตั้งค่าของคุณ

การตรวจสอบความปลอดภัยที่เร็วที่สุด:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Thai --quiet
cat /tmp/x_translated__th.txt
```

ถ้าคุณเห็น "สวัสดีชาวโลก" — คุณเสร็จแล้ว

## ข้อผิดพลาดทั่วไป

| Error | สาเหตุที่เป็นไปได้ |
|---|---|
| `AUTH_ERROR` | คีย์ API ผิด / หมดอายุ วางใหม่ใน Settings |
| `QUOTA_ERROR` | คำขอต่อวันของ tier ฟรีเกิน รอ หรือจ่าย |
| `MODEL_NOT_FOUND` | รายการ `models` ของผู้ให้บริการแบบกำหนดเองไม่รวมโมเดลที่ขอ |
| `VISION_NOT_SUPPORTED` | โมเดลที่คุณเลือกไม่สามารถรับอินพุตภาพ ใช้ `flash` / `pro` / `vision` variant |

ดู [Troubleshooting](../troubleshooting.md) สำหรับเพิ่มเติม
