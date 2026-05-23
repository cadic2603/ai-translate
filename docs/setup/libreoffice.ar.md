---
description: ثبّت LibreOffice حتى يتمكن AI Translate من ترجمة تنسيقات Office القديمة (.doc, .xls, .ppt) وملفات ODF (.odt, .ods, .odp) على macOS وLinux.
---

# LibreOffice (تنسيقات Office)

يختار pipeline ترجمة Office أفضل خلفية متاحة بهذا الترتيب:

1. **win32com** (Windows + MS Office مثبت) — أعلى دقة
2. **LibreOffice UNO** (متعدد المنصات) — fallback عندما لا يكون
   win32com موجودًا
3. **python-docx / openpyxl / python-pptx** (التنسيقات الحديثة
   فقط) — fallback Python خالص عندما لا يكون أي مما سبق متاحًا

LibreOffice هو **المسار الوحيد** لـ `.doc` / `.xls` / `.ppt` القديمة
على Linux وmacOS، والمسار الموصى به على هذه المنصات لتنسيقات Office
الحديثة أيضًا (دقة أفضل من خلفية Python الخالصة، خاصة للجداول
والكائنات المضمنة).

## التثبيت

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    أو قم بالتنزيل من <https://www.libreoffice.org/download/download/>.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    عادةً ما يستخدم تطبيق سطح المكتب على Windows **win32com** مع
    MS Office المثبت — LibreOffice هو *الاحتياطي* إذا كان MS
    Office مفقودًا. ثبت من
    <https://www.libreoffice.org/download/download/>.

## التحقق

```bash
soffice --version
```

إذا حصلت على "command not found" على macOS، فإن الثنائي موجود في
`/Applications/LibreOffice.app/Contents/MacOS/soffice`. يكتشف
التطبيق ذلك تلقائيًا عبر مسارات التثبيت الشائعة، لكن يمكنك التجاوز
في **Settings → General → LibreOffice path** إذا لزم الأمر.

## ما يدعمه

عندما يكون LibreOffice الخلفية النشطة:

| الميزة | ملاحظة |
|---|---|
| **Office الحديث** (`.docx`, `.xlsx`, `.pptx`) | يستخدم كاحتياطي عندما لا يكون win32com متاحًا |
| **Office القديم** (`.doc`, `.xls`, `.ppt`) | مطلوب — Python خالص لا يستطيع قراءتها |
| **ODF** (`.odt`, `.ods`, `.odp`) | يستخدم لتحويل round-trip عندما يكون **Auto-convert ODF** مشغلًا |
| **التحويل التلقائي legacy / ODF → OOXML** | مطلوب |

## العملية الخلفية

في المرة الأولى التي يحتاج فيها LibreOffice، يقوم التطبيق بإطلاق
عملية `soffice` في وضع headless ويبقيها على قيد الحياة عبر الترجمات
(`office_lifecycle.py`). يتم إغلاقها تلقائيًا عند خروج التطبيق.

## محاذير

!!! warning "وقت بدء التشغيل الأول"
    تنتظر الترجمة الأولى التي تصطدم بـ LibreOffice ~5-10 ثوانٍ حتى
    يبدأ `soffice`. الترجمات اللاحقة تعيد استخدام نفس العملية وتكون
    سريعة.

!!! info "سجلات تعطل JVM"
    ينتج مكون Java في LibreOffice أحيانًا ملفات `hs_err_pid*.log`
    عندما يقع segfault. يقوم التطبيق بتوجيهها إلى دليل مؤقت حتى
    لا تلوث مجلد مشروعك.

!!! tip "التحويل التلقائي legacy / ODF"
    قم بتمكين **Settings → Translation → Auto-convert legacy** إذا
    كنت تترجم بشكل روتيني `.doc` / `.xls` / `.ppt`. يحول pipeline
    إلى `.docx` / `.xlsx` / `.pptx` أولاً (عبر
    `convert_to_modern_format`)، يترجم النسخة الحديثة، ثم يحول مرة
    أخرى. الدقة أعلى بكثير من ترجمة التنسيق القديم مباشرة.
