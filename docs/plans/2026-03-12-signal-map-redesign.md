# Signal Map Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the signal map into a disciplined newsroom wireframe surface while fixing hover instability, layout crowding, and readability issues.

**Architecture:** Split the work into two layers. First, move layout, label ranking, and tooltip clamping into small deterministic helpers so the map can be tested and updated without re-running full D3 work on every pointer move. Second, refactor the map shell, topic rail, drawer, and CSS so the existing sketch/wireframe identity becomes quieter, clearer, and more intentional.

**Tech Stack:** React 19, TypeScript, D3, Vite, CSS, Playwright, `tsx` for lightweight local verification scripts.

---

### Task 1: Add deterministic signal-map layout helpers and a failing verification script

**Files:**
- Create: `src/components/signalMapLayout.ts`
- Create: `scripts/test-signal-map-layout.ts`
- Modify: `src/components/SignalMapCanvas.tsx`

**Step 1: Write the failing test**
- Create `scripts/test-signal-map-layout.ts` with assertions for pure helper behavior:
  - projected clusters are fit into inner bounds instead of remaining clumped in one corner
  - tooltip coordinates are clamped to viewport edges
  - label ranking returns only the highest-priority clusters for persistent labels
- Import helpers from the future `src/components/signalMapLayout.ts`.

**Step 2: Run test to verify it fails**
Run: `./node_modules/.bin/tsx scripts/test-signal-map-layout.ts`
Expected: FAIL because `src/components/signalMapLayout.ts` and its exports do not exist yet.

**Step 3: Write minimal implementation**
- Add `src/components/signalMapLayout.ts` with small pure utilities:
  - `fitClusterPositions(...)`
  - `resolveBubbleRadius(...)`
  - `pickVisibleLabels(...)`
  - `clampTooltipPosition(...)`
- Keep the helpers framework-agnostic and deterministic so they can be reused from the canvas.

**Step 4: Run test to verify it passes**
Run: `./node_modules/.bin/tsx scripts/test-signal-map-layout.ts`
Expected: PASS.

**Step 5: Commit**
```bash
git add src/components/signalMapLayout.ts scripts/test-signal-map-layout.ts src/components/SignalMapCanvas.tsx
git commit -m "test: add signal map layout helpers"
```

### Task 2: Fix hover jitter and stabilize tooltip behavior in the canvas

**Files:**
- Modify: `src/components/SignalMapCanvas.tsx`
- Modify: `src/styles/global.css`
- Test: `scripts/test-signal-map-layout.ts`

**Step 1: Write the failing test**
- Extend `scripts/test-signal-map-layout.ts` with assertions for tooltip clamping inputs that model cursor positions at the top-right and bottom-right edges.
- Add a Playwright regression case to a new future file that expects hovering a bubble not to change its center position erratically between frames.

**Step 2: Run test to verify it fails**
Run: `./node_modules/.bin/tsx scripts/test-signal-map-layout.ts`
Expected: PASS for current helpers, but browser verification is still missing and hover jitter still exists in the app.

**Step 3: Write minimal implementation**
- Refactor `SignalMapCanvas.tsx` so:
  - D3 join/layout work no longer depends on tooltip state
  - pointer movement updates tooltip coordinates through a lightweight path
  - hover emphasis affects stroke/fill only, not group transforms
  - selected state remains persistent and separate from hover
- Remove `.signal-bubble:hover { transform: scale(...) }` from the SVG group treatment.
- Clamp tooltip position before render.
- Ensure tooltip remains `pointer-events: none`.

**Step 4: Add browser verification**
- Create `e2e/signal-map.spec.ts` with a Chromium test that:
  - opens the app
  - switches to the signal map tab
  - hovers a visible bubble
  - verifies the tooltip appears
  - verifies the bubble remains visually stable during short repeated hover sampling

**Step 5: Run verification**
Run: `./node_modules/.bin/tsx scripts/test-signal-map-layout.ts`
Run: `./node_modules/.bin/playwright test e2e/signal-map.spec.ts --project=chromium`
Expected: PASS.

**Step 6: Commit**
```bash
git add src/components/SignalMapCanvas.tsx src/styles/global.css scripts/test-signal-map-layout.ts e2e/signal-map.spec.ts
git commit -m "fix: stabilize signal map hover interactions"
```

### Task 3: Rebuild map composition and label strategy

**Files:**
- Modify: `src/components/SignalMapCanvas.tsx`
- Modify: `src/components/signalMapLayout.ts`
- Modify: `src/styles/global.css`
- Test: `scripts/test-signal-map-layout.ts`
- Test: `e2e/signal-map.spec.ts`

**Step 1: Write the failing test**
- Extend `scripts/test-signal-map-layout.ts` with a layout fixture containing dense clusters and assert:
  - fitted positions stay within inner bounds
  - label selection prefers high-coverage/high-score clusters
  - low-priority labels are not returned by default

**Step 2: Run test to verify it fails**
Run: `./node_modules/.bin/tsx scripts/test-signal-map-layout.ts`
Expected: FAIL because the current helper logic does not yet enforce the new density rules.

**Step 3: Write minimal implementation**
- Improve layout helper logic to normalize the projected cluster field into the canvas.
- Add spacing rules so large circles do not visually suffocate neighbors.
- Add label-priority rules based on coverage, score, or urgency.
- Update the canvas render so only selected/high-priority labels are fully visible at rest.

**Step 4: Run verification**
Run: `./node_modules/.bin/tsx scripts/test-signal-map-layout.ts`
Run: `./node_modules/.bin/playwright test e2e/signal-map.spec.ts --project=chromium`
Expected: PASS.

**Step 5: Commit**
```bash
git add src/components/SignalMapCanvas.tsx src/components/signalMapLayout.ts src/styles/global.css scripts/test-signal-map-layout.ts e2e/signal-map.spec.ts
git commit -m "feat: improve signal map layout and label density"
```

### Task 4: Redesign the map shell into a disciplined newsroom wireframe

**Files:**
- Modify: `src/components/SignalMap.tsx`
- Modify: `src/components/TopicSidebar.tsx`
- Modify: `src/styles/global.css`
- Test: `e2e/signal-map.spec.ts`

**Step 1: Write the failing test**
- Extend `e2e/signal-map.spec.ts` with assertions that the desktop map surface contains:
  - a visible topic rail
  - a visible map-local legend or metadata key
  - a visible map refresh control with map-specific scope

**Step 2: Run test to verify it fails**
Run: `./node_modules/.bin/playwright test e2e/signal-map.spec.ts --project=chromium`
Expected: FAIL because the current map shell does not contain the new framing or legend structure.

**Step 3: Write minimal implementation**
- Refactor `SignalMap.tsx` to give the map a clearer shell with:
  - quieter framing
  - clearer map-local controls
  - space for a compact legend/status strip
- Refine `TopicSidebar.tsx` into a more legible analytical rail.
- Adjust CSS to keep the sketch/paper/grid feel while reducing clutter, duplicate emphasis, and heavy chrome.

**Step 4: Run verification**
Run: `./node_modules/.bin/playwright test e2e/signal-map.spec.ts --project=chromium`
Run: `npm run build`
Expected: PASS and successful build.

**Step 5: Commit**
```bash
git add src/components/SignalMap.tsx src/components/TopicSidebar.tsx src/styles/global.css e2e/signal-map.spec.ts
git commit -m "feat: redesign signal map shell and topic rail"
```

### Task 5: Refine the drawer, tooltip, and state hierarchy

**Files:**
- Modify: `src/components/ClusterDrawer.tsx`
- Modify: `src/components/SignalMapCanvas.tsx`
- Modify: `src/styles/global.css`
- Test: `e2e/signal-map.spec.ts`

**Step 1: Write the failing test**
- Extend `e2e/signal-map.spec.ts` with assertions that selecting a bubble opens a drawer with:
  - a visible headline
  - visible key stats
  - a visible article list
- Add a browser assertion that selected state remains visible after the pointer leaves the bubble.

**Step 2: Run test to verify it fails**
Run: `./node_modules/.bin/playwright test e2e/signal-map.spec.ts --project=chromium`
Expected: FAIL because the current drawer/state hierarchy does not yet reflect the new editorial structure.

**Step 3: Write minimal implementation**
- Rebuild `ClusterDrawer.tsx` into a cleaner editorial stack.
- Make selected state more obvious than hover.
- Tighten tooltip copy and visual treatment so it feels like quick context rather than a second panel.
- Adjust CSS spacing, borders, and metadata rhythm to match the redesign.

**Step 4: Run verification**
Run: `./node_modules/.bin/playwright test e2e/signal-map.spec.ts --project=chromium`
Run: `npm run build`
Expected: PASS and successful build.

**Step 5: Commit**
```bash
git add src/components/ClusterDrawer.tsx src/components/SignalMapCanvas.tsx src/styles/global.css e2e/signal-map.spec.ts
git commit -m "feat: refine signal map drawer and tooltip hierarchy"
```

### Task 6: Accessibility, responsiveness, and final review

**Files:**
- Modify: `src/components/SignalMapCanvas.tsx`
- Modify: `src/components/SignalMap.tsx`
- Modify: `src/components/ClusterDrawer.tsx`
- Modify: `src/styles/global.css`
- Test: `e2e/signal-map.spec.ts`

**Step 1: Write the failing test**
- Extend `e2e/signal-map.spec.ts` with assertions that:
  - at least one bubble is keyboard focusable
  - pressing Enter or Space on a focused bubble opens the drawer
  - reduced-motion safe fallbacks do not hide information

**Step 2: Run test to verify it fails**
Run: `./node_modules/.bin/playwright test e2e/signal-map.spec.ts --project=chromium`
Expected: FAIL because keyboard support and final polish are not complete yet.

**Step 3: Write minimal implementation**
- Add keyboard semantics and focus styling for map nodes.
- Make responsive spacing adjustments for narrower desktop widths.
- Add `prefers-reduced-motion` safety for pulse/transition behavior.
- Resolve any final contrast and readability regressions.

**Step 4: Request code review**
- Use a review subagent focused on regressions, accessibility, and interaction stability.

**Step 5: Apply fixes**
- Address important review findings without widening scope.

**Step 6: Final verification**
Run: `./node_modules/.bin/tsx scripts/test-signal-map-layout.ts`
Run: `./node_modules/.bin/playwright test e2e/signal-map.spec.ts --project=chromium`
Run: `npm run build`
Expected: PASS and successful build.

**Step 7: Commit**
```bash
git add src/components/SignalMapCanvas.tsx src/components/SignalMap.tsx src/components/ClusterDrawer.tsx src/styles/global.css e2e/signal-map.spec.ts scripts/test-signal-map-layout.ts
git commit -m "feat: finalize signal map redesign polish"
```
