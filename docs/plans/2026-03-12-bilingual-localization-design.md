# Bilingual Localization Design

## Goal

Stabilize English/Chinese behavior across the entire app by separating UI locale from translated content, moving localization responsibility to predictable system boundaries, and removing the current fragile client-side translation toggle flow.

## Current Problems

- The app conflates locale switching with live LLM translation.
- Chinese mode can silently show English content when translation is unavailable.
- Manual refresh and automatic refresh force the app back to English.
- Weekly and signal-map surfaces are not localized consistently with the live digest.
- Fixed UI strings are scattered across components and are only partially translated.
- The current flow depends on translating a large JSON blob at toggle time, which is slow and structurally brittle.

## Design Decisions

### 1. Split Locale From Content Translation

The app needs two separate concepts:

- `locale`: the user-facing UI language for navigation, controls, labels, empty states, and metadata formatting
- `content locale`: the language of digest, weekly, and signal-map display text

These should move together from the user's perspective, but they must not share the same implementation path. The locale toggle should only change locale state and refetch locale-aware content. It should not orchestrate ad hoc translation inside React components.

### 2. Use A Real UI i18n Layer

All fixed strings should come from translation dictionaries instead of inline ternaries. This covers:

- navigation labels
- buttons and tooltips
- trust labels
- badges and chips
- empty states
- loading/error copy
- signal-map drawer labels
- weekly view labels

This removes mixed-language UI shells and makes future copy changes tractable.

### 3. Make The Backend Own Localized Content

English remains the canonical editorial payload. Chinese is a derived display variant produced by the backend and cached for reuse.

Each surface should expose localized content through a locale-aware API contract:

- live digest
- weekly items
- signal map clusters
- signal map drawer article titles and summaries
- topic labels and trust labels where rendered as text

The frontend should never translate whole payloads on demand.

### 4. Localize Display Text Only

The translation layer should localize only human-facing text:

- headlines
- summaries
- digest copy
- cluster headlines
- topic labels

It should not rewrite structural fields:

- ids
- enums
- URLs
- scores
- timestamps
- source references

This keeps payload shape stable and prevents model rewrites from corrupting arrays or metadata.

### 5. Add Explicit Translation State

The frontend needs a reliable contract instead of implicit fallback. Localized API responses should include:

- `locale`
- `sourceLocale`
- `translationStatus`

`translationStatus` should be one of:

- `ready`
- `pending`
- `unavailable`

If Chinese content is not ready, the UI should render a loading or unavailable state for that surface. It should never pretend that English content is Chinese.

### 6. Persist Locale Across Refreshes

User locale selection should be stored locally and reused on:

- page reload
- manual refresh
- scheduled refresh
- tab changes

Refresh should revalidate content in the current locale, not reset the app to English.

## API Shape

All localized surfaces should follow the same high-level pattern:

- request accepts `locale=en|zh`
- response returns localized display fields
- response includes `locale`, `sourceLocale`, and `translationStatus`

Examples:

### Live Digest

- localized digest headline
- localized executive summary
- localized per-content-type digest copy
- localized item title and summary
- localized breaking alert title and summary

### Weekly

- localized item title and summary
- localized display labels used by the card shell

### Signal Map

- localized cluster headline
- localized drawer article title and summary
- localized topic labels and trust labels

## Backend Behavior

The backend should generate English payloads as it does today, then derive and cache Chinese display variants using a stable fingerprint of the English display content.

Expected behavior:

- `en` responses return immediately
- `zh` responses return cached localized content when available
- if a translation job is still outstanding, the backend can return `pending`
- if localization is disabled or fails, the backend returns `unavailable`

This gives the frontend a predictable contract without needing toggle-time translation logic.

## Frontend Behavior

The locale toggle should:

- update persisted locale state
- refetch or rehydrate active surfaces for that locale
- preserve the current tab and content filter
- avoid destructive resets of digest state

The frontend should use dictionary-driven UI copy for chrome and backend-provided localized content for editorial text.

## Rollout Strategy

### Phase 1: UI Locale Foundation

- add a frontend i18n layer
- move fixed UI strings into translation dictionaries
- persist locale in local storage
- stop resetting locale during refresh

This should eliminate most of the visible UI weirdness quickly.

### Phase 2: Remove Client-Side Digest Translation

- delete the current `translateDigest` toggle-driven flow
- fetch locale-aware live digest content from the backend instead

### Phase 3: Localize Weekly

- update weekly endpoint and weekly UI rendering to use locale-aware data

### Phase 4: Localize Signal Map

- localize cluster headlines, drawer content, topic labels, and trust labels

### Phase 5: Verification

- add targeted frontend tests for locale persistence and UI copy
- add API tests for translation status and locale behavior
- add end-to-end coverage for switching locales and refreshing without resets

## Expected Outcome

After the migration:

- Chinese mode is stable and consistent across the whole app
- locale changes are fast and predictable
- refresh no longer snaps back to English
- translation failures are visible and honest
- the UI shell and content surfaces stay aligned in one language model
