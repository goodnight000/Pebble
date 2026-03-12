import { test, expect } from '@playwright/test';

test.describe('AIPulse - Signal Map', () => {
  test.skip(({ browserName, isMobile }) => browserName !== 'chromium' || isMobile, 'Signal map regression coverage is desktop Chromium-only.');

  test('hovering a signal bubble shows tooltip and selecting it opens the drawer', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('button', { name: /signal map/i })).toBeVisible();
    await page.getByRole('button', { name: /signal map/i }).click();

    const bubbleGroups = page.locator('g.signal-bubble');
    const bubbleCircles = bubbleGroups.locator('circle.signal-bubble-circle');
    const tooltip = page.locator('.signal-tooltip');
    const drawer = page.locator('.cluster-drawer');

    await expect
      .poll(async () => await bubbleGroups.count(), {
        message: 'expected the signal map to render at least one bubble',
        timeout: 15_000,
      })
      .toBeGreaterThan(0);

    const firstBubble = bubbleCircles.first();
    await expect(firstBubble).toBeVisible();
    const beforeHover = await firstBubble.boundingBox();
    expect(beforeHover).not.toBeNull();

    // Hover the bubble itself instead of the full SVG to keep the signal focused on node interactivity.
    await firstBubble.hover({ force: true });
    await expect(tooltip).toBeVisible();
    await expect(tooltip.locator('.signal-tooltip-headline')).not.toHaveText(/^$/);
    await page.waitForTimeout(250);

    const afterHover = await firstBubble.boundingBox();
    expect(afterHover).not.toBeNull();

    if (beforeHover && afterHover) {
      expect(Math.abs(afterHover.x - beforeHover.x)).toBeLessThan(2);
      expect(Math.abs(afterHover.y - beforeHover.y)).toBeLessThan(2);
      expect(Math.abs(afterHover.width - beforeHover.width)).toBeLessThan(2);
      expect(Math.abs(afterHover.height - beforeHover.height)).toBeLessThan(2);
    }

    await firstBubble.click({ force: true });
    await expect(drawer).toHaveClass(/cluster-drawer--open/);

    const drawerHeadline = drawer.locator('.cluster-drawer-headline');
    const drawerStats = drawer.locator('.cluster-drawer-stat');

    await expect(drawerHeadline).toBeVisible();
    await expect(drawerHeadline).not.toHaveText(/^$/);
    await expect(drawerStats).toHaveCount(4);
  });
});
