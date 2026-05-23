---
description: AI Translate एक मुफ्त, cross-platform desktop translator है जो 45+ भाषाओं में documents, PDFs, subtitles, audio और live speech के लिए है।
---

# AI Translate

एक मुफ्त, cross-platform desktop translator जो **45 भाषाएँ** संभालता
है और plain text से कहीं आगे जाता है — यह documents, audio, video,
live speech, screen captures, और बहुत कुछ अनुवाद करता है, सब एक ही
LLM-powered pipeline के साथ।

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Desktop app**

    ---

    एक file drag करें, target language चुनें, translated copy वापस
    पाएँ। Drag-and-drop, history, glossaries, सब कुछ।

    [:octicons-arrow-right-24: 5 मिनट का walkthrough](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Command line**

    ---

    `ait report.docx --target French` — वही pipeline, scriptable और
    headless। CI, batch jobs, servers के लिए उपयोगी।

    [:octicons-arrow-right-24: CLI गाइड](cli.md)

-   :material-robot-outline:{ .lg .middle } **AI agents (MCP)**

    ---

    Translation को Model Context Protocol tools के रूप में expose करें
    ताकि Claude Desktop, Claude Code, और अन्य MCP clients इन्हें
    सीधे call कर सकें।

    [:octicons-arrow-right-24: MCP सेटअप](mcp.md)

</div>

## आप क्या अनुवाद कर सकते हैं

| प्रकार | Formats |
|---|---|
| **Office docs** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, plus legacy `.doc` / `.xls` / `.ppt` |
| **PDFs** | layout preservation के साथ extract-overlay translation, bookmark / form / link translation, scans के लिए OCR fallback |
| **Text & web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Subtitles** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Localization** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Images** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR या LLM vision) |
| **Audio** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Video** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (पूर्ण dubbing pipeline) |

## मुख्य विशेषताएँ {: #headline-features }

- **[टेक्स्ट अनुवाद](features/translate-text.md)** — auto-detection, edit-in-place, TTS playback के साथ instant LLM translation। Right-to-left भाषाएँ (Arabic, Hebrew, Persian) natively render होती हैं।
- **[दस्तावेज़ अनुवाद](features/translate-document.md)** — files drop करें, per-task progress spinner देखें, side-by-side translated copies पाएँ। RTL targets को उचित bidi markup मिलता है; `Ctrl+P` / `Ctrl+G` queue को pause और continue करते हैं।
- **[सबटाइटल बनाएँ (STT)](features/generate-subtitle.md)** — audio / video को SRT / VTT / ASS / SSA में transcribe करें।
- **[आवाज़ बनाएँ (TTS)](features/generate-voice.md)** — subtitles को timing के साथ MP3 / WAV में synthesize करें।
- **[वीडियो डबिंग](features/dubbing.md)** — पूर्ण STT → translate → TTS → source video में वापस mix।
- **[लाइव अनुवाद](features/live-translation.md)** — real-time microphone या system-audio subtitle overlay।
- **[टेक्स्ट निकालें](features/extract-text.md)** — OCR या LLM vision → `.txt` / `.docx`।
- **[शब्दावली](features/glossary.md)** — translations में consistent terminology लागू करें।

!!! tip "Gemini के लिए Vertex AI mode"
    Enterprise users **सेटिंग्स → LLM** में Developer API से Gemini
    calls को **Vertex AI** में switch कर सकते हैं — इसे अपने GCP
    project और region पर इंगित करें, वैकल्पिक रूप से एक
    service-account JSON path दें। देखें
    [LLM Providers](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup)।

!!! tip "पहली बार यहाँ?"
    [इंस्टॉलेशन](getting-started/installation.md) से शुरू करें, फिर
    [5-मिनट first-translation walkthrough](getting-started/first-translation.md)।
    आपके पास एक fresh clone से 10 मिनट से कम में translated document
    होगा।
