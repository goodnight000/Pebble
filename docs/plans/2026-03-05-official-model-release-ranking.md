# Official Model Release Detection And Ranking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect official model releases without brittle title-only matching and recalibrate importance scores so major releases surface with meaningful separation.

**Architecture:** Add an evidence-based official release detector that combines official-source checks, artifact/version extraction, page/path hints, and body evidence. Feed that structured signal into feature extraction and a recalibrated scoring model, then use the calibrated final score across the live API ranking paths.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, unittest

---

### Task 1: Add failing tests for official release detection and score calibration

**Files:**
- Create: `ai_news/tests/test_official_release_detection.py`
- Create: `ai_news/tests/test_score_calibration.py`

**Step 1: Write failing tests**
- Verify `Introducing GPT-5.4` from an official OpenAI URL is classified as `MODEL_RELEASE`.
- Verify a non-release official post is not promoted to `MODEL_RELEASE`.
- Verify an official model release scores `>= 90`.
- Verify ordinary `OTHER` items remain materially lower than official model releases.

**Step 2: Run tests to verify failure**
Run: `DATABASE_URL='postgresql+psycopg://<postgres-connection>' ./ai_news/.venv/bin/python -m unittest discover -s ai_news/tests -v`
Expected: FAIL on missing detector behavior and score thresholds.

### Task 2: Implement official release evidence detector

**Files:**
- Create: `ai_news/app/features/official_releases.py`
- Modify: `ai_news/app/features/compute.py`

**Step 1: Add detector**
- Implement structured evidence checks using official source detection, artifact/version extraction, page/path hints, and release/body signals.
- Return a structured assessment object with `is_official_model_release` and inferred source entity.

**Step 2: Wire detector into feature extraction**
- Promote confident official releases to `MODEL_RELEASE`.
- Backfill canonical entity from the official source when entity extraction is empty.
- Bias topic probabilities toward `llms` for detected model releases.

### Task 3: Recalibrate importance scoring

**Files:**
- Modify: `ai_news/app/scoring/importance.py`
- Modify: `ai_news/app/scoring/llm_judge.py`

**Step 1: Replace compressed weighted-average score with calibrated base-bands plus bounded adjustments**
- Keep existing signal computation, but switch scoring to event-type base ranges plus additive bonuses.
- Guarantee official model releases can reach `90+`.

**Step 2: Prevent LLM blending from lowering strong rule-based scores**
- Blend conservatively and keep the stronger rule score when appropriate.

### Task 4: Use calibrated scores in live ranking

**Files:**
- Modify: `ai_news/app/api/routes_compat.py`
- Modify: `ai_news/app/api/routes_news.py`

**Step 1: Switch ranking/user-score inputs from `global_score` to `final_score` fallback**
- Apply the calibrated score consistently in list, weekly, and stream endpoints.

**Step 2: Verify GPT-5.4 representative ranking improves**
Run DB-backed checks and confirm the official story now ranks above low-quality paraphrases when available.
