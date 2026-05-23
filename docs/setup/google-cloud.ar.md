---
description: قم بربط Google Cloud بـ AI Translate لـ Vision OCR وSpeech-to-Text وText-to-Speech — قم بإعداد مفتاح API وتمكين الخدمات ذات الصلة.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

مفتاح API واحد لـ Google Cloud يدعم ثلاث خلفيات اختيارية:

- **Vision OCR** — محرك OCR مدفوع (1,000 مجاني / شهر)
- **Speech-to-Text v1** — STT مدفوع (60 دقيقة / شهر مجاني)
- **Text-to-Speech v1** — TTS مدفوع (1 M حرف / شهر مجاني لـ
  WaveNet)

تحتاج فقط إلى تمكين APIs التي تستخدمها فعلًا.

## احصل على مفتاح API

1. [أنشئ مشروع Google Cloud](https://console.cloud.google.com/projectcreate)
2. افتح مكتبة API: <https://console.cloud.google.com/apis/library>
3. قم بتمكين أي من:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [أنشئ مفتاح API](https://console.cloud.google.com/apis/credentials):
   انقر **+ Create Credentials → API key**
5. انسخ المفتاح (يبدو مثل `AIza...`).

!!! tip "قيّد المفتاح"
    في صفحة تفاصيل مفتاح API، تحت **API restrictions**، قيّد المفتاح
    فقط على APIs التي قمت بتمكينها. بهذه الطريقة لا يمكن للمفتاح
    المسرب تجميع فواتير على الخدمات التي لم تكن تنوي استخدامها.

## التكوين في التطبيق

في **Settings → Service**:

1. الصق في **Google Cloud API key** → **Save**

هذا المفتاح الواحد متاح الآن لجميع الخدمات الثلاثة من Google.

## قم بتمكين كل خدمة

### Vision OCR

في **Settings → OCR → OCR method = Google Cloud OCR**.

هذا كل شيء — سيستخدم نفس المفتاح من Service.

### Speech-to-Text

في **Settings → Subtitle → STT method = Google Cloud** (لصفحات
Subtitle / Voice) أو **Settings → Live → STT method = Google
Cloud** (لصفحة Live).

في **Settings → Subtitle → Google STT model**، اختر نموذج التعرف:

| Model | الأفضل لـ |
|---|---|
| `latest_long` (افتراضي) | الصوت الطويل (المقابلات، المحاضرات) |
| `latest_short` | أوامر صوتية، عبارات قصيرة |
| `phone_call` | صوت هاتفي (8 kHz) |
| `medical_dictation` / `medical_conversation` | صوت طبي |

### Text-to-Speech

في **Settings → Voice → TTS method = Google Cloud TTS**.

افتراضيًا، يختار الخادم صوتًا بناءً على اللغة والجنس — هذا ما
يحتاجه معظم المستخدمين. تثبيت صوت Google محدد (مثل
`en-US-Chirp3-HD-Charon`، `vi-VN-Wavenet-A`) مدعوم بواسطة المحرك
ولكنه غير معروض كحقل في Settings بعد؛ يمكن تعيينه عن طريق تحرير
`voice/google_tts_voice_name` في `settings.ini` مباشرة. معرفات
الأصوات مدرجة في
<https://cloud.google.com/text-to-speech/docs/voices>.

## أخطاء شائعة

| Error | السبب المحتمل |
|---|---|
| `AUTH_ERROR` | مفتاح خاطئ / منتهي الصلاحية. الصق مرة أخرى في Settings → Service. |
| `API not enabled` | لم تقم بتمكين API محدد (Vision / Speech / TTS) على مشروع Cloud هذا. |
| `QUOTA_ERROR` | تم بلوغ حد المستوى المجاني لـ API هذا. انتظر، أو قم بترقية الفوترة. |
| `INVALID_ARGUMENT_ERROR` | اسم الصوت غير موجود في اللغة التي اخترتها. |

## حماية التكلفة

!!! warning
    جميع APIs الثلاث من Google مدفوعة لاحقًا — بمجرد تجاوز المستوى
    المجاني، تبدأ في الدفع بدون توقف. قم بتعيين
    [تنبيه ميزانية](https://console.cloud.google.com/billing/budgets)
    على مشروع Cloud قبل القيام بعمل حجم كبير.
