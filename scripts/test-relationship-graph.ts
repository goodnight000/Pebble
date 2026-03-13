import assert from 'node:assert/strict';
import {
  applyRelationshipGraphPositionOverrides,
  buildRelationshipGraphVisuals,
  RELATIONSHIP_GRAPH_WINDOW_HOURS,
  RELATIONSHIP_GRAPH_WINDOWS,
  mergeRelationshipGraphPositionOverrides,
  buildRelationshipGraphResponse,
  buildLocalNeighborhood,
  computeGraphViewport,
  pickVisibleNodeLabels,
  projectRelationshipGraphLayout,
  resolveNodeTopicColor,
  resolveRelationshipGraphEdgeTier,
  resolveRelationshipGraphZoomLevel,
  resolveVisibleGraphError,
  pickVisibleEdges,
  scoreEdge,
} from '../src/components/relationshipGraph';
import type {
  RelationshipGraphEdge,
  RelationshipGraphEdgeCandidate,
  RelationshipGraphNode,
} from '../src/types';

const makeNode = (
  id: string,
  overrides: Partial<RelationshipGraphNode> = {},
): RelationshipGraphNode => ({
  id,
  clusterId: id,
  headline: `${id} headline`,
  dominantTopic: 'llms',
  dominantEventType: 'launch',
  importance: 0.5,
  coverageCount: 5,
  sourcesCount: 3,
  velocity: 1.2,
  ageHours: 8,
  trustLabel: 'likely',
  maxGlobalScore: 62,
  keyEntities: ['OpenAI'],
  positionSeed: { x: 0.5, y: 0.5 },
  ...overrides,
});

const makeEdge = (
  id: string,
  source: string,
  target: string,
  overrides: Partial<RelationshipGraphEdge> = {},
): RelationshipGraphEdge => ({
  id,
  source,
  target,
  type: 'market-adjacency',
  score: 0.35,
  evidence: ['Shared market lane'],
  hiddenByDefault: false,
  ...overrides,
});

assert.deepEqual(
  RELATIONSHIP_GRAPH_WINDOWS,
  ['7d', '30d'],
  'relationship graph windows should expose 7d and 30d rolling views',
);
assert.deepEqual(
  RELATIONSHIP_GRAPH_WINDOW_HOURS,
  {
    '7d': 168,
    '30d': 720,
  },
  'rolling graph windows should map to 168 and 720 hours',
);

assert.equal(
  resolveVisibleGraphError(
    '30d',
    {
      '7d': { generatedAt: '2026-03-12T12:00:00Z' },
    },
    {
      '30d': 'Failed to load relationship graph.',
    },
  ),
  'Failed to load relationship graph.',
  'the active graph window should surface its own fetch error when no snapshot exists',
);

assert.equal(
  resolveVisibleGraphError(
    '7d',
    {
      '7d': { generatedAt: '2026-03-12T12:00:00Z' },
    },
    {
      '30d': 'Failed to load relationship graph.',
    },
  ),
  null,
  'switching back to a healthy cached window should clear a different window error',
);

const sharedEntityScore = scoreEdge({
  source: makeNode('alpha', { keyEntities: ['OpenAI', 'Anthropic'] }),
  target: makeNode('beta', { keyEntities: ['Anthropic', 'Mistral'] }),
  sharedEntities: ['Anthropic'],
  eventChain: false,
  marketAdjacency: 0.4,
});

const adjacencyOnlyScore = scoreEdge({
  source: makeNode('gamma', { keyEntities: ['Databricks'] }),
  target: makeNode('delta', { keyEntities: ['Snowflake'] }),
  sharedEntities: [],
  eventChain: false,
  marketAdjacency: 0.7,
});

assert.ok(
  sharedEntityScore > adjacencyOnlyScore,
  'shared-entity evidence should outrank market-adjacency-only evidence',
);

const eventChainScore = scoreEdge({
  source: makeNode('epsilon', { keyEntities: ['Nvidia'] }),
  target: makeNode('zeta', { keyEntities: ['Nvidia'] }),
  sharedEntities: [],
  eventChain: true,
  marketAdjacency: 0.2,
});

const nonEventChainScore = scoreEdge({
  source: makeNode('epsilon', { keyEntities: ['Nvidia'] }),
  target: makeNode('zeta', { keyEntities: ['Nvidia'] }),
  sharedEntities: [],
  eventChain: false,
  marketAdjacency: 0.2,
});

assert.ok(
  eventChainScore > nonEventChainScore,
  'event-chain evidence should increase the overall edge score',
);

const normalizedEntityScore = scoreEdge({
  source: makeNode('entity-a', { keyEntities: ['OpenAI, Inc.'] }),
  target: makeNode('entity-b', { keyEntities: ['open ai'] }),
  sharedEntities: ['OpenAI', 'OpenAI, Inc.', 'open ai'],
  eventChain: false,
  marketAdjacency: 0,
});

const singleEntityScore = scoreEdge({
  source: makeNode('entity-a', { keyEntities: ['OpenAI'] }),
  target: makeNode('entity-b', { keyEntities: ['OpenAI'] }),
  sharedEntities: ['OpenAI'],
  eventChain: false,
  marketAdjacency: 0,
});

assert.equal(
  normalizedEntityScore,
  singleEntityScore,
  'entity normalization should collapse common naming variants into one shared entity',
);

const visibleEdges = pickVisibleEdges([
  makeEdge('edge-1', 'alpha', 'beta', { score: 0.91, type: 'shared-entity' }),
  makeEdge('edge-2', 'alpha', 'gamma', { score: 0.42 }),
  makeEdge('edge-3', 'beta', 'gamma', { score: 0.67, type: 'event-chain' }),
  makeEdge('edge-4', 'gamma', 'delta', { score: 0.29 }),
], {
  maxVisible: 2,
});

assert.deepEqual(
  visibleEdges.map((edge) => edge.id),
  ['edge-1', 'edge-3'],
  'pickVisibleEdges should keep only the strongest global edges by default',
);

const visibleEdgesWithCoverage = pickVisibleEdges(
  [
    makeEdge('edge-1', 'alpha', 'beta', { score: 0.99, type: 'shared-entity' }),
    makeEdge('edge-2', 'alpha', 'gamma', { score: 0.93, type: 'shared-entity' }),
    makeEdge('edge-3', 'alpha', 'delta', { score: 0.88, type: 'event-chain' }),
    makeEdge('edge-4', 'omega', 'sigma', { score: 0.52, type: 'shared-entity' }),
  ],
  {
    maxVisible: 2,
    importantNodeIds: ['omega'],
  },
);

assert.deepEqual(
  visibleEdgesWithCoverage.map((edge) => edge.id),
  ['edge-1', 'edge-4'],
  'pickVisibleEdges should preserve at least one edge for an important node before filling remaining global slots',
);

const layout = projectRelationshipGraphLayout(
  [
    makeNode('core-story', {
      importance: 0.94,
      dominantTopic: 'llms',
      positionSeed: { x: 0.42, y: 0.48 },
    }),
    makeNode('peripheral-story', {
      importance: 0.22,
      dominantTopic: 'llms',
      positionSeed: { x: 0.58, y: 0.52 },
    }),
  ],
  {
    width: 1200,
    height: 720,
    padding: 80,
  },
);

const graphCenter = { x: 600, y: 360 };
const distanceFromCenter = (point: { x: number; y: number }) =>
  Math.hypot(point.x - graphCenter.x, point.y - graphCenter.y);

assert.ok(
  distanceFromCenter(layout.get('core-story')!) < distanceFromCenter(layout.get('peripheral-story')!),
  'higher-importance nodes should bias closer to the graph center than low-importance nodes',
);

const zoomLevelOverview = resolveRelationshipGraphZoomLevel(0.72);
const zoomLevelDetail = resolveRelationshipGraphZoomLevel(2.1);

assert.equal(
  zoomLevelOverview,
  'overview',
  'lower viewport scales should resolve to the overview label tier',
);
assert.equal(
  zoomLevelDetail,
  'detail',
  'higher viewport scales should resolve to the detail label tier',
);

const v2Nodes = [
  makeNode('priority-anchor', {
    importance: 0.98,
    coverageCount: 16,
    dominantTopic: 'agents',
  }),
  makeNode('selected-node', {
    importance: 0.11,
    coverageCount: 2,
    dominantTopic: 'robotics',
  }),
  makeNode('suppressed-node', {
    importance: 0.08,
    coverageCount: 1,
    dominantTopic: 'robotics',
  }),
  makeNode('topic-node', {
    importance: 0.62,
    coverageCount: 7,
    dominantTopic: 'multimodal',
  }),
];

const visuals = buildRelationshipGraphVisuals(v2Nodes);

assert.equal(
  visuals.get('priority-anchor')?.topicColorToken,
  resolveNodeTopicColor('agents'),
  'node visuals should carry a stable topic color token',
);
assert.ok(
  (visuals.get('priority-anchor')?.renderPriority ?? 0) > (visuals.get('selected-node')?.renderPriority ?? 0),
  'node visuals should expose stable render priority values for density decisions',
);
assert.equal(
  resolveNodeTopicColor('multimodal'),
  '--relationship-graph-topic-multimodal',
  'topic color resolution should return deterministic tokens',
);

const overviewLabels = pickVisibleNodeLabels(v2Nodes, visuals, {
  zoomLevel: zoomLevelOverview,
  selectedNodeIds: ['selected-node'],
});
const clusterLabels = pickVisibleNodeLabels(v2Nodes, visuals, {
  zoomLevel: resolveRelationshipGraphZoomLevel(1.2),
  selectedNodeIds: ['selected-node'],
});
const detailLabels = pickVisibleNodeLabels(v2Nodes, visuals, {
  zoomLevel: zoomLevelDetail,
  selectedNodeIds: ['selected-node'],
});
const focusedLabels = pickVisibleNodeLabels(v2Nodes, visuals, {
  zoomLevel: zoomLevelOverview,
  focusedNodeIds: ['suppressed-node'],
});

assert.ok(
  overviewLabels.includes('priority-anchor'),
  'overview density should still expose the highest-priority node label',
);
assert.ok(
  overviewLabels.includes('selected-node'),
  'selected nodes should remain labeled even when base zoom suppresses low-priority labels',
);
assert.ok(
  !overviewLabels.includes('suppressed-node'),
  'low-priority labels should be suppressed at overview zoom',
);
assert.ok(
  detailLabels.includes('suppressed-node'),
  'detail zoom should reveal labels that are suppressed at overview zoom',
);
assert.ok(
  focusedLabels.includes('suppressed-node'),
  'focused neighborhoods should override base label suppression rules',
);
assert.ok(
  clusterLabels.length > overviewLabels.length,
  'mid-zoom tiers should show more labels than the overview tier',
);

const viewport = computeGraphViewport(
  new Map([
    ['priority-anchor', { x: 140, y: 180 }],
    ['selected-node', { x: 860, y: 520 }],
    ['suppressed-node', { x: 620, y: 760 }],
  ]),
  {
    width: 1280,
    height: 720,
    padding: 64,
  },
);

assert.deepEqual(
  viewport.bounds,
  {
    minX: 140,
    minY: 180,
    maxX: 860,
    maxY: 760,
    width: 720,
    height: 580,
  },
  'graph viewport helpers should expose deterministic graph bounds',
);
assert.deepEqual(
  viewport,
  {
    scale: 1.0206896551724138,
    translateX: 129.65517241379308,
    translateY: -119.72413793103448,
    bounds: {
      minX: 140,
      minY: 180,
      maxX: 860,
      maxY: 760,
      width: 720,
      height: 580,
    },
  },
  'graph viewport helpers should return a deterministic centered fit transform',
);

const transformedLeft = viewport.bounds.minX * viewport.scale + viewport.translateX;
const transformedRight = viewport.bounds.maxX * viewport.scale + viewport.translateX;
const transformedTop = viewport.bounds.minY * viewport.scale + viewport.translateY;
const transformedBottom = viewport.bounds.maxY * viewport.scale + viewport.translateY;

assert.ok(
  Math.abs(transformedLeft - 272.55172413793105) < 1e-9,
  'fit math should center the graph horizontally inside the padded viewport',
);
assert.ok(
  Math.abs(transformedRight - 1007.448275862069) < 1e-9,
  'fit math should preserve symmetric horizontal padding after centering',
);
assert.ok(
  Math.abs(transformedTop - 64) < 1e-9,
  'fit math should honor top padding for the tighter viewport dimension',
);
assert.ok(
  Math.abs(transformedBottom - 656) < 1e-9,
  'fit math should honor bottom padding for the tighter viewport dimension',
);

assert.equal(
  resolveRelationshipGraphEdgeTier(
    makeEdge('edge-default', 'alpha', 'beta', { hiddenByDefault: false }),
  ),
  'default',
  'visible unfocused edges should render in the default tier',
);
assert.equal(
  resolveRelationshipGraphEdgeTier(
    makeEdge('edge-hidden', 'alpha', 'beta', { hiddenByDefault: true }),
  ),
  'hidden',
  'hiddenByDefault edges should stay hidden when nothing is focused',
);
assert.equal(
  resolveRelationshipGraphEdgeTier(
    makeEdge('edge-focused', 'alpha', 'beta', { hiddenByDefault: true }),
    {
      focusedEdgeIds: ['edge-focused'],
    },
  ),
  'focused',
  'focused edges should override the default hidden tier',
);

const spreadLayout = projectRelationshipGraphLayout(
  [
    makeNode('agents-core', {
      dominantTopic: 'agents',
      importance: 0.92,
      positionSeed: { x: 0.24, y: 0.41 },
    }),
    makeNode('agents-secondary', {
      dominantTopic: 'agents',
      importance: 0.38,
      positionSeed: { x: 0.27, y: 0.44 },
    }),
    makeNode('robotics-core', {
      dominantTopic: 'robotics',
      importance: 0.88,
      positionSeed: { x: 0.76, y: 0.48 },
    }),
    makeNode('robotics-secondary', {
      dominantTopic: 'robotics',
      importance: 0.28,
      positionSeed: { x: 0.78, y: 0.52 },
    }),
  ],
  {
    width: 1200,
    height: 720,
    padding: 80,
  },
);

const centroid = (ids: string[]) => ({
  x: ids.reduce((sum, id) => sum + spreadLayout.get(id)!.x, 0) / ids.length,
  y: ids.reduce((sum, id) => sum + spreadLayout.get(id)!.y, 0) / ids.length,
});

const agentsCentroid = centroid(['agents-core', 'agents-secondary']);
const roboticsCentroid = centroid(['robotics-core', 'robotics-secondary']);

assert.ok(
  Math.hypot(agentsCentroid.x - roboticsCentroid.x, agentsCentroid.y - roboticsCentroid.y) > 360,
  'topic neighborhoods should stay meaningfully separated in the V2 layout',
);
assert.ok(
  Math.hypot(
    spreadLayout.get('agents-core')!.x - spreadLayout.get('agents-secondary')!.x,
    spreadLayout.get('agents-core')!.y - spreadLayout.get('agents-secondary')!.y,
  ) > 70,
  'lower-priority nodes should not collapse into the same local topic position',
);

const overrides = mergeRelationshipGraphPositionOverrides(
  {
    alpha: { x: 120, y: 210 },
  },
  'beta',
  { x: 640, y: 512 },
);

assert.deepEqual(
  overrides,
  {
    alpha: { x: 120, y: 210 },
    beta: { x: 640, y: 512 },
  },
  'drag state should preserve prior node overrides while updating the active node',
);

const overrideLayout = applyRelationshipGraphPositionOverrides(
  new Map([
    ['alpha', { x: 100, y: 100 }],
    ['beta', { x: 220, y: 240 }],
  ]),
  overrides,
);

assert.deepEqual(
  overrideLayout.get('alpha'),
  { x: 120, y: 210 },
  'position overrides should reproject existing nodes without losing identity',
);
assert.deepEqual(
  overrideLayout.get('beta'),
  { x: 640, y: 512 },
  'position overrides should update dragged nodes predictably',
);

const neighborhood = buildLocalNeighborhood(
  'alpha',
  [
    makeEdge('edge-1', 'alpha', 'beta', { score: 0.91 }),
    makeEdge('edge-2', 'alpha', 'gamma', { score: 0.72 }),
    makeEdge('edge-3', 'beta', 'gamma', { score: 0.67 }),
  ],
  {
    maxEdges: 2,
  },
);

assert.deepEqual(
  neighborhood.edges.map((edge) => edge.id),
  ['edge-1', 'edge-2'],
  'local neighborhoods should surface the strongest first-degree edges for a node',
);

assert.deepEqual(
  Array.from(neighborhood.nodeIds).sort(),
  ['alpha', 'beta', 'gamma'],
  'local neighborhoods should include the selected node and connected node ids',
);

const candidate: RelationshipGraphEdgeCandidate = {
  source: makeNode('alpha', { keyEntities: ['OpenAI', 'Anthropic'] }),
  target: makeNode('beta', { keyEntities: ['Anthropic'] }),
  sharedEntities: ['Anthropic'],
  eventChain: true,
  marketAdjacency: 0.35,
};

const graph7d = buildRelationshipGraphResponse({
  nodes: [candidate.source, candidate.target],
  edgeCandidates: [candidate],
  window: '7d',
  generatedAt: '2026-03-12T12:00:00Z',
});

const graph30d = buildRelationshipGraphResponse({
  nodes: [candidate.source, candidate.target],
  edgeCandidates: [candidate],
  window: '30d',
  generatedAt: '2026-03-12T12:00:00Z',
});

const canonicalGraph = buildRelationshipGraphResponse({
  nodes: [candidate.source, candidate.target],
  edgeCandidates: [
    candidate,
    {
      ...candidate,
      source: candidate.target,
      target: candidate.source,
    },
  ],
  window: '7d',
  generatedAt: '2026-03-12T12:00:00Z',
});

assert.equal(graph7d.window, '7d', 'relationship graph response should preserve 7d metadata');
assert.equal(graph30d.window, '30d', 'relationship graph response should preserve 30d metadata');
assert.equal(graph7d.edges[0]?.type, 'shared-entity');
assert.equal(
  canonicalGraph.edges.length,
  1,
  'reversed relationship candidates should collapse into one canonical relationship edge',
);
assert.deepEqual(
  canonicalGraph.edges[0] && {
    id: canonicalGraph.edges[0].id,
    source: canonicalGraph.edges[0].source,
    target: canonicalGraph.edges[0].target,
  },
  {
    id: 'alpha::beta',
    source: 'alpha',
    target: 'beta',
  },
  'canonicalized edges should keep stable ids and endpoints regardless of input order',
);

// Edge-aware layout: linked nodes should cluster closer than unlinked nodes
const edgeLayout = projectRelationshipGraphLayout(
  [
    makeNode('linked-a', { dominantTopic: 'llms', importance: 0.6, positionSeed: { x: 0.2, y: 0.3 } }),
    makeNode('linked-b', { dominantTopic: 'robotics', importance: 0.6, positionSeed: { x: 0.8, y: 0.7 } }),
    makeNode('isolated-c', { dominantTopic: 'agents', importance: 0.6, positionSeed: { x: 0.5, y: 0.5 } }),
  ],
  {
    width: 1200,
    height: 720,
    padding: 80,
    edges: [
      makeEdge('link-ab', 'linked-a', 'linked-b', { score: 0.95, type: 'shared-entity' }),
    ],
  },
);

const linkedDist = Math.hypot(
  edgeLayout.get('linked-a')!.x - edgeLayout.get('linked-b')!.x,
  edgeLayout.get('linked-a')!.y - edgeLayout.get('linked-b')!.y,
);
const isolatedDistA = Math.hypot(
  edgeLayout.get('isolated-c')!.x - edgeLayout.get('linked-a')!.x,
  edgeLayout.get('isolated-c')!.y - edgeLayout.get('linked-a')!.y,
);
const isolatedDistB = Math.hypot(
  edgeLayout.get('isolated-c')!.x - edgeLayout.get('linked-b')!.x,
  edgeLayout.get('isolated-c')!.y - edgeLayout.get('linked-b')!.y,
);

assert.ok(
  linkedDist < Math.max(isolatedDistA, isolatedDistB),
  `edge-linked nodes should be positioned closer together than unlinked nodes (linked=${linkedDist.toFixed(1)}, isolatedA=${isolatedDistA.toFixed(1)}, isolatedB=${isolatedDistB.toFixed(1)})`,
);

console.log('relationship graph verification passed');
