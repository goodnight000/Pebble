# Wireframe Readability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve scanability and readability in the existing wireframe feed while preserving its industrial visual identity.

**Architecture:** Keep the current wireframe mode and change only the hierarchy of information inside it. The first live card becomes featured, digest metadata becomes cleaner, and cards/breaking alerts move to a clearer scan-first layout with quieter secondary chrome.

**Tech Stack:** React 19, TypeScript, Vite, CSS, `react-dom/server` for lightweight render verification.

---

### Task 1: Add a failing wireframe render test

**Files:**
- Create: `scripts/test-wireframe-readability.tsx`
- Modify: `src/components/NewsCard.tsx`
- Modify: `src/components/BreakingAlert.tsx`

**Step 1: Write the failing test**
- Render a wireframe `NewsCard` with a future `featured` prop and assert the output contains:
  - `news-card-wf--feature`
  - `Signal 96`
  - the primary source title in the top metadata rail
- Render a wireframe `BreakingAlert` and assert the output contains a visible summary and source CTA.

**Step 2: Run test to verify it fails**
Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Expected: FAIL because the future wireframe classes/text are not implemented yet.

**Step 3: Write minimal implementation**
- Add `featured?: boolean` to `NewsCard`.
- Update wireframe card markup to match the new hierarchy.
- Update wireframe breaking alert markup to include summary and source label.

**Step 4: Run test to verify it passes**
Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Expected: PASS.

### Task 2: Improve wireframe feed layout in the app shell

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/styles/global.css`

**Step 1: Write the failing test expectation**
- Extend the render test or add assertions for the first live item to receive featured presentation wiring through `featured={idx === 0}` semantics.

**Step 2: Run test to verify it fails**
Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Expected: FAIL because `App.tsx` does not yet wire featured cards or digest metadata changes.

**Step 3: Write minimal implementation**
- Update the wireframe digest panel in `App.tsx` with a tighter metadata rail.
- Pass `featured` to the first live-feed card in wireframe mode.
- Keep editorial mode untouched.

**Step 4: Run test/build to verify it passes**
Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Run: `npm run build`
Expected: PASS and successful build.

### Task 3: Refine wireframe CSS hierarchy

**Files:**
- Modify: `src/styles/global.css`

**Step 1: Write the failing test expectation**
- Ensure the render test looks for new classes used by the wireframe hierarchy.

**Step 2: Run test to verify it fails**
Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Expected: FAIL until class wiring exists.

**Step 3: Write minimal implementation**
- Add wireframe-specific classes for metadata rails, summary rhythm, featured cards, quieter tags, and digest metadata.
- Reduce headline tracking and summary density only in wireframe mode.

**Step 4: Run verification**
Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Run: `npm run build`
Expected: PASS and successful build.

### Task 4: Review the final UI changes

**Files:**
- Review: `src/App.tsx`
- Review: `src/components/NewsCard.tsx`
- Review: `src/components/BreakingAlert.tsx`
- Review: `src/styles/global.css`

**Step 1: Request code review**
- Use a review subagent focused on regressions, readability, and accessibility.

**Step 2: Apply fixes**
- Fix any important findings before finishing.

**Step 3: Final verification**
Run: `./node_modules/.bin/tsx scripts/test-wireframe-readability.tsx`
Run: `npm run build`
Expected: PASS and successful build.
