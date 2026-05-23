---
description: AI Translate को Model Context Protocol tools के रूप में expose करें ताकि Claude Desktop, Claude Code, और अन्य MCP clients text, files, और audio का अनुवाद कर सकें।
---

# MCP सर्वर (`ait-mcp`)

Translation pipeline को **Model Context Protocol** tools के रूप में
expose करता है ताकि Claude Desktop और Claude Code जैसे AI agents
इसे सीधे drive कर सकें — "इस PDF का French में अनुवाद करो" एक tool
call बन जाता है, copy-paste नहीं।

## क्या expose किया जाता है

नौ tools:

| Tool | उद्देश्य |
|---|---|
| `translate_text` | strings की सूची का अनुवाद करें |
| `translate_document` | File translation tasks queue करें (task IDs लौटाता है) |
| `get_task_status` | Task status poll करें |
| `cancel_task` | In-flight tasks का cooperative cancel |
| `extract_image_text` | OCR या LLM vision |
| `transcribe_audio` | Audio → SRT |
| `synthesize_speech` | Text → MP3 / WAV |
| `query_glossary` | Glossary sets / entries list करें |
| `list_languages` | सभी 45 supported languages |

## सर्वर चलाएँ

```bash
ait-mcp                       # stdio transport (desktop agents के लिए default)
ait-mcp --transport sse       # web clients के लिए Server-Sent Events
ait-mcp --transport sse --port 9000
```

`stdio` वही है जो हर MCP client expect करता है जब तक कि आपने SSE को
explicitly wire नहीं किया हो।

## Claude Desktop में जोड़ें

1. Claude Desktop खोलें → **Settings → Developer → Edit Config**
2. `mcpServers` के तहत यह entry जोड़ें:

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

    `/absolute/path/to/ai-translate` को cloned repo path से बदलें।

3. Claude Desktop को quit करें और फिर से खोलें। Hammer icon अब सभी 9
   tools के साथ "ai-translate" दिखाएगा। आज़माएँ:

    > "इस PDF (`/home/me/report.pdf`) का French में अनुवाद करो —
    > output को source के बगल में सहेजो।"

## Claude Code में जोड़ें

`~/.config/claude-code/mcp_servers.json` (या Claude Code के अंदर से
`claude mcp add`):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Claude Code को restart करें। वही 9 tools callable हो जाते हैं।

## अन्य MCP clients में जोड़ें

कोई भी MCP-compatible client समान आकार लेता है:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (default)

HTTP / SSE-based clients के लिए, `ait-mcp --transport sse --port 9000`
चलाएँ और client को `http://localhost:9000` पर इंगित करें।

## Validation guarantees

हर tool errors पर समान आकार लौटाता है ताकि agents failures को
consistently handle कर सकें:

| Bad input | Tool response |
|---|---|
| Unknown language | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM not configured | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Unsupported file type | `ValueError` allowed extensions listing |
| Malformed `model="…"` (no `:`) | `ValueError` बजाय silently default उपयोग करने के |
| `cancel_task` में Unknown task IDs | `unknown` array में return — कोई error नहीं |
| `transcribe_audio` पर FFmpeg missing | `RuntimeError: FFmpeg is required…` (engine के bare `FFMPEG_NOT_FOUND` tag से re-wrapped) |

इन tools को कॉल करने वाले agents इन contracts पर भरोसा कर सकते हैं।

## Concurrency

`translate_document` pipeline को daemon thread में चलाता है। हर batch
को अपना cancel event मिलता है, इसलिए एक batch को cancel करना दूसरे
को disturb नहीं करता। MCP server active pipelines को process-local
map में track करता है (pipeline खत्म होने पर automatic cleanup)।

## उपयोग के मामले

- **"इस codebase के docs का Vietnamese में अनुवाद करो"** — agent को
  docs folder पर इंगित करें, यह `translate_document` calls को batch
  करता है और प्रत्येक के समाप्त होने तक `get_task_status` poll करता
  है।
- **"आप कौन सी languages support करते हैं?"** — agent
  `list_languages` कॉल करता है, response पढ़ता है।
- **"इस Japanese receipt का अनुवाद करो"** — agent photo पर
  `extract_image_text` कॉल करता है, फिर result पर `translate_text`।
- **"इस Zoom recording के लिए Vietnamese subtitles बनाओ"** — agent
  source language में SRT पाने के लिए `transcribe_audio` कॉल करता है,
  फिर localize करने के लिए हर cue पर `translate_text`, और SRT को
  reassemble करता है।

!!! note "Video dubbing एक MCP tool नहीं है"
    पूर्ण STT → translate → TTS → mux pipeline (desktop app का
    **Dubbing** पेज) अभी केवल GUI के माध्यम से उपलब्ध है। MCP से आप
    `transcribe_audio` + `translate_text` + `synthesize_speech` के
    साथ equivalent खुद compose कर सकते हैं, लेकिन आपको timing-aware
    mux step (FFmpeg) को बाहर handle करना होगा।

## टिप्स

!!! tip "एक बार setup करें, agents हर जगह काम करते हैं"
    MCP server desktop app और CLI के साथ API keys और settings साझा
    करता है। GUI में अपने LLM / OCR / TTS को एक बार configure करें,
    फिर कोई भी agent जो `ait-mcp` से बात करता है वही setup inherit
    करता है।

!!! tip "Cold-start endpoint cache"
    प्रत्येक `(endpoint, model)` pair के लिए, chat-vs-responses-API
    choice और working payload variant OS cache directory में
    `llm_endpoint_cache.json` में persist किए जाते हैं (Linux पर
    `~/.cache/ai-translate/`, macOS पर
    `~/Library/Caches/ai-translate/`, Windows पर
    `%LOCALAPPDATA%\ai-translate\cache\`)। पहले successful call के
    बाद Fresh `ait-mcp` processes auto-detection probe को पूरी तरह
    skip कर देती हैं — जो agents server को on demand spawn करते हैं
    वे हर invocation पर variant-detection round-trips का भुगतान नहीं
    करते। Cache multi-process और multi-thread safe है (atomic rename
    के साथ RLock के तहत read-merge-write)।

!!! tip "Per-tool model picker"
    `translate_text` और `translate_document` tools एक optional
    `model` parameter स्वीकार करते हैं — agents quick turns के लिए
    fast model और production output के लिए heavier एक चुन सकते हैं
    user को desktop app reconfigure करने की आवश्यकता के बिना।

!!! warning "Long-running pipelines"
    `translate_document` task IDs के साथ तुरंत return करता है। Agent
    से expected है कि वह हर task के `Done` या `Failed` तक पहुँचने तक
    `get_task_status` poll करे। Tool call के अंदर synchronously
    प्रतीक्षा न करें; इससे MCP client का timeout fire होने का जोखिम
    है।
