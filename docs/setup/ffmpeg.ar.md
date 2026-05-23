---
description: ثبّت FFmpeg حتى يتمكن AI Translate من فك تشفير الصوت والفيديو لإنشاء الترجمة وتوليف الصوت ودبلجة الفيديو — مطلوب لميزات الوسائط.
---

# FFmpeg

FFmpeg مطلوب لأي سير عمل صوتي / مرئي:

- **إنشاء الترجمة** — فك ترميز الصوت المصدر لـ STT
- **إنشاء الصوت** — دمج مقاطع TTS الموقوتة في ملف واحد
- **الدبلجة** — STT → TTS → mux مرة أخرى في الفيديو
- **الترجمة الفورية** — عندما يمر التقاط صوت النظام عبر `parec`

ليس مدمجًا — قم بتثبيته مرة واحدة على نظامك.

## التثبيت

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    أو، للحصول على بناء أكثر اكتمالاً، قم أولاً بتمكين
    [RPM Fusion](https://rpmfusion.org/Configuration).

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    قم بتنزيل بناء ثابت من <https://www.gyan.dev/ffmpeg/builds/>
    (بناء "release essentials" جيد)، فك ضغطه، ثم أضف مجلد `bin/`
    إلى PATH:

    1. اضغط **Win + R**، اكتب `sysdm.cpl`، اضغط **Enter**
    2. **Advanced → Environment Variables → System variables → Path → Edit**
    3. **New** → الصق المسار المطلق لمجلد `bin` الخاص بـ FFmpeg
    4. **OK** في كل مكان، أعد تشغيل أي طرفيات مفتوحة

## التحقق

```bash
ffmpeg -version
```

يجب أن ترى شعار إصدار مع `--enable-libx264 --enable-libvpx` في سطر
التكوين. إذا رأيت "command not found"، فإن التثبيت لم يصل إلى PATH.

## فحص ما قبل التشغيل في التطبيق

تستدعي صفحات الصوت / الدبلجة `shutil.which("ffmpeg")` قبل بدء
العمل. إذا لم يتم العثور على FFmpeg، فسترى حوار خطأ ودود مع رابط
يعود إلى هنا، وليس مهمة منتصف التشغيل.

## خطأ شائع

| Error | المعنى |
|---|---|
| `FFMPEG_NOT_FOUND` | لم يكن `ffmpeg` على PATH في الوقت الذي حاولت فيه الصفحة تشغيله. ثبّته (أعلاه) وأعد تشغيل التطبيق. |

في خادم MCP (`ait-mcp`)، يتم إعادة لف نفس الخطأ في رسالة قابلة
للقراءة:

> *"FFmpeg is required to decode this audio/video file but is not
> installed or not on PATH. Install FFmpeg and try again."*
