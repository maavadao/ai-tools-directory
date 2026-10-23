"""Read each tool's own site for a preview image and pricing facts: data/enrichment/<shard>.json.

Usage: python scripts/enrich.py [--limit 300] [--max-age 30] [--slug SLUG ...]

For every tool whose data is older than --max-age days (oldest first, at most --limit per run):
  - the home page's own social preview image (og:image) and page title,
  - the pricing page (the tool's `pricing_url`, else a link on the home page that says pricing):
    whether it mentions a free plan or a trial.
Everything comes from the tool's own pages, obeys robots.txt and is cached with the date it was
read. The lowest price shown is recorded in `from`, but it is NOT published: prices scraped from
page text are often wrong (yearly or promo prices, plans loaded by script). Exact prices go in the
tool's own file (`pricing`, `starting_price`, `pricing_url`), which always wins.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from directory import ROOT, load, shard, tool_files
from web import fetch

OUT = ROOT / "data" / "enrichment"
META_RE = re.compile(r"<meta\s+[^>]*>", re.I)
ATTR_RE = re.compile(r'([a-zA-Z:-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')
LINK_RE = re.compile(r'<a\s+[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.I | re.S)
PRICE_RE = re.compile(
    r"(?:US\s?\$|\$|€|£)\s?(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:USD|EUR|GBP)?\s*(?:/|per|a)?\s*(?:user\s*(?:/|per)\s*)?(?:mo\b|month|mth)",
    re.I,
)
SYMBOL_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}
FREE_RE = re.compile(r"\b(free plan|free forever|forever free|free tier|start for free|get started for free|always free|free to use|\$0\b)", re.I)
PROMO_RE = re.compile(r"first month|first \d+ months?|intro|promo|limited[- ]time|trial|discount|save|off\b|was \$|per year|billed (?:annually|yearly)", re.I)
TRIAL_RE = re.compile(r"\b(free trial|\d+[- ]day (?:free )?trial|try (?:it )?free for)\b", re.I)


def meta(page: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for tag in META_RE.findall(page):
        attrs = {m.group(1).lower(): html.unescape(m.group(3) if m.group(3) is not None else m.group(4))
                 for m in ATTR_RE.finditer(tag)}
        key = attrs.get("property") or attrs.get("name")
        if key and "content" in attrs:
            found.setdefault(key.lower(), attrs["content"].strip())
    return found


def text_of(page: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", page)))


def pricing_link(base: str, page: str) -> str | None:
    for href, label in LINK_RE.findall(page):
        if re.search(r"pricing|plans", href, re.I) or re.fullmatch(r"\s*(pricing|plans(?: & pricing)?)\s*", TAG_RE.sub("", label), re.I):
            url = urljoin(base, href.split("#")[0])
            if url.startswith("https://"):
                return url
    return None


def read_pricing(url: str) -> dict | None:
    got = fetch(url)
    if not got:
        return None
    final, page = got
    text = text_of(page)
    prices = []
    for m in PRICE_RE.finditer(text):
        value = float(m.group(1).replace(",", "."))
        around = text[max(0, m.start() - 70): m.end() + 70]
        if 2 <= value <= 5000 and not PROMO_RE.search(around):
            prices.append((value, SYMBOL_CURRENCY.get(re.sub(r"[^$€£]", "", m.group(0))[:1], "USD")))
    out: dict = {"url": final}
    if FREE_RE.search(text):
        out["free"] = True
    if TRIAL_RE.search(text):
        out["trial"] = True
    if prices:
        value, currency = min(prices)
        out["from"], out["currency"] = value, currency
    return out if len(out) > 1 else None


def enrich_one(tool: dict) -> dict:
    result: dict = {"checked": dt.date.today().isoformat()}
    got = fetch(tool["website"])
    if not got:
        return result
    final, page = got
    m = meta(page)
    image = m.get("og:image") or m.get("twitter:image")
    if image:
        image = urljoin(final, image)
        if image.startswith("https://"):
            result["image"] = image
    pricing_url = tool.get("pricing_url") or pricing_link(final, page)
    if pricing_url:
        if p := read_pricing(pricing_url):
            result["pricing"] = p
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--max-age", type=int, default=30)
    ap.add_argument("--slug", nargs="*")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    shards: dict[str, dict] = {}
    for f in OUT.glob("*.json"):
        shards[f.stem] = json.loads(f.read_text())

    today = dt.date.today()
    tools = []
    for path in tool_files():
        data = load(path)
        slug = path.stem
        old = shards.get(shard(slug), {}).get(slug, {})
        age = (today - dt.date.fromisoformat(old["checked"])).days if old.get("checked") else 10**6
        if args.slug and slug not in args.slug:
            continue
        if args.slug or age >= args.max_age:
            tools.append((age, slug, data))
    tools.sort(key=lambda t: (-t[0], t[1]))

    for n, (_, slug, data) in enumerate(tools[: args.limit], 1):
        shards.setdefault(shard(slug), {})[slug] = enrich_one(data)
        if n % 25 == 0:
            print(f"{n}/{min(len(tools), args.limit)} tools", flush=True)
            for k, v in shards.items():
                (OUT / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False, indent=0, sort_keys=True))
    live = {p.stem for p in tool_files()}
    for k, v in shards.items():
        v = {s: e for s, e in v.items() if s in live}
        (OUT / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False, indent=0, sort_keys=True))
    print(f"enriched {min(len(tools), args.limit)} of {len(tools)} due tools")


if __name__ == "__main__":
    main()
