"""Build dist/index.json: every tool, plus what enrich.py read from its own site.

Usage: python scripts/build_index.py [--out PATH]
Facts written by hand in a tool's file always win. From the tool's pricing page we only take
whether it mentions a free plan or a free trial, plus the page's address and the date it was read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from directory import ROOT, categories, load, shard, tool_files

FIELDS = ("name", "description", "category", "website", "company", "tags", "pricing", "starting_price", "currency",
          "free_trial", "pricing_url", "pricing_checked", "open_source", "repository", "platforms",
          "education_discount", "added")


def enrichment() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted((ROOT / "data" / "enrichment").glob("*.json")):
        out.update(json.loads(f.read_text()))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist" / "index.json"))
    args = ap.parse_args()

    extra = enrichment()
    tools = []
    for path in tool_files():
        data = load(path)
        item = {"slug": path.stem}
        for key in FIELDS:
            value = data.get(key)
            if value is None or value == []:
                continue
            item[key] = value.isoformat() if isinstance(value, dt.date) else value
        e = extra.get(path.stem, {})
        if e.get("image"):
            item["image"] = e["image"]
        # The pricing page is only read for flags: a price scraped from page text is too often wrong
        # (yearly prices, promos, plans loaded by script), so exact prices come from the tool's file.
        p = e.get("pricing")
        if p:
            item["pricing_url"] = item.get("pricing_url") or p["url"]
            item["pricing_seen"] = e["checked"]
            if p.get("free") and "pricing" not in item:
                item["free_plan"] = True
            if p.get("trial") and "free_trial" not in item:
                item["free_trial"] = True
        tools.append(item)

    tools.sort(key=lambda t: (t["name"].lower(), t["slug"]))
    cats = categories()
    counts = {c: 0 for c in cats}
    for t in tools:
        counts[t["category"]] = counts.get(t["category"], 0) + 1
    index = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "count": len(tools),
        "categories": {c: {**meta, "count": counts[c]} for c, meta in cats.items()},
        "tools": tools,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {out} with {len(tools)} tools ({sum(1 for t in tools if 'image' in t)} with a preview image)")


if __name__ == "__main__":
    main()
