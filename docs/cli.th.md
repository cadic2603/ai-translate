---
description: ใช้ ait command-line interface เพื่อแปลไฟล์แบบ headless — รองรับ PDFs, เอกสาร Office, คำบรรยาย และกว่า 45 ภาษาจากสคริปต์หรืองาน CI
---

# Command Line (`ait`)

การแปลแบบ headless — ไปป์ไลน์เดียวกับแอปเดสก์ท็อป ไม่ต้องการ
display มีประโยชน์สำหรับ CI, งาน batch, เซิร์ฟเวอร์ และเวิร์กโฟลว์
แบบสคริปต์

## เริ่มต้นอย่างรวดเร็ว

```bash
ait report.docx --target French
```

เอาต์พุตจะปรากฏข้างต้นทางในชื่อ
`report_translated_<src>_<tgt>.docx`

## สูตรทั่วไป

### หลายไฟล์

```bash
ait *.pdf --target Japanese
```

การขยาย Glob เป็นงานของ shell (Unix) บน Windows / `cmd.exe` ให้
รายการไฟล์อย่างชัดเจนหรือใช้ PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### ไดเร็กทอรีเอาต์พุตแบบกำหนดเอง

```bash
ait report.docx --target French --output ./translated/
```

ไดเร็กทอรีจะถูกสร้างถ้าไม่มี ถ้าไม่สามารถสร้างได้ (permission
denied ฯลฯ) คุณจะได้รับข้อผิดพลาดที่ชัดเจนและรหัสออก 2 — ไม่มีการ
รันครึ่งทาง

### ระบุภาษาต้นทาง

```bash
ait letter.txt --target German --source "English (US)"
```

การจับคู่ต้นทางไม่คำนึงถึงตัวพิมพ์ใหญ่/เล็ก "Chinese" เปล่าจะพิมพ์
คำใบ้:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### เลือกโมเดลเฉพาะ

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# หรือ Provider:model_name อื่นใดที่ลงทะเบียนในแท็บ LLM ของแอปเดสก์ท็อป
```

รูปแบบเป็น `Provider:model_name` อย่างเคร่งครัด ขาดเครื่องหมายโคลอน
→ ออก 2 พร้อมข้อความที่ชัดเจนแทนที่จะ fall back เงียบๆ ไปยังโมเดล
Gemini เริ่มต้น

### ตัวเลือก Office

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` ต้องการ OCR ที่กำหนดค่าไว้ (ดู
[เอนจิน OCR](setup/ocr-engines.md))

### Auto-convert รูปแบบเก่า

```bash
ait old-doc.doc --target French --convert-legacy
```

ไปป์ไลน์แปลง `.doc` → `.docx` ก่อน (ความเที่ยงตรงดีกว่า) แปลสำเนา
สมัยใหม่ แปลงกลับ เหมือนกันสำหรับ `--convert-odf` และ `.odt` /
`.ods` / `.odp`

### เงียบ / ละเอียด

```bash
ait report.docx --target French --quiet      # เฉพาะข้อผิดพลาด
ait report.docx --target French --verbose    # firehose DEBUG เต็ม
```

โหมดเริ่มต้นพิมพ์ banner และความคืบหน้าต่อ task ไปยัง stderr; ราย
ละเอียดเต็ม (HTTP body dumps, retry logs) ไปยังไดเร็กทอรี app-log
ของแพลตฟอร์มโดยไม่คำนึงถึงความละเอียดของ console (ดู
[Troubleshooting → Where are the logs?](troubleshooting.md#where-are-the-logs)
สำหรับ path บน OS ของคุณ)

### แสดงรายการภาษาที่รองรับ

```bash
ait --list-languages
```

พิมพ์ภาษาที่รองรับทั้ง 45 ภาษา มีประโยชน์สำหรับการ pipe ไปยัง
shell loops

### เวอร์ชัน

```bash
ait --version
# ait 0.1.0
```

## รหัสออก

| รหัส | ความหมาย |
|---|---|
| `0` | งานทั้งหมดสำเร็จ |
| `2` | ข้อผิดพลาดของอาร์กิวเมนต์ (ภาษาที่ไม่รู้จัก, target ที่หายไป, model รูปแบบผิด, output เขียนไม่ได้, ส่วนขยายไฟล์ที่ไม่รองรับ) |
| `3` | LLM ไม่ได้กำหนดค่า |
| `4` | ความล้มเหลวบางส่วน (บางส่วนสำเร็จ บางส่วนไม่) |
| `5` | ทั้งหมดล้มเหลว |
| `130` | ถูกขัดจังหวะ (`Ctrl+C`) |

## การยกเลิก

`Ctrl+C` หนึ่งครั้ง — การยกเลิกแบบร่วมมือ Checkpoint ของ task
ปัจจุบันถูกบันทึก ไปป์ไลน์ออกอย่างหมดจดที่ขอบเขต polling ถัดไป

`Ctrl+C` อีกครั้ง — การขัดจังหวะแบบหนัก ใช้อย่างประหยัด; ไฟล์บาง
ส่วนอาจถูกทิ้งในสถานะเขียนครึ่ง

## การอ้างอิง flag เต็มรูปแบบ

```bash
ait --help
```

แสดง flag ทุกตัวพร้อมค่าเริ่มต้น เนื้อหาเดียวกันสรุปไว้ที่นี่:

| Flag | Default | Notes |
|---|---|---|
| `--target / -t LANG` | _จำเป็น_ | ไม่คำนึงถึงตัวพิมพ์ใหญ่/เล็ก |
| `--source / -s LANG` | auto-detect | ไม่คำนึงถึงตัวพิมพ์ใหญ่/เล็ก |
| `--output / -o DIR` | parent ของต้นทาง | สร้างถ้าหายไป |
| `--model / -m PROVIDER:MODEL` | desktop default | รูปแบบเคร่งครัด |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | off | ต้องการ OCR ที่กำหนดค่า |
| `--translate-comments` | off | ความคิดเห็น Office |
| `--translate-shapes` | off | รูปร่าง / กล่องข้อความ |
| `--translate-notes` | off | บันทึกของผู้นำเสนอ PowerPoint |
| `--translate-sheet-names` | off | แท็บแผ่นงาน Excel |
| `--convert-legacy` | off | `.doc`/`.xls`/`.ppt` → รูปแบบสมัยใหม่ |
| `--convert-odf` | off | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | off | เก็บรายการประวัติหลังเสร็จสิ้น |
| `--quiet / -q` | off | เฉพาะข้อผิดพลาดบน console |
| `--verbose / -v` | off | DEBUG firehose |
| `--list-languages` | — | พิมพ์ 45 ภาษาและออก |
| `--version` | — | พิมพ์เวอร์ชันและออก |

## เคล็ดลับ

!!! tip "ตั้งค่าครั้งเดียว ใช้ทุกที่"
    CLI แชร์คีย์ API และการตั้งค่ากับแอปเดสก์ท็อป — ตั้งทุกอย่างใน
    GUI ครั้งเดียว จากนั้นทำให้เป็นอัตโนมัติด้วย `ait` จากที่นั่น

!!! tip "Cold-start endpoint cache"
    สำหรับแต่ละคู่ `(endpoint, model)` การเลือก chat-vs-responses-API
    และ working payload variant จะถูกเก็บไว้ใน
    `llm_endpoint_cache.json` ใน OS cache directory
    (`~/.cache/ai-translate/` บน Linux,
    `~/Library/Caches/ai-translate/` บน macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` บน Windows) การเรียก CLI
    แบบ cold-start จะข้าม auto-detection probe ทั้งหมดหลังจากการ
    เรียกที่สำเร็จครั้งแรก — มีประโยชน์เมื่อสคริปต์กับการ deploy
    Azure / vLLM / OpenRouter / Anthropic / DeepSeek ที่ต้องการ
    การปรับแต่ง payload เฉพาะผู้ให้บริการ Cache ปลอดภัยสำหรับ
    multi-process และ multi-thread (read-merge-write ภายใต้ RLock
    พร้อมการเปลี่ยนชื่อแบบ atomic)

!!! tip "Output streams"
    โหมดเริ่มต้นพิมพ์ banner, รายการ task ที่ queued, และความคืบหน้า
    ต่อ task ไปยัง **stdout** (line-buffered เพื่อ interleave อย่าง
    ถูกต้องกับข้อผิดพลาด); ข้อความข้อผิดพลาดและ log records ไปยัง
    **stderr** ใช้ร่วมกับ `--quiet` เพื่อระงับ stdout ทั้งหมดสำหรับ
    การ pipe ที่สะอาด:

    ```bash
    ait --list-languages | grep -i japanese    # ข้อมูลบน stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
