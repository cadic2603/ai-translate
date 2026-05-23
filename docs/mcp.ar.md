---
description: اعرض AI Translate كأدوات Model Context Protocol حتى يتمكن Claude Desktop وClaude Code وعملاء MCP الآخرون من ترجمة النصوص والملفات والصوت.
---

# خادم MCP (`ait-mcp`)

يعرض خط أنابيب الترجمة كأدوات **Model Context Protocol** حتى يمكن
لوكلاء AI مثل Claude Desktop وClaude Code قيادته مباشرةً — "ترجم
هذا الـ PDF إلى الفرنسية" يصبح استدعاء أداة، وليس نسخًا ولصقًا.

## ما يتم عرضه

تسع أدوات:

| الأداة | الغرض |
|---|---|
| `translate_text` | ترجمة قائمة من السلاسل |
| `translate_document` | إدخال مهام ترجمة الملفات في قائمة الانتظار (يُرجع معرفات المهام) |
| `get_task_status` | استطلاع حالة المهمة |
| `cancel_task` | إلغاء تعاوني للمهام قيد التشغيل |
| `extract_image_text` | OCR أو LLM vision |
| `transcribe_audio` | صوت → SRT |
| `synthesize_speech` | نص → MP3 / WAV |
| `query_glossary` | عرض مجموعات / إدخالات المسرد |
| `list_languages` | جميع اللغات الـ 45 المدعومة |

## شغّل الخادم

```bash
ait-mcp                       # نقل stdio (الافتراضي لوكلاء سطح المكتب)
ait-mcp --transport sse       # Server-Sent Events لعملاء الويب
ait-mcp --transport sse --port 9000
```

`stdio` هو ما يتوقعه كل عميل MCP إلا إذا قمت بربط SSE صراحةً.

## أضف إلى Claude Desktop

1. افتح Claude Desktop → **Settings → Developer → Edit Config**
2. أضف هذا الإدخال تحت `mcpServers`:

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    استبدل `/absolute/path/to/ai-translate` بمسار المستودع المستنسخ.

3. أغلق Claude Desktop وأعد فتحه. يجب أن تظهر أيقونة المطرقة الآن
   "ai-translate" مع جميع الأدوات الـ 9. جرّب:

    > "ترجم هذا الـ PDF (`/home/me/report.pdf`) إلى الفرنسية —
    > احفظ المخرجات بجانب المصدر."

## أضف إلى Claude Code

`~/.config/claude-code/mcp_servers.json` (أو `claude mcp add` من
داخل Claude Code):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

أعد تشغيل Claude Code. تصبح نفس الأدوات الـ 9 قابلة للاستدعاء.

## أضف إلى عملاء MCP آخرين

أي عميل متوافق مع MCP يأخذ شكلاً مماثلاً:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (افتراضي)

لعملاء يستندون إلى HTTP / SSE، شغّل
`ait-mcp --transport sse --port 9000` ووجّه العميل إلى
`http://localhost:9000`.

## ضمانات التحقق

تُرجع كل أداة الشكل ذاته عند الأخطاء حتى يتمكن الوكلاء من معالجة
الفشل بشكل متسق:

| إدخال خاطئ | استجابة الأداة |
|---|---|
| لغة غير معروفة | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM غير مكوَّن | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| نوع ملف غير مدعوم | `ValueError` يدرج الامتدادات المسموحة |
| `model="…"` بصيغة خاطئة (بدون `:`) | `ValueError` بدلاً من استخدام الافتراضي بصمت |
| معرفات مهام غير معروفة في `cancel_task` | تُرجع في مصفوفة `unknown` — لا خطأ |
| FFmpeg مفقود في `transcribe_audio` | `RuntimeError: FFmpeg is required…` (مُعاد لفه من علامة `FFMPEG_NOT_FOUND` المجردة للمحرك) |

يمكن للوكلاء الذين يستدعون هذه الأدوات الاعتماد على هذه العقود.

## التزامن

يقوم `translate_document` بتشغيل خط الأنابيب في خيط daemon. تحصل كل
دفعة على حدث الإلغاء الخاص بها، لذا فإن إلغاء دفعة واحدة لا يزعج أخرى.
يتعقب خادم MCP خطوط الأنابيب النشطة في خريطة محلية للعملية (تنظف
تلقائيًا عند انتهاء خط الأنابيب).

## حالات الاستخدام

- **"ترجم وثائق هذا الـ codebase إلى الفيتنامية"** — وجّه الوكيل إلى
  مجلد الوثائق، وهو يدفع استدعاءات `translate_document` ويستطلع
  `get_task_status` حتى تنتهي كل واحدة.
- **"ما اللغات التي تدعمها؟"** — يستدعي الوكيل `list_languages`
  ويقرأ الاستجابة.
- **"ترجم هذا الإيصال الياباني"** — يستدعي الوكيل `extract_image_text`
  على الصورة، ثم `translate_text` على النتيجة.
- **"أنشئ ترجمات فيتنامية لهذا التسجيل من Zoom"** — يستدعي الوكيل
  `transcribe_audio` للحصول على SRT بلغة المصدر، ثم `translate_text`
  على كل cue للتوطين، ويعيد تجميع SRT.

!!! note "دبلجة الفيديو ليست أداة MCP"
    خط أنابيب STT الكامل → translate → TTS → mux (صفحة **الدبلجة** في
    تطبيق سطح المكتب) متاح فقط من خلال واجهة المستخدم الرسومية الآن.
    من MCP يمكنك تأليف المعادل بنفسك مع `transcribe_audio` +
    `translate_text` + `synthesize_speech`، لكنك ستحتاج إلى التعامل مع
    خطوة mux المدركة للتوقيت (FFmpeg) في الخارج.

## نصائح

!!! tip "إعداد لمرة واحدة، الوكلاء يعملون في كل مكان"
    يشارك خادم MCP مفاتيح API والإعدادات مع تطبيق سطح المكتب وCLI.
    قم بتكوين LLM / OCR / TTS مرة واحدة في واجهة المستخدم الرسومية،
    ثم أي وكيل يتحدث إلى `ait-mcp` يرث الإعداد نفسه.

!!! tip "ذاكرة تخزين مؤقت لنقطة النهاية عند البدء البارد"
    لكل زوج `(endpoint, model)`، يتم الاحتفاظ بخيار chat-vs-responses-API
    ومتغير الحمولة العامل في `llm_endpoint_cache.json` في دليل ذاكرة
    التخزين المؤقت لنظام التشغيل (`~/.cache/ai-translate/` على Linux،
    `~/Library/Caches/ai-translate/` على macOS،
    `%LOCALAPPDATA%\ai-translate\cache\` على Windows). تتخطى عمليات
    `ait-mcp` الجديدة فحص الكشف التلقائي تمامًا بعد أول استدعاء ناجح
    — الوكلاء الذين يولِّدون الخادم عند الطلب لا يدفعون رحلات الذهاب
    والإياب لاكتشاف المتغير على كل استدعاء. ذاكرة التخزين المؤقت آمنة
    من حيث متعدد العمليات ومتعدد الخيوط (read-merge-write تحت RLock مع
    إعادة تسمية ذرية).

!!! tip "منتقي النموذج لكل أداة"
    تقبل أدوات `translate_text` و`translate_document` معاملاً
    اختياريًا `model` — يمكن للوكلاء اختيار نموذج سريع للمرات السريعة
    ونموذج أثقل للإنتاج دون الحاجة إلى أن يقوم المستخدم بإعادة تكوين
    تطبيق سطح المكتب.

!!! warning "خطوط الأنابيب طويلة الأمد"
    يُرجع `translate_document` على الفور بمعرفات المهام. من المتوقع
    أن يستطلع الوكيل `get_task_status` حتى تصل كل مهمة إلى `Done` أو
    `Failed`. لا تنتظر بشكل متزامن داخل استدعاء الأداة؛ هذا يخاطر
    بإطلاق مهلة عميل MCP.
