---
description: ثبّت AI Translate على Windows أو macOS أو Linux من ثنائيات مُعدة مسبقًا أو من المصدر — يغطي Python وFFmpeg وإعداد LibreOffice الاختياري.
---

# التثبيت

## ما تحتاجه

- **Python 3.12 أو أحدث** ([download](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — مدير حزم Python سريع. ثبّت بـ:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **مفتاح API لـ LLM** — أي من:
    - [Google Gemini](https://aistudio.google.com/apikey) (مستوى مجاني متاح — موصى به للبدء)
    - أي نقطة نهاية متوافقة مع OpenAI (OpenAI، Anthropic عبر proxy، Ollama / LM Studio محلي، إلخ)

## اختياري، لكنه يفتح المزيد من الميزات

| الأداة | يستخدمها | متى تحتاجها |
|---|---|---|
| **FFmpeg** ([download](https://ffmpeg.org/download.html)) | الترجمة، الصوت، الدبلجة، Live | أي سير عمل صوتي/مرئي |
| **LibreOffice** ([download](https://www.libreoffice.org/download/)) | تنسيقات Office على Linux/macOS | ترجمة `.doc` / `.xls` / `.ppt` القديمة، أو أي ملف Office عند عدم تثبيت MS Office |
| **Tesseract** ([install guide](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | محرك OCR (الافتراضي) | صفحة استخراج النص، ترجمة PDF الممسوحة، ترجمة الصور المضمنة |
| **MS Office** + **pywin32** | Office على Windows | أعلى دقة لترجمة Office على Windows |

يمكنك تثبيت AI Translate دون أي من هذه — الميزات التي تحتاجها
ستخبرك بذلك قبل أن تفشل.

## قم بإعداده

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

يقوم ذلك بتثبيت كل ما هو ضروري لتشغيل تطبيق سطح المكتب وCLI وخادم
MCP.

## شغّله

=== "تطبيق سطح المكتب"
    ```bash
    uv run python -m src.main
    ```

=== "سطر الأوامر"
    ```bash
    uv run ait --version
    ```

=== "خادم MCP"
    ```bash
    uv run ait-mcp           # نقل stdio (لـ Claude Desktop / Code)
    ```

## أضف مفتاح API الخاص بك

في أول مرة تفتح فيها تطبيق سطح المكتب:

1. انقر **الإعدادات** في الشريط الجانبي
2. افتح علامة التبويب **LLM**
3. الصق **مفتاح API الخاص بـ Google Gemini** (أو قم بتكوين مزود
   مخصص متوافق مع OpenAI). يمكن لمستخدمي المؤسسات تبديل Gemini إلى
   **وضع Vertex AI** بدلاً من ذلك — وجّهه إلى مشروع GCP ومنطقة،
   اختياريًا قدّم مسار JSON لحساب الخدمة؛ راجع
   [مزودو LLM](../setup/llm-providers.md) للتفاصيل.
4. اختر نموذجًا افتراضيًا — أي متغير Flash حالي (مثل
   `gemini-2.5-flash`) هو نقطة بداية مجانية متينة. متغيرات Pro
   تعطي جودة أفضل بتكلفة أعلى.
5. أغلق الإعدادات — انتهيت

تُخزن المفاتيح في **OS keychain** الخاص بك (macOS Keychain، Windows
Credential Manager، GNOME / KDE Secret Service على Linux)، وليس في
نص عادي على القرص.

!!! tip "تثبيت بدون واجهة / خادم"
    إذا لم تتمكن من تشغيل تطبيق سطح المكتب لإعداد المفاتيح، راجع
    [مزودو LLM](../setup/llm-providers.md) لأوامر CLI keychain.

## التالي: جرّبه

[الترجمة الأولى في 5 دقائق →](first-translation.md){ .md-button .md-button--primary }
