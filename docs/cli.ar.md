---
description: استخدم واجهة سطر الأوامر ait لترجمة الملفات بدون واجهة — تدعم PDFs ومستندات Office والترجمات وأكثر من 45 لغة من سكربت أو مهمة CI.
---

# سطر الأوامر (`ait`)

ترجمة بدون واجهة — نفس خط الأنابيب مثل تطبيق سطح المكتب، لا تحتاج
إلى عرض. مفيد لـ CI ومهام الدُفعات والخوادم وسير العمل المسكرپت.

## بداية سريعة

```bash
ait report.docx --target French
```

تظهر المخرجات بجانب المصدر باسم
`report_translated_<src>_<tgt>.docx`.

## وصفات شائعة

### ملفات متعددة

```bash
ait *.pdf --target Japanese
```

توسيع Glob هو مهمة الـ shell (Unix). على Windows / `cmd.exe`، أدرج
الملفات صراحةً أو استخدم PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### دليل مخرجات مخصص

```bash
ait report.docx --target French --output ./translated/
```

يتم إنشاء الدليل إذا لم يكن موجودًا. إذا تعذر إنشاؤه (تم رفض
الإذن، إلخ) فستحصل على خطأ واضح ورمز خروج 2 — لا تشغيل جزئي.

### حدد لغة المصدر

```bash
ait letter.txt --target German --source "English (US)"
```

مطابقة المصدر غير حساسة للحالة. "Chinese" المجردة تطبع تلميحًا:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### اختر نموذجًا محددًا

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# أو أي Provider:model_name آخر مسجَّل في علامة تبويب LLM لتطبيق سطح المكتب.
```

التنسيق هو بدقة `Provider:model_name`. علامتا النقطة المفقودتان →
خروج 2 برسالة واضحة بدلاً من الرجوع بصمت إلى نموذج Gemini الافتراضي.

### خيارات Office

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

تتطلب `--translate-images` تكوين OCR (راجع
[محركات OCR](setup/ocr-engines.md)).

### تحويل تلقائي للتنسيقات القديمة

```bash
ait old-doc.doc --target French --convert-legacy
```

يحوّل خط الأنابيب `.doc` → `.docx` أولاً (دقة أفضل)، يترجم النسخة
الحديثة، يحول مرة أخرى. نفس الشيء لـ `--convert-odf` و`.odt` /
`.ods` / `.odp`.

### هادئ / مفصل

```bash
ait report.docx --target French --quiet      # الأخطاء فقط
ait report.docx --target French --verbose    # خط أنابيب DEBUG كامل
```

يطبع الوضع الافتراضي شعارًا وتقدم لكل مهمة على stderr؛ التفاصيل
الكاملة (مكبات HTTP body، سجلات إعادة المحاولة) تذهب إلى دليل
سجلات تطبيق المنصة بغض النظر عن إسهاب وحدة التحكم (راجع
[Troubleshooting → Where are the logs?](troubleshooting.md#where-are-the-logs)
للمسار على نظام التشغيل الخاص بك).

### قائمة اللغات المدعومة

```bash
ait --list-languages
```

يطبع جميع اللغات الـ 45 المدعومة. مفيد لتمريرها إلى حلقات shell.

### الإصدار

```bash
ait --version
# ait 0.1.0
```

## رموز الخروج

| الرمز | المعنى |
|---|---|
| `0` | نجحت جميع المهام |
| `2` | خطأ في الوسائط (لغة غير معروفة، هدف مفقود، نموذج بصيغة سيئة، مخرجات غير قابلة للكتابة، امتداد ملف غير مدعوم) |
| `3` | LLM غير مكوَّن |
| `4` | فشل جزئي (نجح بعضها، فشل البعض) |
| `5` | فشل الكل |
| `130` | تمت المقاطعة (`Ctrl+C`) |

## الإلغاء

`Ctrl+C` مرة واحدة — إلغاء تعاوني. يتم حفظ نقطة فحص المهمة الحالية،
ويخرج خط الأنابيب بنظافة عند حدود الاستطلاع التالية.

`Ctrl+C` مرة أخرى — مقاطعة قسرية. استخدم باعتدال؛ قد تترك ملفات
جزئية في حالة نصف مكتوبة.

## مرجع الأعلام الكامل

```bash
ait --help
```

يعرض كل علم بالقيمة الافتراضية. نفس المحتوى ملخص هنا:

| Flag | Default | Notes |
|---|---|---|
| `--target / -t LANG` | _مطلوب_ | غير حساس للحالة |
| `--source / -s LANG` | اكتشاف تلقائي | غير حساس للحالة |
| `--output / -o DIR` | والد المصدر | يُنشأ إذا كان مفقودًا |
| `--model / -m PROVIDER:MODEL` | افتراضي سطح المكتب | تنسيق صارم |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | off | يتطلب تكوين OCR |
| `--translate-comments` | off | تعليقات Office |
| `--translate-shapes` | off | الأشكال / مربعات النص |
| `--translate-notes` | off | ملاحظات متحدث PowerPoint |
| `--translate-sheet-names` | off | علامات تبويب أوراق Excel |
| `--convert-legacy` | off | `.doc`/`.xls`/`.ppt` → تنسيق حديث |
| `--convert-odf` | off | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | off | الاحتفاظ بإدخالات السجل بعد الانتهاء |
| `--quiet / -q` | off | الأخطاء فقط على وحدة التحكم |
| `--verbose / -v` | off | خط أنابيب DEBUG |
| `--list-languages` | — | طباعة 45 لغة والخروج |
| `--version` | — | طباعة الإصدار والخروج |

## نصائح

!!! tip "إعداد لمرة واحدة، استخدم في كل مكان"
    يشارك CLI مفاتيح API والإعدادات مع تطبيق سطح المكتب — قم بإعداد
    كل شيء مرة واحدة في واجهة المستخدم الرسومية، ثم قم بالأتمتة
    باستخدام `ait` من هناك.

!!! tip "ذاكرة تخزين مؤقت لنقطة النهاية عند البدء البارد"
    لكل زوج `(endpoint, model)`، يتم الاحتفاظ بخيار chat-vs-responses-API
    ومتغير الحمولة العامل في `llm_endpoint_cache.json` في دليل ذاكرة
    التخزين المؤقت لنظام التشغيل (`~/.cache/ai-translate/` على
    Linux، `~/Library/Caches/ai-translate/` على macOS،
    `%LOCALAPPDATA%\ai-translate\cache\` على Windows). تتخطى استدعاءات
    CLI من البدء البارد فحص الكشف التلقائي تمامًا بعد أول استدعاء
    ناجح — مفيد عند البرمجة النصية ضد عمليات نشر Azure / vLLM /
    OpenRouter / Anthropic / DeepSeek التي تحتاج إلى ضبط حمولة محدد
    لكل مزود. ذاكرة التخزين المؤقت آمنة من حيث متعدد العمليات
    ومتعدد الخيوط (read-merge-write تحت RLock مع إعادة تسمية ذرية).

!!! tip "تيارات الإخراج"
    يطبع الوضع الافتراضي الشعار وقائمة المهام في الانتظار وتقدم لكل
    مهمة إلى **stdout** (line-buffered حتى يتداخل بشكل صحيح مع
    الأخطاء)؛ تذهب رسائل الخطأ وسجلات السجل إلى **stderr**. ادمج
    مع `--quiet` لقمع stdout تمامًا للتمرير النظيف:

    ```bash
    ait --list-languages | grep -i japanese    # البيانات على stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
