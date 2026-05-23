---
description: Translations में consistent terminology लागू करने के लिए custom glossary sets manage करें — CSV import/export, language pair के अनुसार scope, project के अनुसार prioritise।
---

# शब्दावली

हर translation job में specific terms को specific translations से
lock करें। Brand names, product terminology, technical jargon, या
character names के लिए उपयोगी जिन्हें आप consistent रखना चाहते हैं।

## यह कैसे काम करता है

एक glossary (source term, target term) pairs की एक list है जो एक
**set** में grouped होती है। जब आप एक set चालू करते हैं, तो ऐप में
हर LLM call को relevant entries prompt में injected मिलती हैं — तो
अनुवाद करने से पहले LLM देखता है "use 'OpenAI' for 'OpenAI', not
'开放AI'"।

एक साथ कई sets active हो सकते हैं। केवल वही entries prompt में
add होती हैं जिनकी source या target batch text में दिखाई देती है
(per-call compression), इसलिए 5,000-entry glossary tokens पर सस्ती
रहती है।

## Step-by-step

1. Sidebar में **शब्दावली** क्लिक करें।
2. **New Set** क्लिक करें (`Ctrl+N`) और इसे एक name दें (जैसे
   "Project Acme")।
3. Left पर set selected के साथ, right pane इसकी entries दिखाता है।
4. एक नई entry create करने के लिए **Add** क्लिक करें। भरें:
    - **Source** — original term
    - **Target** — enforce करने के लिए translation
    - वैकल्पिक रूप से एक comment / note
5. हर term के लिए दोहराएँ।
6. Translations के लिए इसे enable करने के लिए set name पर **Active**
   checkbox tick करें।

## Sets को activate / deactivate करें

हर set name के बगल में **Active** checkbox नियंत्रित करता है कि
इसकी entries LLM prompts में inject होती हैं या नहीं। आप storage में
50 inactive sets छोड़ सकते हैं और केवल वर्तमान project के लिए
आवश्यक 2 को flip on कर सकते हैं।

## Import / Export (CSV)

- **Export** — एक set चुनें, **Export** क्लिक करें → `.csv` के रूप
  में save करें। दो columns: `source`, `target` (UTF-8,
  comma-separated, RFC 4180-quoted)।
- **Import** — **Import** क्लिक करें → एक `.csv` चुनें → एक
  destination set चुनें (existing या new)। एक duplicate source पर
  आपको एक replace-or-skip prompt मिलेगा।

CSV format round-trip करता है, इसलिए Export → Excel में edit →
Import safe है।

## Search और filter

`Ctrl+F` search box पर focus करता है। कोई भी substring type करें और
entries (और set list) matches पर filter हो जाती हैं; matched
substring highlighted होता है। Search clear करने से full list
restore होती है।

Search **accent-insensitive और case-insensitive** है — `cafe` `café`
को ढूँढता है और vice versa।

## In-place edit

Edit करने के लिए किसी भी cell पर क्लिक करें। अगले cell पर move
करने के लिए `Tab` दबाएँ। Revert करने के लिए `Esc` दबाएँ। जब आप row
से बाहर क्लिक करते हैं तो एक auto-save trigger होता है। Empty source
या target invalid entry save करने के बजाय row को revert करता है।

## Delete

- **एक single entry delete करें** — इसे select करें, `Delete`
  दबाएँ। आपको एक confirmation dialog दिखेगा।
- **एक पूरा set delete करें** — set select करें, `Delete` दबाएँ।
  Dialog cascade entry count दिखाता है ताकि आप जान सकें कि आप क्या
  delete कर रहे हैं।

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N` | New set |
| `Ctrl+F` | Search पर focus |
| `Delete` | Selected entry / set delete करें |

## टिप्स

!!! tip "Per-set scope"
    एक set एक *logical* grouping है। Project के अनुसार, client के
    अनुसार, domain के अनुसार (medical / legal / gaming) — जो भी
    समझ में आए। केवल वर्तमान job के लिए relevant sets activate करें।

!!! tip "Glossary translation को override नहीं करता"
    LLM को glossary entries का उपयोग करने का निर्देश दिया जाता है,
    लेकिन यह एक hint बना रहता है — extremely awkward forced
    translations अभी भी surface कर सकते हैं। Full sentences के बजाय
    simple `term → translation` pairs का उपयोग करें।
