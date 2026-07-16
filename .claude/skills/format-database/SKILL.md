---
name: format-database
description: Normalizes backend/database.json — single-line {category, text} entries, grouped and alphabetically sorted by category, exact duplicates collapsed. Use whenever new entries have been added/edited in backend/database.json and it needs formatting/reordering.
---

# Format database.json

`backend/database.json` is the RAG knowledge base for the sales bot. New
entries keep getting pasted in with inconsistent formatting (multi-line
pretty-printed objects instead of the file's single-line convention) and in
whatever order, which scatters same-category entries across the file and
makes it hard to review or extend.

## What this does

Run the bundled script against the live file:

```bash
python3 .claude/skills/format-database/format_database.py backend/database.json
```

(If invoked from inside `backend/`, just omit the path argument — it
defaults to `backend/database.json` relative to the current directory.)

The script:

1. Loads the JSON array and validates every entry is a `{category, text}` object.
2. Removes exact `(category, text)` duplicates, keeping the first occurrence.
3. Stable-sorts all entries by `category` (alphabetical) so every category's
   entries become contiguous, in their original relative order.
4. Re-serializes every entry as a single-line `{"category": ..., "text": ...}`
   object, with a blank line between category groups, and non-ASCII
   characters (e.g. `°`) kept as literal UTF-8 rather than escaped.
5. Writes to a `.tmp` file, validates the tmp file's content against the
   original (same entries minus the intended dedup, no scattered
   categories, valid JSON), and only *then* replaces the real file.
6. Prints a summary: entry count before/after, which duplicates were
   removed, and the final category list with counts.

## After running

- Skim the printed summary — confirm the removed-duplicates list (if any)
  actually looks like duplicates, not two similar-but-distinct facts.
- Spot check the diff (`git diff backend/database.json`) before committing,
  the same way you would for anything else.
- Commit with a message noting the entry count change and duplicates
  removed, e.g. "Normalize database.json formatting (161 -> 158 entries,
  removed 3 exact duplicates)".

## Why a script instead of doing this by hand each time

This exact task has come up multiple times as the knowledge base grows.
Earlier passes were done by hand-writing a one-off Python heredoc each
time — which is how one pass accidentally ran `git checkout -- database.json`
mid-task to fix an unrelated encoding bug, silently discarding ~24
uncommitted entries that weren't in any commit yet (they were recovered
from the conversation transcript, but it shouldn't have happened).

This script never touches git and never trusts a prior read — it always
loads fresh from disk, validates on a `.tmp` file, and only swaps it into
place after every check passes. If anything looks wrong, it exits without
writing, leaving the real file untouched.
