# Disabled Sources

Sources that are currently disabled in `ai_news/app/config_sources.yml` and cannot be ingested. This excludes the original 7 (xAI, Twitter, Bluesky, Baidu, ByteDance, and redundant Meta AI Research / Apple ML sitemaps) and sources that have been replaced by a working alternative (Google News proxy or updated feed URL).

Last validated: 2026-03-12

---

## 403 Bot-Blocked (RSS)

These sites have working RSS feeds but actively block non-browser User-Agents. They return `403 Forbidden` when fetched with our `ai-news-bot/0.1` UA.

| Source | URL | Notes |
|--------|-----|-------|
| SC Media | `https://www.scmagazine.com/feed` | Redirects to scworld.com which blocks bots. Low-priority security trade pub. |
| OpenSSF Blog | `https://openssf.org/feed/` | Feed is confirmed live with browser UA but rejects bot clients. Could be fixed by switching UA to a browser-like string. |
| The Information | `https://www.theinformation.com/feed` | Paywalled tech news site. Feed blocked and content is behind paywall anyway. |
| U Michigan Engineering — Robots | `https://news.engin.umich.edu/category/research/robots/feed/` | WordPress site blocks bot UAs at the server level. |
| Princeton CITP (Freedom to Tinker) | `https://freedom-to-tinker.com/feed/` | WordPress site blocks bot UAs. Princeton CITP tech policy blog. |
| Communications of the ACM | `https://cacm.acm.org/feed/` | ACM went open access in 2024 but their feed endpoint blocks bots. May have moved to `cacm.acm.org/feeds-2/`. |
| USENIX Blog | `https://www.usenix.org/blog/feed` | Drupal site blocks bot UAs. Academic systems/security conference org. |

## 403 Bot-Blocked (Sitemap)

These sites block sitemap access via WAF, Cloudflare, or similar bot protection. University and research org sites are particularly aggressive about this.

| Source | URL | Notes |
|--------|-----|-------|
| Georgetown CSET (Sitemap) | `https://cset.georgetown.edu/sitemap.xml` | Georgetown security studies center. Drupal WAF blocks bots. |
| Ideogram Blog (Sitemap) | `https://ideogram.ai/sitemap.xml` | AI image generation startup. Cloudflare bot protection. |
| U Michigan AI Lab (Sitemap) | `https://ai.engin.umich.edu/sitemap.xml` | University WAF blocks all bot access to sitemap. |
| Cornell AI Initiative (Sitemap) | `https://ai.cornell.edu/sitemap.xml` | University WAF blocks bot access. |
| Cornell Tech (Sitemap) | `https://tech.cornell.edu/sitemap.xml` | University WAF blocks bot access. |
| Columbia AI (Sitemap) | `https://ai.columbia.edu/sitemap.xml` | University WAF blocks bot access. |
| USC ISI News (Sitemap) | `https://www.isi.edu/sitemap.xml` | USC Information Sciences Institute. WAF blocks bots. |
| JHU CLSP News (Sitemap) | `https://www.clsp.jhu.edu/sitemap.xml` | Johns Hopkins Center for Language and Speech Processing. WAF blocks bots. |
| Harvard Kempner Institute (Sitemap) | `https://kempnerinstitute.harvard.edu/sitemap.xml` | Harvard AI research institute. WAF blocks bots. |
| Stanford Internet Observatory (Sitemap) | `https://cyber.fsi.stanford.edu/sitemap.xml` | Stanford cyber policy center. Drupal WAF blocks bots. |
| USC CAIS (Sitemap) | `https://cais.usc.edu/sitemap.xml` | USC Center for AI in Society. WAF blocks bots. |
| USC Viterbi News (Sitemap) | `https://viterbischool.usc.edu/sitemap.xml` | USC engineering school. WAF blocks bots. |
| Caltech CAST (Sitemap) | `https://cast.caltech.edu/sitemap.xml` | Caltech Center for Autonomous Systems. WAF blocks bots. |
| Caltech AI4Science (Sitemap) | `https://ai4science.caltech.edu/sitemap.xml` | Caltech AI for science initiative. WAF blocks bots. |
| Edinburgh Informatics (Sitemap) | `https://informatics.ed.ac.uk/sitemap.xml` | University of Edinburgh. WAF blocks bots. |
| Alan Turing Institute (Sitemap) | `https://www.turing.ac.uk/sitemap.xml` | UK national AI institute. WAF blocks bots. |
| DFKI (Sitemap) | `https://www.dfki.de/sitemap.xml` | German Research Center for AI. WAF blocks bots. |
| Boston Dynamics Blog (Sitemap) | `https://bostondynamics.com/sitemap.xml` | Robotics company. Cloudflare bot protection. |

## 404 — Feed URL Dead

The feed URL returns 404. The site has either restructured, removed their feed, or the URL was wrong to begin with.

| Source | URL | Notes |
|--------|-----|-------|
| NYU AI (Sitemap) | `https://cims.nyu.edu/sitemap.xml` | Courant Institute. No sitemap served at this URL. |
| UT Austin AI (Sitemap) | `https://ai.utexas.edu/sitemap.xml` | No sitemap published by this subdomain. |
| Stanford CRFM (Sitemap) | `https://crfm.stanford.edu/sitemap.xml` | Center for Research on Foundation Models. Static Jekyll site, no sitemap. |
| Stanford RegLab (Sitemap) | `https://reglab.stanford.edu/sitemap.xml` | Stanford regulation lab. No sitemap published. |
| Harvard Berkman Klein Center (Sitemap) | `https://cyber.harvard.edu/sitemap.xml` | Berkman Klein Center for Internet & Society. No sitemap at this URL. |
| Harvard Data Science Initiative (Sitemap) | `https://datascience.harvard.edu/sitemap.xml` | No sitemap published. |
| GT CyberSecurity (Sitemap) | `https://cyber.gatech.edu/sitemap.xml` | Georgia Tech cybersecurity center. No sitemap published. |
| Michigan Robotics News (Sitemap) | `https://robotics.umich.edu/sitemap.xml` | No sitemap published at this URL. |
| UCSD Contextual Robotics (Sitemap) | `https://contextualrobotics.ucsd.edu/sitemap.xml` | No sitemap published. |
| UCSD Jacobs Engineering (Sitemap) | `https://jacobsschool.ucsd.edu/sitemap.xml` | No sitemap published at this URL. |
| Virginia Tech Sanghani Center (Sitemap) | `https://sanghani.cs.vt.edu/sitemap.xml` | No sitemap published. |
| UW-Madison AI (Sitemap) | `https://ai.cs.wisc.edu/sitemap.xml` | No sitemap published. |
| Oxford CS (Sitemap) | `https://www.cs.ox.ac.uk/sitemap.xml` | No sitemap published by Oxford CS department. |
| Oxford Robotics Institute (Sitemap) | `https://ori.ox.ac.uk/sitemap.xml` | No sitemap published. |
| Tsinghua AIR (Sitemap) | `https://air.tsinghua.edu.cn/sitemap.xml` | Institute for AI Industry Research. No sitemap published. |
| CAS Research News (Sitemap) | `https://english.cas.cn/sitemap.xml` | Chinese Academy of Sciences. No sitemap at English portal. |
| RIKEN AIP (Sitemap) | `https://aip.riken.jp/sitemap.xml` | RIKEN Center for Advanced Intelligence Project (Japan). No sitemap. Tried wp-sitemap.xml, also 404. |
| NTU Singapore (Sitemap) | `https://www.ntu.edu.sg/sitemap.xml` | Nanyang Technological University. No sitemap at root. |
| Technion Blog (Sitemap) | `https://www.technion.ac.il/sitemap.xml` | Israel Institute of Technology. No sitemap published. |
| 1X Technologies (Sitemap) | `https://www.1x.tech/sitemap.xml` | Humanoid robotics company. No sitemap published. |

## DNS Failure / Unreachable

The domain does not resolve or the server is unreachable.

| Source | URL | Notes |
|--------|-----|-------|
| Argonne National Lab | `https://today.anl.gov/feed` | `today.anl.gov` does not resolve. May have been decommissioned or merged into main `anl.gov` site. |
| EE Times | `https://www.eetimes.com/feed/` | Domain does not resolve through our network. May be geo-restricted or CDN issue. |
| Georgia Tech Research Horizons (Sitemap) | `https://rh.gatech.edu/sitemap.xml` | `rh.gatech.edu` does not resolve. Subdomain appears decommissioned. |
| SIGGRAPH Blog | `https://blog.siggraph.org/feed/` | Connection refused. Server appears to be down or decommissioned. |

## Sitemap Has No `lastmod` Dates

These sitemaps are reachable and contain URLs, but none of the entries include `lastmod` timestamps. Our sitemap connector requires `lastmod` to enforce recency filtering, so these sources will never produce any candidates.

| Source | URL | URLs in sitemap | Notes |
|--------|-----|-----------------|-------|
| HiddenLayer Research | `https://hiddenlayer.com/sitemap.xml` | 362 | AI security research. Sitemap has URLs but zero `lastmod` entries. |
| Luma Blog News (Sitemap) | `https://lumalabs.ai/blog/sitemap.xml` | 0 | Empty sitemap — no blog URLs listed at all. |
| Luma Press (Sitemap) | `https://lumalabs.ai/press/sitemap.xml` | 0 | Empty sitemap — no press URLs listed. |
| Windsurf Blog (Sitemap) | `https://windsurf.com/sitemap.xml` | 302 | AI code editor. 302 URLs but none have `lastmod`. |
| Kimi Updates (Sitemap) | `https://www.kimi.com/sitemap.xml` | 11 | Moonshot AI's Kimi. No `lastmod` on any entry. |
| Center for AI Safety (Sitemap) | `https://www.safe.ai/sitemap.xml` | 131 | CAIS. 131 URLs but zero `lastmod` timestamps. |
| UK AI Safety Institute (Sitemap) | `https://www.aisi.gov.uk/sitemap.xml` | 152 | Redundant — UK AISI already covered by RSS source via GOV.UK Atom feed. Sitemap has no `lastmod`. |
| Suno Blog (Sitemap) | `https://suno.com/sitemap.xml` | 16 | AI music generation. No `lastmod` dates. |
| CMU SCS News (Sitemap) | `https://csd.cmu.edu/sitemap.xml` | 1 | Only 1 URL, no `lastmod`. Effectively empty. |
| Imperial College ML (Sitemap) | `https://www.imperial.ac.uk/sitemap.xml` | 17,157 | Massive university-wide sitemap but zero `lastmod` on any entry. |
| Agility Robotics (Sitemap) | `https://www.agilityrobotics.com/sitemap.xml` | 109 | Digit humanoid robot maker. 109 URLs but no `lastmod`. |

## Sitemap Parse Error

The URL returns something that is not valid XML, so our sitemap parser cannot process it.

| Source | URL | Notes |
|--------|-----|-------|
| Perplexity AI Blog (Sitemap) | `https://www.perplexity.ai/sitemap.xml` | Returns non-XML content (likely HTML or JS-rendered page). |
| Pika Blog (Sitemap) | `https://pika.art/sitemap.xml` | Returns malformed XML with unescaped entities (`xmlParseEntityRef: no name`). |

## Timeout

The server is too slow to respond within our 30-second timeout.

| Source | URL | Notes |
|--------|-----|-------|
| AMD AI Blog (Sitemap) | `https://www.amd.com/sitemap.xml` | AMD's main sitemap is extremely large and times out. Would need a more targeted sub-sitemap URL. |

## 502 Server Error

| Source | URL | Notes |
|--------|-----|-------|
| UCL AI Centre (Sitemap) | `https://www.ucl.ac.uk/sitemap.xml` | University College London. Returns 502 Bad Gateway — likely an intermittent infrastructure issue. May work on retry. |

---

## Potential Fixes

Several of these could be re-enabled with targeted work:

1. **Bot-blocked RSS feeds** — Could be fixed by changing `user_agent` in the RSS connector to a browser-like string (e.g., `Mozilla/5.0`). This would unblock OpenSSF, CACM, Princeton CITP, USENIX, and several others. Trade-off: some sites may view this as deceptive.

2. **Bot-blocked sitemaps** — Same UA fix could help. Alternatively, adding a Playwright/headless browser fallback for fetching sitemaps would bypass most WAFs.

3. **No-lastmod sitemaps** — Could be fixed by modifying the sitemap connector to optionally skip the `lastmod` requirement and instead rely on URL-based deduplication. This would unlock HiddenLayer (362 URLs), Windsurf (302 URLs), Imperial College (17K URLs), Center for AI Safety (131 URLs), and others.

4. **Google News proxies** — Any site with a web presence can be monitored via `https://news.google.com/rss/search?q=site%3A{domain}`. This is already used for MIT News, Reuters, Microsoft Security, etc. Could be extended to cover more disabled university sources.

5. **AMD timeout** — AMD likely has a blog-specific sub-sitemap. Finding the correct URL (e.g., `https://www.amd.com/en/blogs/sitemap.xml`) would fix this.
