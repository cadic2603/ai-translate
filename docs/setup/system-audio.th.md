---
description: จับเสียงระบบบน Linux, macOS และ Windows สำหรับหน้า Live ของ AI Translate — แปลเสียงใดๆ ที่เล่นบนคอมพิวเตอร์ของคุณแบบเรียลไทม์
---

# การจับเสียงระบบ (Live)

หน้า **[Live Translation](../features/live-translation.md)** สามารถ
จับ **เสียงระบบ** (ทุกอย่างที่เล่นบนลำโพงของคุณ) เพื่อให้คุณสามารถ
ใส่คำบรรยาย / แปลสื่อใดๆ — สาย Zoom, YouTube, Netflix, เกม, เสียง
ระบบ

ใน **Settings → Live → Audio source** (หรือ combo ที่ด้านบนของหน้า
Live) เลือก:

- **Microphone** — เฉพาะไมค์ของคุณ
- **System audio** — เฉพาะสิ่งที่เล่นบนลำโพงของคุณ
- **Both** — ทั้งสองผสมกัน (ดีสำหรับการบรรยายทับสื่อหรือจับการประชุม
  แบบไฮบริด)

เมื่อคุณเลือก **System audio** หรือ **Both** แอปจะส่งไปยัง backend
การจับที่ถูกต้องสำหรับ OS ของคุณ แบนเนอร์เตือนแบบ inline พร้อมลิงก์
ติดตั้งที่คลิกได้จะปรากฏขึ้นถ้าไม่ได้ทำตามข้อกำหนดเบื้องต้นของ OS
เพื่อให้คุณไม่ต้องเริ่มเซสชันเพื่อค้นหาว่ามีบางอย่างหายไป

## Linux (PulseAudio / PipeWire)

ทำงาน out of the box บนทุก distro สมัยใหม่

แอปใช้ `parec` (PulseAudio Recorder) เพื่อ tap **monitor source**
ของ sink ค่าเริ่มต้นของคุณ shim ความเข้ากันได้ของ PulseAudio ของ
PipeWire ทำให้สิ่งนี้โปร่งใส — คุณไม่ต้องการ PulseAudio ดิบ

```bash
parec --version    # ควรพิมพ์อะไรบางอย่าง
```

ถ้า `parec` หายไป แบนเนอร์เตือนตรวจจับ package manager ของ distro
ของคุณและใส่คำสั่งติดตั้งที่แน่นอน — ตัวอย่างเช่น:

> การจับเสียงระบบต้องการ PulseAudio หรือ PipeWire — รัน
> `sudo apt-get install pulseaudio`

ตรวจพบบน apt-get / dnf / pacman / zypper / apk; คุณสามารถ
copy-paste คำสั่งตรงไปยัง terminal ได้

## macOS

CoreAudio ไม่เปิดเผยเสียงระบบแบบ native ดังนั้นคุณต้องการ
**อุปกรณ์ loopback เสมือน** — ติดตั้งหนึ่งใน:

- **[BlackHole](https://existential.audio/blackhole/)** — ฟรี, open source
- **[Loopback](https://rogueamoeba.com/loopback/)** — เสียเงิน, GUI ที่ขัดเกลา
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — ตัวเลือกฟรีรุ่นเก่า
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — เสียเงิน

แอป auto-detect อันใดอันหนึ่งผ่าน
`ffmpeg -f avfoundation -list_devices` และใช้การจับคู่แรก ไม่ต้อง
ตั้ง loopback เป็นเอาต์พุต / อินพุตค่าเริ่มต้นของคุณ — การจับ
เกิดขึ้นโดยตรงผ่าน backend avfoundation ของ `ffmpeg`

หลังจากติดตั้ง แค่เลือก **System audio** ใน combo ของหน้า Live
และแบนเนอร์เตือนหายไป

## Windows

Native — ในกรณีส่วนใหญ่ **ไม่ต้องการซอฟต์แวร์เพิ่ม**

แอปพูดคุยโดยตรงกับ **WASAPI loopback** ผ่านแพ็คเกจ Python
[`soundcard`](https://github.com/bastibe/SoundCard) (ติดตั้งอัตโนมัติ
กับแอปบน Windows) นี่คือ API loopback แบบ native เดียวกันที่
แอปเดสก์ท็อป Tauri / Rust ใช้; มันจับเอาต์พุตลำโพงเริ่มต้นโดยไม่
ต้องใช้สายเสมือน

ถ้า WASAPI loopback ไม่พร้อมใช้งานด้วยเหตุผลใด (Windows เวอร์ชัน
เก่า, ไดรเวอร์เสียงที่ไม่ปกติ) แอป fall back ไปยัง
`ffmpeg -f dshow` ต่ออุปกรณ์ DirectShow loopback เสมือน เลือก
หนึ่งใน:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — ฟรี, ให้ `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — ฟรี, มาเป็น `CABLE Output (VB-Audio Virtual Cable)`
- **Stereo Mix (Realtek Audio)** — ตัวเลือก on-board รุ่นเก่า มักถูกปิดใช้งานโดยค่าเริ่มต้น

แอป probe สำหรับเหล่านี้ตามลำดับและใช้อันแรกที่มีอยู่

## ทำไม "Both" จึงรับเสียงของคุณ AND เสียงระบบ

ในโหมด **Both** แอปเปิด stream การจับสองอันพร้อมกัน — ไมค์ของคุณ
ผ่าน `sounddevice` เสียงระบบผ่าน backend เฉพาะ OS ด้านบน — และผสม
กันที่ระดับ sample-block นี่คือโหมดที่ถูกต้องสำหรับการบรรยายทับ
วิดีโอ หรือจับทั้งสองด้านของการประชุมแบบไฮบริด (เสียงของคุณบวก
ผู้เข้าร่วมบนลำโพง)

> **เคล็ดลับ:** ถ้าคุณได้ยินเสียงสะท้อนหรือได้คำบรรยายซ้ำ คุณมีเสียง
> ระบบเข้ามาผ่านไมโครโฟนของคุณ (ลำโพงดัง → ไมค์รับ) สลับไปที่
> **System audio** อย่างเดียว หรือใช้หูฟัง

## การแก้ไขปัญหา

| อาการ | สาเหตุที่เป็นไปได้ |
|---|---|
| หน้า Live เริ่มต้นแต่ไม่มีคำบรรยาย | เลือกแหล่งเสียงผิด หรือไมค์ค่าเริ่มต้นของคุณถูกปิดเสียง |
| คำบรรยายสำหรับเสียงของคุณแต่ไม่ใช่สำหรับวิดีโอ YouTube | ข้อกำหนดเบื้องต้นของเสียงระบบยังไม่ติดตั้ง (แบนเนอร์ควรแสดงคำแนะนำการติดตั้ง) |
| คำบรรยายสองครั้ง (echo) | โหมด "Both" รับเสียงระบบสองครั้ง — ครั้งหนึ่งจากลำโพงผ่านไมค์ ครั้งหนึ่งผ่าน loopback สลับไปที่ System audio อย่างเดียว หรือใช้หูฟัง |
| แบนเนอร์ยังคงมองเห็นได้หลังจากติดตั้งซอฟต์แวร์ที่หายไป | สลับแท็บและกลับมา — แบนเนอร์ตรวจสอบใหม่ในการแสดงหน้า |
| macOS: BlackHole ติดตั้งแล้วแต่แบนเนอร์ยังอยู่ | ยืนยันว่า BlackHole อยู่ในรายการอุปกรณ์เสียง `ffmpeg -f avfoundation -list_devices true -i ""`; แอปต้องเห็นมันที่นั่น |
| Windows: WASAPI loopback ล้มเหลวแม้ว่าจะไม่มี error | ลองติดตั้ง VB-Audio Virtual Cable เป็น fallback; Windows เวอร์ชันเก่าหรือไดรเวอร์เสียงบางตัวไม่เปิดเผย loopback ผ่าน `soundcard` |
