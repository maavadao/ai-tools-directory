"""Find new AI tools from public APIs and write a tool file for each.

Usage: python scripts/discover.py [--max-new 100] [--source producthunt hf] [--dry-run]

Sources:
  hf           Hugging Face Spaces with the most likes (public API, no key). Off by default: most
               Spaces are open demos and leaderboards, not products with pricing.
  producthunt  Product Hunt's most-voted launches in the "artificial intelligence" topic.
               Needs PRODUCT_HUNT_TOKEN (a free developer token); skipped without one.
Only facts are taken: the name, the web address, a short tagline the makers wrote, and the
category (guessed from tags, "other" when unsure). Tools already listed (by domain or Space) and
domains in removed.toml are skipped. Pricing and preview images come later from enrich.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import time
import urllib.parse
import urllib.request

from add_tool import title_of
from directory import SLUG_RE, dumps, domain, load, path_for, removed_domains, tool_files
from enrich import meta
from web import USER_AGENT, fetch

# Hosts that are platforms, not a tool's own site: a launch that points here isn't listed.
# (Code repositories belong in open-source-ai-repos.)
NOT_A_TOOL_SITE = {
    "github.com", "gitlab.com", "huggingface.co", "producthunt.com", "x.com", "twitter.com", "youtube.com",
    "youtu.be", "linkedin.com", "medium.com", "substack.com", "reddit.com", "apps.apple.com", "play.google.com",
    "chromewebstore.google.com", "chrome.google.com", "addons.mozilla.org", "notion.site", "vercel.app",
    "netlify.app", "github.io", "pages.dev", "web.app", "framer.website", "framer.ai", "typedream.site",
}

CATEGORY_WORDS = [
    ("image", {"image", "text-to-image", "diffusion", "photo", "upscale", "avatar", "art", "stable-diffusion", "logo"}),
    ("video", {"video", "text-to-video", "animation"}),
    ("audio", {"audio", "speech", "voice", "tts", "music", "text-to-speech", "transcription", "whisper"}),
    ("coding", {"code", "coding", "developer", "programming", "github", "devtools", "developer-tools"}),
    ("writing", {"writing", "copywriting", "seo", "content", "writer"}),
    ("chatbots", {"chatbot", "chat", "assistant", "llm", "conversational"}),
    ("research", {"research", "search", "papers", "science"}),
    ("data", {"data", "analytics", "spreadsheet", "dataset", "data-science"}),
    ("education", {"education", "learning", "tutor", "students", "teachers"}),
    ("productivity", {"productivity", "notes", "meetings", "email", "calendar", "task-management"}),
    ("sales-marketing", {"sales", "marketing", "social-media", "advertising", "lead-generation", "crm"}),
    ("customer-support", {"customer-support", "customer-service", "helpdesk"}),
    ("design", {"design", "presentation", "slides", "ui", "branding"}),
    ("agents", {"agents", "agent", "automation", "workflow", "no-code"}),
    ("healthcare", {"health", "healthcare", "fitness", "mental-health", "medical"}),
    ("legal-finance", {"legal", "finance", "accounting", "investing", "fintech"}),
    ("hr", {"hr", "recruiting", "hiring", "interview"}),
    ("developer-platforms", {"api", "infrastructure", "mlops", "hosting", "platform"}),
]


def guess_category(words: list[str]) -> str:
    have = {re.sub(r"[^a-z0-9]+", "-", w.lower()).strip("-") for w in words}
    for category, wanted in CATEGORY_WORDS:
        if have & wanted:
            return category
    return "other"


def clean(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def get_json(url: str, data: bytes | None = None, headers: dict | None = None):
    last: Exception | None = None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except Exception as exc:  # noqa: BLE001 - retry transient errors
            last = exc
            time.sleep(2 ** attempt)
    print(f"request failed: {url.split('?')[0]}: {last}")
    return None


def hf_spaces(pages: int = 10) -> list[dict]:
    out = []
    for page in range(pages):
        items = get_json(f"https://huggingface.co/api/spaces?sort=likes&direction=-1&limit=100&full=true&skip={page * 100}")
        if not items:
            break
        for s in items:
            card = s.get("cardData") or {}
            desc = card.get("short_description") or ""
            if s.get("likes", 0) < 300 or len(desc) < 10 or s.get("private"):
                continue
            out.append({
                "name": clean(card.get("title") or s["id"].split("/")[-1], 80),
                "description": clean(desc, 300),
                "website": f"https://huggingface.co/spaces/{s['id']}",
                "words": list(s.get("tags", [])) + [card.get("sdk", "")],
                "score": s.get("likes", 0),
                "slug_hint": s["id"].split("/")[-1],
            })
        time.sleep(1)
    return out


def product_hunt(tok: str, pages: int = 10) -> list[dict]:
    out, cursor = [], None
    query = """query($after: String) { posts(order: VOTES, topic: "artificial-intelligence", first: 20, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node { name tagline website votesCount topics { edges { node { name } } } } } } }"""
    for _ in range(pages):
        res = get_json("https://api.producthunt.com/v2/api/graphql",
                       json.dumps({"query": query, "variables": {"after": cursor}}).encode(),
                       {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        posts = ((res or {}).get("data") or {}).get("posts")
        if not posts:
            break
        for e in posts["edges"]:
            n = e["node"]
            if len(n.get("tagline") or "") < 10 or n.get("votesCount", 0) < 100:
                continue
            site = resolve(n["website"])
            if site:
                out.append({
                    "name": clean(n["name"], 80), "description": clean(n["tagline"], 300), "website": site,
                    "words": [t["node"]["name"] for t in n["topics"]["edges"]], "score": n["votesCount"],
                    "slug_hint": n["name"],
                })
        if not posts["pageInfo"]["hasNextPage"]:
            break
        cursor = posts["pageInfo"]["endCursor"]
        time.sleep(1)
    return out


def resolve(url: str) -> str | None:
    """Follow Product Hunt's redirect to the tool's own site, dropping tracking parameters."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
        with urllib.request.urlopen(req, timeout=20) as resp:
            final = resp.geturl()
    except Exception:  # noqa: BLE001
        return None
    p = urllib.parse.urlsplit(final)
    if p.scheme != "https" or "producthunt.com" in p.netloc:
        return None
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path.rstrip("/"), "", ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-new", type=int, default=100)
    ap.add_argument("--source", nargs="+", default=["producthunt"], choices=["hf", "producthunt"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    found: list[dict] = []
    if "hf" in args.source:
        found += hf_spaces()
    if "producthunt" in args.source:
        if tok := os.environ.get("PRODUCT_HUNT_TOKEN"):
            found += product_hunt(tok)
        else:
            print("PRODUCT_HUNT_TOKEN not set; skipping Product Hunt")

    removed = removed_domains()
    hosts: set[str] = set()
    slugs = set()
    for path in tool_files():
        hosts.add(domain(load(path)["website"]))
        slugs.add(path.stem)
    today = dt.date.today()
    found.sort(key=lambda t: -t["score"])
    written = 0
    for t in found:
        if written >= args.max_new:
            break
        host = domain(t["website"])
        # A launch is often a feature or a blog post: list the product's own site, once.
        if not host or host in hosts or host in removed or any(host == h or host.endswith("." + h) for h in NOT_A_TOOL_SITE):
            continue
        hosts.add(host)
        site = f"https://{urllib.parse.urlsplit(t['website']).netloc}"
        got = fetch(site)  # polite: obeys robots.txt; unreadable sites are skipped
        if not got:
            continue
        final, page = got
        if domain(final) in hosts and domain(final) != host:  # redirected to a tool we already list
            continue
        hosts.add(domain(final))
        m = meta(page)
        # The site's own name and description, as for the seed tools; Product Hunt's tagline is the fallback.
        name = title_of(page, m, host)
        if name == host.split(".")[0].title() and len(t["name"].split()) <= 3:
            name = t["name"]
        desc = clean(m.get("og:description") or m.get("description") or t["description"], 300)
        if len(desc) < 10:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64].strip("-")
        if not SLUG_RE.match(slug or "") or slug in slugs:
            slug = re.sub(r"[^a-z0-9]+", "-", host).strip("-")[:64].strip("-")
        if not SLUG_RE.match(slug or "") or slug in slugs:
            continue
        slugs.add(slug)
        written += 1
        data = {"name": name, "description": desc, "category": guess_category(t["words"]),
                "website": f"https://{urllib.parse.urlsplit(final).netloc}", "added": today}
        if args.dry_run:
            print(f"would add {slug} ({data['category']}, score {t['score']}) {data['website']}")
            continue
        path = path_for(slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(data))
    print(f"found {len(found)} candidates; {'would write' if args.dry_run else 'wrote'} {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
