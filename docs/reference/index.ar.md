---
description: مرجع المطورين لواجهة برمجة Python في AI Translate — مُنشأ تلقائيًا من docstrings؛ يغطي وحدات core وutils وconstants وCLI وMCP server.
---

# مرجع المطورين

من المرجح أن المستخدمين النهائيين يريدون [صفحات الميزات](../index.md#headline-features)
أو [أدلة الإعداد](../setup/llm-providers.md)، وليس هذا القسم.

هذا **مرجع API مُنشأ تلقائيًا** — صفحة واحدة لكل وحدة Python في
`src/`، تُعرض من docstrings الخاصة بالمشروع. وهو مخصص للمساهمين
والمدمجين الذين يريدون استدعاء الدوال الأساسية من كود Python الخاص
بهم.

## هدف البناء

يقوم `uv run mkdocs build` بإعادة توليد هذه الصفحات من `src/` في كل
بناء، لذا فهي تعكس دائمًا ما هو موجود حاليًا في الكود.

## من أين تبدأ

نقطة دخول الترجمة بدون واجهة هي
[`run_translation_pipeline`](api/core/translator.md) — كل ميزة في
تطبيق سطح المكتب وCLI وخادم MCP تمر في النهاية عبرها. قراءة تلك
الدالة وجارها `TranslationConfig` هي أسرع طريقة لفهم خط الإنابيب.

## التخطيط

- **[Constants](api/constants/index.md)** — مفاتيح الإعدادات، رموز الأخطاء، جداول اللغات، محركات i18n / theme.
- **[Core](api/core/index.md)** — خط أنابيب الترجمة، إرسال LLM، معالجات خاصة بالتنسيق، محركات OCR / STT / TTS، نقاط التحقق، قاعدة البيانات.
- **[Utils](api/utils/index.md)** — مساعدات عرضية.
- **[CLI](api/cli.md)** — نقطة دخول `ait`.
- **[MCP Server](api/mcp_server.md)** — نقطة دخول `ait-mcp`.
