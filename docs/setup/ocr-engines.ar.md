---
description: قم بإعداد محركات OCR لاستخراج نصوص الصور وملفات PDF — اختر بين Tesseract أو EasyOCR دون اتصال، أو Google Vision OCR المستند إلى السحابة.
---

# محركات OCR

يستخدم OCR لقراءة النص من الصور — على صفحة [Extract Text](../features/extract-text.md)
وكذلك كاحتياطي داخل ترجمة Document عندما تكون الصفحة ممسوحة (لا
توجد طبقة نص) أو عندما تقوم بتشغيل **Translate embedded images**.

يمكنك الاختيار من بين ثلاثة محركات OCR.

## Tesseract (الافتراضي الموصى به)

مجاني، سريع، دون اتصال. يحتاج إلى تثبيت نظام.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` يجلب كل لغة مدعومة. لتوفير القرص، قم
    بتثبيت ما تحتاجه فقط (مثل `tesseract-ocr-fra` للفرنسية).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    قم بتنزيل المثبت من
    [إصدارات Tesseract لـ UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
    قم بتشغيله، اقبل الإعدادات الافتراضية — حزم اللغة مدمجة.

تحقق:

```bash
tesseract --version
tesseract --list-langs
```

في تطبيق سطح المكتب: **Settings → OCR → OCR method = Tesseract**.
تم.

## EasyOCR

مجاني، دون اتصال. رائع للنصوص غير اللاتينية (الصينية، الكورية،
اليابانية، التايلاندية). تنزل النماذج عند الاستخدام الأول (~1 GB
إجمالي).

```bash
uv sync --extra easyocr
```

في تطبيق سطح المكتب: **Settings → OCR → OCR method = EasyOCR**.

في المرة الأولى التي تستخدم فيها لغة، يتم تنزيل النموذج ذي الصلة
إلى `~/.EasyOCR/`. التشغيلات اللاحقة فورية.

## Google Cloud Vision

سحابي، مدفوع (1,000 طلب مجاني / شهر). أعلى دقة، خاصة على المحتوى
الصاخب / المكتوب بخط اليد / متعدد النصوص.

1. [أنشئ مشروع Google Cloud](https://console.cloud.google.com/projectcreate)
2. قم بتمكين [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [أنشئ مفتاح API](https://console.cloud.google.com/apis/credentials)
4. في تطبيق سطح المكتب: **Settings → Service → Google Cloud API
   key** → الصق
5. **Settings → OCR → OCR method = Google Cloud OCR**

نفس مفتاح Google Cloud API يدعم Vision OCR وSpeech-to-Text
وText-to-Speech إذا قمت بتمكين هذه APIs أيضًا.

## مقارنة الدقة

علامة تبويب **Settings → OCR** بها جدول مقارنة صغير مدمج — تغطية
اللغة، متصل/دون اتصال، التكلفة، الدقة. أعد قراءته في أي وقت
تشعر فيه بإغراء التبديل.

## متى يستخدم OCR

| المكان | السلوك |
|---|---|
| **صفحة Extract Text** (عندما method = OCR) | OCR مباشر على الصور المسقطة |
| **Translate Document → PDF** | OCR fallback على الصفحات الممسوحة فقط (لا توجد طبقة نص) |
| **Translate Document → Office** مع تشغيل **Translate embedded images** | OCR + LLM vision على كل صورة مضمنة |

## نصائح

!!! tip "اختر لغة المصدر"
    معظم محركات OCR أكثر دقة بكثير عندما تخبرها أي لغة تتوقع.
    صفحات Subtitle / Document / Extract Text كلها تحول منتقي
    **Source language** الخاص بك إلى محرك OCR.

!!! tip "Tesseract كافٍ للنص المطبوع النظيف"
    لا تمد يدك إلى OCR السحابي حتى يفشل Tesseract / EasyOCR
    فعليًا على المحتوى الخاص بك. إنها مجانية، سريعة، وجيدة بشكل
    مذهل.
