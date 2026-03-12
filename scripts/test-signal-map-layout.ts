import assert from 'node:assert/strict';
import {
  clampTooltipPosition,
  fitClusterPositions,
  pickVisibleLabels,
  resolveBubbleRadius,
} from '../src/components/signalMapLayout';
import type { SignalMapCluster } from '../src/types';

const makeCluster = (
  id: string,
  overrides: Partial<SignalMapCluster> = {},
): SignalMapCluster => ({
  id,
  headline: `${id} headline`,
  x: 0.5,
  y: 0.5,
  coverageCount: 5,
  sourcesCount: 3,
  maxGlobalScore: 50,
  velocity: 2,
  pulsing: false,
  trustScore: 0.5,
  trustLabel: 'likely',
  dominantTopic: 'llms',
  topicWeights: { llms: 1 },
  dominantEventType: 'launch',
  entities: [],
  sparkline: [1, 2, 3, 2, 1],
  firstSeenAt: '2026-03-12T00:00:00Z',
  lastSeenAt: '2026-03-12T02:00:00Z',
  ageHours: 2,
  articles: [],
  ...overrides,
});

const spreadClusters = [
  makeCluster('cluster-a', { x: 0.46, y: 0.48, coverageCount: 8 }),
  makeCluster('cluster-b', { x: 0.5, y: 0.5, coverageCount: 20 }),
  makeCluster('cluster-c', { x: 0.54, y: 0.52, coverageCount: 6 }),
];

const fitted = fitClusterPositions(spreadClusters, {
  width: 900,
  height: 640,
  padding: 64,
  gap: 12,
});

assert.equal(fitted.size, spreadClusters.length, 'all clusters should receive fitted positions');

const fittedXs = [...fitted.values()].map((position) => position.x);
const fittedYs = [...fitted.values()].map((position) => position.y);

assert.ok(
  Math.max(...fittedXs) - Math.min(...fittedXs) > 240,
  'fitted positions should expand narrow projected x ranges into usable canvas width',
);
assert.ok(
  Math.max(...fittedYs) - Math.min(...fittedYs) > 120,
  'fitted positions should expand narrow projected y ranges into usable canvas height',
);
assert.ok(
  fittedXs.every((x) => x >= 64 && x <= 836),
  'all fitted x coordinates should remain inside the padded inner bounds',
);
assert.ok(
  fittedYs.every((y) => y >= 64 && y <= 576),
  'all fitted y coordinates should remain inside the padded inner bounds',
);

const smallRadius = resolveBubbleRadius(3, spreadClusters);
const largeRadius = resolveBubbleRadius(20, spreadClusters);
assert.ok(largeRadius > smallRadius, 'larger coverage should produce a larger bubble radius');

const labelIds = pickVisibleLabels(
  [
    makeCluster('selected-cluster', { coverageCount: 4, maxGlobalScore: 10 }),
    makeCluster('high-priority', { coverageCount: 25, maxGlobalScore: 96, pulsing: true }),
    makeCluster('low-priority', { coverageCount: 2, maxGlobalScore: 8 }),
  ],
  new Map([
    ['selected-cluster', { x: 180, y: 160 }],
    ['high-priority', { x: 420, y: 220 }],
    ['low-priority', { x: 430, y: 230 }],
  ]),
  'selected-cluster',
  2,
);

assert.ok(labelIds.has('selected-cluster'), 'selected cluster should always stay labeled');
assert.ok(labelIds.has('high-priority'), 'important clusters should win label priority');
assert.ok(
  !labelIds.has('low-priority'),
  'lower-priority nearby labels should be suppressed when they collide with stronger labels',
);

const tooltip = clampTooltipPosition(
  { x: 790, y: 8 },
  { width: 180, height: 110 },
  { width: 800, height: 600 },
);

assert.ok(tooltip.left <= 608, 'tooltip should be clamped away from the right edge');
assert.ok(tooltip.top >= 12, 'tooltip should be clamped away from the top edge');

console.log('signal map layout verification passed');
