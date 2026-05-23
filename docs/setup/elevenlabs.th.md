---
description: เชื่อมต่อ ElevenLabs กับ AI Translate สำหรับ TTS neural คุณภาพสูง — สร้าง voiceover ในกว่า 30 ภาษาด้วยคำพูดที่สมจริงและมีอารมณ์
---

# ElevenLabs (TTS)

Text-to-speech neural ระดับพรีเมียม ใช้โดยหน้า
**[Generate Voice](../features/generate-voice.md)**,
**[Dubbing](../features/dubbing.md)** และ
**[Live Translation](../features/live-translation.md)** เมื่อคุณ
เลือก ElevenLabs เป็นวิธี TTS

## รับคีย์ API

1. ลงทะเบียนที่ <https://elevenlabs.io>
2. เปิด <https://elevenlabs.io/app/settings/api-keys>
3. คลิก **+ Create New Key** ตั้งชื่อ (เช่น "ai-translate") คัดลอก
   คีย์ (ดูเหมือน `sk_...`)

Tier ฟรีให้ ~10,000 ตัวอักษร / เดือน เพียงพอสำหรับทดสอบ การใช้งาน
production เริ่มประมาณ $5/เดือน

## กำหนดค่าในแอป

ใน **Settings → Service**:

1. วางคีย์ลงใน **ElevenLabs API key** → **Save**
2. ใส่ **Voice ID** ที่ต้องการใน **Voice ID** (หา ID ที่
   <https://elevenlabs.io/app/voice-lab>; คัดลอก ID จาก URL ของ
   เสียง) ปล่อยว่างให้ ElevenLabs เลือกค่าเริ่มต้น

ใน **Settings → Voice**:

1. ตั้ง **TTS method** เป็น **ElevenLabs**
2. เลือก **ElevenLabs model**:

    | Model | ดีที่สุดสำหรับ |
    |---|---|
    | `eleven_multilingual_v2` (ค่าเริ่มต้น) | การใช้งานทั่วไป, สมดุล latency/quality |
    | `eleven_v3` | คุณภาพสูงสุด (ใช้สำหรับการผลิต dubs) |
    | `eleven_flash_v2_5` | latency ต่ำสุด (ใช้สำหรับ Live Translation) |

## ให้พลังกับอะไร

| Page | ใช้ ElevenLabs เมื่อ |
|---|---|
| **Generate Voice** | คุณต้องการ voiceover คุณภาพพรีเมียมจากไฟล์คำบรรยาย |
| **Dubbing** | คุณต้องการ track พากย์คุณภาพสูงในวิดีโอที่แปลแล้ว |
| **Live Translation** | คุณต้องการการเล่นเสียงพูดของคำบรรยายที่แปลแล้วแบบเรียลไทม์ |

## การ clone เสียง

ElevenLabs รองรับการ clone เสียงแบบกำหนดเอง (แผนเสียเงิน) เมื่อ
คุณ clone เสียงในเว็บไซต์ ElevenLabs ให้วาง Voice ID ของมันใน
**Settings → Service → Voice ID** และ pipeline พากย์ / สร้าง
เสียงจะใช้มัน

## ข้อควรระวัง

!!! warning "การตรวจสอบ pre-flight"
    หน้า Voice / Dubbing ตรวจสอบว่าคีย์ ElevenLabs API ของคุณตั้ง
    *ก่อน* เริ่มงาน หากหายไป คุณจะได้รับ dialog ที่เป็นมิตรชี้คุณ
    ไปยัง Settings ไม่ใช่งานครึ่งทาง

!!! tip "Live mode fall back อัตโนมัติ"
    ในหน้า **Live Translation** หากคุณเลือก ElevenLabs แต่ไม่ได้
    กำหนดค่าคีย์ แอปจะ fall back เป็น **Edge TTS** (ฟรี) อัตโนมัติ
    และประกาศ fallback ในป้ายสถานะเพื่อให้คุณสามารถแก้ไขได้เมื่อ
    สะดวก

!!! info "FFmpeg ยังต้องใช้"
    ElevenLabs ส่งคืน bytes เสียง; แอปยังคงใช้ FFmpeg ในการแปลง
    ระหว่างรูปแบบและรวมคลิปที่จับเวลาเป็นไฟล์เดียว ดู
    [การตั้งค่า FFmpeg](ffmpeg.md)

## ข้อผิดพลาดทั่วไป

| Error | สาเหตุที่เป็นไปได้ |
|---|---|
| `AUTH_ERROR` | คีย์ API ผิด / หมดอายุ วางใหม่ใน Settings → Service |
| `QUOTA_ERROR` | ถึงขีดจำกัดตัวอักษร tier ฟรี หรือแผนเสียเงินหมด |
| `MODEL_NOT_FOUND` | โมเดล ElevenLabs ที่เลือกไม่มีให้ใช้แล้ว; เลือกอื่นใน Settings → Voice |
