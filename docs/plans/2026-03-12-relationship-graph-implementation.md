# Relationship Graph Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a second relationship-graph mode beside the existing signal map so users can compare a distribution view with a Bloomberg-style cluster relationship graph.

**Architecture:** Keep the current signal map mode intact and introduce a separate graph mode driven by typed cluster-to-cluster edges. Build the graph in layers: relationship data model first, then graph rendering and interaction, then the relationship brief panel and mode switching. Preserve the current wireframe visual language while making the graph spatially meaningful and evidence-driven.

**Tech Stack:** React 19, TypeScript, D3, Vite, CSS, Playwright, lightweight `tsx` verification scripts.

---

### Task 1: Define relationship graph data types and pure edge-ranking helpers

**Files:**
- Create: `src/components/relationshipGraph.ts`
- Modify: `src/types/index.ts`
- Create: `scripts/test-relationship-graph.ts`

**Step 1: Write the failing test**

Create `scripts/test-relationship-graph.ts` with assertions for future pure helpers:
- a cluster pair with shared entities ranks above a pair with only market adjacency
- event-chain evidence contributes to edge strength
- only the strongest edges are returned by default
- rolling-window graph metadata preserves `7d` and `30d` mode labels

Import future helpers and types from `src/components/relationshipGraph.ts`.

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`

Expected: FAIL because the new relationship graph module and types do not exist yet.

**Step 3: Write minimal implementation**

- Add graph types to `src/types/index.ts`:
  - `RelationshipEdgeType`
  - `RelationshipGraphEdge`
  - `RelationshipGraphNode`
  - `RelationshipGraphResponse`
- Add pure helpers to `src/components/relationshipGraph.ts`:
  - `scoreEdge(...)`
  - `pickVisibleEdges(...)`
  - `buildLocalNeighborhood(...)`
- Keep the module deterministic and UI-agnostic.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/types/index.ts src/components/relationshipGraph.ts scripts/test-relationship-graph.ts
git commit -m "feat: add relationship graph model helpers"
```

### Task 2: Extend the signal-map view model to support a second mode

**Files:**
- Modify: `src/components/SignalMap.tsx`
- Modify: `src/i18n/messages.ts`
- Modify: `src/styles/global.css`
- Test: `scripts/test-relationship-graph.ts`

**Step 1: Write the failing test expectation**

Extend `scripts/test-relationship-graph.ts` or add source assertions that:
- the signal-map surface exposes two modes
- the default remains the current signal-map mode
- graph-specific time windows are represented as rolling `7D` and `30D`

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`

Expected: FAIL because the mode system is not wired yet.

**Step 3: Write minimal implementation**

- Add local UI state in `SignalMap.tsx` for:
  - view mode: `map` vs `graph`
  - graph window: `7d` vs `30d`
- Add UI copy in `src/i18n/messages.ts`
- Add minimal segmented controls or chips in the map shell
- Keep the current signal-map mode unchanged as the default

**Step 4: Run verification**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`
Run: `npm run build`

Expected: PASS and successful build.

**Step 5: Commit**

```bash
git add src/components/SignalMap.tsx src/i18n/messages.ts src/styles/global.css scripts/test-relationship-graph.ts
git commit -m "feat: add relationship graph mode controls"
```

### Task 3: Build a relationship-graph renderer with strongest edges only by default

**Files:**
- Create: `src/components/RelationshipGraphCanvas.tsx`
- Modify: `src/components/relationshipGraph.ts`
- Modify: `src/styles/global.css`
- Test: `scripts/test-relationship-graph.ts`

**Step 1: Write the failing test**

Extend `scripts/test-relationship-graph.ts` with assertions for layout/selection helpers:
- important nodes are centered more strongly than low-priority nodes
- only strongest edges are visible by default
- local neighborhood expansion returns additional edges for a selected node

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`

Expected: FAIL because renderer/layout helpers are not implemented yet.

**Step 3: Write minimal implementation**

- Create `RelationshipGraphCanvas.tsx`
- Use constrained layout logic so:
  - theme neighborhoods group together
  - important nodes bias toward center
  - only strongest edges render at rest
- Keep hover and selection states light and readable
- Reuse the current wireframe grid/system where appropriate

**Step 4: Run verification**

Run: `./node_modules/.bin/tsx scripts/test-relationship-graph.ts`
Run: `npm run build`

Expected: PASS and successful build.

**Step 5: Commit**

```bash
git add src/components/RelationshipGraphCanvas.tsx src/components/relationshipGraph.ts src/styles/global.css scripts/test-relationship-graph.ts
git commit -m "feat: add relationship graph canvas"
```

### Task 4: Add graph interactions and graph-owned empty state behavior

**Files:**
- Modify: `src/components/RelationshipGraphCanvas.tsx`
- Modify: `src/components/SignalMap.tsx`
- Modify: `src/styles/global.css`
- Test: `e2e/relationship-graph.spec.ts`

**Step 1: Write the failing browser test**

Create `e2e/relationship-graph.spec.ts` with Chromium coverage for:
- switching from signal map to relationship graph
- seeing graph nodes and visible edges
- verifying no right panel is present by default
- verifying the graph takes the available space when no panel is open

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`

Expected: FAIL because the graph mode does not exist yet.

**Step 3: Write minimal implementation**

- Render `RelationshipGraphCanvas` when graph mode is active
- Ensure no placeholder panel appears by default
- Make the graph surface expand to full available width
- Add hover reveal for a node’s local hidden edges

**Step 4: Run verification**

Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`
Run: `npm run build`

Expected: PASS and successful build.

**Step 5: Commit**

```bash
git add src/components/RelationshipGraphCanvas.tsx src/components/SignalMap.tsx src/styles/global.css e2e/relationship-graph.spec.ts
git commit -m "feat: add graph mode interactions"
```

### Task 5: Build the relationship brief panel and graph compression behavior

**Files:**
- Create: `src/components/RelationshipGraphPanel.tsx`
- Modify: `src/components/RelationshipGraphCanvas.tsx`
- Modify: `src/components/SignalMap.tsx`
- Modify: `src/styles/global.css`
- Test: `e2e/relationship-graph.spec.ts`

**Step 1: Write the failing browser test**

Extend `e2e/relationship-graph.spec.ts` with assertions that:
- clicking a graph node opens a right panel
- the graph compresses when the panel opens
- the panel shows:
  - cluster header
  - relationship evidence
  - supporting coverage

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`

Expected: FAIL because no relationship brief panel exists yet.

**Step 3: Write minimal implementation**

- Create `RelationshipGraphPanel.tsx`
- Structure the panel in this order:
  - why this cluster matters
  - why it connects
  - supporting coverage
- Make the graph re-center and compress when a node is selected
- Preserve full-width ownership when the panel is closed

**Step 4: Run verification**

Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`
Run: `npm run build`

Expected: PASS and successful build.

**Step 5: Commit**

```bash
git add src/components/RelationshipGraphPanel.tsx src/components/RelationshipGraphCanvas.tsx src/components/SignalMap.tsx src/styles/global.css e2e/relationship-graph.spec.ts
git commit -m "feat: add relationship graph panel"
```

### Task 6: Refine graph evidence, legend, and compare-mode UX

**Files:**
- Modify: `src/components/RelationshipGraphCanvas.tsx`
- Modify: `src/components/RelationshipGraphPanel.tsx`
- Modify: `src/components/SignalMap.tsx`
- Modify: `src/styles/global.css`
- Test: `e2e/relationship-graph.spec.ts`

**Step 1: Write the failing test expectation**

Extend `e2e/relationship-graph.spec.ts` with assertions that:
- the graph legend explains edge types
- selected nodes expose selected state accessibly
- switching between `map` and `graph` preserves a clean compare workflow
- rolling `7D` and `30D` switches update visible graph context

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`

Expected: FAIL because the compare/polish behavior is not complete yet.

**Step 3: Write minimal implementation**

- Add typed edge legend
- Add clearer selected/focus states
- Improve compare-mode switching so the UI never feels like two unrelated tools
- Refine the panel evidence presentation for readability

**Step 4: Run verification**

Run: `./node_modules/.bin/playwright test e2e/relationship-graph.spec.ts --project=chromium`
Run: `npm run build`

Expected: PASS and successful build.

**Step 5: Commit**

```bash
git add src/components/RelationshipGraphCanvas.tsx src/components/RelationshipGraphPanel.tsx src/components/SignalMap.tsx src/styles/global.css e2e/relationship-graph.spec.ts
git commit -m "feat: polish relationship graph compare mode"
```

### Task 7: Final review and handoff validation

**Files:**
- Review: `src/components/relationshipGraph.ts`
- Review: `src/components/RelationshipGraphCanvas.tsx`
- Review: `src/components/RelationshipGraphPanel.tsx`
- Review: `src/components/SignalMap.tsx`
- Review: `src/styles/global.css`
- Review: `scripts/test-relationship-graph.ts`
- Review: `e2e/relationship-graph.spec.ts`

**Step 1: Request code review**

- Use a review subagent focused on:
  - graph semantics
  - readability
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
git add src/components src/styles/global.css scripts/test-relationship-graph.ts e2e/relationship-graph.spec.ts
git commit -m "feat: finalize relationship graph mode"
```
