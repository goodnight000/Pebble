# Relationship Graph Design

**Goal:** Add a Bloomberg-terminal-style relationship graph as a second comparison mode alongside the existing signal map so users can understand both major storylines and non-obvious connections across global tech news.

**Problem:** The current signal map communicates distribution and relative importance, but it does not communicate why clusters are near each other or how stories relate. For VCs, founders, and serious followers of technology, the useful question is not just "what is big?" but also "what is connected, reacting, converging, or causing follow-on movement?"

**Approved Direction:** Keep the current signal map as one mode and add a second mode: a cluster-based relationship graph. The graph should show typed relationships between story clusters, use a rolling 7-day window by default, and reveal stronger local context on hover and click without overwhelming the screen.

## Principles
- Keep the existing wireframe/editorial product personality.
- Treat the relationship graph as a structure view, not a decorative view.
- Optimize for both quick storyline comprehension and discovery of unexpected connections.
- Show only the strongest relationships by default.
- Use cluster nodes, not article nodes, in the main graph.
- Make the graph own the space when the right panel is closed.

## Audience
- VCs looking for emerging themes, central actors, and second-order effects.
- Founders trying to understand the competitive landscape, adjacent moves, and market direction.
- Tech-followers who want a readable map of what matters and how events connect.

## Core Model
### Nodes
- Each node is a story cluster.
- Node size represents importance and/or coverage.
- Node color represents market/theme neighborhood.
- Recency is a secondary visual signal only.

### Edge Types
- `Shared Entity`
  Same company, product, model, regulator, investor, founder, lab, or open-source project.
- `Event Chain`
  One cluster is a plausible follow-on to another:
  launch, acquisition, funding, policy response, benchmark reaction, security response, partnership, etc.
- `Market Adjacency`
  Distinct actors, but the same market wave, competitive lane, or emerging category.

### Edge Ranking
- Strongest default priority: `Shared Entity`
- Next: `Event Chain`
- Weakest visible tier: `Market Adjacency`
- Graph should render only the strongest global edges plus a few strongest local edges per important node.

## Time Window
- Default: rolling `7D`
- Secondary mode: rolling `30D`
- Do not reset on calendar boundaries.
- The graph should preserve continuity across story arcs rather than splitting them at arbitrary week/month boundaries.

## Layout Model
- Theme/market neighborhoods are the primary organizing force.
- Important clusters pull toward the center.
- Related clusters stay near each other through constrained graph layout.
- Time is secondary and should be conveyed subtly through treatment, not a hard axis.
- The result should feel like a relationship surface with meaning, not a scatterplot.

## Interaction Model
### Default State
- Show the strongest storyline structure at a glance.
- Make the most important clusters legible without interaction.
- Show only the strongest relationships by default.

### Hover
- Show a lightweight relationship tooltip.
- Temporarily reveal nearby hidden edges for that node.
- Preview why the node connects to its neighborhood.

### Click
- Lock selection.
- Open the right panel.
- Emphasize the selected node and its first-degree relationship neighborhood.
- Keep unrelated parts of the graph visible but quieter.

### Close
- Close the panel.
- Restore full-width graph ownership.
- Return to the broader overview state.

## Right Panel
The right panel should be a relationship brief, not only an article drawer.

Order:
1. Why this cluster matters
2. Relationship evidence
3. Supporting coverage and sources

### Panel Sections
- Cluster headline and trust/state
- Why it matters this week
- Key stats: coverage, sources, velocity, age
- Top connected clusters grouped by edge type
- Plain-language connection evidence
- Key entities
- Ranked supporting articles and sources

## Layout Behavior
- No panel open:
  - graph takes full available width
  - no empty placeholder panel
- Panel open:
  - graph compresses and re-centers
  - selected node stays visible
  - local network becomes more prominent

## Mode Strategy
- Keep the current signal map intact.
- Add the relationship graph as a second mode so the user can compare the two views directly.
- This reduces migration risk and gives room to evaluate whether the relationship graph should later replace the old map.

## Technical Scope
- Add relationship-graph data structures for typed edges between clusters.
- Extend the frontend data model to support graph nodes, edges, and rolling windows.
- Add a graph mode switch in the signal-map area.
- Build a constrained relationship graph renderer.
- Add a new relationship brief panel that can replace the current drawer in graph mode.
- Add tests for graph semantics, panel behavior, and mode switching.

## Success Criteria
- Users can quickly identify the most important live storylines.
- Users can discover meaningful cross-cluster relationships they would not find from a plain list or scatterplot.
- The graph feels spatially meaningful rather than random.
- The right panel explains relationships before articles.
- The graph expands when the panel is closed and compresses smoothly when it opens.
