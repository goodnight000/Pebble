# Bilingual Localization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current toggle-time translation behavior with a stable bilingual architecture that localizes UI copy and content consistently across live digest, weekly, and signal map surfaces.

**Architecture:** Introduce a frontend locale layer for fixed copy and persisted locale state, then migrate API consumption from client-side translation to locale-aware backend responses. English remains canonical editorial data; Chinese is served as a cached localized display variant with explicit readiness state.

**Tech Stack:** React 19, TypeScript, Vite, FastAPI, Python, Playwright, tsx scripts

---

### Task 1: Add Frontend Locale Infrastructure

**Files:**
- Create: `src/i18n/messages.ts`
- Create: `src/i18n/index.tsx`
- Modify: `src/types/index.ts`
- Modify: `src/App.tsx`

**Step 1: Write the failing test**

Add a focused frontend test or render-check that asserts:
- locale defaults to English when no preference exists
- locale can switch to Chinese without mutating content objects in-place
- refresh logic no longer forces locale back to English

**Step 2: Run test to verify it fails**

Run: `npm run build`
Expected: build still passes, but the checked behavior is absent in the current implementation.

**Step 3: Write minimal implementation**

Add:
- a `Locale` type and message dictionaries
- `getLocale`, `setLocale`, and `t()` helpers or a small context hook
- persisted locale state in `App.tsx`
- refresh logic that respects current locale

**Step 4: Run test to verify it passes**

Run: `npm run build`
Expected: PASS with locale wiring in place.

### Task 2: Move Fixed UI Copy To Dictionaries

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/components/NewsCard.tsx`
- Modify: `src/components/BreakingAlert.tsx`
- Modify: `src/components/SignalMap.tsx`
- Modify: `src/components/SignalMapList.tsx`
- Modify: `src/components/ClusterDrawer.tsx`
- Modify: `src/components/TopicSidebar.tsx`

**Step 1: Write the failing test**

Add assertions or snapshots that cover:
- nav labels
- trust labels
- CTA labels
- empty states
- signal-map drawer labels

**Step 2: Run test to verify it fails**

Run: `npm run build`
Expected: current code still contains inline language ternaries and English-only strings.

**Step 3: Write minimal implementation**

Replace inline string branching with dictionary lookups and shared label helpers. Keep the visual layout unchanged except where longer Chinese copy requires small spacing adjustments.

**Step 4: Run test to verify it passes**

Run: `npm run build`
Expected: PASS with stable locale-driven UI chrome.

### Task 3: Remove Toggle-Time Client Translation

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/services/aiService.ts`

**Step 1: Write the failing test**

Add checks that assert:
- switching locale no longer calls a whole-digest translate endpoint
- app state does not maintain a separate ad hoc `chineseDigest` cache
- locale switches preserve the active tab and current filters

**Step 2: Run test to verify it fails**

Run: `npm run build`
Expected: current app still depends on `translateDigest()` and `chineseDigest`.

**Step 3: Write minimal implementation**

Refactor `App.tsx` to:
- keep a single locale state
- fetch locale-aware content instead of translating a fetched English digest
- remove direct dependency on `translateDigest()`

**Step 4: Run test to verify it passes**

Run: `npm run build`
Expected: PASS with simplified locale switching flow.

### Task 4: Add Locale-Aware Digest API

**Files:**
- Modify: `ai_news/app/api/routes_compat.py`
- Modify: `ai_news/app/llm/client.py`
- Create: `ai_news/tests/test_localized_digest.py`

**Step 1: Write the failing test**

Add API tests asserting:
- `/api/digest/today?locale=en` returns English content with `translationStatus=ready`
- `/api/digest/today?locale=zh` returns localized display fields when available
- translation-disabled conditions return `translationStatus=unavailable` instead of pretending to be localized

**Step 2: Run test to verify it fails**

Run: `pytest ai_news/tests/test_localized_digest.py -v`
Expected: FAIL because the current route is locale-agnostic and translation has no explicit state.

**Step 3: Write minimal implementation**

Add:
- locale query handling
- a localized response envelope
- cached display-text translation for zh
- explicit `translationStatus`

**Step 4: Run test to verify it passes**

Run: `pytest ai_news/tests/test_localized_digest.py -v`
Expected: PASS

### Task 5: Localize Weekly Surface

**Files:**
- Modify: `ai_news/app/api/routes_compat.py`
- Create: `ai_news/tests/test_localized_weekly.py`
- Modify: `src/services/aiService.ts`
- Modify: `src/App.tsx`

**Step 1: Write the failing test**

Add tests asserting weekly responses honor locale and expose explicit translation state when needed.

**Step 2: Run test to verify it fails**

Run: `pytest ai_news/tests/test_localized_weekly.py -v`
Expected: FAIL because weekly content is currently English-only.

**Step 3: Write minimal implementation**

Update weekly endpoint and frontend fetch logic to request locale-aware weekly content and render it without special casing.

**Step 4: Run test to verify it passes**

Run: `pytest ai_news/tests/test_localized_weekly.py -v`
Expected: PASS

### Task 6: Localize Signal Map Surface

**Files:**
- Modify: `ai_news/app/api/routes_signal_map.py`
- Create: `ai_news/tests/test_localized_signal_map.py`
- Modify: `src/services/aiService.ts`
- Modify: `src/components/SignalMap.tsx`
- Modify: `src/components/SignalMapList.tsx`
- Modify: `src/components/ClusterDrawer.tsx`
- Modify: `src/components/TopicSidebar.tsx`

**Step 1: Write the failing test**

Add tests asserting:
- cluster headlines are locale-aware
- topic labels are localized
- drawer article titles and summaries are localized when zh is requested

**Step 2: Run test to verify it fails**

Run: `pytest ai_news/tests/test_localized_signal_map.py -v`
Expected: FAIL because signal map responses are currently locale-agnostic.

**Step 3: Write minimal implementation**

Add locale-aware signal-map response shaping and update frontend consumers to render backend-resolved localized fields.

**Step 4: Run test to verify it passes**

Run: `pytest ai_news/tests/test_localized_signal_map.py -v`
Expected: PASS

### Task 7: End-To-End Verification

**Files:**
- Modify: `e2e/` tests as needed

**Step 1: Add or update end-to-end coverage**

Cover:
- switching to Chinese
- refreshing while staying in Chinese
- opening weekly in Chinese
- opening signal map and drawer in Chinese
- clear fallback behavior when zh content is unavailable

**Step 2: Run tests**

Run: `npm run build`
Expected: PASS

Run: `pytest ai_news/tests/test_localized_digest.py ai_news/tests/test_localized_weekly.py ai_news/tests/test_localized_signal_map.py -v`
Expected: PASS

**Step 3: Review behavior**

Confirm that locale is sticky, UI chrome is consistent, and no surface silently falls back to English while rendered under zh mode.
