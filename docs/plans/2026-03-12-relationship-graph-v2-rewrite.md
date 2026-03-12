# Relationship Graph V2 Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current condensed relationship graph with a scalable V2 renderer that stays readable at rest, supports pan/zoom/drag, and remains maintainable as the graph grows toward low-thousands scale.

**Architecture:** Build a new `RelationshipGraphCanvasV2` alongside the current renderer first. Use a hybrid rendering model: canvas for bulk edges and low-detail density drawing, SVG/HTML overlay for labels, hit targets, selection, and accessibility, with D3 handling zoom, drag, simulation/layout, and viewport transforms. Keep the existing relationship graph data model and panel flow, extending only the frontend view model as needed.

**Tech Stack:** React 19, TypeScript, D3, Canvas 2D, SVG/HTML overlays, Vite, Playwright, lightweight `tsx` verification scripts.

---

### Task 1: Define the V2 graph view model and zoom/LOD helper contract

**Files:**
- Modify: `src/types/index.ts`
- Modify: `src/components/relationshipGraph.ts`
- Modify: `scripts/test-relationship-graph.ts`

**Step 1: Write the failing test**

Extend `scripts/test-relationship-graph.ts` with assertions for pure V2 helper behavior:
- zoom levels produce different label-visibility tiers
- nodes expose a stable render priority and topic color token
- graph bounds/fit helpers return deterministic viewport values
- low-priority labels are suppressed at base zoom while selected/high-priority nodes remain visible

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`

Expected: FAIL because the V2 helper exports and view-model fields do not exist yet.

**Step 3: Write minimal implementation**

- Extend `src/types/index.ts` with narrow V2-only types such as:
  - `RelationshipGraphZoomLevel`
  - `RelationshipGraphNodeVisual`
  - `RelationshipGraphViewport`
- Extend `src/components/relationshipGraph.ts` with pure helpers such as:
  - `buildRelationshipGraphVisuals(...)`
  - `pickVisibleNodeLabels(...)`
  - `computeGraphViewport(...)`
  - `resolveNodeTopicColor(...)`
- Keep the helpers deterministic and renderer-agnostic.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/types/index.ts src/components/relationshipGraph.ts scripts/test-relationship-graph.ts
git commit -m "feat: add relationship graph v2 view model helpers"
```

### Task 2: Build the new hybrid canvas renderer shell beside the current graph

**Files:**
- Create: `src/components/RelationshipGraphCanvasV2.tsx`
- Modify: `src/components/relationshipGraph.ts`
- Modify: `src/styles/global.css`
- Modify: `scripts/test-relationship-graph.ts`

**Step 1: Write the failing test**

Extend `scripts/test-relationship-graph.ts` with assertions for renderer-facing helpers:
- viewport fit math centers the graph inside padded bounds
- zoom level thresholds drive different label-density outcomes
- edge rendering tiers distinguish default, focused, and hidden edges

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`

Expected: FAIL because the V2 renderer helpers are incomplete.

**Step 3: Write minimal implementation**

- Create `src/components/RelationshipGraphCanvasV2.tsx`
- Implement a layered surface:
  - canvas for bulk edge drawing
  - overlay layer for interactive nodes and labels
- Use the pure helpers from `relationshipGraph.ts` for:
  - layout projection
  - label visibility
  - viewport fit
- Add base styling in `src/styles/global.css` for the V2 surface only.

**Step 4: Run verification**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`
Run: `npm run build`

Expected: PASS and successful build.

**Step 5: Commit**

```bash
git add src/components/RelationshipGraphCanvasV2.tsx src/components/relationshipGraph.ts src/styles/global.css scripts/test-relationship-graph.ts
git commit -m "feat: add relationship graph v2 renderer shell"
```

### Task 3: Add zoom, pan, fit, and reset controls

**Files:**
- Modify: `src/components/RelationshipGraphCanvasV2.tsx`
- Modify: `src/styles/global.css`
- Test: `e2e/relationship-graph.spec.ts`

**Step 1: Write the failing browser test**

Extend `e2e/relationship-graph.spec.ts` with assertions that:
- graph mode shows zoom controls
- users can zoom in and reset view
- the graph remains visible after reset
- the active window (`7D` or `30D`) remains unchanged while zooming

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`

Expected: FAIL because V2 zoom controls do not exist yet.

**Step 3: Write minimal implementation**

- Add D3 zoom behavior to `RelationshipGraphCanvasV2.tsx`
- Add UI controls for:
  - zoom in
  - zoom out
  - reset
  - fit
- Keep transforms centralized in one viewport state model.

**Step 4: Run verification**

Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`
Run: `npm run build`

Expected: PASS and successful build.

**Step 5: Commit**

```bash
git add src/components/RelationshipGraphCanvasV2.tsx src/styles/global.css e2e/relationship-graph.spec.ts
git commit -m "feat: add relationship graph v2 zoom controls"
```

### Task 4: Add draggable nodes and stronger neighborhood spread

**Files:**
- Modify: `src/components/RelationshipGraphCanvasV2.tsx`
- Modify: `src/components/relationshipGraph.ts`
- Modify: `scripts/test-relationship-graph.ts`
- Test: `e2e/relationship-graph.spec.ts`

**Step 1: Write the failing tests**

Extend `scripts/test-relationship-graph.ts` with assertions that:
- topic neighborhoods are spaced farther apart than the current baseline
- center pile-up is reduced for lower-priority nodes
- drag state preserves node identity and updates local position overrides predictably

Extend `e2e/relationship-graph.spec.ts` with a drag interaction assertion.

**Step 2: Run tests to verify they fail**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`
Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`

Expected: FAIL because drag and improved spacing do not exist yet.

**Step 3: Write minimal implementation**

- Improve `projectRelationshipGraphLayout(...)` in `relationshipGraph.ts`
- Add node drag support in `RelationshipGraphCanvasV2.tsx`
- Keep drag behavior local to the session view state; do not mutate the core data model.

**Step 4: Run verification**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`
Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`
Run: `npm run build`

Expected: PASS and successful build.

**Step 5: Commit**

```bash
git add src/components/RelationshipGraphCanvasV2.tsx src/components/relationshipGraph.ts scripts/test-relationship-graph.ts e2e/relationship-graph.spec.ts
git commit -m "feat: add draggable relationship graph v2 layout"
```

### Task 5: Redesign color, label density, and edge hierarchy for readability

**Files:**
- Modify: `src/components/RelationshipGraphCanvasV2.tsx`
- Modify: `src/components/relationshipGraph.ts`
- Modify: `src/styles/global.css`
- Modify: `src/i18n/messages.ts`
- Test: `e2e/relationship-graph.spec.ts`

**Step 1: Write the failing tests**

Extend `scripts/test-relationship-graph.ts` with assertions that:
- topic colors are stable and deterministic
- base zoom shows fewer labels than focused/zoomed states
- selected nodes and focused neighborhoods override suppression rules

Extend `e2e/relationship-graph.spec.ts` with assertions that:
- topic colors are visible on graph nodes
- label density changes after zooming
- focused/selected nodes remain readable

**Step 2: Run tests to verify they fail**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`
Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`

Expected: FAIL because the V2 visual hierarchy is not complete yet.

**Step 3: Write minimal implementation**

- Add a topic color system in `relationshipGraph.ts`
- Apply topic colors and edge hierarchy in `RelationshipGraphCanvasV2.tsx`
- Reduce resting label density aggressively
- Make selected and hovered neighborhoods visually clearer than the background graph
- Update legend/copy in `src/i18n/messages.ts`
- Refine CSS in `src/styles/global.css`

**Step 4: Run verification**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`
Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`
Run: `npm run build`

Expected: PASS and successful build.

**Step 5: Commit**

```bash
git add src/components/RelationshipGraphCanvasV2.tsx src/components/relationshipGraph.ts src/styles/global.css src/i18n/messages.ts scripts/test-relationship-graph.ts e2e/relationship-graph.spec.ts
git commit -m "feat: improve relationship graph v2 readability"
```

### Task 6: Integrate V2 into the signal-map surface and preserve panel workflow

**Files:**
- Modify: `src/components/SignalMap.tsx`
- Modify: `src/components/RelationshipGraphPanel.tsx`
- Modify: `src/components/RelationshipGraphCanvasV2.tsx`
- Modify: `src/styles/global.css`
- Test: `e2e/relationship-graph.spec.ts`

**Step 1: Write the failing browser test**

Extend `e2e/relationship-graph.spec.ts` with assertions that:
- graph mode uses the V2 renderer
- panel-open state still allows zoom/pan navigation
- switching between `map` and `graph` remains clean
- `7D` and `30D` still drive the correct active graph window

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`

Expected: FAIL because the app is still using the older graph renderer.

**Step 3: Write minimal implementation**

- Replace V1 usage in `SignalMap.tsx` with `RelationshipGraphCanvasV2`
- Keep the existing panel and selection flow, updating only what V2 needs
- Ensure panel-open layout still leaves meaningful graph context visible

**Step 4: Run verification**

Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`
Run: `npm run build`

Expected: PASS and successful build.

**Step 5: Commit**

```bash
git add src/components/SignalMap.tsx src/components/RelationshipGraphPanel.tsx src/components/RelationshipGraphCanvasV2.tsx src/styles/global.css e2e/relationship-graph.spec.ts
git commit -m "feat: switch signal map to relationship graph v2"
```

### Task 7: Remove or retire the old renderer cleanly

**Files:**
- Delete or retire: `src/components/RelationshipGraphCanvas.tsx`
- Modify: `src/components/SignalMap.tsx`
- Review: `src/components/relationshipGraph.ts`
- Review: `src/styles/global.css`

**Step 1: Write the failing build expectation**

Run: `npm run build`

Expected: FAIL if any references still point to the old renderer or stale styles remain.

**Step 2: Write minimal implementation**

- Remove dead references to V1
- Delete obsolete CSS selectors only after V2 is confirmed complete
- Keep the public graph behavior unchanged

**Step 3: Run verification**

Run: `npm run build`
Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`

Expected: PASS.

**Step 4: Commit**

```bash
git add src/components/SignalMap.tsx src/components/relationshipGraph.ts src/styles/global.css src/components/RelationshipGraphCanvas.tsx
git commit -m "refactor: retire relationship graph v1 renderer"
```

### Task 8: Final review and handoff validation

**Files:**
- Review: `src/components/RelationshipGraphCanvasV2.tsx`
- Review: `src/components/RelationshipGraphPanel.tsx`
- Review: `src/components/relationshipGraph.ts`
- Review: `src/components/SignalMap.tsx`
- Review: `src/styles/global.css`
- Review: `scripts/test-relationship-graph.ts`
- Review: `e2e/relationship-graph.spec.ts`

**Step 1: Request code review**

- Use a review subagent focused on:
  - graph readability at rest
  - zoom/drag interaction quality
  - accessibility
  - regression risk

**Step 2: Apply fixes**

- Fix any important findings before finishing.

**Step 3: Final verification**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`
Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`
Run: `npm run build`

Expected: PASS and successful build.

**Step 4: Commit**

```bash
git add src/components src/styles/global.css src/i18n/messages.ts scripts/test-relationship-graph.ts e2e/relationship-graph.spec.ts
git commit -m "feat: finalize relationship graph v2 rewrite"
```
