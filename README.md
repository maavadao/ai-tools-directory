# maavaDao AI tools directory

**AI tools, sites and suites, open source or not: what they do, what they cost, and what people think. Free for everyone, part of [maavaDao](https://maavadao.com/directory).**

Browse it at [maavadao.com/directory](https://maavadao.com/directory). The open-source side lives in
[open-source-ai-repos](https://github.com/maavadao/open-source-ai-repos).

## How it works

Every tool is one small [TOML](https://toml.io) file, `tools/<first letter>/<slug>.toml`:

```toml
name = "Notion AI"
description = "Writing, summaries and Q&A built into your Notion workspace."
category = "productivity"
website = "https://www.notion.com/product/ai"
pricing = "freemium"          # free, freemium, paid or contact
starting_price = 10           # per month, cheapest paid plan
pricing_url = "https://www.notion.com/pricing"
pricing_checked = 2026-10-23  # when someone last checked it against that page
added = 2026-10-23
```

Each day a workflow finds new tools, refreshes the data below, and publishes `index.json` to GitHub
Pages at <https://maavadao.github.io/ai-tools-directory/index.json>. The website reads that file.

| What | Where it comes from |
| --- | --- |
| Name, tagline, category | The tool's own site. Tools are found from the project websites listed in [open-source-ai-repos](https://github.com/maavadao/open-source-ai-repos), [Product Hunt's API](https://api.producthunt.com/v2/docs) (which blocks GitHub's servers, so it only works when run from elsewhere), or a member's suggestion. Taglines are the makers' own words or ours, never another directory's text |
| Preview image | The tool's own social preview image (`og:image`), read from its home page |
| Free plan / free trial flags | Whether the tool's own pricing page mentions them, with the date it was read |
| Exact prices | Written into the tool's file by a person from its pricing page (`pricing_url`, `pricing_checked`). We don't scrape prices out of page text, because yearly prices, promos and scripts make that wrong too often |
| Ratings | maavaDao members, 1 to 5 stars, on the website. No scores are copied from review sites |

Pages are read politely: we obey `robots.txt`, identify ourselves, and make one request a second.

## Add a tool

1. `python scripts/add_tool.py https://example.com --category writing` starts a file from the tool's own page.
2. Check it, add the pricing from the tool's pricing page, then `python scripts/validate.py`.
3. Open a pull request. Or just [suggest a tool](../../issues/new?template=suggest-a-tool.yml).

## Makers: fix or remove your listing

[Fix a listing](../../issues/new?template=fix-a-listing.yml) or
[remove it](../../issues/new?template=remove-a-listing.yml). Removed domains go in `removed.toml`
and are never added again.

## Layout

| Path | What |
| --- | --- |
| `tools/` | One file per tool |
| `categories.toml` | The categories |
| `schema/tool.schema.json` | What a tool file may contain |
| `data/enrichment/` | What the daily run read from each tool's own site |
| `removed.toml` | Domains whose makers asked to be removed |
| `scripts/` | `validate`, `add_tool`, `discover`, `enrich`, `build_index` (Python 3.11+) |

## Licence

Apache 2.0. The data is facts and short descriptions; the tools' names and images belong to their makers.
