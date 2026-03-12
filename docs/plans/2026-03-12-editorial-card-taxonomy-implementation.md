# Editorial Card Taxonomy And Layout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor story categories, broaden topic chips, and redesign the news card layout so cards read more clearly and show up to four meaningful chips without premature overflow.

**Architecture:** Update the backend compatibility layer to emit stronger editorial categories and richer display-topic chips, then update the frontend type system and card components to render the new hierarchy with a more stable two-row header and taller card bodies. Verification will combine backend unit tests, render assertions, and a production build.

**Tech Stack:** FastAPI, Python, React 19, TypeScript, Vite, tsx render-check scripts

---

### Task 1: Lock Backend Taxonomy With Failing Tests

**Files:**
- Create: `ai_news/tests/test_editorial_card_taxonomy.py`
- Modify: `ai_news/app/api/routes_compat.py`

**Step 1: Write the failing test**

Add tests that assert:
- `MODEL_RELEASE` maps to `Product`
- `SECURITY_INCIDENT` maps to `Security`
- fallback stories use `General` instead of `Trend`
- broad topic inputs produce up to four visible chips in stable order

**Step 2: Run test to verify it fails**

Run: `pytest ai_news/tests/test_editorial_card_taxonomy.py -v`
Expected: FAIL because the current category mapping still returns legacy labels and the chip vocabulary is narrower.

**Step 3: Write minimal implementation**

Update `routes_compat.py` category literals, event mappings, fallback rules, and chip-building logic.

**Step 4: Run test to verify it passes**

Run: `pytest ai_news/tests/test_editorial_card_taxonomy.py -v`
Expected: PASS

### Task 2: Update Frontend Type Surface

**Files:**
- Modify: `src/types/index.ts`
- Modify: `src/config/constants.tsx`

**Step 1: Write the failing test**

Extend the render verification script to assert the new category labels and topic-chip behavior expected by the card.

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Expected: FAIL because frontend types and config still use the old category set.

**Step 3: Write minimal implementation**

Update the union types and category color/config mappings to the new editorial taxonomy.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Expected: PASS or progress to the next failing assertion about layout markup.

### Task 3: Redesign Card Header And Footer Markup

**Files:**
- Modify: `src/components/NewsCard.tsx`
- Modify: `src/components/BreakingAlert.tsx` if shared visual language needs parity
- Modify: `scripts/test-wireframe-readability.tsx`

**Step 1: Write the failing test**

Add assertions for:
- separate top and bottom meta rows
- trust badge present in the top row without sharing a wrapping group with the signal pill
- up to four chips rendered directly for rich stories

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Expected: FAIL because the current card uses a single flex meta rail and still overflows to `+1`.

**Step 3: Write minimal implementation**

Refactor `NewsCard.tsx` into a two-row header and show up to four visible footer chips.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Expected: PASS

### Task 4: Adjust Vertical Sizing And Layout CSS

**Files:**
- Modify: `src/styles/global.css`

**Step 1: Write the failing test**

Add render assertions that target the new structural class names used for the reorganized rails and larger card treatment.

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Expected: FAIL until the CSS-backed class structure exists.

**Step 3: Write minimal implementation**

Increase card minimum heights, add dedicated header-row classes, stabilize alignment, and preserve footer spacing for four chips.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Expected: PASS

### Task 5: Full Verification

**Files:**
- Modify only as needed from prior tasks

**Step 1: Run backend tests**

Run: `pytest ai_news/tests/test_editorial_card_taxonomy.py -v`

**Step 2: Run frontend render checks**

Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`

**Step 3: Run production build**

Run: `npm run build`

**Step 4: Review output**

Confirm the new taxonomy is emitted, the card header is stable, and the build remains green.
