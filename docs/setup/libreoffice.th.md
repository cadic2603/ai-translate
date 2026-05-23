---
description: ติดตั้ง LibreOffice เพื่อให้ AI Translate สามารถแปลรูปแบบ Office รุ่นเก่า (.doc, .xls, .ppt) และไฟล์ ODF (.odt, .ods, .odp) บน macOS และ Linux
---

# LibreOffice (รูปแบบ Office)

Pipeline การแปล Office เลือก backend ที่ดีที่สุดที่มีในลำดับนี้:

1. **win32com** (Windows + MS Office ติดตั้ง) — ความเที่ยงตรงสูงสุด
2. **LibreOffice UNO** (ข้ามแพลตฟอร์ม) — fallback เมื่อไม่มี
   win32com
3. **python-docx / openpyxl / python-pptx** (รูปแบบสมัยใหม่เท่านั้น)
   — fallback Python บริสุทธิ์เมื่อไม่มีอันใดข้างต้น

LibreOffice เป็น **เส้นทางเดียว** สำหรับ `.doc` / `.xls` / `.ppt`
รุ่นเก่าบน Linux และ macOS และเส้นทางที่แนะนำบนแพลตฟอร์มเหล่านั้น
สำหรับรูปแบบ Office สมัยใหม่ด้วย (ความเที่ยงตรงดีกว่า backend
Python บริสุทธิ์ โดยเฉพาะตารางและวัตถุที่ฝัง)

## ติดตั้ง

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    หรือดาวน์โหลดจาก <https://www.libreoffice.org/download/download/>

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    แอปเดสก์ท็อปบน Windows มักใช้ **win32com** กับ MS Office ที่
    ติดตั้ง — LibreOffice เป็น *fallback* ถ้า MS Office หายไป
    ติดตั้งจาก <https://www.libreoffice.org/download/download/>

## ตรวจสอบ

```bash
soffice --version
```

ถ้าคุณได้ "command not found" บน macOS ไบนารีอยู่ที่
`/Applications/LibreOffice.app/Contents/MacOS/soffice` แอปจะ
auto-discover มันผ่านเส้นทางการติดตั้งทั่วไป แต่คุณสามารถแทนที่ใน
**Settings → General → LibreOffice path** ได้ถ้าจำเป็น

## ให้พลังกับอะไร

เมื่อ LibreOffice เป็น backend ที่ใช้งานอยู่:

| ฟีเจอร์ | หมายเหตุ |
|---|---|
| **Office สมัยใหม่** (`.docx`, `.xlsx`, `.pptx`) | ใช้เป็น fallback เมื่อไม่มี win32com |
| **Office รุ่นเก่า** (`.doc`, `.xls`, `.ppt`) | จำเป็น — Python บริสุทธิ์อ่านไม่ได้ |
| **ODF** (`.odt`, `.ods`, `.odp`) | ใช้สำหรับการแปลง round-trip เมื่อ **Auto-convert ODF** เปิด |
| **Auto-convert legacy / ODF → OOXML** | จำเป็น |

## กระบวนการเบื้องหลัง

ครั้งแรกที่ต้องการ LibreOffice แอปจะสร้างกระบวนการ `soffice` ใน
โหมด headless และทำให้มันยังมีชีวิตอยู่ระหว่างการแปล
(`office_lifecycle.py`) มันปิดตัวเองอัตโนมัติเมื่อออกจากแอป

## ข้อควรระวัง

!!! warning "เวลาเริ่มต้นครั้งแรก"
    การแปลครั้งแรกที่กระทบ LibreOffice รอ ~5-10 วินาทีให้ `soffice`
    เริ่มทำงาน การแปลถัดไปใช้กระบวนการเดิมและรวดเร็ว

!!! info "JVM crash logs"
    ส่วนประกอบ Java ของ LibreOffice บางครั้งสร้างไฟล์
    `hs_err_pid*.log` เมื่อมัน segfault แอป route ไปยังไดเร็กทอรี
    ชั่วคราวเพื่อไม่ให้ pollute โฟลเดอร์โครงการของคุณ

!!! tip "Auto-convert legacy / ODF"
    เปิดใช้งาน **Settings → Translation → Auto-convert legacy**
    ถ้าคุณแปล `.doc` / `.xls` / `.ppt` เป็นประจำ Pipeline จะแปลง
    เป็น `.docx` / `.xlsx` / `.pptx` ก่อน (ผ่าน
    `convert_to_modern_format`) แปลสำเนาสมัยใหม่ จากนั้นแปลงกลับ
    ความเที่ยงตรงสูงกว่าการแปลรูปแบบรุ่นเก่าโดยตรงมาก
