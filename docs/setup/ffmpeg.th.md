---
description: ติดตั้ง FFmpeg เพื่อให้ AI Translate สามารถถอดรหัสเสียงและวิดีโอสำหรับการสร้างคำบรรยาย, การสังเคราะห์เสียง และการพากย์เสียงวิดีโอ — จำเป็นสำหรับฟีเจอร์มีเดีย
---

# FFmpeg

FFmpeg จำเป็นสำหรับเวิร์กโฟลว์เสียง / วิดีโอใดๆ:

- **สร้างคำบรรยาย** — ถอดรหัสเสียงต้นทางสำหรับ STT
- **สร้างเสียง** — รวมคลิป TTS ที่จับเวลาเป็นไฟล์เดียว
- **พากย์เสียง** — STT → TTS → mux กลับเข้าวิดีโอ
- **การแปลสด** — เมื่อการจับเสียงระบบผ่าน `parec`

ไม่ได้รวมไว้ — ติดตั้งครั้งเดียวบนระบบของคุณ

## ติดตั้ง

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    หรือ สำหรับ build ที่สมบูรณ์ยิ่งขึ้น เปิดใช้งาน
    [RPM Fusion](https://rpmfusion.org/Configuration) ก่อน

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    ดาวน์โหลด static build จาก
    <https://www.gyan.dev/ffmpeg/builds/> (build "release
    essentials" ใช้ได้) แตกไฟล์ จากนั้นเพิ่มโฟลเดอร์ `bin/` ไปยัง
    PATH ของคุณ:

    1. กด **Win + R** พิมพ์ `sysdm.cpl` กด **Enter**
    2. **Advanced → Environment Variables → System variables → Path → Edit**
    3. **New** → วาง path สมบูรณ์ของโฟลเดอร์ `bin` ของ FFmpeg
    4. **OK** ทุกที่ รีสตาร์ทเทอร์มินัลที่เปิดอยู่

## ตรวจสอบ

```bash
ffmpeg -version
```

คุณควรเห็น banner เวอร์ชันที่มี `--enable-libx264 --enable-libvpx`
ในบรรทัดการกำหนดค่า ถ้าเห็น "command not found" การติดตั้งยังไม่
อยู่ใน PATH

## การตรวจสอบ pre-flight ในแอป

หน้า Voice / Dubbing เรียก `shutil.which("ffmpeg")` ก่อนเริ่มงาน
ถ้าไม่พบ FFmpeg คุณจะเห็น dialog ข้อผิดพลาดที่เป็นมิตรพร้อมลิงก์
กลับมาที่นี่ ไม่ใช่ task ที่รันครึ่งทาง

## ข้อผิดพลาดทั่วไป

| Error | ความหมาย |
|---|---|
| `FFMPEG_NOT_FOUND` | `ffmpeg` ไม่ได้อยู่ใน PATH ในเวลาที่หน้าพยายามรันมัน ติดตั้ง (ด้านบน) และรีสตาร์ทแอป |

ในเซิร์ฟเวอร์ MCP (`ait-mcp`) ข้อผิดพลาดเดียวกันถูก wrap ใหม่เป็น
ข้อความที่อ่านได้:

> *"FFmpeg is required to decode this audio/video file but is not
> installed or not on PATH. Install FFmpeg and try again."*
