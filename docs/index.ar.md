---
description: AI Translate هو مترجم سطح مكتب مجاني ومتعدد المنصات للمستندات وملفات PDF والترجمات والصوت والكلام المباشر بأكثر من 45 لغة.
---

# AI Translate

مترجم سطح مكتب مجاني ومتعدد المنصات يتعامل مع **45 لغة** ويتجاوز
النص العادي بكثير — يترجم المستندات والصوت والفيديو والكلام المباشر
ولقطات الشاشة والمزيد، كل ذلك من خلال خط أنابيب واحد مدعوم بـ LLM.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **تطبيق سطح المكتب**

    ---

    اسحب ملفًا، اختر لغة هدف، احصل على نسخة مترجمة. السحب والإفلات،
    السجل، المسارد، كل شيء.

    [:octicons-arrow-right-24: شرح في 5 دقائق](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **سطر الأوامر**

    ---

    `ait report.docx --target French` — نفس خط الأنابيب، قابل للبرمجة
    وبدون واجهة. مفيد لـ CI ومهام الدُفعات والخوادم.

    [:octicons-arrow-right-24: دليل CLI](cli.md)

-   :material-robot-outline:{ .lg .middle } **وكلاء AI (MCP)**

    ---

    اعرض الترجمة كأدوات Model Context Protocol حتى يتمكن Claude
    Desktop وClaude Code وعملاء MCP الآخرون من استدعائها مباشرة.

    [:octicons-arrow-right-24: إعداد MCP](mcp.md)

</div>

## ما يمكنك ترجمته

| النوع | التنسيقات |
|---|---|
| **مستندات Office** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`، بالإضافة إلى `.doc` / `.xls` / `.ppt` القديمة |
| **ملفات PDF** | ترجمة بطريقة الاستخراج والتراكب مع الحفاظ على التخطيط، ترجمة الإشارات المرجعية / النماذج / الروابط، احتياطي OCR للمسحوحات ضوئيًا |
| **النص والويب** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **الترجمات** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **التوطين** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **الصور** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR أو LLM vision) |
| **الصوت** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **الفيديو** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (خط أنابيب دبلجة كامل) |

## الميزات الرئيسية {: #headline-features }

- **[ترجمة النص](features/translate-text.md)** — ترجمة LLM فورية مع الكشف التلقائي والتحرير في المكان وتشغيل TTS. تُعرض اللغات من اليمين إلى اليسار (العربية والعبرية والفارسية) بشكل أصلي.
- **[ترجمة المستند](features/translate-document.md)** — أفلِت الملفات، شاهد دوّامة تقدم لكل مهمة، احصل على نسخ مترجمة جنبًا إلى جنب. تحصل أهداف RTL على ترميز bidi مناسب؛ يقوم `Ctrl+P` / `Ctrl+G` بإيقاف ومتابعة قائمة الانتظار.
- **[إنشاء الترجمة (STT)](features/generate-subtitle.md)** — نسخ الصوت / الفيديو إلى SRT / VTT / ASS / SSA.
- **[إنشاء الصوت (TTS)](features/generate-voice.md)** — تركيب الترجمات إلى MP3 / WAV مع التوقيت.
- **[دبلجة الفيديو](features/dubbing.md)** — STT كامل → ترجمة → TTS → مزج مرة أخرى في فيديو المصدر.
- **[الترجمة الفورية](features/live-translation.md)** — تراكب ترجمات الميكروفون أو صوت النظام في الوقت الفعلي.
- **[استخراج النص](features/extract-text.md)** — OCR أو LLM vision → `.txt` / `.docx`.
- **[المسرد](features/glossary.md)** — فرض مصطلحات متسقة عبر الترجمات.

!!! tip "وضع Vertex AI لـ Gemini"
    يمكن لمستخدمي المؤسسات تبديل استدعاءات Gemini من Developer API
    إلى **Vertex AI** في **الإعدادات → LLM** — وجّهها إلى مشروع GCP
    والمنطقة الخاصين بك، اختياريًا قدّم مسار JSON لحساب الخدمة. راجع
    [مزودو LLM](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "هل هذه أول مرة؟"
    ابدأ بـ [التثبيت](getting-started/installation.md)، ثم
    [شرح الترجمة الأولى في 5 دقائق](getting-started/first-translation.md).
    سيكون لديك مستند مترجم في أقل من 10 دقائق من نسخة جديدة.
