"""Check every tool file against the schema and the directory rules. Exits non-zero on any problem.

Usage: python scripts/validate.py [FILE ...]   (no arguments checks every tool file)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from directory import ROOT, SLUG_RE, TOOLS, categories, domain, load, removed_domains, shard, tool_files

HINTS = {
    "website": 'must be a full link starting with "https://"',
    "pricing_url": 'must be a full link starting with "https://"',
    "tags": 'tags are lowercase words joined by hyphens, like "speech-to-text"',
    "added": "must be a date written as YYYY-MM-DD, like 2026-10-23",
    "pricing_checked": "must be a date written as YYYY-MM-DD, like 2026-10-23",
}


def message(err) -> str:
    field = str(err.path[0]) if err.path else ""
    if err.validator in ("pattern", "format") and field in HINTS:
        return HINTS[field]
    return err.message


def main(argv: list[str]) -> int:
    schema = json.loads((ROOT / "schema" / "tool.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    cats = categories()
    removed = removed_domains()
    problems: list[str] = []
    sites: dict[str, str] = {}
    today = dt.date.today().isoformat()

    for p in TOOLS.rglob("*"):
        if p.is_file() and (p.suffix != ".toml" or p.parent.parent != TOOLS):
            problems.append(f"{p.relative_to(ROOT)}: files go in tools/<first character>/<slug>.toml")

    files = list(tool_files())
    only = {Path(a).resolve() for a in argv}
    for path in files:
        rel = path.relative_to(ROOT)
        slug = path.stem
        report = not only or path.resolve() in only
        try:
            data = load(path)
        except Exception as exc:  # noqa: BLE001 - report any TOML error
            problems.append(f"{rel}: not valid TOML ({exc})")
            continue

        site = domain(str(data.get("website") or ""))
        path_key = f"{site}{(data.get('website') or '').split(site, 1)[-1].rstrip('/')}" if site else ""
        if path_key:
            if path_key in sites and report:
                problems.append(f"{rel}: {data['website']} is already listed in {sites[path_key]}")
            sites.setdefault(path_key, str(rel))
        if not report:
            continue
        if site in removed:
            problems.append(f"{rel}: {site} asked to be removed (removed.toml)")
        if not SLUG_RE.match(slug):
            problems.append(f"{rel}: file name must be lowercase letters, digits and hyphens")
        elif path.parent.name != shard(slug):
            problems.append(f"{rel}: move it to tools/{shard(slug)}/{slug}.toml")
        for key in ("added", "pricing_checked"):
            if isinstance(data.get(key), dt.date):
                data[key] = data[key].isoformat()
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            where = "/".join(str(p) for p in err.path) or "(top)"
            problems.append(f"{rel}: {where}: {message(err)}")
        if data.get("category") not in cats:
            problems.append(f"{rel}: category must be one of the ids in categories.toml: {', '.join(cats)}")
        for key in ("added", "pricing_checked"):
            if isinstance(data.get(key), str) and data[key] > today:
                problems.append(f"{rel}: {key} is in the future")
        if data.get("pricing") in ("free", "contact") and "starting_price" in data:
            problems.append(f"{rel}: a {data['pricing']} tool has no starting_price")
        if "starting_price" in data and "pricing_url" not in data:
            problems.append(f"{rel}: starting_price needs pricing_url, the page the price was read on")

    for p in problems:
        print(p)
    print(f"{len(only) or len(files)} tool(s) checked, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
