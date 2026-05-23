---
description: ตั้งค่าเอนจิน OCR สำหรับการดึงข้อความจากภาพและ PDF — เลือกระหว่าง Tesseract หรือ EasyOCR ออฟไลน์ หรือ Google Vision OCR บนคลาวด์
---

# เอนจิน OCR

OCR ใช้เพื่ออ่านข้อความจากภาพ — ทั้งบนหน้า [Extract Text](../features/extract-text.md)
และเป็น fallback ภายในการแปล Document เมื่อหน้าถูกสแกน (ไม่มี
เลเยอร์ข้อความ) หรือเมื่อคุณเปิด **Translate embedded images**

คุณสามารถเลือกจากเอนจิน OCR สามตัว

## Tesseract (ค่าเริ่มต้นที่แนะนำ)

ฟรี, รวดเร็ว, ออฟไลน์ ต้องการการติดตั้งระบบ

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` นำทุกภาษาที่รองรับมา หากต้องการประหยัดดิสก์
    ติดตั้งเฉพาะที่ต้องการ (เช่น `tesseract-ocr-fra` สำหรับฝรั่งเศส)

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    ดาวน์โหลด installer จาก
    [Tesseract releases ของ UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
    เรียกใช้ ยอมรับค่าเริ่มต้น — แพ็คภาษามาพร้อม

ตรวจสอบ:

```bash
tesseract --version
tesseract --list-langs
```

ในแอปเดสก์ท็อป: **Settings → OCR → OCR method = Tesseract** เสร็จ

## EasyOCR

ฟรี, ออฟไลน์ ดีมากสำหรับสคริปต์ที่ไม่ใช่ละติน (จีน, เกาหลี, ญี่ปุ่น,
ไทย) โมเดลดาวน์โหลดในการใช้ครั้งแรก (~1 GB ทั้งหมด)

```bash
uv sync --extra easyocr
```

ในแอปเดสก์ท็อป: **Settings → OCR → OCR method = EasyOCR**

ครั้งแรกที่คุณใช้สำหรับภาษาหนึ่ง โมเดลที่เกี่ยวข้องดาวน์โหลดไปยัง
`~/.EasyOCR/` การรันถัดไปทันที

## Google Cloud Vision

คลาวด์, เสียเงิน (1,000 คำขอฟรี / เดือน) ความแม่นยำสูงสุด โดยเฉพาะ
บนเนื้อหาที่มีเสียงรบกวน / ลายมือ / สคริปต์ผสม

1. [สร้างโครงการ Google Cloud](https://console.cloud.google.com/projectcreate)
2. เปิดใช้งาน [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [สร้างคีย์ API](https://console.cloud.google.com/apis/credentials)
4. ในแอปเดสก์ท็อป: **Settings → Service → Google Cloud API key**
   → วาง
5. **Settings → OCR → OCR method = Google Cloud OCR**

คีย์ Google Cloud API เดียวกันขับเคลื่อน Vision OCR, Speech-to-Text
และ Text-to-Speech ถ้าคุณเปิดใช้งาน APIs เหล่านั้นด้วย

## เปรียบเทียบความแม่นยำ

แท็บ **Settings → OCR** มีตารางเปรียบเทียบเล็กๆ ในตัว — ความครอบ
คลุมภาษา, ออนไลน์/ออฟไลน์, ราคา, ความแม่นยำ อ่านซ้ำเมื่อใดก็ตามที่
คุณรู้สึกอยากเปลี่ยน

## เมื่อใดใช้ OCR

| ที่ | พฤติกรรม |
|---|---|
| **หน้า Extract Text** (เมื่อ method = OCR) | OCR โดยตรงบนภาพที่ drop |
| **Translate Document → PDF** | OCR fallback ในหน้าที่สแกนเท่านั้น (ไม่มีเลเยอร์ข้อความ) |
| **Translate Document → Office** ด้วย **Translate embedded images** เปิด | OCR + LLM vision บนทุกภาพที่ฝัง |

## เคล็ดลับ

!!! tip "เลือกภาษาต้นทาง"
    เอนจิน OCR ส่วนใหญ่แม่นยำมากขึ้นเมื่อคุณบอกว่าคาดหวังภาษาใด
    หน้า Subtitle / Document / Extract Text ทั้งหมดส่งตัวเลือก
    **Source language** ของคุณไปยังเอนจิน OCR

!!! tip "Tesseract เพียงพอสำหรับข้อความพิมพ์สะอาด"
    อย่าเอื้อมไป OCR คลาวด์จนกว่า Tesseract / EasyOCR จะล้มเหลว
    บนเนื้อหาของคุณจริงๆ พวกมันฟรี รวดเร็ว และดีอย่างน่าประหลาดใจ
