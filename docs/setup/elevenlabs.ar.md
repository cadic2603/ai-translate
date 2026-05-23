---
description: قم بربط ElevenLabs بـ AI Translate لـ TTS عصبي عالي الجودة — قم بإنشاء أصوات في أكثر من 30 لغة مع كلام واقعي ومعبر.
---

# ElevenLabs (TTS)

تحويل نص إلى كلام عصبي متميز. تستخدمه صفحات
**[Generate Voice](../features/generate-voice.md)**,
**[Dubbing](../features/dubbing.md)**, و
**[Live Translation](../features/live-translation.md)** عند اختيار
ElevenLabs كطريقة TTS.

## احصل على مفتاح API

1. اشترك في <https://elevenlabs.io>
2. افتح <https://elevenlabs.io/app/settings/api-keys>
3. انقر **+ Create New Key**، سمّه (مثل "ai-translate")، انسخ
   المفتاح (يبدو مثل `sk_...`)

يمنحك المستوى المجاني ~10,000 حرف / شهر، يكفي للاختبار. يبدأ
الاستخدام الإنتاجي حول $5/شهر.

## التكوين في التطبيق

في **Settings → Service**:

1. الصق المفتاح في **ElevenLabs API key** → **Save**
2. أدخل **Voice ID** المفضل لديك في **Voice ID** (ابحث عن المعرفات
   على <https://elevenlabs.io/app/voice-lab>؛ انسخ ID من URL
   الصوت). اتركه فارغًا ليختار ElevenLabs الافتراضي.

في **Settings → Voice**:

1. اضبط **TTS method** على **ElevenLabs**
2. اختر **ElevenLabs model**:

    | Model | الأفضل لـ |
    |---|---|
    | `eleven_multilingual_v2` (افتراضي) | استخدام عام، توازن latency/quality |
    | `eleven_v3` | أعلى جودة (استخدم لدبلجات الإنتاج) |
    | `eleven_flash_v2_5` | أقل latency (استخدم لـ Live Translation) |

## ما يدعمه

| Page | استخدم ElevenLabs عندما |
|---|---|
| **Generate Voice** | تريد voiceovers عالية الجودة من ملفات الترجمة |
| **Dubbing** | تريد مسار دبلجة عالي الجودة على فيديو مترجم |
| **Live Translation** | تريد التشغيل المنطوق للترجمات في الوقت الفعلي |

## استنساخ الصوت

يدعم ElevenLabs استنساخ الصوت المخصص (خطة مدفوعة). بمجرد أن
تستنسخ صوتًا على موقع ElevenLabs، الصق Voice ID الخاص به في
**Settings → Service → Voice ID** وسيستخدمه pipeline الدبلجة /
إنشاء الصوت.

## محاذير

!!! warning "فحص ما قبل التشغيل"
    تتحقق صفحات الصوت / الدبلجة من تعيين مفتاح ElevenLabs API
    الخاص بك *قبل* بدء العمل. إذا كان مفقودًا فستحصل على حوار
    ودود يشير إلى Settings، وليس مهمة منتصف التشغيل.

!!! tip "Live mode يعود تلقائيًا"
    على صفحة **Live Translation**، إذا حددت ElevenLabs لكن لم تقم
    بتكوين مفتاح، فإن التطبيق يعود إلى **Edge TTS** (مجاني) ويعلن
    عن العودة في تسمية الحالة حتى تتمكن من إصلاحه عند الراحة.

!!! info "FFmpeg لا يزال مطلوبًا"
    يُرجع ElevenLabs بايتات صوتية؛ لا يزال التطبيق يستخدم FFmpeg
    للتحويل بين التنسيقات ولدمج المقاطع الموقوتة في ملف واحد.
    راجع [إعداد FFmpeg](ffmpeg.md).

## أخطاء شائعة

| Error | السبب المحتمل |
|---|---|
| `AUTH_ERROR` | مفتاح API خاطئ / منتهي الصلاحية. الصق مرة أخرى في Settings → Service. |
| `QUOTA_ERROR` | تم بلوغ حد حروف المستوى المجاني، أو استنفاد الخطة المدفوعة. |
| `MODEL_NOT_FOUND` | نموذج ElevenLabs المحدد لم يعد متاحًا؛ اختر آخر في Settings → Voice. |
