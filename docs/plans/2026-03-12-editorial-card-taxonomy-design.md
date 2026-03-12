# Editorial Card Taxonomy And Layout Design

## Goal

Refactor the news card taxonomy and layout so cards communicate story type, subject matter, trust, and score with clearer semantics and more stable spacing. The redesign should eliminate the current misuse of `Trend` as a fallback, support broader topic coverage, and reduce footer overflow by giving cards more vertical room.

## Problems

- The current main category set is too coarse. `Trend` is acting as a fallback rather than a true editorial label.
- Topic tags are too narrow for the range of stories the product can surface.
- The top rail is unstable because the trust badge and signal pill compete for horizontal space.
- Cards are slightly too short for the current footer density, so topic chips collapse into `+1` too early.

## Design Decisions

### 1. Story Type And Subject Matter Stay Separate

Main category answers: what kind of story is this?

Topic chips answer: what is this story about?

Trust badge answers: how verified is it?

Signal pill answers: how important is it?

This keeps the card readable and prevents category labels from doing too many jobs at once.

### 2. Main Category System

Replace the current primary categories with:

- `Research`
- `Product`
- `Company`
- `Funding`
- `Policy`
- `Open Source`
- `Hardware`
- `Security`
- `General`

`Trend` is removed as a primary category. If a future design wants to surface momentum or novelty, that should be a secondary status marker rather than a top-level category.

### 3. Topic Chip System

Use a broader semantic topic vocabulary for visible chips:

- `LLMs`
- `Multimodal`
- `Agents`
- `Robotics`
- `Vision`
- `Speech`
- `Video`
- `Coding`
- `Developer Tools`
- `Open Source`
- `Enterprise`
- `Consumer`
- `Healthcare`
- `Biotech`
- `Science`
- `Education`
- `Hardware`
- `Infrastructure`
- `Security`
- `Governance`

Cards should show at most 4 topic chips. Chips should be ranked by topic confidence and deduped against the main category so the footer does not waste slots on repeated meaning.

### 4. Card Layout

The card header becomes a stable two-row system:

- Row 1: category chip, source name, trust badge
- Row 2: timestamp on the left, signal pill pinned right

This creates fixed roles for each element and avoids the current wrap collision between `Official` and `Signal`.

The footer remains three-part:

- Topic chips on the left
- Source action in the middle
- Share action on the right

### 5. Vertical Rhythm

Increase the minimum height for standard and featured cards so footer tags fit more naturally. The card should still allow overflow summarization, but only after 4 meaningful chips are considered.

## Mapping Rules

### Main Category Mapping

- Event-driven mappings should remain authoritative where the event type is specific.
- `MODEL_RELEASE` and `PRODUCT_LAUNCH` map to `Product`.
- `BIG_TECH_ANNOUNCEMENT` and `M_AND_A` map to `Company`.
- `STARTUP_FUNDING` maps to `Funding`.
- `OPEN_SOURCE_RELEASE` maps to `Open Source`.
- `CHIP_HARDWARE` maps to `Hardware`.
- `SECURITY_INCIDENT` maps to `Security`.
- `RESEARCH_PAPER` and `BENCHMARK_RESULT` map to `Research`.
- `POLICY_REGULATION` and `GOVERNMENT_ACTION` map to `Policy`.
- Remaining unmapped stories should use topic-based fallbacks before landing in `General`.

### Topic Chip Mapping

The existing internal topic probabilities remain the source of truth for now. A richer display-layer mapping translates internal topics into the new visible chip vocabulary.

Examples:

- `audio_speech` -> `Speech`
- `hardware_chips` -> `Hardware`, `Infrastructure`
- `safety_policy` -> `Governance`
- `enterprise_apps` -> `Enterprise`
- `research_methods` -> `Science`
- `startups_funding` -> no direct topic chip unless editorially useful; main category already covers it

The display layer can also derive additional chips from event type or source context when the current internal topics are not expressive enough.

## Edge Cases

- Official cards should not change the right edge alignment of the signal pill.
- Very long source names should wrap without pushing the trust badge below the title.
- Cards with four relevant topic chips should show all four without collapsing to `+1` by default.
- Category and topic chips should not echo the same concept in wasteful ways.

## Verification

- Update render checks so the new markup structure is asserted explicitly.
- Add backend checks for category mapping and chip generation.
- Run the frontend build and the local render verification script after implementation.
