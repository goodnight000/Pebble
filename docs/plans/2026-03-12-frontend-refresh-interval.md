# Frontend Refresh Interval Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop live frontend monitoring and refresh the digest on initial load, every 30 minutes, or when the user clicks refresh.

**Architecture:** Keep the backend scheduler and digest generation unchanged. Remove the frontend's live `subscribe()` path from the main app and replace it with a single interval-driven digest reload in the React lifecycle.

**Tech Stack:** React 19, TypeScript, Vite, Node assert-based verification scripts

---

### Task 1: Add regression coverage

**Files:**
- Create: `scripts/test-app-refresh-policy.ts`
- Test: `scripts/test-app-refresh-policy.ts`

**Step 1: Write the failing test**

Add a script that asserts:
- `src/App.tsx` does not call `aiService.subscribe(`
- `src/App.tsx` uses `30 * 60 * 1000` as the refresh interval

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/tsx scripts/test-app-refresh-policy.ts`
Expected: FAIL because the app still subscribes to live updates.

### Task 2: Implement interval-based refresh

**Files:**
- Modify: `src/App.tsx`

**Step 1: Write minimal implementation**

Update the main lifecycle effect so it:
- loads the digest once on mount
- starts a `setInterval` that calls `loadInitialNews` every 30 minutes
- clears the interval on unmount
- removes the live subscription branch

**Step 2: Run test to verify it passes**

Run: `./node_modules/.bin/tsx scripts/test-app-refresh-policy.ts`
Expected: PASS

### Task 3: Verify app still builds

**Files:**
- No source changes required unless verification exposes a type error

**Step 1: Run targeted verification**

Run: `npm run build`
Expected: PASS
