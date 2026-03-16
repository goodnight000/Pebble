# VC Firm Ingestion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ~40 VC firm content sources to the ingestion pipeline so AIPulse surfaces startup funding, investment theses, and AI market analysis from the top venture capital firms.

**Architecture:** Three tiers of sources map to two existing connectors (`rss`, `sitemap`) plus one small YAML flag (`lastmod_optional`) that already exists. No new connector code is needed — the existing sitemap connector with `lastmod_optional: true` handles sites without lastmod dates. All changes are config-only (YAML entries) except for a validation script.

**Tech Stack:** YAML config (`config_sources.yml`), existing `RSSConnector` and `SitemapConnector`, Python validation script.

---

## Summary of Sources

| Phase | Method | Count | Firms |
|-------|--------|-------|-------|
| 1 | RSS feeds (confirmed working) | 15 | Air Street, Radical, Madrona, Insight Partners, Sequoia, Battery, Menlo, a16z Substack, Tomasz Tunguz, Elad Gil, Nathan Benaich, Y Combinator, Balderton, M12, Obvious |
| 2 | Sitemap with lastmod | 11 | a16z, Greylock, Coatue, GV, Bessemer, Sapphire, NFX, Lightspeed, AI Fund, Norwest, Kleiner Perkins |
| 3 | Sitemap without lastmod (`lastmod_optional: true`) | 9 | General Catalyst, Antler, Lux Capital, Accel, Felicis, Scale VP, Amplify Partners, Emergence Capital, Khosla Ventures |

**Excluded (no usable content source):** Tiger Global, Founders Fund, Innovation Endeavors (no public content); Two Sigma Ventures (no blog in sitemap); 500.co (no blog content in sitemap); IVP (broken sitemap with localhost URLs); Gradient Ventures (no sitemap, uncertain domain); SignalFire, Redpoint main site, NEA, Techstars, Conviction (no sitemap AND no RSS — already have Tomasz Tunguz for Redpoint and these don't justify a new connector). Khosla Vinod Medium and FirstMark Medium feeds were stale/infrequent — replaced with sitemap-based ingestion where available.

---

## Task 1: Add Phase 1 RSS Sources to config_sources.yml

**Files:**
- Modify: `ai_news/app/config_sources.yml` (append after line 3077)

**Step 1: Append the VC Firms RSS section**

Add the following YAML block at the end of the `sources:` list in `config_sources.yml`:

```yaml

  # ============================================================
  # VC FIRMS — RSS FEEDS
  # ============================================================

  - name: "Air Street Capital (Air Street Press)"
    kind: "rss"
    feed_url: "https://press.airstreet.com/feed"
    authority: 0.82
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Radical Ventures"
    kind: "rss"
    feed_url: "https://radical.vc/feed/"
    authority: 0.80
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Madrona Venture Group"
    kind: "rss"
    feed_url: "https://www.madrona.com/feed/"
    authority: 0.78
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Insight Partners"
    kind: "rss"
    feed_url: "https://www.insightpartners.com/feed/"
    authority: 0.80
    always_scrape: false
    priority_poll: false
    enabled: true

  - name: "Sequoia Capital"
    kind: "rss"
    feed_url: "https://sequoiacap.com/feed/"
    authority: 0.88
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Battery Ventures"
    kind: "rss"
    feed_url: "https://www.battery.com/feed/"
    authority: 0.78
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Menlo Ventures"
    kind: "rss"
    feed_url: "https://menlovc.com/feed/"
    authority: 0.78
    always_scrape: false
    priority_poll: false
    enabled: true

  - name: "a16z (Substack)"
    kind: "rss"
    feed_url: "https://www.a16z.news/feed"
    authority: 0.90
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Tomasz Tunguz (Redpoint GP)"
    kind: "rss"
    feed_url: "https://tomtunguz.com/index.xml"
    authority: 0.76
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Elad Gil"
    kind: "rss"
    feed_url: "https://blog.eladgil.com/feed"
    authority: 0.80
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Nathan Benaich (State of AI)"
    kind: "rss"
    feed_url: "https://nathanbenaich.substack.com/feed"
    authority: 0.84
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Y Combinator Blog"
    kind: "rss"
    feed_url: "https://www.ycombinator.com/blog/rss"
    authority: 0.85
    always_scrape: false
    priority_poll: false
    enabled: true

  - name: "Balderton Capital"
    kind: "rss"
    feed_url: "https://www.balderton.com/feed/"
    authority: 0.74
    always_scrape: false
    priority_poll: false
    enabled: true

  - name: "M12 (Microsoft Ventures)"
    kind: "rss"
    feed_url: "https://m12.vc/feed/"
    authority: 0.76
    always_scrape: false
    priority_poll: false
    enabled: true

  - name: "Obvious Ventures"
    kind: "rss"
    feed_url: "https://obvious.com/ideas/feed/"
    authority: 0.72
    always_scrape: false
    priority_poll: false
    enabled: true
```

**Step 2: Verify YAML syntax**

Run:
```bash
cd ai_news && python -c "import yaml; yaml.safe_load(open('app/config_sources.yml'))" && echo "YAML OK"
```
Expected: `YAML OK`

**Step 3: Verify source count increased**

Run:
```bash
cd ai_news && python -c "
import yaml
cfg = yaml.safe_load(open('app/config_sources.yml'))
sources = cfg.get('sources', [])
vc_names = [s['name'] for s in sources if 'Air Street' in s['name'] or 'Radical Ventures' in s['name'] or 'Madrona' in s['name'] or 'Insight Partners' in s['name'] or 'Sequoia Capital' in s['name'] or 'Battery Ventures' in s['name'] or 'Menlo Ventures' in s['name'] or 'a16z' in s['name'] or 'Tunguz' in s['name'] or 'Elad Gil' in s['name'] or 'Nathan Benaich' in s['name'] or 'Y Combinator Blog' in s['name'] or 'Balderton' in s['name'] or 'M12' in s['name'] or 'Obvious' in s['name']]
print(f'Found {len(vc_names)} VC RSS sources')
for n in vc_names:
    print(f'  - {n}')
"
```
Expected: `Found 15 VC RSS sources` with all names listed.

**Step 4: Commit**

```bash
git add ai_news/app/config_sources.yml
git commit -m "feat: add 15 VC firm RSS feed sources for startup/funding coverage"
```

---

## Task 2: Add Phase 2 Sitemap Sources (with lastmod) to config_sources.yml

**Files:**
- Modify: `ai_news/app/config_sources.yml` (append after Task 1 entries)

**Step 1: Append the VC Firms sitemap section (with lastmod)**

Add the following YAML block continuing after the RSS section:

```yaml

  # ============================================================
  # VC FIRMS — SITEMAPS (with lastmod dates)
  # ============================================================

  - name: "a16z Blog"
    kind: "sitemap"
    sitemap_url: "https://a16z.com/sitemap_index.xml"
    # Posts live at root-level slugs; no single path filter works.
    # Use broad path filter that excludes known non-content paths.
    authority: 0.90
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Greylock Partners"
    kind: "sitemap"
    sitemap_url: "https://greylock.com/post-sitemap.xml"
    path_filter: "/greymatter/"
    authority: 0.82
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Coatue Management"
    kind: "sitemap"
    sitemap_url: "https://www.coatue.com/sitemap.xml"
    path_filter: "/blog/"
    authority: 0.80
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "GV (Google Ventures)"
    kind: "sitemap"
    sitemap_url: "https://www.gv.com/sitemap.xml"
    path_filter: "/news/"
    authority: 0.82
    always_scrape: false
    priority_poll: false
    enabled: true

  - name: "Bessemer Venture Partners"
    kind: "sitemap"
    sitemap_url: "https://www.bvp.com/post-sitemap.xml"
    path_filter: "/atlas/"
    authority: 0.82
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Sapphire Ventures"
    kind: "sitemap"
    sitemap_url: "https://sapphireventures.com/blog-sitemap.xml"
    path_filter: "/blog/"
    authority: 0.76
    always_scrape: false
    priority_poll: false
    enabled: true

  - name: "NFX"
    kind: "sitemap"
    sitemap_url: "https://nfx.com/sitemap.xml"
    path_filter: "/post/"
    authority: 0.78
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Lightspeed Venture Partners"
    kind: "sitemap"
    sitemap_url: "https://lsvp.com/post-sitemap.xml"
    path_filter: "/stories/"
    authority: 0.80
    always_scrape: false
    priority_poll: false
    enabled: true

  - name: "AI Fund (Andrew Ng)"
    kind: "sitemap"
    sitemap_url: "https://aifund.ai/post-sitemap.xml"
    path_filter: "/insights/"
    authority: 0.80
    always_scrape: true
    priority_poll: false
    enabled: true

  - name: "Norwest Venture Partners"
    kind: "sitemap"
    sitemap_url: "https://norwest.com/blog-sitemap.xml"
    path_filter: "/blog/"
    authority: 0.74
    always_scrape: false
    priority_poll: false
    enabled: true

  - name: "Kleiner Perkins"
    kind: "sitemap"
    sitemap_url: "https://www.kleinerperkins.com/post-sitemap.xml"
    path_filter: "/perspectives/"
    authority: 0.82
    always_scrape: true
    priority_poll: false
    enabled: true
```

**Step 2: Verify YAML syntax**

Run:
```bash
cd ai_news && python -c "import yaml; yaml.safe_load(open('app/config_sources.yml'))" && echo "YAML OK"
```
Expected: `YAML OK`

**Step 3: Verify sitemap source count**

Run:
```bash
cd ai_news && python -c "
import yaml
cfg = yaml.safe_load(open('app/config_sources.yml'))
sources = cfg.get('sources', [])
vc_sitemap = [s['name'] for s in sources if s.get('kind') == 'sitemap' and any(kw in s['name'] for kw in ['a16z Blog', 'Greylock', 'Coatue', 'GV (', 'Bessemer', 'Sapphire', 'NFX', 'Lightspeed', 'AI Fund', 'Norwest', 'Kleiner'])]
print(f'Found {len(vc_sitemap)} VC sitemap-with-lastmod sources')
for n in vc_sitemap:
    print(f'  - {n}')
"
```
Expected: `Found 11 VC sitemap-with-lastmod sources`

**Step 4: Commit**

```bash
git add ai_news/app/config_sources.yml
git commit -m "feat: add 11 VC firm sitemap sources (with lastmod) for startup coverage"
```

---

## Task 3: Add Phase 3 Sitemap Sources (without lastmod, using lastmod_optional)

**Files:**
- Modify: `ai_news/app/config_sources.yml` (append after Task 2 entries)

**Context:** The existing `SitemapConnector` already supports `lastmod_optional: true` — when set, it accepts URLs without lastmod dates (capped at 200 per poll to prevent flooding). The `lastmod_optional` flag is read from the YAML config in `_get_yaml_flags()` in `pipeline.py` and passed to the `SitemapConnector` constructor. This is already used by existing sources in the codebase.

**Step 1: Append the VC Firms sitemap section (without lastmod)**

```yaml

  # ============================================================
  # VC FIRMS — SITEMAPS (no lastmod, uses lastmod_optional)
  # ============================================================

  - name: "General Catalyst"
    kind: "sitemap"
    sitemap_url: "https://www.generalcatalyst.com/sitemap.xml"
    path_filter: "/stories/"
    authority: 0.82
    always_scrape: true
    priority_poll: false
    enabled: true
    lastmod_optional: true

  - name: "Antler"
    kind: "sitemap"
    sitemap_url: "https://www.antler.co/sitemap.xml"
    path_filter: "/blog/"
    authority: 0.72
    always_scrape: false
    priority_poll: false
    enabled: true
    lastmod_optional: true

  - name: "Lux Capital"
    kind: "sitemap"
    sitemap_url: "https://www.luxcapital.com/sitemap.xml"
    path_filter: "/content/"
    authority: 0.78
    always_scrape: true
    priority_poll: false
    enabled: true
    lastmod_optional: true

  - name: "Accel"
    kind: "sitemap"
    sitemap_url: "https://www.accel.com/sitemap.xml"
    path_filter: "/noteworthies/"
    authority: 0.82
    always_scrape: true
    priority_poll: false
    enabled: true
    lastmod_optional: true

  - name: "Felicis Ventures"
    kind: "sitemap"
    sitemap_url: "https://www.felicis.com/sitemap.xml"
    path_filter: "/insight/"
    authority: 0.76
    always_scrape: false
    priority_poll: false
    enabled: true
    lastmod_optional: true

  - name: "Scale Venture Partners"
    kind: "sitemap"
    sitemap_url: "https://www.scalevp.com/sitemap.xml"
    path_filter: "/blog/"
    authority: 0.74
    always_scrape: false
    priority_poll: false
    enabled: true
    lastmod_optional: true

  - name: "Amplify Partners"
    kind: "sitemap"
    sitemap_url: "https://www.amplifypartners.com/sitemap.xml"
    path_filter: "/blog-posts/"
    authority: 0.76
    always_scrape: true
    priority_poll: false
    enabled: true
    lastmod_optional: true

  - name: "Emergence Capital"
    kind: "sitemap"
    sitemap_url: "https://www.emcap.com/sitemap.xml"
    path_filter: "/thoughts/"
    authority: 0.76
    always_scrape: true
    priority_poll: false
    enabled: true
    lastmod_optional: true

  - name: "Khosla Ventures"
    kind: "sitemap"
    sitemap_url: "https://www.khoslaventures.com/sitemap.xml"
    path_filter: "/posts/"
    authority: 0.80
    always_scrape: true
    priority_poll: false
    enabled: true
    lastmod_optional: true
```

**Step 2: Verify YAML syntax**

Run:
```bash
cd ai_news && python -c "import yaml; yaml.safe_load(open('app/config_sources.yml'))" && echo "YAML OK"
```
Expected: `YAML OK`

**Step 3: Verify all VC sources are present**

Run:
```bash
cd ai_news && python -c "
import yaml
cfg = yaml.safe_load(open('app/config_sources.yml'))
sources = cfg.get('sources', [])
vc_all = [s for s in sources if any(kw in s['name'] for kw in [
    'Air Street', 'Radical Ventures', 'Madrona', 'Insight Partners',
    'Sequoia Capital', 'Battery Ventures', 'Menlo Ventures', 'a16z',
    'Tunguz', 'Elad Gil', 'Nathan Benaich', 'Y Combinator Blog',
    'Balderton', 'M12', 'Obvious', 'Greylock', 'Coatue', 'GV (',
    'Bessemer', 'Sapphire', 'NFX', 'Lightspeed', 'AI Fund', 'Norwest',
    'Kleiner', 'General Catalyst', 'Antler', 'Lux Capital', 'Accel',
    'Felicis', 'Scale Venture', 'Amplify', 'Emergence', 'Khosla',
])]
rss = [s for s in vc_all if s['kind'] == 'rss']
sitemap = [s for s in vc_all if s['kind'] == 'sitemap']
print(f'Total VC sources: {len(vc_all)} (RSS: {len(rss)}, Sitemap: {len(sitemap)})')
for s in vc_all:
    lm = ' [lastmod_optional]' if s.get('lastmod_optional') else ''
    print(f'  [{s[\"kind\"]:7s}] {s[\"name\"]}{lm}')
"
```
Expected: `Total VC sources: 35 (RSS: 15, Sitemap: 20)`

**Step 4: Commit**

```bash
git add ai_news/app/config_sources.yml
git commit -m "feat: add 9 VC firm sitemap sources (lastmod_optional) for startup coverage"
```

---

## Task 4: Write and Run Feed Validation Script

**Files:**
- Create: `scripts/validate-vc-feeds.py`

**Purpose:** Hit every new VC source's feed/sitemap URL and confirm it returns valid content (not 404, not HTML, not empty). This catches dead URLs before they hit production.

**Step 1: Write the validation script**

```python
"""Validate all VC firm feed and sitemap URLs are reachable and return valid content."""
from __future__ import annotations

import sys
import yaml
import httpx
import feedparser
from lxml import etree
from pathlib import Path

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}

VC_KEYWORDS = [
    "Air Street", "Radical Ventures", "Madrona", "Insight Partners",
    "Sequoia Capital", "Battery Ventures", "Menlo Ventures", "a16z",
    "Tunguz", "Elad Gil", "Nathan Benaich", "Y Combinator Blog",
    "Balderton", "M12", "Obvious", "Greylock", "Coatue", "GV (",
    "Bessemer", "Sapphire", "NFX", "Lightspeed", "AI Fund", "Norwest",
    "Kleiner", "General Catalyst", "Antler", "Lux Capital", "Accel",
    "Felicis", "Scale Venture", "Amplify", "Emergence", "Khosla",
]


def is_vc_source(name: str) -> bool:
    return any(kw in name for kw in VC_KEYWORDS)


def validate_rss(name: str, url: str) -> tuple[bool, str]:
    try:
        resp = httpx.get(url, headers=BROWSER_HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        n_entries = len(parsed.entries)
        if n_entries == 0 and not parsed.feed.get("title"):
            return False, f"No entries and no feed title — likely not a valid feed"
        return True, f"OK — {n_entries} entries, feed title: {parsed.feed.get('title', 'N/A')}"
    except httpx.HTTPStatusError as e:
        return False, f"HTTP {e.response.status_code}"
    except Exception as e:
        return False, f"Error: {e}"


def validate_sitemap(name: str, url: str, path_filter: str | None) -> tuple[bool, str]:
    try:
        headers = {**BROWSER_HEADERS, "Accept": "application/xml, text/xml, */*"}
        resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "html" in content_type and "xml" not in content_type:
            return False, f"Returns HTML, not XML (content-type: {content_type})"
        root = etree.fromstring(resp.content)
        tag = etree.QName(root).localname.lower()
        if tag == "sitemapindex":
            child_locs = root.xpath(".//*[local-name()='sitemap']/*[local-name()='loc']/text()")
            return True, f"OK — sitemap index with {len(child_locs)} child sitemaps"
        url_elems = root.xpath(".//*[local-name()='url']")
        if path_filter:
            matching = [u for u in url_elems
                        if any(path_filter in (loc.text or "")
                               for loc in u.xpath("./*[local-name()='loc']"))]
            return True, f"OK — {len(url_elems)} total URLs, {len(matching)} match path_filter '{path_filter}'"
        return True, f"OK — {len(url_elems)} URLs"
    except httpx.HTTPStatusError as e:
        return False, f"HTTP {e.response.status_code}"
    except etree.XMLSyntaxError as e:
        return False, f"XML parse error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def main():
    config_path = Path(__file__).resolve().parent.parent / "ai_news" / "app" / "config_sources.yml"
    cfg = yaml.safe_load(config_path.open())
    sources = cfg.get("sources", [])

    vc_sources = [s for s in sources if is_vc_source(s["name"])]
    print(f"\nValidating {len(vc_sources)} VC sources...\n")

    failures = []
    for src in vc_sources:
        name = src["name"]
        kind = src["kind"]
        url = src.get("feed_url") or src.get("sitemap_url", "")

        if kind == "rss":
            ok, msg = validate_rss(name, url)
        elif kind == "sitemap":
            path_filter = src.get("path_filter")
            ok, msg = validate_sitemap(name, url, path_filter)
        else:
            ok, msg = False, f"Unknown kind: {kind}"

        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name} ({kind})")
        print(f"         {url}")
        print(f"         {msg}")
        print()
        if not ok:
            failures.append(name)

    print(f"\n{'='*60}")
    print(f"Results: {len(vc_sources) - len(failures)}/{len(vc_sources)} passed")
    if failures:
        print(f"\nFailed sources:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All VC sources validated successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

**Step 2: Run the validation script**

Run:
```bash
cd ai_news && .venv/bin/python ../scripts/validate-vc-feeds.py
```
Expected: All 35 sources pass. If any fail, proceed to Task 5 to fix them.

**Step 3: Commit**

```bash
git add scripts/validate-vc-feeds.py
git commit -m "feat: add validation script for VC firm feed/sitemap URLs"
```

---

## Task 5: Fix Any Failing Sources

**Files:**
- Modify: `ai_news/app/config_sources.yml` (fix broken URLs)

**Step 1: For each failing source from Task 4, investigate and fix**

Common fixes:
- **404 on sitemap URL**: Try alternative sitemap paths (`/sitemap_index.xml`, `/wp-sitemap.xml`, `/post-sitemap.xml`). If all fail, set `enabled: false` with a comment explaining why.
- **HTML instead of XML**: The site may require `browser_ua: true` for TLS fingerprint bypass. Add that flag.
- **0 entries in RSS**: The feed may be behind Cloudflare. Add `browser_ua: true`.
- **Wrong path_filter**: Adjust based on actual sitemap content.

For each fix, update the YAML entry and re-run:
```bash
cd ai_news && .venv/bin/python ../scripts/validate-vc-feeds.py
```

**Step 2: Disable any truly unreachable sources**

If a source consistently fails after trying alternatives, disable it:
```yaml
    enabled: false  # URL returns 404; no alternative found 2026-03-14
```

**Step 3: Re-run validation until all enabled sources pass**

```bash
cd ai_news && .venv/bin/python ../scripts/validate-vc-feeds.py
```
Expected: All enabled sources pass.

**Step 4: Commit**

```bash
git add ai_news/app/config_sources.yml
git commit -m "fix: resolve failing VC feed/sitemap URLs after validation"
```

---

## Task 6: Verify Seed and Pipeline Integration

**Files:**
- No new files — verify existing code handles the new sources

**Step 1: Verify seed_sources loads the new entries**

Run:
```bash
cd ai_news && .venv/bin/python -c "
from app.config import load_source_config
cfg = load_source_config()
sources = cfg.get('sources', [])
vc = [s for s in sources if any(kw in s['name'] for kw in ['Air Street', 'Radical Ventures', 'Madrona', 'Sequoia Capital', 'a16z', 'Greylock', 'General Catalyst'])]
print(f'load_source_config finds {len(vc)} sample VC sources (out of 35 total)')
for s in vc:
    sitemap_url = s.get('sitemap_url', '')
    feed_url = s.get('feed_url', '')
    print(f'  {s[\"name\"]} -> kind={s[\"kind\"]}, feed_url={feed_url}, sitemap_url={sitemap_url}')
"
```
Expected: Shows 7+ VC sources with correct URLs and kinds.

**Step 2: Verify _connector_for_source handles all source kinds**

The new sources use only `rss` and `sitemap` kinds, which are already handled in `_connector_for_source()` at `ai_news/app/tasks/pipeline.py:453-481`. No changes needed.

Verify:
```bash
cd ai_news && .venv/bin/python -c "
from app.config import load_source_config
cfg = load_source_config()
sources = cfg.get('sources', [])
kinds = set(s['kind'] for s in sources)
print(f'All source kinds in config: {sorted(kinds)}')
assert 'rss' in kinds
assert 'sitemap' in kinds
print('OK — rss and sitemap both present and handled by pipeline')
"
```

**Step 3: Verify seed_sources would correctly persist sitemap sources**

The `seed_sources()` function at `ai_news/app/scripts/seed_sources.py:18-41` maps `sitemap_url` -> `feed_url` and `path_filter` -> `base_url` for sitemap sources. Verify:
```bash
cd ai_news && .venv/bin/python -c "
from app.config import load_source_config
cfg = load_source_config()
sources = cfg.get('sources', [])
# Simulate what seed_sources does for sitemap entries
for s in sources:
    if s.get('kind') == 'sitemap' and 'Greylock' in s.get('name', ''):
        feed_url = s.get('feed_url') or s.get('sitemap_url')
        base_url = s.get('base_url') or s.get('path_filter')
        print(f'{s[\"name\"]}:')
        print(f'  feed_url (sitemap_url) = {feed_url}')
        print(f'  base_url (path_filter) = {base_url}')
        print(f'  lastmod_optional = {s.get(\"lastmod_optional\", False)}')
        break
"
```
Expected: Shows Greylock with `feed_url = https://greylock.com/post-sitemap.xml` and `base_url = /greymatter/`.

**Step 4: Verify _get_yaml_flags reads lastmod_optional**

The `_get_yaml_flags()` function reads per-source flags from the YAML config. The `lastmod_optional` flag is already supported. Verify:
```bash
cd ai_news && grep -n "lastmod_optional" app/tasks/pipeline.py
```
Expected: Shows the line where `lastmod_optional` is extracted from flags.

**Step 5: Commit (no changes expected — this is verification only)**

If no fixes were needed, skip this commit. If any issues were found and fixed, commit them:
```bash
git add -A && git commit -m "fix: address integration issues found during VC source verification"
```

---

## Task 7: End-to-End Smoke Test

**Files:**
- No changes — run the app and verify no errors

**Step 1: Start the backend**

Run:
```bash
npm run dev:ai
```

Wait for startup to complete (seeds sources, runs migrations).

**Step 2: Check logs for errors**

Look for:
- No `KeyError` or `ValueError` during source seeding
- No unhandled exceptions related to the new VC sources
- Sources successfully seeded: look for the seed_sources log output

**Step 3: Trigger a pipeline run and watch for errors**

In a separate terminal:
```bash
cd ai_news && .venv/bin/python -c "
from app.tasks.pipeline import run_ingest
run_ingest()
"
```

Watch the output for:
- `[pipeline] source fetch failed: <VC source name>` — indicates a feed fetch error
- Any 404s, connection errors, or XML parse errors

**Step 4: If errors occur, fix the source config and re-run**

Common runtime issues:
- Cloudflare blocking: Add `browser_ua: true` to the source YAML
- SSL errors: May need `browser_ua: true` for curl_cffi TLS fingerprinting
- Timeout: Increase timeout or check if the site is down temporarily

**Step 5: Verify articles are being ingested**

```bash
cd ai_news && .venv/bin/python -c "
from app.db import session_scope
from app.models import Source, RawItem
with session_scope() as session:
    vc_sources = session.query(Source).filter(Source.name.like('%Sequoia%') | Source.name.like('%a16z%') | Source.name.like('%Madrona%')).all()
    for src in vc_sources:
        count = session.query(RawItem).filter(RawItem.source_id == src.id).count()
        print(f'{src.name}: {count} raw items')
"
```
Expected: At least some sources show >0 raw items after a pipeline run.

**Step 6: Final commit if any fixes were made**

```bash
git add -A && git commit -m "fix: resolve runtime issues with VC source ingestion"
```

---

## Task 8: Clean Up Validation Script (optional)

**Files:**
- Delete or move: `scripts/validate-vc-feeds.py` (if not wanted in the repo long-term)

**Step 1: Decide on keeping the script**

The validation script is useful for future source additions. If keeping:
```bash
git add scripts/validate-vc-feeds.py
git commit -m "chore: keep VC feed validation script for future source additions"
```

If removing:
```bash
rm scripts/validate-vc-feeds.py
git add -A && git commit -m "chore: remove one-time VC feed validation script"
```

---

## Appendix: Complete Source Reference

### Phase 1 — RSS (15 sources)

| # | Name | Feed URL | Authority |
|---|------|----------|-----------|
| 1 | Air Street Capital | `press.airstreet.com/feed` | 0.82 |
| 2 | Radical Ventures | `radical.vc/feed/` | 0.80 |
| 3 | Madrona Venture Group | `madrona.com/feed/` | 0.78 |
| 4 | Insight Partners | `insightpartners.com/feed/` | 0.80 |
| 5 | Sequoia Capital | `sequoiacap.com/feed/` | 0.88 |
| 6 | Battery Ventures | `battery.com/feed/` | 0.78 |
| 7 | Menlo Ventures | `menlovc.com/feed/` | 0.78 |
| 8 | a16z (Substack) | `a16z.news/feed` | 0.90 |
| 9 | Tomasz Tunguz | `tomtunguz.com/index.xml` | 0.76 |
| 10 | Elad Gil | `blog.eladgil.com/feed` | 0.80 |
| 11 | Nathan Benaich | `nathanbenaich.substack.com/feed` | 0.84 |
| 12 | Y Combinator Blog | `ycombinator.com/blog/rss` | 0.85 |
| 13 | Balderton Capital | `balderton.com/feed/` | 0.74 |
| 14 | M12 (Microsoft) | `m12.vc/feed/` | 0.76 |
| 15 | Obvious Ventures | `obvious.com/ideas/feed/` | 0.72 |

### Phase 2 — Sitemap with lastmod (11 sources)

| # | Name | Sitemap URL | Path Filter | Authority |
|---|------|-------------|-------------|-----------|
| 1 | a16z Blog | `a16z.com/sitemap_index.xml` | (none — root slugs) | 0.90 |
| 2 | Greylock Partners | `greylock.com/post-sitemap.xml` | `/greymatter/` | 0.82 |
| 3 | Coatue Management | `coatue.com/sitemap.xml` | `/blog/` | 0.80 |
| 4 | GV (Google Ventures) | `gv.com/sitemap.xml` | `/news/` | 0.82 |
| 5 | Bessemer VP | `bvp.com/post-sitemap.xml` | `/atlas/` | 0.82 |
| 6 | Sapphire Ventures | `sapphireventures.com/blog-sitemap.xml` | `/blog/` | 0.76 |
| 7 | NFX | `nfx.com/sitemap.xml` | `/post/` | 0.78 |
| 8 | Lightspeed VP | `lsvp.com/post-sitemap.xml` | `/stories/` | 0.80 |
| 9 | AI Fund | `aifund.ai/post-sitemap.xml` | `/insights/` | 0.80 |
| 10 | Norwest VP | `norwest.com/blog-sitemap.xml` | `/blog/` | 0.74 |
| 11 | Kleiner Perkins | `kleinerperkins.com/post-sitemap.xml` | `/perspectives/` | 0.82 |

### Phase 3 — Sitemap without lastmod (9 sources)

| # | Name | Sitemap URL | Path Filter | Authority |
|---|------|-------------|-------------|-----------|
| 1 | General Catalyst | `generalcatalyst.com/sitemap.xml` | `/stories/` | 0.82 |
| 2 | Antler | `antler.co/sitemap.xml` | `/blog/` | 0.72 |
| 3 | Lux Capital | `luxcapital.com/sitemap.xml` | `/content/` | 0.78 |
| 4 | Accel | `accel.com/sitemap.xml` | `/noteworthies/` | 0.82 |
| 5 | Felicis Ventures | `felicis.com/sitemap.xml` | `/insight/` | 0.76 |
| 6 | Scale VP | `scalevp.com/sitemap.xml` | `/blog/` | 0.74 |
| 7 | Amplify Partners | `amplifypartners.com/sitemap.xml` | `/blog-posts/` | 0.76 |
| 8 | Emergence Capital | `emcap.com/sitemap.xml` | `/thoughts/` | 0.76 |
| 9 | Khosla Ventures | `khoslaventures.com/sitemap.xml` | `/posts/` | 0.80 |

### Excluded (with reasons)

| Firm | Reason |
|------|--------|
| Tiger Global | No public content |
| Founders Fund | No public blog |
| Innovation Endeavors | Minimal public content |
| Two Sigma Ventures | Sitemap has no blog content |
| 500.co | Sitemap has only program pages, no blog |
| IVP | Broken sitemap (localhost URLs) |
| Gradient Ventures | No sitemap, uncertain domain |
| SignalFire | No sitemap, no RSS |
| NEA | No sitemap, no RSS |
| Techstars | No sitemap, no RSS |
| Conviction | No sitemap, no RSS |
| Redpoint (main site) | No sitemap (covered by Tomasz Tunguz RSS) |
| Vinod Khosla (Medium) | Stale (covered by Khosla Ventures sitemap) |
| FirstMark (Medium) | Sporadic (not enough volume to justify) |
| Spark Capital (Medium) | Very infrequent, mostly fund announcements |
