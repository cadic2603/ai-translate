---
description: AI Translate के Python API के लिए डेवलपर संदर्भ — docstrings से ऑटो-जनरेटेड; core, utils, constants, CLI और MCP server मॉड्यूल कवर करता है।
---

# डेवलपर संदर्भ

अंतिम उपयोगकर्ता शायद इस सेक्शन के बजाय [फीचर पेज](../index.md#headline-features)
या [सेटअप गाइड](../setup/llm-providers.md) चाहते हैं।

यह **ऑटो-जनरेटेड API संदर्भ** है — `src/` में हर Python मॉड्यूल के
लिए एक पेज, प्रोजेक्ट के docstrings से रेंडर किया गया। यह उन
contributors और integrators के लिए है जो अपने Python कोड से
underlying functions को कॉल करना चाहते हैं।

## Build target

`uv run mkdocs build` हर बिल्ड पर `src/` से इन पेजों को फिर से
generate करता है, इसलिए वे हमेशा कोड की वर्तमान स्थिति को दर्शाते
हैं।

## कहाँ से शुरू करें

Headless translation entry point है
[`run_translation_pipeline`](api/core/translator.md) — डेस्कटॉप ऐप,
CLI और MCP server की हर फीचर अंततः इसी से होकर गुजरती है। उस
function और इसके `TranslationConfig` neighbour को पढ़ना pipeline
को समझने का सबसे तेज़ तरीका है।

## लेआउट

- **[Constants](api/constants/index.md)** — settings keys, error codes, language tables, i18n / theme engines.
- **[Core](api/core/index.md)** — translation pipeline, LLM dispatch, format-specific processors, OCR / STT / TTS engines, checkpoints, database.
- **[Utils](api/utils/index.md)** — cross-cutting helpers.
- **[CLI](api/cli.md)** — `ait` entry point.
- **[MCP Server](api/mcp_server.md)** — `ait-mcp` entry point.
