# Trust Verification Redesign

## Goal

Replace the current generic trust-label system with a verification model that matches the actual evidence type of each article. The redesign should stop treating freshness as trust, recognize directly verifiable artifacts like GitHub repos and papers, and produce labels that are honest for readers and stable for ranking logic.

## Current State

The current implementation stores article trust in `articles.trust_score`, `articles.trust_label`, and `articles.trust_components`, with cluster mirrors in `clusters.cluster_trust_score` and `clusters.cluster_trust_label`. The main scorer in `ai_news/app/scoring/trust.py` uses one weighted formula for every article type:

- corroboration `30%`
- official confirmation `25%`
- source trust `20%`
- claim quality `15%`
- primary document `10%`

That score is then converted into one of:

- `official`
- `confirmed`
- `likely`
- `developing`
- `unverified`
- `disputed`

This output is consumed by:

- `ai_news/app/tasks/pipeline.py` for article persistence
- `ai_news/app/scoring/time_decay.py` for `urgent`
- `ai_news/app/scoring/llm_judge.py` for final-score blending
- `ai_news/app/api/routes_graph.py` and `ai_news/app/api/routes_signal_map.py` for cluster trust recomputation
- frontend badge rendering in `src/components/NewsCard.tsx` and `src/components/BreakingAlert.tsx`

## Problems

### 1. The System Mixes Up Different Questions

One label is currently doing all of these jobs at once:

- how direct the evidence is
- how trustworthy the source is
- how corroborated the story is
- how fresh the story is

Those should not be collapsed into a single state.

### 2. `Developing` Is Doing Too Much Work

`developing` currently acts as a catch-all fallback for low-corroboration recent stories. That makes it vague and misleading:

- it describes time, not evidence quality
- it applies to real artifacts that are already directly verifiable
- it crowds out more precise labels

### 3. Directly Verifiable Artifacts Are Under-Recognized

GitHub repo roots, Hugging Face repos, model cards, papers, release notes, and package registry pages should often qualify as primary evidence. The current logic mainly recognizes narrow URL patterns and official-domain matches, so genuine first-party artifacts found via community feeds are downgraded.

### 4. Different Article Types Need Different Rules

The system should not evaluate these the same way:

- official product announcement
- GitHub repo or release
- arXiv preprint
- published paper with DOI
- Reuters-style reported news
- community/social discovery post

### 5. Cluster Trust Is Recomputed Separately

Graph and signal-map routes currently re-derive cluster trust labels instead of trusting one canonical backend computation. That creates drift risk and makes migrations harder.

## Approaches Considered

### Approach 1: Tune Existing Weights And Thresholds

This is the lowest-cost option. It would reduce some obvious label errors, but it would not solve the core problem: one weighted formula is still evaluating incompatible evidence types.

### Approach 2: Keep One Score But Add Type-Aware Weights

This is better. A GitHub repo, a preprint, and a reported article could each use different weights, while still producing one score and one label. The issue is that it still forces incompatible states into one badge.

### Approach 3: Separate Verification State, Freshness State, And Confidence

This is the recommended design.

It introduces:

- `verification_mode`: what kind of item this is
- `verification_state`: what level of evidence we have
- `freshness_state`: how mature the story is
- `verification_confidence`: 0-100 confidence within the correct mode

This matches the product problem much better and removes the need to overload `trust_label`.

## Recommended Model

### 1. Verification Mode

Every article should first be classified into one of these modes:

- `artifact`
- `official_statement`
- `research_preprint`
- `research_published`
- `reported_news`
- `community_post`

This classification is not user-facing. It is an internal routing decision for evidence rules.

### 2. Verification State

This becomes the primary user-facing badge:

- `verified_artifact`
- `official_statement`
- `corroborated_report`
- `single_source_report`
- `community_signal`
- `disputed`
- `corrected_or_retracted`

Interpretation:

- `verified_artifact`: the linked artifact itself is directly verifiable
- `official_statement`: the source is the organization or actor making the claim
- `corroborated_report`: independent reporting and supporting evidence exist
- `single_source_report`: a plausible report exists, but it is not yet independently confirmed
- `community_signal`: discovered in community/social channels without strong evidence yet
- `disputed`: contradiction or denial exists
- `corrected_or_retracted`: the underlying item has been updated negatively

### 3. Freshness State

Freshness should be displayed separately from verification:

- `fresh`: first seen less than 6 hours ago
- `maturing`: 6 to 24 hours old
- `stable`: more than 24 hours old

This replaces the current use of `developing`.

### 4. Verification Confidence

Keep a numeric score from `0` to `100`, but score within the article’s verification mode. The score is not the badge. It is the confidence measure behind the badge and the downstream ranking input.

## Type-Specific Verification Rules

### A. Artifact

Applies to:

- GitHub repos and releases
- Hugging Face models and datasets
- package registry pages
- docs or changelog pages that represent the artifact directly

Primary signals:

- artifact exists and is reachable
- owning org or maintainer identity is credible
- repo/org matches official domain or known maintainer identity
- release/tag/commit signature or release integrity evidence exists
- docs, package, or model card align with the artifact

Score dimensions:

- `identity_authenticity`: 30
- `direct_evidence_strength`: 35
- `artifact_integrity`: 20
- `claim_alignment`: 10
- `external_corroboration`: 5

Rules:

- if the repo or release exists and identity is strong, minimum state is `verified_artifact`
- HN, Reddit, Mastodon, and similar feeds should never force this back down to `community_signal`
- GitHub repo roots should count as primary evidence, not just `/releases` pages

### B. Official Statement

Applies to first-party blogs, announcement pages, press releases, docs pages, status pages, and policy announcements.

Primary signals:

- final URL resolves to official domain
- author or organization identity is explicit
- body text contains the actual statement or direct supporting document
- headline claims are supported by body text

Score dimensions:

- `identity_authenticity`: 35
- `direct_evidence_strength`: 30
- `claim_alignment`: 20
- `external_corroboration`: 10
- `update_status`: 5

Rules:

- official-domain pages with direct supporting content map to `official_statement`
- official pages should not automatically be scored as perfect if the headline overstates what the page actually says

### C. Research Preprint

Applies to arXiv, SSRN, bioRxiv, and similar preprint hosts.

Primary signals:

- canonical paper page exists
- authors and affiliations are present
- code, data, or project page links exist
- claims match the abstract/body
- no retraction/correction signal exists

Score dimensions:

- `paper_identity`: 20
- `document_existence`: 25
- `author_affiliation_strength`: 15
- `supporting_artifacts`: 15
- `claim_alignment`: 15
- `external_corroboration`: 10

Rules:

- preprints are real documents, so they should not be treated as rumor
- preprints are not peer-reviewed, so confidence should be capped below published research unless strong external evidence exists
- recommended cap: `verification_confidence <= 79` unless independently validated

### D. Published Research

Applies to DOI-backed journal and conference publications.

Primary signals:

- DOI and publisher metadata exist
- Crossref or Crossmark update state is clean
- venue and publisher identity are credible
- code/data availability where relevant

Score dimensions:

- `document_identity`: 20
- `publisher_or_venue_strength`: 20
- `update_status`: 20
- `supporting_artifacts`: 10
- `claim_alignment`: 15
- `external_corroboration`: 15

Rules:

- published research without correction or retraction can score higher than preprints
- correction or retraction overrides the normal label to `corrected_or_retracted`

### E. Reported News

Applies to newsroom reporting about events not directly represented by the final URL artifact.

Primary signals:

- attribution quality
- named vs anonymous sourcing
- direct document, quote, transcript, filing, or screenshot evidence
- number of genuinely independent reporters/outlets
- contradiction or denial signals

Score dimensions:

- `attribution_quality`: 25
- `direct_evidence_strength`: 25
- `corroboration_independence`: 25
- `publisher_reliability`: 10
- `claim_alignment`: 10
- `contradiction_penalty`: 5

Rules:

- anonymous-source-only stories must cap at `single_source_report` until corroborated
- two or more independent reports plus direct evidence can graduate to `corroborated_report`
- wire copies and attribution chains should not count as independent corroboration

### F. Community Post

Applies to Mastodon posts, X posts, Reddit posts, Hacker News discussions, forum posts, and similar discovery content.

Primary signals:

- account or poster authenticity
- whether the post links to a direct artifact or official statement
- corroboration by independent sources
- contradiction in replies or external sources

Score dimensions:

- `poster_authenticity`: 20
- `linked_evidence_strength`: 35
- `external_corroboration`: 20
- `provenance`: 10
- `contradiction_penalty`: 15

Rules:

- community posts without linked evidence should remain `community_signal`
- if a community post links to an artifact or official statement, the system should reclassify into the linked evidence mode instead of leaving it as `community_post`
- recommended cap without external evidence: `verification_confidence <= 69`

## Override Rules

These rules should short-circuit the normal scorer:

- if strong contradiction or denial evidence exists, state becomes `disputed`
- if a paper or official item is corrected or retracted, state becomes `corrected_or_retracted`
- if a community discovery link resolves to a verified artifact, state becomes `verified_artifact`
- if an article is anonymous-source-only with no supporting document, state cannot exceed `single_source_report`

## Schema Changes

### Article Fields

Add:

- `verification_mode TEXT`
- `verification_state TEXT`
- `freshness_state TEXT`
- `verification_confidence FLOAT`
- `verification_signals JSON`
- `update_status TEXT`
- `canonical_evidence_url TEXT NULL`

Keep during migration:

- `trust_score`
- `trust_label`
- `trust_components`
- `confirmation_level`

Mapping during migration:

- `trust_score` becomes a compatibility mirror of `verification_confidence`
- `trust_components` becomes a compatibility mirror of `verification_signals`
- `trust_label` is derived from `verification_state` using a legacy adapter

### Cluster Fields

Add:

- `cluster_verification_state TEXT`
- `cluster_freshness_state TEXT`
- `cluster_verification_confidence FLOAT`
- `cluster_verification_signals JSON`

Keep during migration:

- `cluster_trust_score`
- `cluster_trust_label`
- `has_official_confirmation`

## Legacy Compatibility Mapping

For existing UI and ranking code that still expects `trust_label`, map as follows:

- `verified_artifact` -> `official`
- `official_statement` -> `official`
- `corroborated_report` -> `confirmed`
- `single_source_report` -> `likely`
- `community_signal` -> `unverified`
- `disputed` -> `disputed`
- `corrected_or_retracted` -> `disputed`

This mapping is intentionally lossy and should be temporary.

## Pipeline Changes

### 1. Replace One-Step Trust Scoring With Gated Verification

The pipeline should do this in order:

1. classify `verification_mode`
2. resolve evidence identity and canonical evidence URL
3. gather mode-specific evidence signals
4. apply override rules
5. compute `verification_confidence`
6. derive `verification_state`
7. derive `freshness_state`
8. populate compatibility trust fields

### 2. Move Artifact Detection Earlier

Artifact-aware detection should happen before the current trust stage. The existing `is_official_source(article.final_url)` input is too narrow. Detection should understand:

- GitHub repo root
- GitHub release page
- Hugging Face repo/model/dataset
- docs and changelog pages
- arXiv and DOI pages
- package registries

### 3. Stop Recomputing Cluster Trust In API Routes

`routes_graph.py` and `routes_signal_map.py` should read canonical cluster verification fields instead of re-deriving labels from article trust.

## UI Changes

### Primary Badge

Show the new `verification_state` as the trust badge:

- `Verified Artifact`
- `Official Statement`
- `Corroborated Report`
- `Single-Source Report`
- `Community Signal`
- `Disputed`
- `Corrected / Retracted`

### Secondary Badge

Show a smaller freshness badge:

- `Fresh`
- `Maturing`
- `Stable`

This is where the current meaning of `Developing` should move, but with clearer wording.

## Ranking And Urgency Changes

### Urgency

Replace the current `TRUSTED_LABELS` gate with verification-state logic:

- urgent-eligible:
  - `verified_artifact`
  - `official_statement`
  - `corroborated_report`
- optionally urgent if high confidence:
  - `single_source_report` with `verification_confidence >= 70`

`community_signal` should not be urgent by default.

### Final Score Blending

The LLM judge should use:

- `verification_state`
- `verification_confidence`
- `update_status`

instead of the current `trust_label` and `confirmation_level` pair.

## Migration Plan

### Phase 1: Additive Schema

- add new article and cluster columns
- leave all current reads intact

### Phase 2: Dual Write

- compute both legacy trust fields and new verification fields in `pipeline.py`
- keep API responses unchanged except for adding new fields

### Phase 3: Backfill

- rerun scoring for the last 30 to 90 days of articles
- prioritize clusters currently labeled `developing`
- spot-check artifact, official, research, and reported-news examples

### Phase 4: Switch Read Paths

- UI badges switch to `verification_state`
- urgency switches to verification logic
- graph and signal-map switch to canonical cluster verification fields
- cluster label recomputation in API routes is removed

### Phase 5: Remove Compatibility Layer

- remove legacy `trust_label` UI logic
- remove temporary mapping code
- remove stale trust-specific tests once verification coverage replaces them

## Testing

Add fixture-driven tests for at least these cases:

- GitHub repo linked from Hacker News resolves to `verified_artifact`
- GitHub release page with official org identity scores above generic community discovery
- official product announcement on official domain resolves to `official_statement`
- arXiv preprint resolves to research mode and is capped below published paper confidence
- DOI-backed paper with correction or retraction resolves to `corrected_or_retracted`
- single anonymous-source report stays `single_source_report`
- two independent reports with direct evidence resolve to `corroborated_report`
- Mastodon or Reddit post without linked evidence remains `community_signal`
- graph and signal-map endpoints return stored cluster verification values rather than recomputed legacy trust

## Recommendation

Implement Approach 3. It is the only option that fixes the underlying category error instead of tuning around it. The product does not have a generic trust-label problem. It has an evidence-model problem.
