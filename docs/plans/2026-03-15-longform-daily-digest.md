# Longform Daily Digest Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current short headline+summary digest with a longform, personality-driven daily digest page (5-10 minute read, TLDR/The Verge style) with source links, archive navigation, and translation support.

**Architecture:** Add a `longform_html` column to the existing `DailyDigest` model. A new LLM prompt generates a structured longform article with sections (only when each section has substance), inline source links, and a witty journalist voice. The frontend gets a new `DailyDigestPage` component rendered in a new default "digest" tab, with an archive sidebar to browse past digests. The existing live feed becomes a secondary tab. HTML is sanitized with DOMPurify before rendering.

**Tech Stack:** Python/FastAPI backend, SQLAlchemy + Alembic, LLM via OpenRouter/OpenAI, React + TypeScript frontend, DOMPurify for HTML sanitization, existing Vite build.

---

## Task 1: Database Migration — Add `longform_html` to DailyDigest

**Files:**
- Create: `ai_news/alembic/versions/0007_longform_digest.py`
- Modify: `ai_news/app/models.py:282-298`

**Step 1: Create migration file**

Create `ai_news/alembic/versions/0007_longform_digest.py`:

```python
"""add longform_html to daily_digests

Revision ID: 0007_longform_digest
Revises: 0006_entity_canon_maps
Create Date: 2026-03-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_longform_digest"
down_revision = "0006_entity_canon_maps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_digests", sa.Column("longform_html", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_digests", "longform_html")
```

**Step 2: Add column to SQLAlchemy model**

In `ai_news/app/models.py`, add to the `DailyDigest` class (after `storage_path`):

```python
longform_html = Column(Text, nullable=True)
```

**Step 3: Run migration**

```bash
cd ai_news && alembic upgrade head
```

**Step 4: Commit**

```bash
git add ai_news/alembic/versions/0007_longform_digest.py ai_news/app/models.py
git commit -m "feat: add longform_html column to DailyDigest model"
```

---

## Task 2: Longform Digest LLM Prompt & Generator

**Files:**
- Modify: `ai_news/app/llm/prompts.py` (add LONGFORM_DIGEST_SYSTEM_PROMPT, LONGFORM_DIGEST_USER_PROMPT)
- Modify: `ai_news/app/llm/client.py` (add `generate_longform_digest` method)

**Step 1: Add longform prompts to `ai_news/app/llm/prompts.py`**

Append these constants:

```python
LONGFORM_DIGEST_SYSTEM_PROMPT = """You are the lead AI correspondent for Pebble — a sharp, witty tech journalist who genuinely loves this beat. Think of yourself as the writer readers actually look forward to hearing from every morning. Your style:

- **Voice**: Conversational but authoritative. You drop the occasional wry observation or cultural reference. You're not afraid to have an opinion, but you back it up. Think The Verge meets TLDR meets a really smart friend who happens to cover AI for a living.
- **Tone**: Energetic but not breathless. Skeptical but not cynical. You get excited about genuinely cool stuff and you're honest when something is overhyped.
- **Structure**: You write in clean, punchy paragraphs. Short sentences mixed with longer analytical ones. You use section headers when transitioning topics but only when a section has real substance.
- **References**: When you mention a development, weave the source link naturally into the prose using markdown links. Example: "Google just dropped [Gemini 2.0](https://blog.google/...) and honestly, the multimodal improvements are no joke."
- **Personality quirks**: You might start with a punchy opening line about the day's vibe. You occasionally address the reader directly. You close with a brief, memorable sign-off.

You are writing a daily digest that should be a 5-10 minute read. Do NOT pad with filler. If a section only has one minor item, fold it into another section or skip it. Every paragraph should earn its place.

Return your response as a JSON object with these keys:
- "title": A catchy, specific headline for today's digest (not generic — reference the biggest story)
- "subtitle": A one-line teaser (15 words max)
- "sections": An array of objects, each with:
  - "heading": Section title (e.g., "The Big One", "Research Corner", "Open Source Drops", "Money Moves", "Policy Watch", "Quick Hits")
  - "body": The section content in markdown. Use [linked text](url) for source references. Use **bold** for emphasis. Keep paragraphs short.
- "sign_off": A brief closing line (1-2 sentences, with personality)
- "source_count": How many distinct sources you referenced

Guidelines for sections:
- Only include a section if it has genuinely important content. 3-6 sections is typical.
- The first section should cover the biggest story of the day in depth.
- A "Quick Hits" section at the end can bundle 2-4 smaller items as bullet points.
- Research papers should be explained accessibly — what they found, why it matters, not just "a paper was published."
- For funding/business news, give context — is this a big deal? How does it compare?
- GitHub/open source: focus on what developers can actually use, not just star counts.
"""

LONGFORM_DIGEST_USER_PROMPT = """Write today's daily AI digest based on these articles. Each article includes a title, summary, source name, URL, category, and significance score.

ARTICLES:
{articles_json}

Remember:
- Only create sections for topics with substantial content
- Weave source URLs as inline markdown links naturally in the prose
- Be specific and opinionated — generic summaries are boring
- Target 5-10 minute read length
- Return strict JSON with keys: title, subtitle, sections (array of {{heading, body}}), sign_off, source_count
"""
```

**Step 2: Add `generate_longform_digest` method to `ai_news/app/llm/client.py`**

Add this method to the `LLMClient` class:

```python
def generate_longform_digest(self, articles: list[dict]) -> dict | None:
    """Generate a longform daily digest article with personality and inline source links."""
    from app.llm.prompts import LONGFORM_DIGEST_SYSTEM_PROMPT, LONGFORM_DIGEST_USER_PROMPT

    if not articles:
        return None
    if not self.enabled:
        return None

    cache_key = f"longform_digest:{hashlib.sha256(json.dumps(articles, sort_keys=True).encode('utf-8')).hexdigest()}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        content = self.chat(
            [
                {"role": "system", "content": LONGFORM_DIGEST_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": LONGFORM_DIGEST_USER_PROMPT.format(
                        articles_json=json.dumps(articles, ensure_ascii=False)
                    ),
                },
            ],
            json_object=True,
        )
        parsed = json.loads(content or "{}")
        if not parsed.get("title") or not parsed.get("sections"):
            return None
        set_cached(cache_key, parsed)
        return parsed
    except Exception:
        logger.exception("Longform digest generation failed")
        return None
```

**Step 3: Add translation method for longform digest**

Add to `LLMClient`:

```python
def translate_longform_digest(self, digest: dict) -> dict | None:
    """Translate a longform digest to zh-CN, preserving markdown links."""
    if not digest:
        return None
    payload = {
        "title": digest.get("title", ""),
        "subtitle": digest.get("subtitle", ""),
        "sections": [
            {"heading": s.get("heading", ""), "body": s.get("body", "")}
            for s in digest.get("sections", [])
        ],
        "sign_off": digest.get("sign_off", ""),
    }
    result = self._translate_cached_json(
        cache_namespace="translate_longform_digest",
        payload=payload,
        instruction=(
            "Translate the following AI news digest into professional simplified Chinese (zh-CN). "
            "Preserve all markdown formatting and [link](url) references exactly. "
            "Translate the prose but keep URLs, proper nouns (company/product names), and technical terms unchanged.\n\n"
            "PAYLOAD:\n{payload}\n\n"
            "Return the same JSON structure with translated text fields."
        ),
    )
    if not isinstance(result, dict) or not result.get("title"):
        return None
    return {**digest, **result}
```

**Step 4: Commit**

```bash
git add ai_news/app/llm/prompts.py ai_news/app/llm/client.py
git commit -m "feat: add longform digest LLM prompt with journalist personality"
```

---

## Task 3: Modify Daily Digest Task to Generate Longform

**Files:**
- Modify: `ai_news/app/tasks/daily_digest.py`

**Step 1: Update `run_daily_digest` to build and store longform content**

After the existing per-content-type loop (after line ~255 in daily_digest.py), add longform generation. The key change: build a richer article payload with URLs and source names for the LLM, then call `generate_longform_digest`, and store the result in a DailyDigest row with `content_type="longform"`.

Inside `run_daily_digest()`, after the `for ct, items in groups.items():` loop completes but still inside the `for user in users:` block, add:

```python
# ── Generate longform digest ──
longform_articles = []
if all_items:
    art_ids = [item["id"] for item in all_items]
    articles_with_raw = (
        session.query(Article, RawItem, Source)
        .join(RawItem, Article.raw_item_id == RawItem.id)
        .join(Source, RawItem.source_id == Source.id)
        .filter(Article.id.in_(art_ids))
        .all()
    )
    for article, raw, source in articles_with_raw:
        longform_articles.append({
            "title": raw.title,
            "summary": article.summary or raw.snippet or (article.text[:400] if article.text else ""),
            "source_name": source.name,
            "url": article.final_url,
            "category": article.event_type,
            "content_type": article.content_type,
            "significance_score": article.final_score or article.global_score or 0,
        })
    # Sort by significance so LLM sees most important first
    longform_articles.sort(key=lambda x: x["significance_score"], reverse=True)

longform_result = llm.generate_longform_digest(longform_articles[:30])
if longform_result:
    # Convert structured JSON to rendered HTML
    longform_html = _render_longform_html(longform_result)

    existing_lf = (
        session.query(DailyDigest)
        .filter(
            DailyDigest.user_id == user.id,
            func.date(DailyDigest.date) == now.date(),
            DailyDigest.content_type == "longform",
        )
        .first()
    )
    if existing_lf:
        existing_lf.article_ids = all_ids
        existing_lf.headline = longform_result.get("title")
        existing_lf.executive_summary = longform_result.get("subtitle")
        existing_lf.longform_html = longform_html
        existing_lf.llm_authored = True
    else:
        lf_digest = DailyDigest(
            user_id=user.id,
            date=now,
            article_ids=all_ids,
            content_type="longform",
            headline=longform_result.get("title"),
            executive_summary=longform_result.get("subtitle"),
            longform_html=longform_html,
            llm_authored=True,
        )
        session.add(lf_digest)
```

**Step 2: Add the `_render_longform_html` helper function**

Add this at module level in `daily_digest.py`:

```python
import re

def _render_longform_html(digest_json: dict) -> str:
    """Convert the structured longform digest JSON into rendered HTML."""
    parts: list[str] = []
    parts.append(f'<h1 class="digest-title">{_escape(digest_json.get("title", ""))}</h1>')
    subtitle = digest_json.get("subtitle", "")
    if subtitle:
        parts.append(f'<p class="digest-subtitle">{_escape(subtitle)}</p>')

    for section in digest_json.get("sections", []):
        heading = section.get("heading", "")
        body = section.get("body", "")
        if heading:
            parts.append(f'<h2 class="digest-section-heading">{_escape(heading)}</h2>')
        if body:
            parts.append(_markdown_to_html(body))

    sign_off = digest_json.get("sign_off", "")
    if sign_off:
        parts.append(f'<p class="digest-sign-off">{_md_inline(sign_off)}</p>')

    return "\n".join(parts)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_inline(text: str) -> str:
    """Convert inline markdown (bold, links) to HTML."""
    text = _escape(text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Links — only allow http/https URLs
    def _safe_link(m):
        label, url = m.group(1), m.group(2)
        if not url.startswith(('http://', 'https://')):
            return label
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _safe_link, text)
    return text


def _markdown_to_html(md: str) -> str:
    """Minimal markdown-to-HTML: paragraphs, bold, links, bullet lists."""
    lines = md.strip().split("\n")
    html_parts: list[str] = []
    in_list = False
    paragraph_lines: list[str] = []

    def flush_paragraph():
        nonlocal paragraph_lines
        if paragraph_lines:
            text = " ".join(paragraph_lines)
            html_parts.append(f"<p>{_md_inline(text)}</p>")
            paragraph_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            flush_paragraph()
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{_md_inline(stripped[2:])}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            paragraph_lines.append(stripped)

    flush_paragraph()
    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)
```

**Step 3: Commit**

```bash
git add ai_news/app/tasks/daily_digest.py
git commit -m "feat: generate longform HTML digest during daily task"
```

---

## Task 4: Backend API Endpoints for Longform Digest & Archive

**Files:**
- Modify: `ai_news/app/api/routes_api.py`

**Step 1: Add archive endpoint**

Add to `routes_api.py`:

```python
@router.get("/digest/archive")
def digest_archive(
    limit: int = Query(30, ge=1, le=90),
    db=Depends(get_db),
):
    """Return a list of dates that have longform digests available."""
    settings = get_settings()
    rows = (
        db.query(
            func.date(DailyDigest.date).label("digest_date"),
            DailyDigest.headline,
            DailyDigest.executive_summary,
        )
        .filter(
            DailyDigest.user_id == settings.public_user_id,
            DailyDigest.content_type == "longform",
            DailyDigest.longform_html.isnot(None),
        )
        .order_by(func.date(DailyDigest.date).desc())
        .limit(limit)
        .all()
    )
    return {
        "digests": [
            {
                "date": str(row.digest_date),
                "headline": row.headline or "Daily AI Digest",
                "subtitle": row.executive_summary or "",
            }
            for row in rows
        ]
    }
```

**Step 2: Add daily digest endpoint (by date)**

```python
@router.get("/digest/daily")
def digest_daily(
    date: str = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    locale: str = Query("en", pattern="^(en|zh)$"),
    db=Depends(get_db),
):
    """Return the longform digest for a given date (defaults to today)."""
    from datetime import date as date_type

    settings = get_settings()
    if date:
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            target_date = _naive_utc(utcnow()).date()
    else:
        target_date = _naive_utc(utcnow()).date()

    row = (
        db.query(DailyDigest)
        .filter(
            DailyDigest.user_id == settings.public_user_id,
            func.date(DailyDigest.date) == target_date,
            DailyDigest.content_type == "longform",
        )
        .first()
    )

    if not row or not row.longform_html:
        return {
            "date": str(target_date),
            "headline": None,
            "subtitle": None,
            "longformHtml": None,
            "llmAuthored": False,
            "locale": locale,
            "available": False,
        }

    html = row.longform_html
    headline = row.headline
    subtitle = row.executive_summary

    if locale == "zh":
        llm = LLMClient()
        translated = llm._translate_cached_json(
            cache_namespace="translate_longform_html",
            payload={"headline": headline or "", "subtitle": subtitle or "", "html": html},
            instruction=(
                "Translate the following AI news digest into professional simplified Chinese (zh-CN). "
                "The html field contains rendered HTML — translate the text content but preserve ALL HTML tags, "
                "attributes, URLs, proper nouns (company/product names), and technical terms unchanged.\n\n"
                "PAYLOAD:\n{payload}\n\n"
                "Return JSON with keys: headline, subtitle, html"
            ),
        )
        if translated and isinstance(translated, dict):
            html = translated.get("html") or html
            headline = translated.get("headline") or headline
            subtitle = translated.get("subtitle") or subtitle

    return {
        "date": str(target_date),
        "headline": headline,
        "subtitle": subtitle,
        "longformHtml": html,
        "llmAuthored": True,
        "locale": locale,
        "available": True,
    }
```

**Step 3: Commit**

```bash
git add ai_news/app/api/routes_api.py
git commit -m "feat: add /api/digest/daily and /api/digest/archive endpoints"
```

---

## Task 5: Install DOMPurify & Frontend Types/API Service

**Files:**
- Modify: `package.json` (add dompurify)
- Modify: `src/types/index.ts`
- Modify: `src/services/aiService.ts`

**Step 1: Install DOMPurify**

```bash
npm install dompurify && npm install -D @types/dompurify
```

**Step 2: Add types to `src/types/index.ts`**

```typescript
export interface LongformDigest {
  date: string;
  headline: string | null;
  subtitle: string | null;
  longformHtml: string | null;
  llmAuthored: boolean;
  locale: Language;
  available: boolean;
}

export interface DigestArchiveEntry {
  date: string;
  headline: string;
  subtitle: string;
}

export interface DigestArchiveResponse {
  digests: DigestArchiveEntry[];
}
```

**Step 3: Add API methods to `src/services/aiService.ts`**

```typescript
async fetchDailyDigest(date?: string, locale: Language = 'en'): Promise<LongformDigest> {
  const params = new URLSearchParams({ locale });
  if (date) params.set('date', date);
  const response = await this.fetchImpl(`/api/digest/daily?${params}`);
  if (!response.ok) {
    await failWithResponse(response, 'Failed to fetch daily digest');
  }
  return response.json();
}

async fetchDigestArchive(limit = 30): Promise<DigestArchiveEntry[]> {
  const response = await this.fetchImpl(`/api/digest/archive?limit=${limit}`);
  if (!response.ok) {
    await failWithResponse(response, 'Failed to fetch digest archive');
  }
  const data = await response.json();
  return data.digests ?? [];
}
```

Update import at the top of `aiService.ts`:
```typescript
import { DigestArchiveEntry, DigestResponse, GraphResponse, Language, LongformDigest, NewsItem } from '@/types';
```

**Step 4: Commit**

```bash
git add package.json package-lock.json src/types/index.ts src/services/aiService.ts
git commit -m "feat: add DOMPurify, frontend types and API methods for longform digest"
```

---

## Task 6: DailyDigestPage Component

**Files:**
- Create: `src/components/DailyDigestPage.tsx`

**Step 1: Create the component**

This component renders the longform HTML digest (sanitized with DOMPurify), a date-based archive sidebar, and handles loading/empty states.

```tsx
import React, { useState, useEffect, useCallback } from 'react';
import DOMPurify from 'dompurify';
import { AIService } from '@/services/aiService';
import { DigestArchiveEntry, Language, LongformDigest } from '@/types';
import { ChevronLeft, ChevronRight, CalendarDays, BookOpen } from 'lucide-react';

interface DailyDigestPageProps {
  aiService: AIService;
  language: Language;
}

const formatDisplayDate = (dateStr: string, language: Language): string => {
  const date = new Date(dateStr + 'T00:00:00');
  if (language === 'zh') {
    return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });
  }
  return date.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
};

const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const sanitizeHtml = (html: string): string => {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['h1', 'h2', 'h3', 'p', 'a', 'strong', 'em', 'ul', 'li', 'br'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
  });
};

const DailyDigestPage: React.FC<DailyDigestPageProps> = ({ aiService, language }) => {
  const [digest, setDigest] = useState<LongformDigest | null>(null);
  const [archive, setArchive] = useState<DigestArchiveEntry[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>(todayStr());
  const [loading, setLoading] = useState(true);
  const [showArchive, setShowArchive] = useState(false);

  const loadDigest = useCallback(async (date: string) => {
    setLoading(true);
    try {
      const data = await aiService.fetchDailyDigest(date, language);
      setDigest(data);
    } catch (err) {
      console.error('Failed to load digest', err);
      setDigest(null);
    } finally {
      setLoading(false);
    }
  }, [aiService, language]);

  const loadArchive = useCallback(async () => {
    try {
      const data = await aiService.fetchDigestArchive();
      setArchive(data);
    } catch (err) {
      console.error('Failed to load archive', err);
    }
  }, [aiService]);

  useEffect(() => {
    void loadDigest(selectedDate);
  }, [selectedDate, loadDigest]);

  useEffect(() => {
    void loadArchive();
  }, [loadArchive]);

  const navigateDate = (direction: -1 | 1) => {
    const idx = archive.findIndex(a => a.date === selectedDate);
    if (idx === -1) {
      if (archive.length > 0) setSelectedDate(archive[0].date);
      return;
    }
    const newIdx = idx - direction; // archive is desc, so -1 = newer, +1 = older
    if (newIdx >= 0 && newIdx < archive.length) {
      setSelectedDate(archive[newIdx].date);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="space-y-4 text-center">
          <div className="mx-auto h-16 w-16 rounded-full border-2 border-[var(--ink)] bg-[var(--panel)] flex items-center justify-center">
            <BookOpen className="w-7 h-7 text-[var(--accent)] animate-pulse" />
          </div>
          <p className="text-sm font-bold uppercase tracking-widest text-[var(--muted)]">
            {language === 'en' ? 'Loading digest...' : '加载中...'}
          </p>
        </div>
      </div>
    );
  }

  if (!digest?.available) {
    return (
      <div className="mx-auto max-w-3xl space-y-8 p-6 pt-8">
        <div className="wf-panel p-8 text-center space-y-4">
          <CalendarDays className="w-10 h-10 mx-auto text-[var(--muted)]" />
          <h2 className="text-xl font-bold">
            {language === 'en' ? 'No digest available for this date' : '该日期暂无简报'}
          </h2>
          <p className="text-sm text-[var(--muted)]">
            {language === 'en'
              ? 'The daily digest is generated at 6:00 AM UTC each day. Check back later or browse the archive.'
              : '每日简报于 UTC 6:00 生成。请稍后查看或浏览存档。'}
          </p>
          {archive.length > 0 && (
            <button
              onClick={() => setSelectedDate(archive[0].date)}
              className="wf-button mt-4"
            >
              {language === 'en' ? 'View latest digest' : '查看最新简报'}
            </button>
          )}
        </div>

        {archive.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-widest text-[var(--muted)]">
              {language === 'en' ? 'Recent Digests' : '近期简报'}
            </h3>
            {archive.slice(0, 7).map((entry) => (
              <button
                key={entry.date}
                onClick={() => setSelectedDate(entry.date)}
                className={`w-full text-left wf-panel p-4 hover:bg-[var(--panel)] transition-colors ${
                  entry.date === selectedDate ? 'border-[var(--accent)]' : ''
                }`}
              >
                <p className="text-xs font-bold uppercase tracking-widest text-[var(--muted)]">
                  {formatDisplayDate(entry.date, language)}
                </p>
                <p className="text-sm font-semibold mt-1">{entry.headline}</p>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6 pt-8">
      {/* Date navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigateDate(-1)}
          className="wf-button flex items-center gap-1 text-xs"
          disabled={archive.findIndex(a => a.date === selectedDate) >= archive.length - 1}
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">{language === 'en' ? 'Older' : '更早'}</span>
        </button>

        <button
          onClick={() => setShowArchive(!showArchive)}
          className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-[var(--muted)] hover:text-[var(--ink)] transition-colors"
        >
          <CalendarDays className="w-3.5 h-3.5" />
          {formatDisplayDate(selectedDate, language)}
        </button>

        <button
          onClick={() => navigateDate(1)}
          className="wf-button flex items-center gap-1 text-xs"
          disabled={archive.findIndex(a => a.date === selectedDate) <= 0}
        >
          <span className="hidden sm:inline">{language === 'en' ? 'Newer' : '更新'}</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Archive dropdown */}
      {showArchive && archive.length > 0 && (
        <div className="wf-panel p-4 space-y-2">
          <h3 className="text-xs font-bold uppercase tracking-widest text-[var(--muted)] mb-3">
            {language === 'en' ? 'Archive' : '存档'}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-64 overflow-y-auto custom-scrollbar">
            {archive.map((entry) => (
              <button
                key={entry.date}
                onClick={() => { setSelectedDate(entry.date); setShowArchive(false); }}
                className={`text-left p-3 rounded-lg border-2 transition-all text-xs ${
                  entry.date === selectedDate
                    ? 'border-[var(--accent)] bg-[var(--accent-muted)]'
                    : 'border-[var(--grid)] hover:border-[var(--muted)]'
                }`}
              >
                <span className="font-bold uppercase tracking-wider">
                  {formatDisplayDate(entry.date, language)}
                </span>
                <span className="block mt-1 text-[var(--muted)] truncate">{entry.headline}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Digest content — sanitized with DOMPurify */}
      <article
        className="digest-longform wf-panel p-6 md:p-10"
        dangerouslySetInnerHTML={{ __html: sanitizeHtml(digest.longformHtml ?? '') }}
      />

      {/* Meta footer */}
      <div className="flex items-center justify-center gap-4 text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--muted)] pb-12">
        <span>{digest.llmAuthored ? (language === 'en' ? 'AI-authored digest' : 'AI 撰写') : ''}</span>
        <span>&middot;</span>
        <span>{formatDisplayDate(selectedDate, language)}</span>
      </div>
    </div>
  );
};

export default DailyDigestPage;
```

**Step 2: Commit**

```bash
git add src/components/DailyDigestPage.tsx
git commit -m "feat: add DailyDigestPage component with archive navigation and DOMPurify"
```

---

## Task 7: Longform Digest CSS Styles

**Files:**
- Modify: `src/styles/global.css`

**Step 1: Add digest longform styles**

Append to `src/styles/global.css`:

```css
/* ── Longform Digest ── */

.digest-longform {
  font-family: 'IBM Plex Mono', monospace;
  line-height: 1.75;
  color: var(--ink);
}

.digest-longform .digest-title {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 2.5rem;
  line-height: 1;
  letter-spacing: 0.02em;
  margin-bottom: 0.5rem;
  text-transform: uppercase;
}

@media (min-width: 768px) {
  .digest-longform .digest-title {
    font-size: 3.5rem;
  }
}

.digest-longform .digest-subtitle {
  font-size: 1rem;
  color: var(--muted);
  margin-bottom: 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 2px solid var(--grid);
  font-style: italic;
}

.digest-longform .digest-section-heading {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 1.5rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-top: 2.5rem;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--accent);
  color: var(--ink);
}

.digest-longform p {
  margin-bottom: 1rem;
  font-size: 0.85rem;
}

.digest-longform a {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 2px;
  text-decoration-thickness: 1px;
  transition: color 0.15s;
}

.digest-longform a:hover {
  color: var(--ink);
}

.digest-longform strong {
  font-weight: 600;
}

.digest-longform ul {
  list-style: none;
  padding-left: 0;
  margin-bottom: 1rem;
}

.digest-longform ul li {
  position: relative;
  padding-left: 1.25rem;
  margin-bottom: 0.5rem;
  font-size: 0.85rem;
}

.digest-longform ul li::before {
  content: '▸';
  position: absolute;
  left: 0;
  color: var(--accent);
  font-weight: bold;
}

.digest-longform .digest-sign-off {
  margin-top: 2.5rem;
  padding-top: 1.5rem;
  border-top: 2px solid var(--grid);
  font-style: italic;
  color: var(--muted);
  font-size: 0.85rem;
}
```

**Step 2: Commit**

```bash
git add src/styles/global.css
git commit -m "feat: add longform digest typography styles"
```

---

## Task 8: Update App.tsx — Add Digest Tab as Default

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/i18n/messages.ts`

**Step 1: Add i18n strings for the digest tab**

In `src/i18n/messages.ts`, add to `NAV_LABELS`:
```typescript
digest: { en: 'Daily Digest', zh: '每日简报' },
```

**Step 2: Update App.tsx**

Key changes:
1. Add `'digest'` to the `AppTab` type
2. Add digest nav item as the first item
3. Set default `activeTab` to `'digest'`
4. Import and render `DailyDigestPage` when `activeTab === 'digest'`

In `App.tsx`:

a. Update imports — add:
```typescript
import DailyDigestPage from '@/components/DailyDigestPage';
import { BookOpen } from 'lucide-react';
```

b. Change `AppTab` type:
```typescript
type AppTab = 'digest' | 'live' | 'weekly' | 'history' | 'map';
```

c. Update `NAV_ITEMS` — add digest as first item:
```typescript
const NAV_ITEMS: NavDef[] = [
  { id: 'digest', icon: <BookOpen className="w-4 h-4" />, color: '#ff6a00' },
  { id: 'live', icon: <Compass className="w-4 h-4" />, color: '#10b981' },
  { id: 'weekly', icon: <Calendar className="w-4 h-4" />, color: '#8b5cf6' },
  { id: 'history', icon: <BarChart3 className="w-4 h-4" />, color: '#e67e22' },
  { id: 'map', icon: <Network className="w-4 h-4" />, color: '#3b82f6' },
];
```

d. Change default tab:
```typescript
const [activeTab, setActiveTab] = useState<AppTab>('digest');
```

e. Add digest page rendering — in the render section, inside `{activeTab !== 'map' && (`, add before the existing content:

```tsx
{activeTab === 'digest' && (
  <DailyDigestPage aiService={aiService} language={language} />
)}
```

f. Wrap the existing `{hasDigest ? (` block so it only renders for non-digest tabs:
```tsx
{activeTab !== 'digest' && (
  <>
    {hasDigest ? (
      // ... existing content ...
    ) : (
      // ... existing loading state ...
    )}
  </>
)}
```

**Step 3: Commit**

```bash
git add src/App.tsx src/i18n/messages.ts
git commit -m "feat: add Daily Digest tab as default landing page"
```

---

## Task 9: Build Verification & End-to-End Check

**Step 1: Verify TypeScript compilation**

```bash
npm run build
```

Expected: Clean build with no errors.

**Step 2: Run the app**

```bash
npm run dev
```

Expected: App starts, default tab is "Daily Digest", can navigate between tabs, live feed still works on its own tab.

**Step 3: Verify backend endpoints**

```bash
curl http://localhost:8000/api/digest/archive
curl http://localhost:8000/api/digest/daily
```

Expected: Both return JSON responses (archive may be empty, daily may have `available: false` until the next 6 AM run or manual trigger).

**Step 4: Final commit (if any remaining changes)**

```bash
git add -A
git commit -m "feat: complete longform daily digest system with archive and personality"
```

---

## Implementation Notes

- **No React Router needed** — the existing tab navigation handles page switching. The digest tab is just another tab, keeping architecture simple.
- **Longform stored as `content_type="longform"`** — reuses the existing DailyDigest table, just adds the new column. The per-section digests (all/news/research/github) continue to work for the live feed tab.
- **Markdown rendering** — a minimal server-side converter handles bold, links, paragraphs, and bullet lists. No need for a client-side markdown library.
- **HTML sanitization** — DOMPurify sanitizes the server-rendered HTML before inserting into the DOM, with a strict allowlist of tags and attributes.
- **Link safety** — the server-side markdown converter only allows http/https URLs in links, preventing javascript: or data: URI injection.
- **Translation** — the longform HTML is translated via the existing `_translate_cached_json` pattern, preserving HTML structure.
- **Schedule unchanged** — runs at 6 AM UTC via the existing Celery beat / inline scheduler. No manual trigger.
