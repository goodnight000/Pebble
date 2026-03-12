# Signal Map Redesign Design

**Goal:** Make the signal map feel elegant, legible, and stable while preserving the current sketch/wireframe personality.

**Problem:** The current signal map keeps the right raw ingredients, but the composition is noisy and under-controlled. Bubbles collapse into one area, labels collide, hover behavior is unstable, the topic rail is hard to read, and the surrounding controls compete with the chart instead of supporting it.

**Approved Direction:** Keep the paper-and-ink wireframe identity and evolve it into a disciplined newsroom surface. The redesign should feel like an editorial intelligence desk: precise, breathable, and analytical rather than loud, cramped, or playful.

## Principles
- Preserve the sketch/wireframe identity: paper background, visible grid, mono metadata, ink outlines, orange accent.
- Replace visual noise with hierarchy. Fewer decorations should carry more meaning.
- Treat the map as the primary artifact and everything else as framing.
- Favor restrained motion over constant motion.
- Make the chart readable without requiring hover.
- Keep the interface credible for dense information work, not just visually distinctive.

## UX Goals
- Users should understand what the chart encodes within a few seconds.
- The map should use the available canvas instead of clustering into one corner.
- Hover should reveal detail, not disturb layout.
- The sidebar and drawer should support fast scanning rather than adding clutter.
- The selected cluster should be obvious and persistent.
- The UI should feel composed and elegant at desktop sizes while still degrading cleanly on mobile.

## Visual Direction
### Overall mood
- Editorial operations desk
- Technical, but not cold
- Sketch-like, but disciplined
- High contrast, but not aggressive

### Typography
- Keep the existing mono/editorial pairing, but tighten the hierarchy.
- Use the display face mainly for headlines and section anchors.
- Use mono text for metadata, labels, scales, and legends.
- Increase small-text legibility so information does not disappear into the texture.

### Color
- Keep the paper background and orange accent.
- Keep topic colors, but use them more selectively and with more consistent saturation.
- Reduce the number of simultaneous competing emphasis colors in a single area.
- Reserve the orange accent for selection, live state, and high-priority UI cues.

### Texture and framing
- Keep the grid background, but let it recede behind the data.
- Use dashed borders as a secondary motif, not a default for every object.
- Use solid ink framing for primary structure and lighter/dashed treatment for secondary scaffolding.

## Information Architecture
### Map
- The signal map is the hero surface.
- It should present clusters with clear visual spread, readable relative size, and a visible selected state.
- The map should include a compact legend that explains:
  - bubble size
  - color/topic
  - trust or urgency treatment

### Topic rail
- The topic rail remains on the left.
- It should read as a compact analytical strip, not a decorative list.
- Labels need more breathing room and stronger readability.
- Daily cells should be quieter and more comparable.

### Drawer
- The drawer remains on the right as the detail surface.
- It should adopt a more editorial rhythm:
  - trust/state
  - headline
  - key stats
  - entities
  - trend
  - supporting articles
- It should feel lighter and more structured than the current version.

### Controls
- Global app controls remain in the shell header.
- Map-local controls must be clearly scoped to the map.
- Duplicate refresh affordances need cleaner framing and meaning.

## Interaction Design
### Hover
- Hover should add subtle emphasis only.
- Bubbles should not physically jump, rescale unpredictably, or cause other nodes to flicker.
- Tooltips should be lightweight, stable, and clamped to the viewport.

### Selection
- Click should create a persistent selected state distinct from hover.
- Selected bubbles should feel pinned and intentional.
- The drawer should reflect the selected cluster immediately.

### Motion
- Entrance motion should be soft and coordinated.
- Ongoing motion should be sparse.
- Pulse effects should only appear for truly urgent clusters and should not dominate the chart.
- Reduced-motion users should get the same information with less animation.

### Accessibility
- Bubbles should be keyboard reachable.
- Focus, hover, and selected states should be visually distinct.
- Tooltip content should not be the only place critical information is available.

## Functional Changes
### Layout and positioning
- Fit projected points into usable bounds rather than plotting raw positions directly.
- Add spacing or collision handling so large bubbles do not crush smaller ones.
- Preserve relative map neighborhoods while improving distribution.

### Label strategy
- Show persistent labels only for top-priority clusters.
- De-emphasize or hide low-priority labels until hover or selection.
- Prevent the label field from becoming a grey blur.

### Tooltip content
- Keep tooltip content short and useful.
- Prioritize headline, trust, velocity, and source count.
- Clamp position to stay visible near edges.

### Drawer content
- Tighten article cards and metadata.
- Make stat groups easier to compare.
- Clarify section boundaries without over-framing each block.

## Technical Scope
- Modify `src/components/SignalMapCanvas.tsx` to separate expensive D3 layout work from lightweight hover updates.
- Add a small layout helper module for map fitting, spacing, label priority, and tooltip clamping.
- Modify `src/components/SignalMap.tsx` to improve map-level framing, control placement, and legend structure.
- Modify `src/components/TopicSidebar.tsx` to improve topic rail readability and density.
- Modify `src/components/ClusterDrawer.tsx` to improve information rhythm and editorial hierarchy.
- Modify `src/styles/global.css` to establish the refined wireframe visual system and interaction states.
- Add targeted verification for signal map layout and hover stability.

## Success Criteria
- Hover no longer causes visible jitter or frantic node movement.
- The map fills the canvas in a balanced way.
- At a glance, the user can identify the most important clusters.
- The interface feels calmer, clearer, and more deliberate without losing its wireframe identity.
- The signal map remains functional on desktop and mobile breakpoints.
