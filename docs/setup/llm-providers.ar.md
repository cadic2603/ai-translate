---
description: "قم بتكوين موفري LLM للترجمة: Google Gemini (موصى به)، نقاط نهاية متوافقة مع OpenAI، أو أي موفر مخصص بمفتاح API."
---

# موفرو LLM

يستدعي pipeline الترجمة Large Language Model للترجمة الفعلية. يمكنك
تكوين واحد أو عدة؛ يتيح منتقي النموذج لكل ميزة لكل صفحة استخدام
نموذج مختلف.

## Google Gemini (موصى به للإعداد لأول مرة) {: #google-gemini-recommended-for-first-time-setup }

المستوى المجاني سخي وجيد بما يكفي لمعظم الاستخدام الشخصي.

1. اذهب إلى <https://aistudio.google.com/apikey>
2. انقر **Create API key** (سجّل الدخول بحساب Google الخاص بك)
3. انسخ المفتاح (يبدو مثل `AIza...`)
4. في تطبيق سطح المكتب: **Settings → LLM → Gemini API key** →
   الصق → **Save**
5. اختر نموذجًا افتراضيًا في القائمة المنسدلة **Default Gemini
   model**. تميل خط Google إلى أن يبدو مثل:

    - متغيرات **Flash** (مثل `gemini-2.5-flash`) — سريع، مستوى
      مجاني سخي، جودة جيدة. نقطة بداية موصى بها.
    - متغيرات **Pro** — أبطأ، جودة أعلى، أكثر تكلفة.
    - **Flash-lite** — الأسرع، الأرخص، جودة أقل.

    تعتمد أسماء النماذج المتاحة بالضبط على ما طرحته Google لحسابك؛
    اختر اسمًا يحتوي على `flash` للحصول على افتراضي متوازن.

تم. يتم تخزين المفتاح في keychain نظام التشغيل، وليس بنص عادي.

### وضع Vertex AI (للمؤسسات)

داخل كتلة تكوين Gemini، يتيح لك زوج radio التبديل من **Developer
API** إلى **Vertex AI** — نفس نماذج Gemini، تتم محاسبتها من خلال
حساب GCP الخاص بك، مع عناصر تحكم على مستوى المؤسسة (VPC-SC، سجلات
التدقيق، الإقامة الإقليمية للبيانات).

1. في **Settings → LLM**، قم بالتبديل من **Developer API** إلى
   **Vertex AI** في radio Gemini
2. املأ:
    - **Project** — معرف مشروع GCP الخاص بك
    - **Location** — منطقة Vertex (الافتراضية `us-central1`)
    - **Credentials path** *(اختياري)* — مسار إلى ملف مفتاح JSON
      لحساب الخدمة. اتركه فارغًا لاستخدام Application Default
      Credentials (`gcloud auth application-default login`)
3. **Save**. تتم إعادة تعبئة قائمة النماذج المنسدلة من Vertex
   بمجرد تعيين المشروع.

يتم التعامل مع تحديث OAuth بواسطة `google-genai` تلقائيًا. يتم
تخزين مسار JSON لحساب الخدمة بنص عادي عن قصد (*المسار* ليس سرًا
— محتويات الملف هي السر، وتبقى على القرص حيث تحتفظ بها أفضل ممارسة
موثقة من Google).

## OpenAI / متوافق مع OpenAI

أي شيء يعرض REST API متوافق مع OpenAI يعمل — OpenAI نفسها،
Anthropic عبر [LiteLLM proxy](https://docs.litellm.ai)، Ollama
المحلي، LM Studio، vLLM، Together.ai، Groq، وما إلى ذلك.

في **Settings → LLM**:

1. انقر **Add Custom Provider**
2. املأ:
    - **Name** — تسمية مثل "OpenAI" / "Local Ollama" / "Anthropic"
    - **API endpoint** — URL الأساسي (مثل
      `https://api.openai.com/v1` أو `http://localhost:11434/v1`
      لـ Ollama)
    - **API key** — اتركه فارغًا للنقاط المحلية غير المصادق عليها
    - **Models** — قائمة مفصولة بفواصل (مثل `gpt-4o-mini, gpt-4o,
      gpt-3.5-turbo`)
3. انقر **Save**.

يتم تخزين الموفرين المخصصين كـ JSON blob في keychain نظام التشغيل
(بما في ذلك مفاتيح API).

## تبديل النموذج الافتراضي

تعيّن قائمة **Default Gemini model** المنسدلة في **Settings → LLM**
fallback يستخدمه كل صفحة ميزة لا تحتوي على منتقيها الخاص.

الصفحات بمنتقيها الخاصة من النموذج:

- **Translate Text** — `Translate Text settings tab → Default model`
- **Translate Document** — يختار لكل مهمة؛ يعود إلى الافتراضي
- **Subtitle / Voice / Dubbing / Live / Extract Text** — كل منها
  لها افتراضي خاص بالميزة في علامة تبويب الإعدادات الخاصة بها

هذا يتيح لك المزج والمطابقة: Flash مجاني للمباشر، Pro للمستندات
الكبيرة، Ollama المحلي للبيانات الحساسة.

## أين يتم تخزين المفاتيح

| OS | التخزين |
|---|---|
| **macOS** | Keychain (login keychain) |
| **Windows** | Credential Manager |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (بدون daemon)** | يعود إلى INI نص عادي في `~/.config/ai-translate/settings.ini` |

يتم ترحيل قيمة INI الاحتياطية إلى keychain عند القراءة الأولى كلما
أصبح keychain متاحًا — لا توجد خطوة يدوية.

## التثبيت بدون رأس / للخادم

بدون جلسة سطح مكتب، لا يزال بإمكانك تعيين المفاتيح عبر `keyring`
CLI الخاص بـ Python (بعد `uv sync`):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# الموفرون المخصصون (الصق JSON blob — راجع UI Settings للمخطط)
uv run keyring set ai-translate llm/custom_providers
```

أو قم بتعيين نفس مفاتيح INI مباشرة في `settings.ini` — يقوم
التطبيق بترحيلها إلى keychain عند القراءة الأولى. الملف موجود في:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## اختبار الإعداد

أسرع فحص للسلامة:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Arabic --quiet
cat /tmp/x_translated__ar.txt
```

إذا رأيت "مرحبا بالعالم." — فقد انتهيت.

## أخطاء شائعة

| Error | السبب المحتمل |
|---|---|
| `AUTH_ERROR` | مفتاح API خاطئ / منتهي الصلاحية. الصق مرة أخرى في Settings. |
| `QUOTA_ERROR` | تم تجاوز طلبات اليوم للمستوى المجاني. انتظر، أو ادفع. |
| `MODEL_NOT_FOUND` | قائمة `models` للموفر المخصص لا تتضمن النموذج المطلوب. |
| `VISION_NOT_SUPPORTED` | لا يمكن للنموذج الذي اخترته إدخال الصور. استخدم متغير `flash` / `pro` / `vision`. |

راجع [Troubleshooting](../troubleshooting.md) لمزيد من المعلومات.
