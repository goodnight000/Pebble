#!/usr/bin/env python3
"""
Google News RSS proxy fallback for disabled sources.

Reads config_sources.yml, finds disabled sources, attempts to build
Google News RSS proxy URLs for them, validates that the proxy returns
actual RSS items, and updates the config file for recovered sources.
"""

import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai_news" / "app" / "config_sources.yml"

# Sources that are truly defunct / acquired — skip entirely
SKIP_NAME_FRAGMENTS = [
    "Neptune AI",
    "Greentech Media",
    "Data Science Central",
    "Determined AI",
    "Gradient AI",
]

# Social media kinds — not recoverable via Google News
SKIP_KINDS = {"mastodon", "bluesky", "twitter"}

# Sources disabled for non-feed reasons (e.g. Cloudflare blocks on scraping)
SKIP_NAMES_EXACT = [
    "xAI (Sitemap)",
]

# Sources that are duplicates or covered by existing Google News proxies
SKIP_COMMENTS = [
    "covered by Google News proxy",
    "covered by MIT News AI Google News proxy",
    "Duplicate of",
    "Covered by Qualcomm",
    "Duplicate of DoorDash",
    "Duplicate of Google Cloud",
]

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Words to strip from source names when generating keywords
STRIP_WORDS = {
    "blog", "sitemap", "rss", "feed", "news", "via", "google",
    "(sitemap)", "(via", "news)", "the", "of", "and", "for", "in", "on",
    "a", "an", "to",
}


def extract_domain(source: dict) -> str | None:
    """Extract domain from feed_url or sitemap_url."""
    url = source.get("feed_url") or source.get("sitemap_url")
    if not url:
        return None
    parsed = urlparse(url)
    domain = parsed.hostname
    if not domain:
        return None
    # Strip www. prefix for cleaner Google News queries
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def generate_keywords(name: str, domain: str | None) -> str:
    """Generate search keywords from source name and context."""
    # Clean the name
    clean = name.replace("(Sitemap)", "").replace("(via Google News)", "")
    clean = re.sub(r"\s+", " ", clean).strip()

    words = clean.split()
    meaningful = []
    for w in words:
        if w.lower().strip("()") in STRIP_WORDS:
            continue
        meaningful.append(w)

    # Determine the type of source for keyword enrichment
    name_lower = name.lower()
    is_engineering = "engineering" in name_lower or "tech" in name_lower
    is_ai_ml = any(kw in name_lower for kw in ["ai", "ml", "machine learning",
                                                  "artificial intelligence",
                                                  "deep learning", "neural"])
    is_research = any(kw in name_lower for kw in ["research", "lti", "csail",
                                                    "lab", "arxiv", "paper"])
    is_robotics = "robot" in name_lower
    is_security = any(kw in name_lower for kw in ["security", "cyber", "threat"])

    # Build keyword string
    keywords = " ".join(meaningful)

    # If the name is just a company name, add context keywords
    if is_engineering and "engineering" not in keywords.lower():
        keywords += " engineering blog"
    elif is_ai_ml:
        if "AI" not in keywords:
            keywords += " AI"
    elif is_research:
        if "research" not in keywords.lower():
            keywords += " AI research"
    elif is_robotics:
        if "robotics" not in keywords.lower():
            keywords += " robotics"
    elif is_security:
        pass  # security keywords already present
    else:
        # Generic source — add AI/tech context if no obvious category
        # Check if domain gives clues
        if domain and any(x in (domain or "") for x in [".ai", "ml", "data"]):
            keywords += " AI"
        elif not any(x in keywords.lower() for x in ["ai", "ml", "tech",
                                                       "data", "science",
                                                       "engineering", "research"]):
            # Very generic — add broad tech/AI qualifier
            keywords += " AI technology"

    return keywords.strip()


def build_google_news_url(domain: str, keywords: str) -> str:
    """Build Google News RSS proxy URL."""
    query = f"site:{domain} {keywords}"
    encoded = quote(query, safe="")
    return (
        f"https://news.google.com/rss/search?q={encoded}"
        f"&hl=en-US&gl=US&ceid=US%3Aen"
    )


async def validate_feed(client: httpx.AsyncClient, url: str) -> tuple[bool, int]:
    """
    Fetch a Google News proxy URL and check it returns valid RSS with items.
    Returns (is_valid, item_count).
    """
    try:
        resp = await client.get(url, timeout=20.0, follow_redirects=True)
        if resp.status_code != 200:
            return False, 0
        text = resp.text
        # Check for RSS/Atom items
        item_count = text.count("<item>") + text.count("<entry>")
        return item_count > 0, item_count
    except Exception:
        return False, 0


def should_skip(source: dict) -> tuple[bool, str]:
    """Check if a source should be skipped. Returns (skip, reason)."""
    name = source.get("name", "")
    kind = source.get("kind", "")

    # Skip social media kinds
    if kind in SKIP_KINDS:
        return True, f"social media ({kind})"

    # Skip defunct sources by name fragment
    for frag in SKIP_NAME_FRAGMENTS:
        if frag.lower() in name.lower():
            return True, f"defunct ({frag})"

    # Skip sources disabled for non-feed reasons
    if name in SKIP_NAMES_EXACT:
        return True, "non-feed issue (Cloudflare blocked)"

    return False, ""


def source_already_covered(source: dict, lines: list[str], source_line_map: dict) -> bool:
    """Check if a source's disable comment indicates it's already covered."""
    name = source.get("name", "")
    if name not in source_line_map:
        return False
    start_line = source_line_map[name]
    # Look at the surrounding lines for skip comments
    for i in range(max(0, start_line - 2), min(len(lines), start_line + 10)):
        line = lines[i]
        for skip_comment in SKIP_COMMENTS:
            if skip_comment.lower() in line.lower():
                return True
    return False


def find_source_lines(lines: list[str]) -> dict[str, int]:
    """Map source names to their line indices."""
    name_to_line = {}
    for i, line in enumerate(lines):
        m = re.match(r'\s*-\s*name:\s*"(.+?)"', line)
        if m:
            name_to_line[m.group(1)] = i
    return name_to_line


def update_config_lines(
    lines: list[str],
    source_name: str,
    source_line_map: dict[str, int],
    google_news_url: str,
) -> list[str]:
    """
    Update config lines for a recovered source.
    Uses line-by-line replacement to preserve YAML comments.
    """
    if source_name not in source_line_map:
        return lines

    start = source_line_map[source_name]
    # Find the block end (next source or end of file)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r'\s*-\s*name:', lines[i]):
            end = i
            break

    new_block_lines = []
    found_kind = False
    found_feed_url = False
    found_enabled = False
    removed_sitemap = False

    for i in range(start, end):
        line = lines[i]

        # Update kind to rss
        if re.match(r'\s*kind:\s*"', line):
            indent = re.match(r'(\s*)', line).group(1)
            new_block_lines.append(f'{indent}kind: "rss"\n')
            found_kind = True
            continue

        # Update feed_url
        if re.match(r'\s*feed_url:\s*"', line):
            indent = re.match(r'(\s*)', line).group(1)
            new_block_lines.append(
                f'{indent}# Google News proxy - original feed was dead\n'
            )
            new_block_lines.append(
                f'{indent}feed_url: "{google_news_url}"\n'
            )
            found_feed_url = True
            continue

        # Remove sitemap_url (replaced by feed_url)
        if re.match(r'\s*sitemap_url:\s*"', line):
            indent = re.match(r'(\s*)', line).group(1)
            if not found_feed_url:
                new_block_lines.append(
                    f'{indent}# Google News proxy - original feed was dead\n'
                )
                new_block_lines.append(
                    f'{indent}feed_url: "{google_news_url}"\n'
                )
                found_feed_url = True
            removed_sitemap = True
            continue

        # Remove path_filter (not needed with Google News proxy)
        if re.match(r'\s*path_filter:\s*"', line):
            continue

        # Remove lastmod_optional
        if re.match(r'\s*lastmod_optional:\s*', line):
            continue

        # Update enabled: false → enabled: true
        if re.match(r'\s*enabled:\s*false', line):
            indent = re.match(r'(\s*)', line).group(1)
            new_block_lines.append(f'{indent}enabled: true\n')
            found_enabled = True
            continue

        # Remove old disable-reason comments (lines that are just comments
        # between fields), but keep the name comment line
        if line.strip().startswith("#") and i > start:
            comment_lower = line.strip().lower()
            # Remove old dead-feed comments
            if any(kw in comment_lower for kw in [
                "404", "403", "feed url dead", "server error",
                "sitemap 404", "sitemap 403", "sitemap returns html",
                "disabled", "dead", "blocked", "defunct",
                "old feed", "feed 404", "domain 404",
            ]):
                continue

        new_block_lines.append(line)

    # If sitemap source and we didn't find a feed_url line, we need to
    # add kind: rss if not yet done
    if not found_kind:
        # Insert kind after name line
        for j, bl in enumerate(new_block_lines):
            if re.match(r'\s*-\s*name:', bl):
                indent = re.match(r'(\s*)', bl).group(1) + "  "
                new_block_lines.insert(j + 1, f'{indent}kind: "rss"\n')
                break

    # Replace the original block
    return lines[:start] + new_block_lines + lines[end:]


async def main():
    print(f"Loading config from: {CONFIG_PATH}")
    with open(CONFIG_PATH) as f:
        raw_text = f.read()

    config = yaml.safe_load(raw_text)
    sources = config.get("sources", [])

    # Read lines for line-by-line editing
    with open(CONFIG_PATH) as f:
        lines = f.readlines()

    source_line_map = find_source_lines(lines)

    # Find disabled sources
    disabled = [s for s in sources if not s.get("enabled", True)]
    print(f"\nTotal disabled sources: {len(disabled)}")

    # Filter candidates
    candidates = []
    skipped = []
    already_covered = []

    for s in disabled:
        name = s.get("name", "")
        skip, reason = should_skip(s)
        if skip:
            skipped.append((name, reason))
            continue

        if source_already_covered(s, lines, source_line_map):
            already_covered.append(name)
            continue

        domain = extract_domain(s)
        if not domain:
            skipped.append((name, "no URL to extract domain from"))
            continue

        # Skip feeds.buzzsprout.com, feeds.simplecast.com, feeds.transistor.fm
        # — these are podcast hosting platforms, not blog domains
        if domain in ("feeds.buzzsprout.com", "feeds.simplecast.com",
                       "feeds.transistor.fm", "bensbites.beehiiv.com"):
            skipped.append((name, "podcast/newsletter hosting platform"))
            continue

        # Skip github.com atom feeds — too specific
        if domain == "github.com":
            skipped.append((name, "GitHub release feed (not a blog domain)"))
            continue

        # Chinese-language sites — Google News EN won't have good coverage
        if domain in ("www.baidu.com", "baidu.com", "volcengine.com",
                       "www.volcengine.com"):
            skipped.append((name, "Chinese-language site"))
            continue

        candidates.append(s)

    print(f"Skipped (truly defunct/social/other): {len(skipped)}")
    for name, reason in skipped:
        print(f"  SKIP  {name} — {reason}")

    print(f"\nAlready covered by existing Google News proxies: {len(already_covered)}")
    for name in already_covered:
        print(f"  COVERED  {name}")

    print(f"\nCandidates to try: {len(candidates)}")

    # Build proxy URLs and validate
    sem = asyncio.Semaphore(10)
    recovered = []
    still_broken = []

    async with httpx.AsyncClient(
        headers={"User-Agent": BROWSER_UA},
        follow_redirects=True,
    ) as client:

        async def try_source(source):
            name = source.get("name", "")
            domain = extract_domain(source)
            keywords = generate_keywords(name, domain)
            proxy_url = build_google_news_url(domain, keywords)

            async with sem:
                valid, count = await validate_feed(client, proxy_url)

            if valid:
                recovered.append({
                    "name": name,
                    "domain": domain,
                    "keywords": keywords,
                    "proxy_url": proxy_url,
                    "item_count": count,
                })
                print(f"  OK    {name} — {count} items via site:{domain}")
            else:
                still_broken.append({
                    "name": name,
                    "domain": domain,
                    "keywords": keywords,
                    "proxy_url": proxy_url,
                })
                print(f"  FAIL  {name} — no items for site:{domain}")

        tasks = [try_source(s) for s in candidates]
        await asyncio.gather(*tasks)

    # Update config file for recovered sources
    if recovered:
        print(f"\n{'='*60}")
        print(f"Updating config for {len(recovered)} recovered sources...")

        # Re-read lines fresh for editing
        with open(CONFIG_PATH) as f:
            lines = f.readlines()

        source_line_map = find_source_lines(lines)

        for rec in recovered:
            lines = update_config_lines(
                lines, rec["name"], source_line_map, rec["proxy_url"]
            )
            # Rebuild the line map after each edit (line numbers shift)
            source_line_map = find_source_lines(lines)

        with open(CONFIG_PATH, "w") as f:
            f.writelines(lines)

        print("Config file updated.")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total disabled sources:          {len(disabled)}")
    print(f"Skipped (defunct/social/other):   {len(skipped)}")
    print(f"Already covered by proxy:        {len(already_covered)}")
    print(f"Candidates tried:                {len(candidates)}")
    print(f"  Recovered (Google News proxy): {len(recovered)}")
    print(f"  Still broken (no items):       {len(still_broken)}")
    print()

    if recovered:
        print("RECOVERED:")
        for r in sorted(recovered, key=lambda x: x["name"]):
            print(f"  + {r['name']} ({r['item_count']} items)")
    print()

    if still_broken:
        print("STILL BROKEN:")
        for b in sorted(still_broken, key=lambda x: x["name"]):
            print(f"  - {b['name']} (site:{b['domain']})")

    return 0 if recovered else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
