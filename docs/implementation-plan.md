# Data Collection Implementation Plan

## Design Language Reference

All new UI follows the existing AIPulse wireframe aesthetic:
- **Colors:** `--paper` (#f7f4ee), `--panel` (#fbf9f4), `--ink` (#111), `--accent` (#ff6a00)
- **Typography:** Bebas Neue headings, IBM Plex Mono body, uppercase + letter-spacing
- **Borders:** 2px solid/dashed, 4px solid left accent on cards
- **Shadows:** `6px 6px 0 var(--ink)` hard offset
- **Radius:** 14-16px (cards), 999px (pills/chips)
- **Icons:** Lucide React, 12-16px
- **Animations:** `wf-reveal` fade-in + slide-up, staggered `--delay`

---

## Wave 1: Foundation (Low Effort, Immediate Data)

### 1.1 Implicit Behavioral Tracking

**No visible UI.** A silent analytics module that records user behavior.

#### Backend

**New model: `UserEvent`**
```
Table: user_events
──────────────────────────────────────
id              UUID PK
session_id      Text NOT NULL          -- anonymous session identifier
user_id         UUID FK → User NULL    -- linked after auth, null for anon
event_type      Text NOT NULL          -- enum below
article_id      UUID FK → Article NULL -- which article, if applicable
payload         JSON                   -- event-specific data
created_at      DateTime               -- when it happened
```

**Event types and payloads:**

| event_type | payload | What it captures |
|---|---|---|
| `page_view` | `{tab, content_filter, referrer}` | Which view they're on |
| `article_impression` | `{article_id, position, viewport_pct}` | Card appeared in viewport |
| `article_click` | `{article_id, target: "source"|"title"}` | Clicked through to article |
| `article_dwell` | `{article_id, dwell_ms, scroll_depth_pct}` | How long they read, how far they scrolled |
| `article_copy` | `{article_id, text_length, text_preview}` | Copied text from article (first 50 chars only) |
| `digest_view` | `{content_type, dwell_ms}` | Time spent on digest panel |
| `session_start` | `{viewport_w, viewport_h, timezone}` | Device info |
| `session_heartbeat` | `{active_ms, idle_ms}` | Are they actually engaged |
| `filter_change` | `{from, to}` | Changed content tab |
| `share_click` | `{article_id, method}` | Clicked share button |

**New endpoint:**
```
POST /api/events
Body: { session_id, events: [{ event_type, article_id?, payload, timestamp }] }
Response: 204 No Content
```

Events are batched client-side and flushed every 10 seconds or on page unload (via `navigator.sendBeacon`). No response body needed.

#### Frontend

**New file: `src/services/tracker.ts`**

A singleton module imported in `App.tsx`. Hooks into:
- `IntersectionObserver` on each `NewsCard` for impression tracking
- `visibilitychange` event for session heartbeats
- `copy` event listener on document for clipboard tracking
- Timer per visible card for dwell time
- `sendBeacon` on `beforeunload` for reliable flush

**No UI components.** Completely invisible. The tracker exports hooks:
- `useTrackImpression(articleId, ref)` — attach to NewsCard wrapper
- `useTrackDwell(articleId, ref)` — measures time card is in viewport
- `trackEvent(type, payload)` — manual event logging

**Integration points:**
- `NewsCard.tsx`: Wrap card div in `useTrackImpression` + `useTrackDwell`
- `App.tsx`: Call `tracker.init(sessionId)` on mount, `tracker.flush()` on unmount
- Share button: Add `trackEvent('share_click', ...)` to existing `shareStory()`

---

### 1.2 Multi-Dimensional Article Reactions

Reaction buttons on every `NewsCard`. One tap, no modals.

#### Backend

**New model: `ArticleReaction`**
```
Table: article_reactions
──────────────────────────────────────
id              UUID PK
session_id      Text NOT NULL
user_id         UUID FK → User NULL
article_id      UUID FK → Article NOT NULL
reaction        Text NOT NULL          -- 'important' | 'overhyped' | 'misleading' | 'old_news' | 'insightful'
created_at      DateTime
```

**Constraints:** UNIQUE(session_id, article_id) — one reaction per user per article (can change, not stack)

**New endpoints:**
```
POST /api/reactions
Body: { session_id, article_id, reaction }
Response: { reaction_counts: { important: 12, overhyped: 3, ... } }

GET  /api/reactions/{article_id}
Response: { counts: { ... }, user_reaction: "important"|null }
```

#### Frontend

**Location: Bottom of each `NewsCard`, between tags and share button**

```
┌─────────────────────────────────────────────────────┐
│  [Category] Source  14:32        [Trust] [Signal 87] │
│                                                      │
│  Article Title Goes Here                             │
│  Summary text preview...                             │
│                                                      │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐           │
│  │ ⚡  │ │ 📢  │ │ ⚠   │ │ 🔄  │ │ 💡  │           │
│  │ Key │ │Hype │ │ Off │ │ Old │ │ Gem │           │
│  │ 12  │ │  3  │ │  1  │ │  0  │ │  8  │           │
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘           │
│                                                      │
│  [LLM] [Agents] [+2]    Read source ↗    [Share]    │
└─────────────────────────────────────────────────────┘
```

**Component: `ReactionBar`**

5 reaction buttons in a horizontal row. Each button:
- Lucide icon (Zap, Megaphone, AlertTriangle, RotateCcw, Lightbulb)
- Short label underneath (Key, Hype, Off, Old, Gem)
- Count underneath label
- Default state: `border: 1.5px dashed var(--grid)`, `color: var(--muted)`, `bg: transparent`
- Selected state: `border: 2px solid var(--ink)`, `bg: var(--accent-muted)`, `color: var(--ink)`, slight scale(1.05)
- Hover state: `border-color: var(--ink)`, translate-y -1px

**Styling specs:**
```css
.wf-reaction-bar {
  display: flex;
  gap: 0.4rem;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
}

.wf-reaction-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 10px;
  border: 1.5px dashed var(--grid);
  border-radius: 10px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  background: transparent;
  cursor: pointer;
  transition: all 150ms ease;
  min-width: 44px;          /* touch target */
}

.wf-reaction-btn:hover {
  border-color: var(--ink);
  transform: translateY(-1px);
}

.wf-reaction-btn--active {
  border: 2px solid var(--ink);
  background: var(--accent-muted);
  color: var(--ink);
  transform: scale(1.05);
}

.wf-reaction-count {
  font-size: 10px;
  font-weight: 600;
  color: var(--ink);
  opacity: 0.6;
}
```

**Placement in NewsCard.tsx:**
Insert `<ReactionBar>` between the summary `<p>` and the footer `.wf-card-footer`. The reaction bar sits in its own row, visually separated with a thin dashed border-top.

**Data flow:**
1. On mount: Fetch reaction counts for this article (batch with article list)
2. On click: POST reaction, optimistically update count, toggle active state
3. Clicking the same reaction again removes it (DELETE semantics via POST with null)

---

### 1.3 Reading Streaks

Track consecutive days of app usage. Show streak counter prominently in the sidebar.

#### Backend

**New model: `UserStreak`**
```
Table: user_streaks
──────────────────────────────────────
session_id      Text PK               -- or user_id when auth exists
current_streak  Integer DEFAULT 0
longest_streak  Integer DEFAULT 0
last_active_date Date                 -- last calendar date they visited
streak_shields  Integer DEFAULT 1     -- free shields (forgive 1 missed day)
total_days_active Integer DEFAULT 0
created_at      DateTime
updated_at      DateTime
```

**New endpoint:**
```
POST /api/streak/checkin
Body: { session_id }
Response: {
  current_streak: 12,
  longest_streak: 23,
  streak_alive: true,
  shield_used_today: false,
  shields_remaining: 1,
  total_days: 47
}
```

**Logic:**
- On checkin, compare `last_active_date` with today:
  - Same day → no change, return current
  - Yesterday → increment streak, update date
  - 2 days ago + shields > 0 → use shield, increment streak, update date
  - 3+ days ago (or 2 days + no shield) → reset streak to 1, update date
- Always update `longest_streak = max(longest_streak, current_streak)`

#### Frontend

**Location: Left sidebar, below the nav items**

```
┌──────────────────────────┐
│  ◆ Live Intelligence     │
│  ◆ Weekly Signal         │
│  ◆ History               │
│  ◆ Signal Map            │
│  ◆ Terminal              │
│                          │
│  ┌──────────────────┐    │
│  │  🔥 12-DAY       │    │
│  │  STREAK           │    │
│  │                    │    │
│  │  ● ● ● ● ● ● ●  │    │
│  │  M T W T F S S    │    │
│  │                    │    │
│  │  Best: 23 days    │    │
│  │  🛡 1 shield       │    │
│  └──────────────────┘    │
└──────────────────────────┘
```

**Component: `StreakWidget`**

A small card in the sidebar below navigation.

**Elements:**
- **Streak count:** Large Bebas Neue number + "DAY STREAK" label
  - Color: `var(--accent)` when active, `var(--muted)` when broken
  - Flame icon from Lucide (`Flame`) next to count
- **Week dots:** 7 circles for the current week (Mon-Sun)
  - Filled circle (`●`): day was active
  - Empty circle (`○`): day was missed
  - Today highlighted with accent border ring
  - Each dot: 8px diameter, `border: 1.5px solid var(--ink)`
  - Active dot: `background: var(--accent)`
- **Stats line:** "Best: 23 days" in small muted mono text
- **Shield indicator:** Shield icon + remaining count, small muted text

**Styling specs:**
```css
.wf-streak-widget {
  margin-top: auto;           /* push to bottom of sidebar */
  padding: 16px;
  border: 2px dashed var(--grid);
  border-radius: 14px;
  background: var(--panel);
}

.wf-streak-count {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 32px;
  line-height: 1;
  letter-spacing: 0.04em;
  color: var(--accent);
}

.wf-streak-label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.wf-streak-dots {
  display: flex;
  gap: 6px;
  margin: 12px 0 8px;
}

.wf-streak-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid var(--ink);
  background: transparent;
}

.wf-streak-dot--active {
  background: var(--accent);
}

.wf-streak-dot--today {
  box-shadow: 0 0 0 3px var(--accent-muted);
}
```

**Mobile:** On screens < lg (where sidebar is hidden), show a compact streak pill in the header bar next to the language toggle: `🔥 12` in a small bordered pill.

**Data flow:**
1. On app mount: POST `/api/streak/checkin` with session_id
2. Store response in state, render widget
3. Session_id persisted in localStorage

---

### 1.4 Digest Summary Feedback

"Was this useful?" on the digest panel. Simplest possible RLHF signal.

#### Backend

**New model: `DigestFeedback`**
```
Table: digest_feedback
──────────────────────────────────────
id              UUID PK
session_id      Text NOT NULL
user_id         UUID FK → User NULL
digest_id       UUID FK → DailyDigest NULL
content_type    Text NOT NULL          -- 'all' | 'news' | 'research' | 'github'
feedback        Text NOT NULL          -- 'helpful' | 'not_helpful'
date            Date NOT NULL
created_at      DateTime
```

**Constraints:** UNIQUE(session_id, date, content_type)

**New endpoint:**
```
POST /api/digest/feedback
Body: { session_id, content_type, feedback }
Response: { status: "ok" }
```

#### Frontend

**Location: Bottom-right of the digest panel, after the executive summary**

```
┌────────────────────────────────────────────────────────────┐
│  TODAY'S BRIEFING                                          │
│                                                            │
│  Headline Text Here                                        │
│  Executive summary paragraph goes here with the            │
│  day's key AI developments...                              │
│                                                            │
│  [LLM-Authored] [Updated 14:32]                            │
│                                                            │
│                           Was this briefing useful?         │
│                           [👍 Yes]  [👎 No]                 │
└────────────────────────────────────────────────────────────┘
```

**Component: `DigestFeedback`**

Inline in the digest panel. Two small buttons.

**Elements:**
- Question text: "Was this briefing useful?" — small mono, muted, right-aligned
- Two buttons: ThumbsUp / ThumbsDown icons (Lucide `ThumbsUp`, `ThumbsDown`)
- Default state: icon only, `color: var(--muted)`, `border: 1.5px dashed var(--grid)`, `border-radius: 10px`, `padding: 6px 12px`
- Selected state: `border: 2px solid var(--ink)`, ThumbsUp → `color: #10b981` (green), ThumbsDown → `color: var(--accent)` (orange)
- After selection: Buttons replaced with "Thanks for the feedback" text (same style, fades in)

**Styling specs:**
```css
.wf-digest-feedback {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  justify-content: flex-end;
  margin-top: 1rem;
  padding-top: 0.75rem;
  border-top: 1px dashed var(--grid);
}

.wf-digest-feedback__label {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.wf-digest-feedback__btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1.5px dashed var(--grid);
  border-radius: 10px;
  background: transparent;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 500;
  color: var(--muted);
  cursor: pointer;
  transition: all 150ms ease;
}

.wf-digest-feedback__btn:hover {
  border-color: var(--ink);
  color: var(--ink);
}

.wf-digest-feedback__thanks {
  font-size: 10px;
  font-weight: 500;
  color: var(--muted);
  letter-spacing: 0.06em;
  animation: wf-reveal 300ms ease both;
}
```

---

## Wave 2: Engagement & Rich Data (Medium Effort)

### 2.1 Weekly AI Quiz

A new tab/page accessible from the sidebar. Auto-generated from the week's top stories.

#### Backend

**New models:**

```
Table: quizzes
──────────────────────────────────────
id              UUID PK
week_start      Date NOT NULL          -- Monday of the quiz week
title           Text                   -- "AI IQ — Week of Mar 10"
questions       JSON NOT NULL          -- array of question objects (see below)
source_article_ids JSON               -- articles used to generate questions
generated_at    DateTime
published       Boolean DEFAULT false

Table: quiz_attempts
──────────────────────────────────────
id              UUID PK
quiz_id         UUID FK → Quiz NOT NULL
session_id      Text NOT NULL
user_id         UUID FK → User NULL
answers         JSON NOT NULL          -- [{question_idx, selected_option, correct, time_ms}]
score           Integer NOT NULL       -- number correct
total           Integer NOT NULL
completed_at    DateTime
```

**Question JSON structure:**
```json
{
  "question": "Which company released a 405B parameter model this week?",
  "options": ["OpenAI", "Meta", "Anthropic", "Google"],
  "correct_idx": 1,
  "difficulty": "medium",
  "article_id": "uuid-of-source-article",
  "explanation": "Meta released Llama 3.1 405B on March 8th.",
  "topic": "llms"
}
```

**New endpoints:**
```
GET  /api/quiz/current
Response: { quiz_id, title, questions: [{question, options}], total }
(correct_idx omitted until submission)

POST /api/quiz/submit
Body: { quiz_id, session_id, answers: [{question_idx, selected_option, time_ms}] }
Response: {
  score: 7,
  total: 10,
  results: [{correct, correct_answer, explanation, article_id}],
  percentile: 82,
  streak_bonus: true
}

GET  /api/quiz/leaderboard
Query: ?week_start=2026-03-09
Response: {
  entries: [{rank, display_name, score, time_total_ms}],
  user_rank: 14,
  total_participants: 342
}
```

**Quiz generation:** Backend LLM task (weekly cron or manual trigger):
1. Gather top 20 articles from the week (by global_score)
2. Prompt LLM with article titles + summaries: "Generate 10 multiple-choice questions..."
3. Store in `quizzes` table
4. Questions span different topics and difficulty levels

#### Frontend

**Location: New sidebar nav item "Quiz" between "Weekly Signal" and "History"**

Nav item: `{ id: 'quiz', en: 'AI IQ Quiz', zh: 'AI 知识测试', icon: <BrainCircuit />, color: '#f59e0b' }`

**Quiz Page Layout:**

```
┌──────────────────────────────────────────────────────────────────┐
│  AI IQ — WEEK OF MAR 10                                         │
│  342 practitioners tested · avg score 6.8/10                    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  QUESTION 3 OF 10                         [● ● ● ○ ○ …] │    │
│  │                                                          │    │
│  │  Which company announced a $2B investment in             │    │
│  │  European AI infrastructure this week?                   │    │
│  │                                                          │    │
│  │  ┌──────────────────────────────────────────────────┐    │    │
│  │  │  A.  Microsoft                                    │    │    │
│  │  └──────────────────────────────────────────────────┘    │    │
│  │  ┌──────────────────────────────────────────────────┐    │    │
│  │  │  B.  Google                                       │    │    │
│  │  └──────────────────────────────────────────────────┘    │    │
│  │  ┌──────────────────────────────────────────────────┐    │    │
│  │  │  C.  Amazon                                       │    │    │
│  │  └──────────────────────────────────────────────────┘    │    │
│  │  ┌──────────────────────────────────────────────────┐    │    │
│  │  │  D.  NVIDIA                                       │    │    │
│  │  └──────────────────────────────────────────────────┘    │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  [← Previous]                                    [Next →]        │
└──────────────────────────────────────────────────────────────────┘
```

**After answering (reveal state):**

```
│  │  ┌──────────────────────────────────────────────────┐    │
│  │  │  A.  Microsoft                          ✓ CORRECT │    │
│  │  └────── border: 2px solid #10b981 ─────────────────┘    │
│  │  ┌──────────────────────────────────────────────────┐    │
│  │  │  B.  Google                                       │    │
│  │  └──────────────────────────────────────────────────┘    │
│  │                                                          │
│  │  Microsoft announced a €1.6B ($2B) investment in         │
│  │  Swedish AI data centers on March 8th.                   │
│  │                       [Read source article →]            │
```

**Results screen (after all 10 questions):**

```
┌──────────────────────────────────────────────────────────────┐
│                                                               │
│              YOUR SCORE                                       │
│                                                               │
│              ┌──────────┐                                     │
│              │          │                                     │
│              │  8 / 10  │                                     │
│              │          │                                     │
│              └──────────┘                                     │
│                                                               │
│       TOP 18% OF PRACTITIONERS                                │
│                                                               │
│  ┌─────────────────────────────┐                              │
│  │  Strong: LLMs, Hardware     │                              │
│  │  Weak: Policy, Startups     │                              │
│  └─────────────────────────────┘                              │
│                                                               │
│  🔥 Streak extended! 13 days                                  │
│                                                               │
│  [Share Score]          [View Leaderboard]                     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

**Component structure:**
- `QuizPage.tsx` — container with state machine (loading → question → reveal → results)
- `QuizQuestion.tsx` — question card with option buttons
- `QuizResults.tsx` — score card with topic breakdown
- `QuizLeaderboard.tsx` — ranked list of participants

**Styling:**

Option buttons:
```css
.wf-quiz-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border: 2px dashed var(--grid);
  border-radius: 14px;
  background: var(--panel);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 150ms ease;
  width: 100%;
  text-align: left;
}

.wf-quiz-option:hover {
  border-color: var(--ink);
  border-style: solid;
  transform: translateY(-2px);
  box-shadow: 4px 4px 0 var(--ink);
}

.wf-quiz-option--selected {
  border: 2px solid var(--ink);
  background: var(--accent-muted);
}

.wf-quiz-option--correct {
  border: 2px solid #10b981;
  background: rgba(16, 185, 129, 0.12);
}

.wf-quiz-option--wrong {
  border: 2px solid #f43f5e;
  background: rgba(244, 63, 94, 0.08);
}
```

Score card:
```css
.wf-quiz-score {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 64px;
  line-height: 1;
  letter-spacing: 0.04em;
  text-align: center;
  border: 3px solid var(--ink);
  border-radius: 16px;
  padding: 24px 32px;
  box-shadow: 6px 6px 0 var(--ink);
  display: inline-block;
}
```

Progress dots (top of question card):
```css
.wf-quiz-progress {
  display: flex;
  gap: 6px;
}

.wf-quiz-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid var(--ink);
}

.wf-quiz-dot--correct { background: #10b981; }
.wf-quiz-dot--wrong { background: #f43f5e; }
.wf-quiz-dot--current { box-shadow: 0 0 0 3px var(--accent-muted); }
.wf-quiz-dot--pending { background: transparent; }
```

**Share card:** Generate a shareable image/card: "I scored 8/10 on this week's AI IQ Quiz on AIPulse." Uses same wireframe aesthetic. Share via native share API (existing pattern in NewsCard).

---

### 2.2 A/B Summary Voting

Occasionally show users two summary versions of the same story and ask which is better.

#### Backend

**New models:**

```
Table: summary_pairs
──────────────────────────────────────
id              UUID PK
article_id      UUID FK → Article NOT NULL
cluster_id      UUID FK → Cluster NULL
summary_a       Text NOT NULL
summary_b       Text NOT NULL
generator_a     Text                   -- 'llm_v1' | 'llm_v2' | 'extractive' | 'user_edit'
generator_b     Text
created_at      DateTime
active          Boolean DEFAULT true

Table: summary_votes
──────────────────────────────────────
id              UUID PK
pair_id         UUID FK → SummaryPair NOT NULL
session_id      Text NOT NULL
user_id         UUID FK → User NULL
choice          Text NOT NULL          -- 'a' | 'b' | 'skip'
time_ms         Integer                -- how long they deliberated
created_at      DateTime
```

**Constraints:** UNIQUE(pair_id, session_id)

**New endpoints:**
```
GET  /api/vote/next
Query: ?session_id=xxx
Response: { pair_id, article_title, summary_a, summary_b }
(or 204 if no pairs available)

POST /api/vote
Body: { pair_id, session_id, choice, time_ms }
Response: { votes_a: 23, votes_b: 41, total_votes_cast: 5 }
```

**Pair generation:** Cron job runs daily:
1. Pick top articles from last 24 hours
2. Generate 2 summaries with different LLM temperatures/prompts
3. Store as summary_pair

#### Frontend

**Location: Inline in the news feed, inserted every ~8 cards as a special card**

The vote card replaces a regular NewsCard position in the grid (spans full width like featured card).

```
┌──────────────────────────────────────────────────────────────────┐
│  ⚖  WHICH SUMMARY IS BETTER?         Community Picks · 64 votes │
│                                                                   │
│  Re: "OpenAI Announces GPT-5 with Native Tool Use"              │
│                                                                   │
│  ┌───────────────────────────┐  ┌───────────────────────────┐    │
│  │                           │  │                           │    │
│  │  Summary A text goes      │  │  Summary B text goes      │    │
│  │  here. It focuses on      │  │  here. It takes a         │    │
│  │  the technical details    │  │  different angle on       │    │
│  │  of the announcement...   │  │  the announcement...      │    │
│  │                           │  │                           │    │
│  │       [Pick This]         │  │       [Pick This]         │    │
│  └───────────────────────────┘  └───────────────────────────┘    │
│                                                                   │
│                         [Skip →]                                  │
└──────────────────────────────────────────────────────────────────┘
```

**After voting (reveal state):**

```
│  ┌───────── 36% ────────────┐  ┌───────── 64% ✓ ──────────┐    │
│  │                           │  │                           │    │
│  │  (same text, now with     │  │  (same text, with green   │    │
│  │  muted opacity)           │  │  left border accent)      │    │
│  │                           │  │                           │    │
│  └───────────────────────────┘  └───────────────────────────┘    │
│                                                                   │
│  Thanks! Your vote helps improve our AI summaries.               │
```

**Component: `SummaryVoteCard.tsx`**

**Styling:**
```css
.wf-vote-card {
  grid-column: 1 / -1;         /* span full width */
  border: 2px solid var(--ink);
  border-radius: 16px;
  background: var(--panel);
  padding: 24px;
  box-shadow: 6px 6px 0 var(--ink);
}

.wf-vote-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.wf-vote-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 720px) {
  .wf-vote-pair {
    grid-template-columns: 1fr;
  }
}

.wf-vote-summary {
  padding: 18px;
  border: 2px dashed var(--grid);
  border-radius: 14px;
  font-size: 12px;
  line-height: 1.7;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.wf-vote-summary:hover {
  border-color: var(--ink);
  border-style: solid;
}

.wf-vote-summary--winner {
  border-color: #10b981;
  border-style: solid;
  border-left-width: 4px;
}

.wf-vote-pick-btn {
  align-self: center;
  padding: 8px 20px;
  border: 2px solid var(--ink);
  border-radius: 999px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  cursor: pointer;
  background: transparent;
  transition: all 150ms ease;
}

.wf-vote-pick-btn:hover {
  background: var(--accent-muted);
  box-shadow: 3px 3px 0 var(--ink);
  transform: translateY(-2px);
}
```

---

### 2.3 Highlight + Annotate

Users can highlight text passages in article summaries displayed in the app.

#### Backend

**New model: `Highlight`**
```
Table: highlights
──────────────────────────────────────
id              UUID PK
session_id      Text NOT NULL
user_id         UUID FK → User NULL
article_id      UUID FK → Article NOT NULL
text            Text NOT NULL          -- the highlighted passage
start_offset    Integer                -- character offset in summary
end_offset      Integer
note            Text NULL              -- optional annotation
created_at      DateTime
```

**New endpoints:**
```
POST /api/highlights
Body: { session_id, article_id, text, start_offset, end_offset, note? }
Response: { id, popular_count }

GET  /api/highlights/{article_id}/popular
Response: { highlights: [{text, count, start_offset, end_offset}] }

DELETE /api/highlights/{id}
Body: { session_id }
Response: 204
```

#### Frontend

**Interaction: Text selection on article summaries**

When a user selects text inside a `wf-card-summary`, a small floating toolbar appears above the selection:

```
                    ┌─────────────────┐
                    │ 💡 Save  │ 📝 Note │
                    └─────────────────┘
     "This is the selected text that the
      user highlighted with their cursor"
```

**Component: `HighlightToolbar.tsx`**

A floating div positioned above the selection using `window.getSelection().getRangeAt(0).getBoundingClientRect()`.

**Elements:**
- Save button: Lightbulb icon + "Save" — highlights the text with a yellow background
- Note button: Edit3 icon + "Note" — opens a small inline text input below the highlight

**Saved highlights appearance:**
```css
.wf-highlight {
  background: rgba(255, 106, 0, 0.15);    /* accent, subtle */
  border-bottom: 2px solid var(--accent);
  padding: 1px 2px;
  border-radius: 2px;
  cursor: pointer;
}

.wf-highlight:hover {
  background: rgba(255, 106, 0, 0.25);
}
```

**Popular highlights:** If an article has passages highlighted by 3+ users, show a subtle indicator:
- Small eye icon + count floats to the right of popular passages
- `"12 readers highlighted this"` tooltip on hover

**Floating toolbar styling:**
```css
.wf-highlight-toolbar {
  position: absolute;
  display: flex;
  gap: 2px;
  padding: 4px;
  border: 2px solid var(--ink);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: 4px 4px 0 var(--ink);
  z-index: 100;
  animation: wf-reveal 150ms ease both;
}

.wf-highlight-toolbar__btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  cursor: pointer;
}

.wf-highlight-toolbar__btn:hover {
  background: var(--accent-muted);
}
```

**Note on expanded article view:** Highlights work best when the full summary is visible. Consider expanding the summary on click (remove line-clamp) so users can highlight longer passages.

---

### 2.4 AI Expertise Score + Profile

A points system that accumulates as users interact. Visible on profile and leaderboard.

#### Backend

**New model: `UserProfile`**
```
Table: user_profiles
──────────────────────────────────────
session_id      Text PK
display_name    Text NULL              -- optional, for leaderboard
expertise_score Integer DEFAULT 0
level           Integer DEFAULT 1
articles_read   Integer DEFAULT 0
quizzes_taken   Integer DEFAULT 0
quiz_avg_score  Float DEFAULT 0
predictions_made Integer DEFAULT 0
reactions_given  Integer DEFAULT 0
highlights_made  Integer DEFAULT 0
votes_cast      Integer DEFAULT 0
top_topics      JSON DEFAULT '[]'      -- computed from reading patterns
reader_archetype Text NULL             -- 'The Researcher' | 'The Trend Spotter' | etc.
created_at      DateTime
updated_at      DateTime
```

**Points system:**
| Action | Points |
|---|---|
| Daily visit (streak checkin) | +5 |
| Read article (dwell > 30s) | +2 |
| React to article | +3 |
| Take quiz | +10 |
| Quiz correct answer | +5 |
| Cast summary vote | +3 |
| Highlight passage | +2 |
| Add note to highlight | +5 |
| Prediction made | +8 |

**Levels:**
- Level 1: Observer (0-50 pts)
- Level 2: Reader (51-200)
- Level 3: Analyst (201-500)
- Level 4: Expert (501-1200)
- Level 5: Authority (1200+)

**Reader archetypes** (computed weekly from topic distribution):
- "The Researcher" — reads mostly research papers
- "The Trend Spotter" — reads across all categories evenly
- "The Insider" — focuses on industry + startup news
- "The Policy Hawk" — heavy policy/safety reading
- "The Builder" — focuses on GitHub + tools
- "The Skeptic" — high ratio of "overhyped" / "misleading" reactions

**New endpoint:**
```
GET /api/profile/{session_id}
Response: {
  display_name, expertise_score, level, level_name,
  articles_read, quizzes_taken, quiz_avg_score,
  top_topics, reader_archetype,
  next_level_at, progress_pct
}
```

#### Frontend

**Location: Sidebar, above the streak widget. Also accessible as a full page.**

**Sidebar compact view:**
```
┌──────────────────────────┐
│  LEVEL 3 · ANALYST       │
│  ████████░░░  412 / 500  │
│  ⚡ 412 pts              │
│                          │
│  "The Trend Spotter"     │
└──────────────────────────┘
```

**Component: `ExpertiseWidget`**

**Elements:**
- Level label: Small uppercase chip, `border: 2px solid var(--ink)`, current level name
- Progress bar: Full width, height 6px, `border: 1.5px solid var(--ink)`, `border-radius: 999px`
  - Fill: `background: var(--accent)`, width = progress_pct%
- Points: Zap icon + score in mono font
- Archetype: Italic mono text, muted color, in quotes

```css
.wf-expertise-widget {
  padding: 14px 16px;
  border: 2px dashed var(--grid);
  border-radius: 14px;
  background: var(--panel);
  margin-bottom: 12px;
}

.wf-expertise-level {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--ink);
}

.wf-expertise-bar {
  width: 100%;
  height: 6px;
  border: 1.5px solid var(--ink);
  border-radius: 999px;
  margin: 8px 0 6px;
  overflow: hidden;
}

.wf-expertise-bar__fill {
  height: 100%;
  background: var(--accent);
  border-radius: 999px;
  transition: width 500ms ease;
}

.wf-expertise-pts {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
}

.wf-expertise-archetype {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-style: italic;
  color: var(--muted);
  margin-top: 6px;
}
```

---

## Wave 3: Differentiation (Higher Effort, Moat-Building)

### 3.1 Prediction Market

Users predict outcomes on significant stories. Track accuracy over time.

#### Backend

**New models:**

```
Table: predictions
──────────────────────────────────────
id              UUID PK
article_id      UUID FK → Article NOT NULL
cluster_id      UUID FK → Cluster NULL
question        Text NOT NULL          -- "Will this matter in 6 months?"
prediction_type Text NOT NULL          -- 'binary' | 'scale' | 'timeline'
options         JSON NULL              -- for binary: null, for scale: labels
resolution_date Date NULL              -- when to check outcome
resolved        Boolean DEFAULT false
resolution      Text NULL              -- the actual outcome
created_at      DateTime

Table: user_predictions
──────────────────────────────────────
id              UUID PK
prediction_id   UUID FK → Prediction NOT NULL
session_id      Text NOT NULL
user_id         UUID FK → User NULL
choice          Text NOT NULL          -- 'yes'|'no' for binary, or scale value
confidence      Integer                -- 50-99 percent
reasoning       Text NULL              -- optional one-sentence reason
created_at      DateTime
updated_at      DateTime               -- can update prediction
```

**Constraints:** UNIQUE(prediction_id, session_id)

**New endpoints:**
```
GET  /api/predictions/active
Response: [{ id, question, article_title, prediction_type, options, vote_counts, your_prediction? }]

POST /api/predictions/vote
Body: { prediction_id, session_id, choice, confidence, reasoning? }
Response: { distribution: { yes: 64, no: 36 }, total_votes: 89 }

GET  /api/predictions/track-record/{session_id}
Response: {
  total: 23,
  correct: 16,
  accuracy: 0.70,
  calibration: [{ confidence_bucket: 70, actual_accuracy: 0.68 }, ...],
  brier_score: 0.18
}
```

#### Frontend

**Location: Inline in news feed, attached to high-significance articles**

On articles with score >= 75, a prediction prompt appears below the summary:

```
┌─────────────────────────────────────────────────────┐
│  [Category] Source  14:32        [Trust] [Signal 87] │
│                                                      │
│  Article Title Goes Here                             │
│  Summary text...                                     │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  📊 PREDICT                                    │  │
│  │  Will this matter in 6 months?                 │  │
│  │                                                │  │
│  │  [Transformative] [Significant] [Forgettable]  │  │
│  │                                                │  │
│  │  Confidence: ──────●────── 75%                 │  │
│  │                                                │  │
│  │  Why? (optional) [____________________]        │  │
│  │                                                │  │
│  │  Community: 64% say Significant · 89 votes     │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  [⚡ Key] [📢 Hype] ...     Read source    [Share]  │
└─────────────────────────────────────────────────────┘
```

**Component: `PredictionPrompt.tsx`**

Embedded inside NewsCard for qualifying articles. Collapsible — shows just "📊 Predict" header by default, expands on click.

**Choice buttons:** Same style as quiz options but horizontal pills
**Confidence slider:** Native range input styled to match:
```css
.wf-confidence-slider {
  -webkit-appearance: none;
  width: 100%;
  height: 6px;
  border: 1.5px solid var(--ink);
  border-radius: 999px;
  background: var(--panel);
  outline: none;
}

.wf-confidence-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border: 2px solid var(--ink);
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
}
```

**Reasoning input:** Single-line text input, dashed border, mono font, placeholder "One sentence: why?"

---

### 3.2 "Spot the AI" Game

Mix AI-generated and human-written summaries. Users guess which is which.

#### Backend

**New models:**

```
Table: spot_ai_rounds
──────────────────────────────────────
id              UUID PK
article_id      UUID FK → Article NOT NULL
human_summary   Text NOT NULL          -- original/editorial summary
ai_summary      Text NOT NULL          -- LLM-generated summary
human_position  Text NOT NULL          -- 'a' | 'b' (randomized)
created_at      DateTime
active          Boolean DEFAULT true

Table: spot_ai_guesses
──────────────────────────────────────
id              UUID PK
round_id        UUID FK → SpotAIRound NOT NULL
session_id      Text NOT NULL
user_id         UUID FK → User NULL
guess           Text NOT NULL          -- 'a' | 'b' (which they think is AI)
correct         Boolean NOT NULL
time_ms         Integer
created_at      DateTime
```

**New endpoints:**
```
GET  /api/spot-ai/round
Response: { round_id, article_title, summary_a, summary_b }

POST /api/spot-ai/guess
Body: { round_id, session_id, guess, time_ms }
Response: {
  correct: true,
  ai_was: "b",
  community_accuracy: 0.62,
  your_streak: 5,
  detection_skill: "Sharp-eyed"
}
```

#### Frontend

**Location: Accessible from sidebar as a sub-item under Quiz, or as a card in the feed**

```
┌──────────────────────────────────────────────────────────────┐
│  🤖 SPOT THE AI                          Round 3 · 🎯 4/5    │
│                                                               │
│  Both summaries describe the same article.                   │
│  Which one was written by AI?                                │
│                                                               │
│  ┌──────────────────────────┐  ┌──────────────────────────┐  │
│  │                          │  │                          │  │
│  │  Summary A               │  │  Summary B               │  │
│  │  "OpenAI announced a     │  │  "In a significant move, │  │
│  │  new reasoning model     │  │  OpenAI has unveiled      │  │
│  │  that outperforms..."    │  │  their latest reasoning   │  │
│  │                          │  │  model which surpasses..."│  │
│  │                          │  │                          │  │
│  │   [This is the AI 🤖]   │  │   [This is the AI 🤖]   │  │
│  └──────────────────────────┘  └──────────────────────────┘  │
│                                                               │
│  Community accuracy: 62% get it right                        │
└──────────────────────────────────────────────────────────────┘
```

Same two-column layout as A/B voting. After guessing, the AI summary gets a `border-left: 4px solid var(--accent)` indicator and the reveal text shows: "The AI summary was B. 62% of readers spotted it correctly."

---

### 3.3 Monthly Wrapped Report

Personalized monthly reading report with shareable cards.

#### Backend

**New endpoint:**
```
GET /api/wrapped/{session_id}
Query: ?month=2026-03
Response: {
  month: "March 2026",
  articles_read: 147,
  total_time_minutes: 342,
  top_topics: [{ topic: "LLMs", count: 43, pct: 29 }, ...],
  top_entities: [{ entity: "OpenAI", count: 22 }, ...],
  reader_archetype: "The Trend Spotter",
  prediction_accuracy: 0.73,
  quiz_avg: 7.2,
  streak_best: 23,
  percentile_reading: 94,
  percentile_quiz: 78,
  highlights_count: 34,
  reactions_count: 89,
  share_cards: [
    { type: "top_topics", image_url: "...", text: "My top AI topics in March: LLMs, Agents, Hardware" },
    { type: "score", image_url: "...", text: "Top 6% reader on AIPulse this month" }
  ]
}
```

Computed from aggregated `user_events`, `quiz_attempts`, `user_predictions`, `article_reactions`, `highlights`.

#### Frontend

**Location: New sidebar nav item or accessible from profile**

**Full-page scrollable report with sections:**

```
┌──────────────────────────────────────────────────────────────┐
│                                                               │
│              YOUR MARCH 2026 INTELLIGENCE REPORT              │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  147 ARTICLES READ                                    │    │
│  │  5.7 hours of reading                                │    │
│  │  Top 6% of all readers                               │    │
│  │                                         [Share 📤]   │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  YOUR TOP TOPICS                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  LLMs          ████████████████████░░░░░░░░  29%     │    │
│  │  Agents        ██████████████░░░░░░░░░░░░░░  22%     │    │
│  │  Hardware      ██████████░░░░░░░░░░░░░░░░░░  16%     │    │
│  │  Safety        ████████░░░░░░░░░░░░░░░░░░░░  13%     │    │
│  │  Startups      ██████░░░░░░░░░░░░░░░░░░░░░░  10%     │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  YOUR READER TYPE                                             │
│  ┌──────────────────────────────────────────────────────┐    │
│  │           "THE TREND SPOTTER"                         │    │
│  │  You read broadly across categories,                  │    │
│  │  always looking for the next big shift.               │    │
│  │                                         [Share 📤]   │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  PREDICTIONS                                                  │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Accuracy: 73%          Calibration: Well-calibrated  │    │
│  │  23 predictions made    16 resolved correctly         │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  QUIZ PERFORMANCE                                             │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Average: 7.2 / 10     Top 22% of quiz takers        │    │
│  │  Strongest: Hardware    Weakest: Policy               │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  🔥 BEST STREAK: 23 DAYS                                     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

Each section card uses the standard `wf-panel` styling with hard shadows. Share buttons on key cards use the existing native share pattern.

**Styling:** Each stat card follows the wireframe panel pattern:
```css
.wf-wrapped-card {
  border: 2px solid var(--ink);
  border-radius: 16px;
  padding: 24px;
  background: var(--panel);
  box-shadow: 6px 6px 0 var(--ink);
  margin-bottom: 20px;
}

.wf-wrapped-stat {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 48px;
  line-height: 1;
  letter-spacing: 0.04em;
}

.wf-wrapped-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 6px 0;
}

.wf-wrapped-bar__fill {
  height: 12px;
  background: var(--accent);
  border: 1.5px solid var(--ink);
  border-radius: 999px;
}

.wf-wrapped-bar__label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  font-weight: 500;
  min-width: 80px;
}
```

---

## Wave 4: From Original Strategy

These features were defined in `data-collection-strategy.md` and are built on top of the Wave 1-3 foundation.

### 4.1 AI Tool Stack Tracking
- Profile page: "What do you use?" section
- Predefined list of AI tools/models/APIs with search
- Toggle on/off, track changes over time
- Backend: `UserToolStack` model with `tool_name`, `category`, `added_at`, `removed_at`, `switch_reason`

### 4.2 Claim Verification
- Extend article model with extracted claims (JSON array)
- Each claim rendered as an interactive chip in the article card
- Users tap to verify/dispute with one-sentence reason
- Backend: `ClaimVerification` model

### 4.3 Cross-Article Linking
- "Related" button on each card
- Opens a modal to search and link another article
- Relationship type picker (caused_by, responds_to, contradicts, builds_on, competes_with)
- Backend: `ArticleLink` model with directional relationship

### 4.4 Translation Corrections
- On ZH view, each sentence is clickable
- Click opens inline edit with original EN text above
- Backend: `TranslationCorrection` model

---

## Database Migration Plan

Each wave gets its own Alembic migration:

```
alembic/versions/
  0006_wave1_tracking.py        -- UserEvent, ArticleReaction, UserStreak, DigestFeedback
  0007_wave2_engagement.py      -- Quiz, QuizAttempt, SummaryPair, SummaryVote, Highlight, UserProfile
  0008_wave3_advanced.py        -- Prediction, UserPrediction, SpotAIRound, SpotAIGuess
  0009_wave4_extensions.py      -- UserToolStack, ClaimVerification, ArticleLink, TranslationCorrection
```

---

## New API Route Files

```
ai_news/app/api/
  routes_news.py          (existing)
  routes_compat.py        (existing)
  routes_tracking.py      (NEW — events, streaks, profile)
  routes_reactions.py     (NEW — reactions, highlights, digest feedback)
  routes_quiz.py          (NEW — quiz, spot-the-ai)
  routes_voting.py        (NEW — summary votes, predictions)
  routes_wrapped.py       (NEW — monthly reports)
```

Register in `main.py`:
```python
app.include_router(tracking_router)
app.include_router(reactions_router)
app.include_router(quiz_router)
app.include_router(voting_router)
app.include_router(wrapped_router)
```

---

## New Frontend Files

```
src/
  components/
    NewsCard.tsx              (MODIFY — add ReactionBar, PredictionPrompt)
    BreakingAlert.tsx         (existing, no changes)
    ReactionBar.tsx           (NEW)
    StreakWidget.tsx           (NEW)
    ExpertiseWidget.tsx        (NEW)
    DigestFeedback.tsx         (NEW)
    HighlightToolbar.tsx       (NEW)
    PredictionPrompt.tsx       (NEW)
    SummaryVoteCard.tsx        (NEW)
    QuizPage.tsx              (NEW)
    QuizQuestion.tsx           (NEW)
    QuizResults.tsx            (NEW)
    QuizLeaderboard.tsx        (NEW)
    SpotAIGame.tsx            (NEW)
    WrappedReport.tsx          (NEW)
  services/
    aiService.ts              (MODIFY — add new API methods)
    tracker.ts                (NEW — behavioral tracking module)
  hooks/
    useTracker.ts             (NEW — impression + dwell hooks)
  styles/
    global.css                (MODIFY — add new component classes)
  App.tsx                     (MODIFY — add new nav items, routes)
```

---

## Integration Summary

### NewsCard.tsx Changes
```
Before:
  [Meta row]
  [Title]
  [Summary]
  [Footer: tags | link | share]

After:
  [Meta row]
  [Title]
  [Summary (highlightable)]
  [Prediction prompt (if score >= 75)]    ← NEW
  [Reaction bar]                          ← NEW
  [Footer: tags | link | share]
```

### App.tsx Changes
- New nav items: Quiz (Wave 2)
- New state: `streakData`, `profileData`, `activeQuiz`
- Initialize tracker on mount
- Insert `SummaryVoteCard` every ~8 items in news grid
- Add `StreakWidget` and `ExpertiseWidget` to sidebar
- Add `DigestFeedback` to digest panel

### Sidebar Layout (Final)
```
┌──────────────────────────┐
│  AI PULSE                │
│                          │
│  ◆ Live Intelligence     │
│  ◆ Weekly Signal         │
│  ◆ AI IQ Quiz            │  ← NEW
│  ◆ History               │
│  ◆ Signal Map            │
│  ◆ Terminal              │
│                          │
│  ┌──────────────────┐    │
│  │ LEVEL 3 · ANALYST│    │  ← NEW
│  │ ████████░░ 412pt │    │
│  │ "Trend Spotter"  │    │
│  └──────────────────┘    │
│                          │
│  ┌──────────────────┐    │
│  │ 🔥 12-DAY STREAK │    │  ← NEW
│  │ ● ● ● ● ● ○ ○   │    │
│  │ Best: 23 · 🛡 1   │    │
│  └──────────────────┘    │
└──────────────────────────┘
```
