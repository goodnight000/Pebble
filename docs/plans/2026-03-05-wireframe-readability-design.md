# Wireframe Readability Design

**Goal:** Improve readability and scanning in the existing wireframe interface without changing its visual identity.

**Problem:** The wireframe feed currently feels text-dense because titles, score pills, tags, trust badges, source links, and decorative treatment all compete for attention. The UI has personality, but the information hierarchy is too flat.

**Approved Direction:** Keep the industrial wireframe system and introduce a clearer two-speed hierarchy: fast scan on first glance, easier reading once a story has attention.

## Principles
- Preserve the wireframe language: dashed borders, strong outlines, mono metadata, brutalist offsets.
- Make the title the dominant read target.
- Collapse metadata into a cleaner top rail.
- Reduce secondary chrome so trust, score, tags, and source no longer fight the headline.
- Keep summaries shorter and more breathable.
- Give the top story more emphasis without turning the layout into a different product.

## UX Changes
### Digest panel
- Keep the current hero panel structure.
- Add a tighter meta rail for update time, active filter, and story count.
- Reduce decorative noise impact so the headline and summary read first.
- Keep chips, but make them quieter than the headline.

### Wireframe cards
- Promote the first live-feed card to a featured card in wireframe mode.
- Rebuild card hierarchy to:
  - top rail: category, source, time
  - title
  - 2-3 line summary
  - bottom rail: trust, signal, one tag, share/source action
- Tighten uppercase headline tracking slightly for readability.
- Limit summaries to 3 lines in standard cards.
- Show one visible tag by default instead of two.
- Show source more prominently than tags.

### Breaking alert
- Keep the wireframe alert treatment.
- Add a one-line summary and clearer source CTA so the alert is easier to parse.
- Lower metadata clutter around the title.

## Technical Scope
- Modify `src/App.tsx` for wireframe-only feed layout and digest hierarchy.
- Modify `src/components/NewsCard.tsx` for the new wireframe card structure and featured state.
- Modify `src/components/BreakingAlert.tsx` for the simplified wireframe breaking alert.
- Modify `src/styles/global.css` for new wireframe-only utility classes and spacing adjustments.
- Add a lightweight render test script to validate the new wireframe structure.
