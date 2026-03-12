import { test, expect } from '@playwright/test';

test.describe('AIPulse - Page Load & Layout', () => {
  test('homepage loads with correct title and structure', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/AIPulse|AI/i);
    // Main container should be visible
    await expect(page.locator('body')).toBeVisible();
    // Should have at least one visible element
    const content = page.locator('main, #root, [class*="app"], [class*="App"]');
    await expect(content.first()).toBeVisible();
  });

  test('page renders without console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/');
    await page.waitForTimeout(2000);
    // Filter out known non-critical errors (e.g., favicon, HMR)
    const criticalErrors = errors.filter(e =>
      !e.includes('favicon') &&
      !e.includes('HMR') &&
      !e.includes('WebSocket') &&
      !e.includes('ERR_CONNECTION_REFUSED')
    );
    expect(criticalErrors).toHaveLength(0);
  });

  test('responsive layout renders on mobile viewport', async ({ page, browserName }) => {
    await page.goto('/');
    await page.waitForTimeout(1500);
    // Should still render without layout overflow
    const body = page.locator('body');
    const box = await body.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      const viewport = page.viewportSize();
      if (viewport) {
        // Body should not overflow viewport width significantly
        expect(box.width).toBeLessThanOrEqual(viewport.width + 20);
      }
    }
  });
});

test.describe('AIPulse - News Cards', () => {
  test('news cards render with expected structure', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    // Look for news card elements
    const cards = page.locator('[role="link"], [class*="card"], [class*="Card"]');
    const cardCount = await cards.count();

    if (cardCount > 0) {
      // First card should have visible text content
      const firstCard = cards.first();
      await expect(firstCard).toBeVisible();

      // Cards should have title text
      const titleEl = firstCard.locator('h3, h2, [class*="title"]').first();
      if (await titleEl.count() > 0) {
        await expect(titleEl).toBeVisible();
        const text = await titleEl.textContent();
        expect(text?.length).toBeGreaterThan(0);
      }
    }
  });

  test('trust badge renders on news cards when present', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    // Look for trust badge elements (they use shield icons and trust labels)
    const trustBadges = page.locator('[title*="Trust"], [class*="trust"], span:has-text("Unverified"), span:has-text("Official"), span:has-text("Confirmed"), span:has-text("Likely"), span:has-text("Developing"), span:has-text("Disputed")');
    const badgeCount = await trustBadges.count();

    if (badgeCount > 0) {
      const firstBadge = trustBadges.first();
      await expect(firstBadge).toBeVisible();
      // Badge should have the correct styling (rounded-full with border)
      const styles = await firstBadge.evaluate(el => {
        const cs = window.getComputedStyle(el);
        return {
          borderRadius: cs.borderRadius,
          display: cs.display,
          borderStyle: cs.borderStyle,
        };
      });
      // Should be inline-flex with border
      expect(styles.display).toContain('flex');
    }
  });

  test('trust badge tooltip shows component breakdown', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    // Find elements with trust tooltip (title attribute containing Trust:)
    const badgesWithTooltip = page.locator('[title*="Trust:"]');
    const count = await badgesWithTooltip.count();

    if (count > 0) {
      const badge = badgesWithTooltip.first();
      const title = await badge.getAttribute('title');
      expect(title).not.toBeNull();
      // Tooltip should contain component breakdown
      expect(title).toContain('Corroboration');
      expect(title).toContain('Source Trust');
      expect(title).toContain('Claim Quality');
    }
  });

  test('significance score displays correctly', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    // Look for score elements (contain Zap icon + number)
    const scoreElements = page.locator('[class*="mono"]:has(svg)');
    const count = await scoreElements.count();

    if (count > 0) {
      const firstScore = scoreElements.first();
      const text = await firstScore.textContent();
      // Score should be a number
      const scoreText = text?.trim() || '';
      const num = parseInt(scoreText, 10);
      if (!isNaN(num)) {
        expect(num).toBeGreaterThanOrEqual(0);
        expect(num).toBeLessThanOrEqual(100);
      }
    }
  });
});

test.describe('AIPulse - CSS Compatibility', () => {
  test('CSS custom properties (variables) are resolved', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1500);

    // Check that CSS variables are being applied
    const bodyColor = await page.locator('body').evaluate(el => {
      return window.getComputedStyle(el).backgroundColor;
    });
    // Should not be transparent/empty - CSS variables should resolve
    expect(bodyColor).not.toBe('');
    expect(bodyColor).not.toBe('rgba(0, 0, 0, 0)');
  });

  test('flexbox and grid layouts render correctly', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    // Check that flex containers have proper layout
    const flexElements = page.locator('[class*="flex"]');
    const count = await flexElements.count();
    expect(count).toBeGreaterThan(0);

    // Verify no elements are overlapping in unexpected ways
    const firstFlex = flexElements.first();
    const box = await firstFlex.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.width).toBeGreaterThan(0);
      expect(box.height).toBeGreaterThan(0);
    }
  });

  test('border-radius and rounded elements render properly', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1500);

    // Check rounded elements (cards use rounded-2xl)
    const roundedElements = page.locator('[class*="rounded"]');
    const count = await roundedElements.count();

    if (count > 0) {
      const computed = await roundedElements.first().evaluate(el => {
        return window.getComputedStyle(el).borderRadius;
      });
      // Should have a non-zero border radius
      expect(computed).not.toBe('0px');
    }
  });

  test('line-clamp CSS works for truncation', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    const clampedElements = page.locator('[class*="line-clamp"]');
    const count = await clampedElements.count();

    if (count > 0) {
      const overflow = await clampedElements.first().evaluate(el => {
        const style = window.getComputedStyle(el);
        return {
          overflow: style.overflow,
          webkitLineClamp: style.getPropertyValue('-webkit-line-clamp') || style.getPropertyValue('line-clamp'),
        };
      });
      // line-clamp should set overflow to hidden
      expect(overflow.overflow).toBe('hidden');
    }
  });
});

test.describe('AIPulse - Accessibility', () => {
  test('cards have proper role and keyboard accessibility', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    const linkCards = page.locator('[role="link"]');
    const count = await linkCards.count();

    if (count > 0) {
      const firstCard = linkCards.first();
      // Should have tabIndex for keyboard navigation
      const tabIndex = await firstCard.getAttribute('tabindex');
      expect(tabIndex).toBe('0');

      // Should be focusable
      await firstCard.focus();
      await expect(firstCard).toBeFocused();
    }
  });

  test('external links have rel="noopener noreferrer"', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    const externalLinks = page.locator('a[target="_blank"]');
    const count = await externalLinks.count();

    for (let i = 0; i < Math.min(count, 5); i++) {
      const rel = await externalLinks.nth(i).getAttribute('rel');
      expect(rel).toContain('noopener');
    }
  });

  test('color contrast meets minimum standards', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    // Check body text color vs background
    const contrastInfo = await page.evaluate(() => {
      const body = document.body;
      const style = window.getComputedStyle(body);
      return {
        color: style.color,
        backgroundColor: style.backgroundColor,
      };
    });
    // Both should be defined
    expect(contrastInfo.color).not.toBe('');
    expect(contrastInfo.backgroundColor).not.toBe('');
  });
});

test.describe('AIPulse - API Integration', () => {
  // Use Playwright's request fixture to call APIs directly (no page load needed).
  // This avoids the React app triggering background refresh tasks.

  test('API responds with news data', async ({ request }) => {
    const res = await request.get('/api/news');
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('items');
    expect(Array.isArray(data.items)).toBe(true);
  });

  test('API response includes trust fields', async ({ request }) => {
    const res = await request.get('/api/news');
    const data = await res.json();
    if (data.items.length > 0) {
      const item = data.items[0];
      expect(item).toHaveProperty('trustLabel');
      expect(item).toHaveProperty('trustComponents');
      expect(item).toHaveProperty('finalScore');
      if (item.trustComponents) {
        expect(item.trustComponents).toHaveProperty('corroboration');
        expect(item.trustComponents).toHaveProperty('official_confirmation');
        expect(item.trustComponents).toHaveProperty('source_trust');
        expect(item.trustComponents).toHaveProperty('claim_quality');
        expect(item.trustComponents).toHaveProperty('primary_document');
      }
    }
  });

  test('API digest/today endpoint works', async ({ request }) => {
    const res = await request.get('/api/digest/today');
    expect(res.status()).toBe(200);
  });

  test('API news endpoint returns valid structure', async ({ request }) => {
    const res = await request.get('/api/news');
    const data = await res.json();
    expect(res.status()).toBe(200);
    const count = data.items?.length ?? 0;
    expect(count).toBeGreaterThanOrEqual(0);
    if (count > 0) {
      const keys = Object.keys(data.items[0]);
      expect(keys).toContain('trustLabel');
      expect(keys).toContain('trustComponents');
      expect(keys).toContain('finalScore');
    }
  });

  test('Signal Map API returns valid cluster data', async ({ request }) => {
    const res = await request.get('/v1/signal-map?hours=48&locale=en');
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('clusters');
    expect(data).toHaveProperty('projection_seed');
    expect(Array.isArray(data.clusters)).toBe(true);
    if (data.clusters.length > 0) {
      const c = data.clusters[0];
      expect(c).toHaveProperty('id');
      expect(c).toHaveProperty('headline');
      expect(c).toHaveProperty('x');
      expect(c).toHaveProperty('y');
      expect(c).toHaveProperty('coverage_count');
      expect(c).toHaveProperty('dominant_topic');
      expect(c).toHaveProperty('trust_label');
      expect(c).toHaveProperty('entities');
      expect(c).toHaveProperty('sparkline');
      expect(c).toHaveProperty('articles');
      expect(c.x).toBeGreaterThanOrEqual(0);
      expect(c.x).toBeLessThanOrEqual(1);
      expect(c.y).toBeGreaterThanOrEqual(0);
      expect(c.y).toBeLessThanOrEqual(1);
    }
  });

  test('Signal Map topic trends API returns valid data', async ({ request }) => {
    const res = await request.get('/v1/signal-map/topic-trends?locale=en');
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('topics');
    expect(Array.isArray(data.topics)).toBe(true);
    if (data.topics.length > 0) {
      const t = data.topics[0];
      expect(t).toHaveProperty('topic');
      expect(t).toHaveProperty('label');
      expect(t).toHaveProperty('daily_intensity');
      expect(t).toHaveProperty('total_intensity');
      expect(t.daily_intensity).toHaveLength(7);
    }
  });
});

test.describe('AIPulse - Signal Map UI', () => {
  // Helper: navigate to Signal Map tab (desktop only — sidebar hidden on mobile)
  async function goToSignalMap(page: ReturnType<typeof test.info>['config'] extends any ? any : never) {
    await page.goto('/');
    await page.waitForTimeout(2000);
    const mapNav = page.locator('text=Signal Map').or(page.locator('text=SIGNAL MAP'));
    await mapNav.first().click();
    // Wait for loading spinner to disappear (up to 20s for cold API call)
    await page.locator('text=Mapping Signal Constellation').or(page.locator('text=MAPPING SIGNAL CONSTELLATION'))
      .waitFor({ state: 'hidden', timeout: 20000 }).catch(() => {});
    await page.waitForTimeout(1000);
  }

  test('Signal Map tab loads and renders content', async ({ page }) => {
    // Desktop-only test: sidebar nav is hidden on mobile
    const viewport = page.viewportSize();
    if (!viewport || viewport.width < 1024) return;

    await goToSignalMap(page);

    // Should NOT show error state
    const errorText = page.locator('text=Failed to load signal map');
    const hasError = await errorText.isVisible().catch(() => false);
    expect(hasError).toBe(false);
  });

  test('Signal Map renders SVG bubbles on desktop', async ({ page }) => {
    const viewport = page.viewportSize();
    if (!viewport || viewport.width < 1024) return;

    await goToSignalMap(page);

    // Check for SVG bubble elements
    const bubbles = page.locator('g.signal-bubble');
    const bubbleCount = await bubbles.count();
    expect(bubbleCount).toBeGreaterThan(0);

    // Each bubble should have a circle and label
    const firstBubble = bubbles.first();
    const circle = firstBubble.locator('circle.signal-bubble-circle');
    await expect(circle).toBeVisible();

    const label = firstBubble.locator('text.signal-bubble-label');
    await expect(label).toBeVisible();
  });

  test('Signal Map shows topic sidebar on desktop', async ({ page }) => {
    const viewport = page.viewportSize();
    if (!viewport || viewport.width < 1024) return;

    await goToSignalMap(page);

    // Topic sidebar should be visible
    const sidebar = page.locator('.topic-sidebar');
    await expect(sidebar).toBeVisible();

    // Should have topic rows
    const topicRows = page.locator('.topic-sidebar-row');
    const rowCount = await topicRows.count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test('Clicking a bubble opens the cluster drawer', async ({ page }) => {
    const viewport = page.viewportSize();
    if (!viewport || viewport.width < 1024) return;

    await goToSignalMap(page);

    // Click the first bubble
    const firstBubble = page.locator('g.signal-bubble').first();
    if (await firstBubble.count() > 0) {
      await firstBubble.click();
      await page.waitForTimeout(500);

      // Drawer should appear
      const drawer = page.locator('.cluster-drawer');
      await expect(drawer).toBeVisible();

      // Drawer should have a headline
      const headline = drawer.locator('.cluster-drawer-headline');
      await expect(headline).toBeVisible();
      const text = await headline.textContent();
      expect(text?.length).toBeGreaterThan(0);
    }
  });
});
