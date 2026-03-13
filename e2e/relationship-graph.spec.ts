import { expect, test } from '@playwright/test';

test.describe('AIPulse - Relationship Graph', () => {
  test.skip(({ browserName, isMobile }) => browserName !== 'chromium' || isMobile, 'Relationship graph coverage is desktop Chromium-only.');

  test('switching to graph mode renders nodes, edges, legend, and no panel by default', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('button', { name: /relationship graph/i }).click();
    await page.locator('.relationship-graph-toggle').getByRole('button', { name: /relationship graph/i }).click();

    const graphCanvas = page.getByTestId('relationship-graph-canvas');
    const graphNodes = page.locator('[data-testid^="graph-node-"]');
    const graphEdges = page.locator('[data-testid^="graph-edge-"]');

    await expect(graphCanvas).toHaveAttribute('data-window', '7d');
    await expect
      .poll(async () => graphNodes.count(), { timeout: 20_000 })
      .toBeGreaterThan(0);
    await expect
      .poll(async () => graphEdges.count(), { timeout: 20_000 })
      .toBeGreaterThan(0);

    await expect(page.getByText(/shared entity/i)).toBeVisible();
    await expect(page.getByText(/event chain/i)).toBeVisible();
    await expect(page.getByText(/market adjacency/i)).toBeVisible();
    await expect(page.getByTestId('relationship-graph-panel')).toHaveCount(0);
    await expect(page.locator('.relationship-graph-canvas')).not.toHaveClass(/graph-panel-open/);
  });

  test('selecting a graph node opens the panel, compresses the graph, and window controls stay interactive', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('button', { name: /relationship graph/i }).click();
    await page.locator('.relationship-graph-toggle').getByRole('button', { name: /relationship graph/i }).click();

    const firstNode = page.locator('[data-testid^="graph-node-"]').first();
    await expect(firstNode).toBeVisible();
    await firstNode.click();

    const panel = page.getByTestId('relationship-graph-panel');
    await expect(panel).toBeVisible();
    await expect(page.locator('.relationship-graph-canvas')).toHaveClass(/graph-panel-open/);
    await expect(panel.getByText(/why this cluster matters/i)).toBeVisible();
    await expect(panel.getByText(/relationship evidence/i)).toBeVisible();
    await expect(panel.getByText(/supporting coverage/i)).toBeVisible();
    await expect(firstNode).toHaveAttribute('aria-pressed', 'true');

    await page.getByRole('button', { name: '30D' }).click();
    await expect(page.getByTestId('relationship-graph-canvas')).toHaveAttribute('data-window', '30d');

    await page.locator('.relationship-graph-toggle').getByRole('button', { name: /^relationship graph$/i }).click();
    await expect
      .poll(async () => page.locator('.signal-bubble').count(), { timeout: 20_000 })
      .toBeGreaterThan(0);
    await expect(page.getByTestId('relationship-graph-panel')).toHaveCount(0);
  });

  test('graph mode exposes zoom controls and reset preserves the active window', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('button', { name: /relationship graph/i }).click();
    await page.locator('.relationship-graph-toggle').getByRole('button', { name: /relationship graph/i }).click();

    const graphCanvas = page.getByTestId('relationship-graph-canvas');
    const zoomIn = page.getByRole('button', { name: /zoom in/i });
    const reset = page.getByRole('button', { name: /reset view/i });

    await expect(graphCanvas).toHaveAttribute('data-window', '7d');
    await expect(zoomIn).toBeVisible();
    await expect(reset).toBeVisible();

    const initialScale = await graphCanvas.getAttribute('data-scale');
    await zoomIn.click();
    await expect(graphCanvas).not.toHaveAttribute('data-scale', initialScale ?? '');

    await reset.click();
    await expect(graphCanvas).toHaveAttribute('data-window', '7d');
    await expect(graphCanvas).toHaveAttribute('data-scale', initialScale ?? '1');
    await expect(page.locator('[data-testid^="graph-node-"]').first()).toBeVisible();
  });

  test('graph nodes can be dragged without losing selection state', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('button', { name: /relationship graph/i }).click();
    await page.locator('.relationship-graph-toggle').getByRole('button', { name: /relationship graph/i }).click();

    const firstNode = page.locator('[data-testid^="graph-node-"]').first();
    await expect(firstNode).toBeVisible();

    const initialX = await firstNode.getAttribute('data-screen-x');
    const initialY = await firstNode.getAttribute('data-screen-y');

    await firstNode.dragTo(page.locator('[data-testid="relationship-graph-canvas"]'), {
      targetPosition: { x: 220, y: 220 },
    });
    await firstNode.click();

    await expect(firstNode).toHaveAttribute('aria-pressed', 'true');
    await expect(firstNode).not.toHaveAttribute('data-screen-x', initialX ?? '');
    await expect(firstNode).not.toHaveAttribute('data-screen-y', initialY ?? '');
  });
});
