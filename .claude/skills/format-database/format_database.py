#!/usr/bin/env python3
"""
Normalizes a database.json knowledge-base file:

- every entry is written as a single-line {"category": ..., "text": ...} object
- entries are stable-sorted by category (alphabetical), so every category's
  entries are contiguous, with a blank line between category groups
- exact (category, text) duplicates are collapsed to a single copy
- non-ASCII characters (e.g. °) are kept as literal UTF-8, not \\uXXXX escapes

Safety: writes to a .tmp file, validates it against the original in memory,
and only then replaces the real file. Never touches git — this script is the
only source of truth for "did content change", so there is nothing to
reconstruct from git history if something goes wrong.
"""

import json
import sys
from pathlib import Path


def format_database(path: Path) -> None:
    with open(path, encoding="utf-8") as f:
        original = json.load(f)

    if not isinstance(original, list):
        sys.exit(f"error: {path} is not a JSON array")

    for i, item in enumerate(original):
        if not isinstance(item, dict) or "category" not in item or "text" not in item:
            sys.exit(f"error: entry {i} is not a {{category, text}} object: {item!r}")

    # dedupe: keep the first occurrence of each exact (category, text) pair
    deduped = []
    seen = set()
    removed = []
    for item in original:
        key = (item["category"], item["text"])
        if key in seen:
            removed.append(key)
            continue
        seen.add(key)
        deduped.append(item)

    # stable sort by category — entries within a category keep their
    # original relative order, but all same-category entries become contiguous
    sorted_entries = sorted(deduped, key=lambda item: item["category"])

    def encode_str(s: str) -> str:
        return json.dumps(s, ensure_ascii=False)

    lines = ["["]
    prev_category = None
    for i, item in enumerate(sorted_entries):
        if prev_category is not None and item["category"] != prev_category:
            lines.append("")
        comma = "," if i < len(sorted_entries) - 1 else ""
        lines.append(
            f'    {{"category": {encode_str(item["category"])}, '
            f'"text": {encode_str(item["text"])}}}{comma}'
        )
        prev_category = item["category"]
    lines.append("]")
    lines.append("")
    new_content = "\n".join(lines)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # validate the tmp file before touching the real one
    with open(tmp_path, encoding="utf-8") as f:
        reloaded = json.load(f)

    expected_count = len(original) - len(removed)
    if len(reloaded) != expected_count:
        tmp_path.unlink()
        sys.exit(
            f"error: expected {expected_count} entries after dedup, got "
            f"{len(reloaded)} — aborting, real file untouched"
        )

    # multiset check: every entry in `reloaded` must exist in `original`,
    # and every entry in `original` must exist in `reloaded` (accounting for
    # the intentional dedup removals)
    from collections import Counter
    orig_counts = Counter((i["category"], i["text"]) for i in original)
    new_counts = Counter((i["category"], i["text"]) for i in reloaded)
    for key, count in new_counts.items():
        if count != 1:
            tmp_path.unlink()
            sys.exit(f"error: {key} appears {count} times after dedup — aborting")
    for key in orig_counts:
        if key not in new_counts:
            tmp_path.unlink()
            sys.exit(f"error: entry {key} vanished entirely — aborting")

    seen_pairs = set()
    for item in reloaded:
        key = (item["category"], item["text"])
        if key in seen_pairs:
            tmp_path.unlink()
            sys.exit(f"error: duplicate survived: {key} — aborting")
        seen_pairs.add(key)

    categories = []
    cat_positions = {}
    for i, item in enumerate(reloaded):
        cat_positions.setdefault(item["category"], []).append(i)
        if item["category"] not in categories:
            categories.append(item["category"])
    non_contiguous = [
        c for c, pos in cat_positions.items()
        if pos != list(range(pos[0], pos[0] + len(pos)))
    ]
    if non_contiguous:
        tmp_path.unlink()
        sys.exit(f"error: categories still scattered after sort: {non_contiguous}")

    tmp_path.replace(path)

    print(f"OK: {len(original)} -> {len(reloaded)} entries "
          f"({len(removed)} exact duplicate(s) removed)")
    if removed:
        print("Removed duplicates:")
        for cat, text in removed:
            print(f"  [{cat}] {text}")
    print(f"{len(categories)} categories, all contiguous:")
    for cat in categories:
        print(f"  {cat} ({len(cat_positions[cat])})")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend/database.json")
    if not target.exists():
        sys.exit(f"error: {target} does not exist")
    format_database(target)
