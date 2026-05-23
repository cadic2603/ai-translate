---
description: Expose AI Translate as Model Context Protocol tools so Claude Desktop, Claude Code, and other MCP clients can translate text, files, and audio.
---

# MCP Server (`ait-mcp`)

Exposes the translation pipeline as **Model Context Protocol** tools so
AI agents like Claude Desktop and Claude Code can drive it directly —
"Translate this PDF into French" becomes a tool call, not a copy-paste.

## What gets exposed

Nine tools:

| Tool | Purpose |
|---|---|
| `translate_text` | Translate a list of strings |
| `translate_document` | Queue file translation tasks (returns task IDs) |
| `get_task_status` | Poll task status |
| `cancel_task` | Cooperative cancel of in-flight tasks |
| `extract_image_text` | OCR or LLM vision |
| `transcribe_audio` | Audio → SRT |
| `synthesize_speech` | Text → MP3 / WAV |
| `query_glossary` | List glossary sets / entries |
| `list_languages` | All 45 supported languages |

## Run the server

```bash
ait-mcp                       # stdio transport (default for desktop agents)
ait-mcp --transport sse       # Server-Sent Events for web clients
ait-mcp --transport sse --port 9000
```

`stdio` is what every MCP client expects unless you've wired up SSE
explicitly.

## Add to Claude Desktop

1. Open Claude Desktop → **Settings → Developer → Edit Config**
2. Add this entry under `mcpServers`:

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

    Replace `/absolute/path/to/ai-translate` with the cloned repo path.

3. Quit and re-open Claude Desktop. The hammer icon should now show
   "ai-translate" with all 9 tools. Try:

    > "Translate this PDF (`/home/me/report.pdf`) into French — save
    > the output next to the source."

## Add to Claude Code

`~/.config/claude-code/mcp_servers.json` (or `claude mcp add` from
inside Claude Code):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Restart Claude Code. The same 9 tools become callable.

## Add to other MCP clients

Any MCP-compatible client takes a similar shape:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (default)

For HTTP / SSE-based clients, run `ait-mcp --transport sse --port 9000`
and point the client at `http://localhost:9000`.

## Validation guarantees

Every tool returns the same shape on errors so agents can handle
failures consistently:

| Bad input | Tool response |
|---|---|
| Unknown language | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM not configured | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Unsupported file type | `ValueError` listing allowed extensions |
| Malformed `model="…"` (no `:`) | `ValueError` instead of silently using default |
| Unknown task IDs in `cancel_task` | Returned in the `unknown` array — no error |
| FFmpeg missing on `transcribe_audio` | `RuntimeError: FFmpeg is required…` (re-wrapped from the engine's bare `FFMPEG_NOT_FOUND` tag) |

Agents calling these tools can rely on these contracts.

## Concurrency

`translate_document` runs the pipeline in a daemon thread. Each batch
gets its own cancel event, so cancelling one batch doesn't disturb
another. The MCP server tracks active pipelines in a process-local
map (cleaned up automatically when the pipeline finishes).

## Use cases

- **"Translate this codebase's docs into Vietnamese"** — point the
  agent at the docs folder, it batches `translate_document` calls and
  polls `get_task_status` until each one finishes.
- **"What languages do you support?"** — agent calls `list_languages`,
  reads the response.
- **"Translate this Japanese receipt"** — agent calls
  `extract_image_text` on the photo, then `translate_text` on the
  result.
- **"Generate Vietnamese subtitles for this Zoom recording"** — agent
  calls `transcribe_audio` to get an SRT in the source language, then
  `translate_text` on each cue to localise, and reassembles the SRT.

!!! note "Video dubbing isn't an MCP tool"
    The full STT → translate → TTS → mux pipeline (the desktop app's
    **Dubbing** page) is only available through the GUI right now. From
    MCP you can compose the equivalent yourself with
    `transcribe_audio` + `translate_text` + `synthesize_speech`, but
    you'll need to handle the timing-aware mux step (FFmpeg) outside.

## Tips

!!! tip "Setup once, agents work everywhere"
    The MCP server shares API keys and settings with the desktop app
    and CLI. Configure your LLM / OCR / TTS once in the GUI, then any
    agent that talks to `ait-mcp` inherits the same setup.

!!! tip "Cold-start endpoint cache"
    For each `(endpoint, model)` pair, the chat-vs-responses-API choice
    and the working payload variant are persisted to
    `llm_endpoint_cache.json` in the OS cache directory
    (`~/.cache/ai-translate/` on Linux,
    `~/Library/Caches/ai-translate/` on macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` on Windows). Fresh `ait-mcp`
    processes skip the auto-detection probe entirely after the first
    successful call — agents that spawn the server on demand don't pay
    the variant-detection round-trips on every invocation. The cache
    is multi-process and multi-thread safe (read-merge-write under
    RLock with atomic rename).

!!! tip "Per-tool model picker"
    The `translate_text` and `translate_document` tools accept an
    optional `model` parameter — agents can pick a fast model for
    quick turns and a heavier one for production output without
    needing the user to reconfigure the desktop app.

!!! warning "Long-running pipelines"
    `translate_document` returns immediately with task IDs. The agent
    is expected to poll `get_task_status` until each task reaches
    `Done` or `Failed`. Don't wait synchronously inside the tool call;
    that risks the MCP client's timeout firing.
