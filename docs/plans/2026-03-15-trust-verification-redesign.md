# Trust Verification Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the legacy trust-label pipeline with a type-aware verification model that separates evidence state, freshness, and confidence while keeping a temporary compatibility layer for existing UI and ranking code.

**Architecture:** Introduce a new verification scorer beside the current trust scorer, dual-write new article and cluster fields, and migrate downstream consumers in phases. The implementation should keep the current product working while progressively switching urgency, graph, signal-map, and UI badges onto canonical verification fields.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic-style DB migration pattern used in this repo, Python unit tests, React, TypeScript.

---

### Task 1: Add additive schema and failing verification-model tests

**Files:**
- Create: `ai_news/tests/test_verification_model.py`
- Modify: `ai_news/app/models.py`
- Create: `ai_news/migrations/<timestamp>_add_verification_fields.py`

**Step 1: Write the failing test**
- Create `ai_news/tests/test_verification_model.py` with fixtures for:
  - GitHub repo discovered via Hacker News
  - official blog announcement
  - anonymous-source news report
  - Mastodon-only post
- Assert future outputs for:
  - `verification_mode`
  - `verification_state`
  - `freshness_state`
  - `verification_confidence`

**Step 2: Run test to verify it fails**
Run: `./ai_news/.venv/bin/python -m unittest ai_news/tests/test_verification_model.py`
Expected: FAIL because the verification scorer and schema fields do not exist yet.

**Step 3: Write minimal implementation**
- Add article columns in `ai_news/app/models.py`:
  - `verification_mode`
  - `verification_state`
  - `freshness_state`
  - `verification_confidence`
  - `verification_signals`
  - `update_status`
  - `canonical_evidence_url`
- Add cluster columns:
  - `cluster_verification_state`
  - `cluster_freshness_state`
  - `cluster_verification_confidence`
  - `cluster_verification_signals`
- Add the matching DB migration file.

**Step 4: Run test to verify it still fails for logic reasons**
Run: `./ai_news/.venv/bin/python -m unittest ai_news/tests/test_verification_model.py`
Expected: FAIL because schema exists but scoring logic is still missing.

**Step 5: Commit**
```bash
git add ai_news/tests/test_verification_model.py ai_news/app/models.py ai_news/migrations
git commit -m "test: add verification model schema scaffolding"
```

### Task 2: Build the article verification classifier and scorer

**Files:**
- Create: `ai_news/app/scoring/verification.py`
- Modify: `ai_news/app/scoring/trust.py`
- Modify: `ai_news/app/tasks/pipeline.py`
- Test: `ai_news/tests/test_verification_model.py`

**Step 1: Write the failing test**
- Extend `ai_news/tests/test_verification_model.py` with explicit assertions for:
  - GitHub repo root maps to `artifact` and `verified_artifact`
  - official blog post maps to `official_statement`
  - anonymous-source-only report caps at `single_source_report`
  - community post without linked evidence stays `community_signal`

**Step 2: Run test to verify it fails**
Run: `./ai_news/.venv/bin/python -m unittest ai_news/tests/test_verification_model.py`
Expected: FAIL because the new classifier and scorer do not exist.

**Step 3: Write minimal implementation**
- Add `ai_news/app/scoring/verification.py` with:
  - `VerificationInputs`
  - `classify_verification_mode(...)`
  - `compute_verification(...)`
  - freshness derivation helper
  - legacy compatibility mapping helper
- Recognize artifact URLs for:
  - GitHub repo roots and releases
  - Hugging Face model/dataset pages
  - arXiv and DOI paper URLs
  - package registry pages
- Update `pipeline.py` to dual-write:
  - new verification fields
  - legacy trust fields derived from the compatibility adapter
- Keep `ai_news/app/scoring/trust.py` only as the compatibility layer during migration, or reduce it to pure legacy mapping if that is cleaner.

**Step 4: Run test to verify it passes**
Run: `./ai_news/.venv/bin/python -m unittest ai_news/tests/test_verification_model.py`
Expected: PASS.

**Step 5: Commit**
```bash
git add ai_news/app/scoring/verification.py ai_news/app/scoring/trust.py ai_news/app/tasks/pipeline.py ai_news/tests/test_verification_model.py
git commit -m "feat: add article verification scoring"
```

### Task 3: Canonicalize cluster verification and remove route-level trust recomputation

**Files:**
- Create: `ai_news/tests/test_cluster_verification.py`
- Modify: `ai_news/app/tasks/pipeline.py`
- Modify: `ai_news/app/api/routes_graph.py`
- Modify: `ai_news/app/api/routes_signal_map.py`

**Step 1: Write the failing test**
- Create `ai_news/tests/test_cluster_verification.py` with assertions that:
  - cluster verification state comes from stored cluster fields
  - graph and signal-map routes do not recompute `developing`/`likely`/`confirmed`
  - a cluster with a top verified artifact remains `verified_artifact`

**Step 2: Run test to verify it fails**
Run: `./ai_news/.venv/bin/python -m unittest ai_news/tests/test_cluster_verification.py`
Expected: FAIL because routes still derive cluster trust locally.

**Step 3: Write minimal implementation**
- Update `pipeline.py` to persist:
  - `cluster_verification_state`
  - `cluster_freshness_state`
  - `cluster_verification_confidence`
  - `cluster_verification_signals`
- Replace `_compute_cluster_trust(...)` usage in:
  - `ai_news/app/api/routes_graph.py`
  - `ai_news/app/api/routes_signal_map.py`
- Make the routes read stored cluster verification fields directly.

**Step 4: Run test to verify it passes**
Run: `./ai_news/.venv/bin/python -m unittest ai_news/tests/test_cluster_verification.py`
Expected: PASS.

**Step 5: Commit**
```bash
git add ai_news/app/tasks/pipeline.py ai_news/app/api/routes_graph.py ai_news/app/api/routes_signal_map.py ai_news/tests/test_cluster_verification.py
git commit -m "refactor: use canonical cluster verification fields"
```

### Task 4: Migrate urgency and final-score consumers to verification semantics

**Files:**
- Create: `ai_news/tests/test_verification_consumers.py`
- Modify: `ai_news/app/scoring/time_decay.py`
- Modify: `ai_news/app/scoring/llm_judge.py`
- Modify: `ai_news/app/scoring/editorial_rank.py`
- Modify: `ai_news/tests/test_e2e_scoring_paths.py`

**Step 1: Write the failing test**
- Create `ai_news/tests/test_verification_consumers.py` with assertions that:
  - `verified_artifact`, `official_statement`, and `corroborated_report` can be urgent
  - `community_signal` cannot be urgent by default
  - `corrected_or_retracted` is penalized in final scoring
- Extend `ai_news/tests/test_e2e_scoring_paths.py` to assert compatibility behavior under dual-write.

**Step 2: Run test to verify it fails**
Run: `./ai_news/.venv/bin/python -m unittest ai_news/tests/test_verification_consumers.py ai_news/tests/test_e2e_scoring_paths.py`
Expected: FAIL because consumers still key off legacy trust labels.

**Step 3: Write minimal implementation**
- Update `time_decay.py` to gate urgency by verification state instead of `TRUSTED_LABELS`.
- Update `llm_judge.py` to accept:
  - `verification_state`
  - `verification_confidence`
  - `update_status`
- Update `editorial_rank.py` if needed so cluster verification state is interpreted consistently with the new fields.

**Step 4: Run test to verify it passes**
Run: `./ai_news/.venv/bin/python -m unittest ai_news/tests/test_verification_consumers.py ai_news/tests/test_e2e_scoring_paths.py`
Expected: PASS.

**Step 5: Commit**
```bash
git add ai_news/app/scoring/time_decay.py ai_news/app/scoring/llm_judge.py ai_news/app/scoring/editorial_rank.py ai_news/tests/test_verification_consumers.py ai_news/tests/test_e2e_scoring_paths.py
git commit -m "feat: migrate ranking consumers to verification states"
```

### Task 5: Add API fields and switch the UI badge model

**Files:**
- Modify: `ai_news/app/api/routes_api.py`
- Modify: `ai_news/app/api/routes_compat.py`
- Modify: `src/types/index.ts`
- Modify: `src/i18n/messages.ts`
- Modify: `src/components/NewsCard.tsx`
- Modify: `src/components/BreakingAlert.tsx`
- Create: `src/components/FreshnessBadge.tsx`

**Step 1: Write the failing test**
- Add or extend a frontend render test or lightweight verification script to assert that:
  - cards render the new verification badge
  - cards render a separate freshness badge
  - legacy `trustLabel` remains available during compatibility mode

**Step 2: Run test to verify it fails**
Run: `npm run build`
Expected: PASS for the current app, but the new fields and badge components are still missing.

**Step 3: Write minimal implementation**
- Add new API fields for article and cluster responses:
  - `verificationState`
  - `verificationConfidence`
  - `freshnessState`
  - optional `verificationSignals`
- Add frontend type support.
- Replace current badge mappings in `NewsCard.tsx` and `BreakingAlert.tsx`.
- Introduce a separate freshness badge component.
- Keep legacy `trustLabel` in the payload until the compatibility phase ends.

**Step 4: Run verification**
Run: `npm run build`
Expected: PASS.

**Step 5: Commit**
```bash
git add ai_news/app/api/routes_api.py ai_news/app/api/routes_compat.py src/types/index.ts src/i18n/messages.ts src/components/NewsCard.tsx src/components/BreakingAlert.tsx src/components/FreshnessBadge.tsx
git commit -m "feat: expose verification states in the UI"
```

### Task 6: Backfill, review, and remove the hottest migration risks

**Files:**
- Create: `ai_news/scripts/backfill_verification.py`
- Create: `ai_news/tests/test_verification_backfill.py`
- Modify: `docs/plans/2026-03-15-trust-verification-redesign-design.md`
- Modify: `docs/plans/2026-03-15-trust-verification-redesign.md`

**Step 1: Write the failing test**
- Create `ai_news/tests/test_verification_backfill.py` covering:
  - existing article rows with null verification fields
  - preservation of legacy trust fields during backfill
  - recomputation of cluster verification fields

**Step 2: Run test to verify it fails**
Run: `./ai_news/.venv/bin/python -m unittest ai_news/tests/test_verification_backfill.py`
Expected: FAIL because the backfill script does not exist.

**Step 3: Write minimal implementation**
- Add `ai_news/scripts/backfill_verification.py` to rescore a bounded date range.
- Include dry-run and batch-size options.
- Document rollout order and rollback notes in the design or runbook docs.

**Step 4: Request code review**
- Use a review subagent focused on migration safety, compatibility leaks, and label regressions.

**Step 5: Apply fixes**
- Address any correctness issues found in review without widening scope.

**Step 6: Final verification**
Run: `./ai_news/.venv/bin/python -m unittest ai_news/tests/test_verification_model.py ai_news/tests/test_cluster_verification.py ai_news/tests/test_verification_consumers.py ai_news/tests/test_verification_backfill.py`
Run: `npm run build`
Expected: PASS.

**Step 7: Commit**
```bash
git add ai_news/scripts/backfill_verification.py ai_news/tests/test_verification_backfill.py docs/plans/2026-03-15-trust-verification-redesign-design.md docs/plans/2026-03-15-trust-verification-redesign.md
git commit -m "chore: add verification backfill and rollout docs"
```

Plan complete and saved to `docs/plans/2026-03-15-trust-verification-redesign.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
