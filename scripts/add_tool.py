"""Start a new tool file from the tool's own home page.

Usage: python scripts/add_tool.py https://example.com [--category writing] [--slug example]

Reads the page title and description the tool's makers wrote (obeying robots.txt), writes
tools/<x>/<slug>.toml, and leaves pricing for enrich.py or a human. Check the file, rewrite the
description if it isn't clear, then open a pull request.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re

from directory import SLUG_RE, categories, dumps, domain, load, path_for, removed_domains, tool_files
from enrich import meta
from web import fetch


def clean(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def title_of(page: str, m: dict[str, str], host: str) -> str:
    raw = m.get("og:site_name") or ""
    if not raw:
        t = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        raw = re.split(r"\s[|\-–—:·]\s", re.sub(r"\s+", " ", t.group(1)).strip())[0] if t else ""
    # A slogan rather than a name: fall back to the domain.
    if not raw or len(raw.split()) > 4:
        raw = host.split(".")[0].title()
    return clean(raw, 80)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--category", default="other")
    ap.add_argument("--slug")
    args = ap.parse_args()

    if args.category not in categories():
        print(f"category must be one of: {', '.join(categories())}")
        return 1
    if not args.url.startswith("https://"):
        print("give the tool's home page, like https://example.com")
        return 1
    host = domain(args.url)
    if host in removed_domains():
        print(f"{host} asked to be removed from the directory")
        return 1
    for existing in tool_files():
        if domain(str(load(existing).get("website", ""))) == host:
            print(f"{host} is already listed in {existing}")
            return 1
    got = fetch(args.url)
    if not got:
        print("couldn't read that page (down, not HTML, or its robots.txt says no bots)")
        return 1
    final, page = got
    m = meta(page)
    desc = clean(m.get("og:description") or m.get("description") or "", 300)
    if len(desc) < 10:
        print("the page has no description; write the file by hand from templates/tool.toml")
        return 1
    name = title_of(page, m, host)
    slug = args.slug or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not SLUG_RE.match(slug) or path_for(slug).exists():
        slug = re.sub(r"[^a-z0-9]+", "-", host).strip("-")
    path = path_for(slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps({"name": name, "description": desc, "category": args.category,
                           "website": final.split("?")[0].rstrip("/") if final.count("/") <= 3 else final.split("?")[0],
                           "added": dt.date.today()}))
    print(f"wrote {path}. Check it, then run: python scripts/validate.py {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
