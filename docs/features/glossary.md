---
description: Manage custom glossary sets to enforce consistent terminology across translations — import/export CSV, scope per language pair, prioritise per project.
---

# Glossary

Lock specific terms to specific translations across every translation
job. Useful for brand names, product terminology, technical jargon, or
character names you want kept consistent.

## How it works

A glossary is a list of (source term, target term) pairs grouped into
a **set**. When you turn a set on, every LLM call in the app gets the
relevant entries injected into the prompt — so the LLM sees "use
'OpenAI' for 'OpenAI', not '开放AI'" before it translates.

Multiple sets can be active at once. Only entries whose source or target
appears in the batch text get added to the prompt (per-call compression),
so a 5,000-entry glossary stays cheap on tokens.

## Walkthrough

1. Click **Glossary** in the sidebar.
2. Click **New Set** (`Ctrl+N`) and give it a name (e.g. "Project Acme").
3. With the set selected on the left, the right pane shows its entries.
4. Click **Add** to create a new entry. Fill in:
    - **Source** — the original term
    - **Target** — the translation to enforce
    - Optionally a comment / note
5. Repeat for each term.
6. Tick the **Active** checkbox on the set name to enable it for translations.

## Activate / deactivate sets

The **Active** checkbox next to each set name controls whether its
entries are injected into LLM prompts. You can leave 50 inactive sets
in storage and only flip on the 2 you need for the current project.

## Import / Export (CSV)

- **Export** — pick a set, click **Export** → save as `.csv`. Two columns:
  `source`, `target` (UTF-8, comma-separated, RFC 4180-quoted).
- **Import** — click **Import** → pick a `.csv` → choose a destination
  set (existing or new). On a duplicate source you'll get a replace-or-skip
  prompt.

The CSV format round-trips, so an Export → edit-in-Excel → Import is
safe.

## Search and filter

`Ctrl+F` focuses the search box. Type any substring and entries (and
the set list) filter to matches; the matched substring is highlighted.
Clearing the search restores the full list.

Search is **accent-insensitive and case-insensitive** — `cafe` finds
`café` and vice versa.

## Edit in place

Click any cell to edit. Press `Tab` to move to the next cell. Press
`Esc` to revert. An auto-save triggers when you click off the row.
Empty source or target reverts the row instead of saving an invalid
entry.

## Delete

- **Delete a single entry** — select it, press `Delete`. You'll see a
  confirmation dialog.
- **Delete a whole set** — select the set, press `Delete`. The dialog
  shows the cascade entry count so you know what you're nuking.

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N` | New set |
| `Ctrl+F` | Focus search |
| `Delete` | Delete selected entry / set |

## Tips

!!! tip "Per-set scope"
    A set is a *logical* grouping. Group by project, by client, by
    domain (medical / legal / gaming) — whatever makes sense. Activate
    only the sets relevant to the current job.

!!! tip "Glossary doesn't override translation"
    The LLM is instructed to use the glossary entries, but it remains
    a hint — extremely awkward forced translations can still surface.
    Use simple `term → translation` pairs rather than full sentences.
