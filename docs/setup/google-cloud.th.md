---
description: เชื่อมต่อ Google Cloud กับ AI Translate สำหรับ Vision OCR, Speech-to-Text และ Text-to-Speech — ตั้งค่าคีย์ API และเปิดใช้บริการที่เกี่ยวข้อง
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

คีย์ API เดียวของ Google Cloud ขับเคลื่อน backend ที่เป็นทางเลือก
สามรายการ:

- **Vision OCR** — เอนจิน OCR เสียเงิน (1,000 ฟรี / เดือน)
- **Speech-to-Text v1** — STT เสียเงิน (60 นาที / เดือนฟรี)
- **Text-to-Speech v1** — TTS เสียเงิน (1 M ตัวอักษร / เดือนฟรี
  สำหรับ WaveNet)

คุณต้องเปิดใช้งานเฉพาะ APIs ที่คุณใช้จริง

## รับคีย์ API

1. [สร้างโครงการ Google Cloud](https://console.cloud.google.com/projectcreate)
2. เปิดไลบรารี API: <https://console.cloud.google.com/apis/library>
3. เปิดใช้งานหนึ่งใน:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [สร้างคีย์ API](https://console.cloud.google.com/apis/credentials):
   คลิก **+ Create Credentials → API key**
5. คัดลอกคีย์ (ดูเหมือน `AIza...`)

!!! tip "จำกัดคีย์"
    ในหน้ารายละเอียดคีย์ API ภายใต้ **API restrictions** จำกัดคีย์
    ไว้เฉพาะ APIs ที่คุณเปิดใช้งาน ด้วยวิธีนี้ คีย์ที่รั่วไหลจะ
    ไม่สามารถสะสมค่าใช้จ่ายในบริการที่คุณไม่ได้ตั้งใจจะใช้

## กำหนดค่าในแอป

ใน **Settings → Service**:

1. วางลงใน **Google Cloud API key** → **Save**

คีย์เดียวนี้พร้อมใช้งานสำหรับบริการ Google ทั้งสามแล้ว

## เปิดใช้งานแต่ละบริการ

### Vision OCR

ใน **Settings → OCR → OCR method = Google Cloud OCR**

แค่นั้น — มันจะใช้คีย์เดียวกันจาก Service

### Speech-to-Text

ใน **Settings → Subtitle → STT method = Google Cloud** (สำหรับหน้า
Subtitle / Voice) หรือ **Settings → Live → STT method = Google
Cloud** (สำหรับหน้า Live)

ใน **Settings → Subtitle → Google STT model** เลือกโมเดลการรู้จำ:

| Model | ดีที่สุดสำหรับ |
|---|---|
| `latest_long` (ค่าเริ่มต้น) | เสียงรูปแบบยาว (สัมภาษณ์, การบรรยาย) |
| `latest_short` | คำสั่งเสียง, วลีสั้น |
| `phone_call` | เสียงโทรศัพท์ (8 kHz) |
| `medical_dictation` / `medical_conversation` | เสียงด้านการแพทย์ |

### Text-to-Speech

ใน **Settings → Voice → TTS method = Google Cloud TTS**

โดยค่าเริ่มต้น เซิร์ฟเวอร์เลือกเสียงตามภาษาและเพศ — นั่นคือสิ่งที่
ผู้ใช้ส่วนใหญ่ต้องการ การ pin เสียง Google เฉพาะ (เช่น
`en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`) ได้รับการสนับสนุนโดย
เอนจินแต่ยังไม่ได้เปิดเผยเป็นฟิลด์ Settings; สามารถตั้งโดยแก้ไข
`voice/google_tts_voice_name` ใน `settings.ini` โดยตรง รหัสเสียง
อยู่ใน <https://cloud.google.com/text-to-speech/docs/voices>

## ข้อผิดพลาดทั่วไป

| Error | สาเหตุที่เป็นไปได้ |
|---|---|
| `AUTH_ERROR` | คีย์ผิด / หมดอายุ วางใหม่ใน Settings → Service |
| `API not enabled` | คุณยังไม่ได้เปิดใช้งาน API ที่เฉพาะเจาะจง (Vision / Speech / TTS) ในโครงการ Cloud นี้ |
| `QUOTA_ERROR` | ถึงขีดจำกัด tier ฟรีสำหรับ API นี้ รอ หรืออัปเกรดการเรียกเก็บเงิน |
| `INVALID_ARGUMENT_ERROR` | ชื่อเสียงไม่มีอยู่ในภาษาที่คุณเลือก |

## การป้องกันต้นทุน

!!! warning
    APIs ทั้งสามของ Google เป็นแบบจ่ายภายหลัง — เมื่อคุณเกิน tier
    ฟรี คุณเริ่มถูกเรียกเก็บเงินโดยไม่หยุด ตั้ง
    [การแจ้งเตือนงบประมาณ](https://console.cloud.google.com/billing/budgets)
    บนโครงการ Cloud ก่อนทำงานปริมาณมาก
