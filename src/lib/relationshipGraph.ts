import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from 'd3';
import type { SimulationLinkDatum, SimulationNodeDatum } from 'd3';
import type {
  RelationshipEdgeType,
  RelationshipGraphBounds,
  RelationshipGraphEdge,
  RelationshipGraphEdgeCandidate,
  RelationshipGraphNode,
  RelationshipGraphNodeVisual,
  RelationshipGraphResponse,
  RelationshipGraphViewport,
  RelationshipGraphWindow,
  RelationshipGraphZoomLevel,
  GraphCluster,
  GraphEdge,
} from '@/types';

export const RELATIONSHIP_GRAPH_WINDOWS = ['7d', '30d'] as const satisfies readonly RelationshipGraphWindow[];
export const RELATIONSHIP_GRAPH_WINDOW_HOURS: Record<RelationshipGraphWindow, number> = {
  '7d': 168,
  '30d': 720,
};

const EDGE_TYPE_PRIORITY: Record<RelationshipEdgeType, number> = {
  'follow-up': 5,
  'reaction': 4,
  'competing': 3,
  'shared-entity': 3,
  'event-chain': 2,
  'market-adjacency': 1,
  'embedding-similarity': 0,
};

const TOPIC_ORDER = [
  'llms',
  'multimodal',
  'agents',
  'robotics',
  'vision',
  'audio_speech',
  'hardware_chips',
  'open_source',
  'startups_funding',
  'enterprise_apps',
  'safety_policy',
  'research_methods',
  'mixed',
] as const;

const EVENT_FAMILY_ALIASES: Record<string, string> = {
  announcement: 'release',
  benchmark: 'benchmark',
  benchmark_result: 'benchmark',
  big_tech_announcement: 'release',
  chip_hardware: 'release',
  collaboration: 'partnership',
  funding: 'funding',
  government_action: 'policy',
  grant: 'funding',
  launch: 'release',
  m_and_a: 'ma',
  merger: 'ma',
  model_release: 'release',
  open_source_release: 'release',
  partnership: 'partnership',
  policy: 'policy',
  policy_regulation: 'policy',
  product_launch: 'release',
  recall: 'security',
  regulation: 'policy',
  release: 'release',
  research: 'research',
  research_paper: 'research',
  security: 'security',
  security_incident: 'security',
  startup_funding: 'funding',
  update: 'release',
};

const EVENT_CHAIN_COMPATIBILITY = new Set([
  'release:benchmark',
  'release:policy',
  'release:partnership',
  'research:release',
  'research:benchmark',
  'funding:release',
  'funding:partnership',
  'security:policy',
  'security:release',
  'policy:release',
  'policy:security',
  'partnership:release',
]);

interface PickVisibleEdgesOptions {
  maxVisible?: number;
  importantNodeIds?: string[];
}

interface BuildLocalNeighborhoodOptions {
  maxEdges?: number;
}

interface BuildRelationshipGraphResponseOptions {
  nodes: RelationshipGraphNode[];
  edgeCandidates: RelationshipGraphEdgeCandidate[];
  window: RelationshipGraphWindow;
  generatedAt: string;
  maxVisibleEdges?: number;
}

interface ForceNode extends SimulationNodeDatum {
  id: string;
  dominantTopic: string;
  importance: number;
  radius: number;
  topicAnchorX: number;
  topicAnchorY: number;
}

interface ForceLink extends SimulationLinkDatum<ForceNode> {
  score: number;
}

interface RelationshipGraphLayoutOptions {
  width: number;
  height: number;
  padding?: number;
  edges?: RelationshipGraphEdge[];
}

interface PickVisibleNodeLabelsOptions {
  zoomLevel: RelationshipGraphZoomLevel;
  selectedNodeIds?: string[];
  focusedNodeIds?: string[];
}

interface ComputeGraphViewportOptions {
  width: number;
  height: number;
  padding?: number;
}

interface ResolveRelationshipGraphEdgeTierOptions {
  focusedEdgeIds?: string[];
  focusedNodeIds?: string[];
}

interface BuildRelationshipGraphOptions {
  clusters: GraphCluster[];
  window: RelationshipGraphWindow;
  generatedAt: string;
  maxVisibleEdges?: number;
  serverEdges?: GraphEdge[];
}

export interface RelationshipGraphPosition {
  x: number;
  y: number;
}

interface GraphSnapshotStatus {
  generatedAt: string;
}

const clamp01 = (value: number): number => Math.max(0, Math.min(1, value));

const CORPORATE_SUFFIX_PATTERN =
  /\b(incorporated|inc|corp|corporation|company|co|llc|ltd|limited|plc|gmbh|ag)\b/g;

const compareEdges = (left: RelationshipGraphEdge, right: RelationshipGraphEdge): number => {
  if (right.score !== left.score) {
    return right.score - left.score;
  }

  const priorityDelta = EDGE_TYPE_PRIORITY[right.type] - EDGE_TYPE_PRIORITY[left.type];
  if (priorityDelta !== 0) {
    return priorityDelta;
  }

  return left.id.localeCompare(right.id);
};

const hashString = (value: string): number => {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
};

const normalizeEntity = (entity: string): string =>
  entity
    .trim()
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^\w\s]/g, ' ')
    .replace(CORPORATE_SUFFIX_PATTERN, ' ')
    .replace(/\s+/g, '');

const canonicalizeEndpoints = (leftId: string, rightId: string): {
  source: string;
  target: string;
} => (
  leftId.localeCompare(rightId) <= 0
    ? { source: leftId, target: rightId }
    : { source: rightId, target: leftId }
);

const toEdgeType = (candidate: RelationshipGraphEdgeCandidate): RelationshipEdgeType => {
  if (candidate.sharedEntities.length > 0) {
    return 'shared-entity';
  }
  if (candidate.eventChain) {
    return 'event-chain';
  }
  return 'market-adjacency';
};

const describeEvidence = (candidate: RelationshipGraphEdgeCandidate): string[] => {
  const evidence: string[] = [];

  if (candidate.sharedEntities.length > 0) {
    evidence.push(`Shared entities: ${candidate.sharedEntities.join(', ')}`);
  }
  if (candidate.eventChain) {
    evidence.push('Event chain evidence');
  }
  if (candidate.marketAdjacency > 0) {
    evidence.push(`Market adjacency ${(clamp01(candidate.marketAdjacency) * 100).toFixed(0)}%`);
  }

  return evidence;
};

const normalizeImportance = (value: number, max: number): number => {
  if (max <= 0) {
    return 0;
  }
  return clamp01(value / max);
};

const topicSortIndex = (topic: string): number => {
  const index = TOPIC_ORDER.indexOf(topic as typeof TOPIC_ORDER[number]);
  return index === -1 ? TOPIC_ORDER.length : index;
};

const normalizeTopicToken = (topic: string): string => (
  topic
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    || 'mixed'
);

const topicSimilarity = (
  leftTopicWeights: Record<string, number>,
  rightTopicWeights: Record<string, number>,
  leftTopic: string,
  rightTopic: string,
): number => {
  const topicKeys = new Set([
    ...Object.keys(leftTopicWeights),
    ...Object.keys(rightTopicWeights),
  ]);

  let dotProduct = 0;
  let leftMagnitude = 0;
  let rightMagnitude = 0;

  for (const topic of topicKeys) {
    const left = leftTopicWeights[topic] ?? 0;
    const right = rightTopicWeights[topic] ?? 0;
    dotProduct += left * right;
    leftMagnitude += left * left;
    rightMagnitude += right * right;
  }

  const cosine = leftMagnitude > 0 && rightMagnitude > 0
    ? dotProduct / Math.sqrt(leftMagnitude * rightMagnitude)
    : 0;

  const dominantTopicBonus = leftTopic === rightTopic ? 0.12 : 0;
  return clamp01(cosine + dominantTopicBonus);
};

const eventFamily = (eventType: string): string => {
  const normalized = eventType.trim().toLowerCase();
  return (EVENT_FAMILY_ALIASES[normalized] ?? normalized) || 'other';
};

const eventChainScore = (left: GraphCluster, right: GraphCluster): number => {
  const leftFamily = eventFamily(left.dominantEventType);
  const rightFamily = eventFamily(right.dominantEventType);
  const compatible = EVENT_CHAIN_COMPATIBILITY.has(`${leftFamily}:${rightFamily}`)
    || EVENT_CHAIN_COMPATIBILITY.has(`${rightFamily}:${leftFamily}`);
  if (!compatible) {
    return 0;
  }

  const timeDeltaHours = Math.abs(left.ageHours - right.ageHours);
  return clamp01(1 - timeDeltaHours / 96);
};

const entityIntersection = (
  leftEntities: GraphCluster['entities'],
  rightEntities: GraphCluster['entities'],
): string[] => {
  const rightMap = new Map<string, string>();
  for (const entity of rightEntities) {
    const normalized = normalizeEntity(entity.name);
    if (!normalized) {
      continue;
    }
    rightMap.set(normalized, entity.name);
  }

  const shared = new Map<string, string>();
  for (const entity of leftEntities) {
    const normalized = normalizeEntity(entity.name);
    if (!normalized || !rightMap.has(normalized)) {
      continue;
    }
    shared.set(normalized, entity.name);
  }

  return [...shared.values()].sort((left, right) => left.localeCompare(right));
};

const buildNodeImportance = (cluster: GraphCluster): number =>
  (cluster.coverageCount * 1.8)
  + (cluster.maxGlobalScore * 0.72)
  + (cluster.sourcesCount * 1.2)
  + (cluster.velocity * 2.8)
  + (cluster.pulsing ? 16 : 0);

const toGraphNode = (
  cluster: GraphCluster,
  maxImportance: number,
): RelationshipGraphNode => ({
  id: cluster.id,
  clusterId: cluster.id,
  headline: cluster.headline,
  dominantTopic: cluster.dominantTopic,
  dominantEventType: cluster.dominantEventType,
  importance: normalizeImportance(buildNodeImportance(cluster), maxImportance),
  coverageCount: cluster.coverageCount,
  sourcesCount: cluster.sourcesCount,
  velocity: cluster.velocity,
  ageHours: cluster.ageHours,
  trustLabel: cluster.trustLabel,
  maxGlobalScore: cluster.maxGlobalScore,
  keyEntities: cluster.entities.slice(0, 5).map((entity) => entity.name),
  positionSeed: {
    x: clamp01(cluster.x),
    y: clamp01(cluster.y),
  },
});

export function scoreEdge(candidate: RelationshipGraphEdgeCandidate): number {
  const normalizedSharedEntities = new Set(
    candidate.sharedEntities
      .map(normalizeEntity)
      .filter((entity) => entity.length > 0),
  ).size;
  const sharedEntityScore = normalizedSharedEntities > 0
    ? 0.58 + Math.min(normalizedSharedEntities - 1, 2) * 0.12
    : 0;
  const eventChainContribution = candidate.eventChain ? 0.24 : 0;
  const adjacencyScore = clamp01(candidate.marketAdjacency) * 0.18;

  return clamp01(sharedEntityScore + eventChainContribution + adjacencyScore);
}

export function pickVisibleEdges(
  edges: RelationshipGraphEdge[],
  options: PickVisibleEdgesOptions = {},
): RelationshipGraphEdge[] {
  const maxVisible = options.maxVisible ?? Math.min(8, edges.length);
  const sortedEdges = [...edges].sort(compareEdges);
  const selectedIds = new Set<string>();
  const visibleEdges: RelationshipGraphEdge[] = [];

  for (const nodeId of options.importantNodeIds ?? []) {
    const candidate = sortedEdges.find((edge) => (
      !selectedIds.has(edge.id) && (edge.source === nodeId || edge.target === nodeId)
    ));

    if (!candidate) {
      continue;
    }

    visibleEdges.push(candidate);
    selectedIds.add(candidate.id);

    if (visibleEdges.length >= maxVisible) {
      return [...visibleEdges].sort(compareEdges);
    }
  }

  for (const edge of sortedEdges) {
    if (selectedIds.has(edge.id)) {
      continue;
    }

    visibleEdges.push(edge);
    selectedIds.add(edge.id);

    if (visibleEdges.length >= maxVisible) {
      break;
    }
  }

  return visibleEdges.sort(compareEdges);
}

export function buildLocalNeighborhood(
  nodeId: string,
  edges: RelationshipGraphEdge[],
  options: BuildLocalNeighborhoodOptions = {},
): {
  edges: RelationshipGraphEdge[];
  nodeIds: Set<string>;
} {
  const maxEdges = options.maxEdges ?? 4;
  const localEdges = [...edges]
    .filter((edge) => edge.source === nodeId || edge.target === nodeId)
    .sort(compareEdges)
    .slice(0, maxEdges);

  const nodeIds = new Set<string>([nodeId]);
  for (const edge of localEdges) {
    nodeIds.add(edge.source);
    nodeIds.add(edge.target);
  }

  return {
    edges: localEdges,
    nodeIds,
  };
}

export function buildRelationshipGraphResponse(
  options: BuildRelationshipGraphResponseOptions,
): RelationshipGraphResponse {
  const candidateByEdgeId = new Map<string, RelationshipGraphEdgeCandidate>();

  for (const candidate of options.edgeCandidates) {
    const endpoints = canonicalizeEndpoints(candidate.source.id, candidate.target.id);
    const edgeId = `${endpoints.source}::${endpoints.target}`;
    const existing = candidateByEdgeId.get(edgeId);

    if (!existing) {
      candidateByEdgeId.set(edgeId, {
        ...candidate,
        source: endpoints.source === candidate.source.id ? candidate.source : candidate.target,
        target: endpoints.target === candidate.target.id ? candidate.target : candidate.source,
      });
      continue;
    }

    const sharedEntities = Array.from(new Set([
      ...existing.sharedEntities,
      ...candidate.sharedEntities,
    ])).sort((left, right) => left.localeCompare(right));

    candidateByEdgeId.set(edgeId, {
      ...existing,
      sharedEntities,
      eventChain: existing.eventChain || candidate.eventChain,
      marketAdjacency: Math.max(existing.marketAdjacency, candidate.marketAdjacency),
    });
  }

  const edges = [...candidateByEdgeId.values()].map((candidate) => ({
    id: `${candidate.source.id}::${candidate.target.id}`,
    source: candidate.source.id,
    target: candidate.target.id,
    type: toEdgeType(candidate),
    score: scoreEdge(candidate),
    evidence: describeEvidence(candidate),
    hiddenByDefault: true,
  }));

  const visibleIds = new Set(
    pickVisibleEdges(edges, {
      maxVisible: options.maxVisibleEdges,
      importantNodeIds: options.nodes
        .filter((node) => node.importance >= 0.72)
        .sort((left, right) => {
          if (right.importance !== left.importance) {
            return right.importance - left.importance;
          }
          if (right.coverageCount !== left.coverageCount) {
            return right.coverageCount - left.coverageCount;
          }
          return left.id.localeCompare(right.id);
        })
        .slice(0, 2)
        .map((node) => node.id),
    }).map((edge) => edge.id),
  );

  return {
    nodes: options.nodes,
    edges: edges
      .map((edge) => ({
        ...edge,
        hiddenByDefault: !visibleIds.has(edge.id),
      }))
      .sort(compareEdges),
    window: options.window,
    generatedAt: options.generatedAt,
  };
}

export function buildRelationshipGraph(
  options: BuildRelationshipGraphOptions,
): RelationshipGraphResponse {
  if (options.clusters.length === 0) {
    return {
      nodes: [],
      edges: [],
      window: options.window,
      generatedAt: options.generatedAt,
    };
  }

  const maxImportance = options.clusters.reduce(
    (currentMax, cluster) => Math.max(currentMax, buildNodeImportance(cluster)),
    0,
  );
  const nodes = options.clusters.map((cluster) => toGraphNode(cluster, maxImportance));

  if (options.serverEdges && options.serverEdges.length > 0) {
    const edges: RelationshipGraphEdge[] = options.serverEdges.map((se) => ({
      id: se.id,
      source: se.source,
      target: se.target,
      type: se.type,
      score: se.score,
      evidence: se.evidence,
      hiddenByDefault: true,
    }));

    const visibleIds = new Set(
      pickVisibleEdges(edges, {
        maxVisible: options.maxVisibleEdges ?? Math.min(Math.max(8, Math.round(nodes.length * 0.3)), 14),
        importantNodeIds: nodes
          .filter((node) => node.importance >= 0.72)
          .sort((left, right) => {
            if (right.importance !== left.importance) return right.importance - left.importance;
            if (right.coverageCount !== left.coverageCount) return right.coverageCount - left.coverageCount;
            return left.id.localeCompare(right.id);
          })
          .slice(0, 2)
          .map((node) => node.id),
      }).map((edge) => edge.id),
    );

    return {
      nodes,
      edges: edges.map((edge) => ({
        ...edge,
        hiddenByDefault: !visibleIds.has(edge.id),
      })).sort(compareEdges),
      window: options.window,
      generatedAt: options.generatedAt,
    };
  }

  const clusterById = new Map(options.clusters.map((cluster) => [cluster.id, cluster]));
  const edgeCandidates: RelationshipGraphEdgeCandidate[] = [];

  for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
      const leftNode = nodes[leftIndex];
      const rightNode = nodes[rightIndex];
      const leftCluster = clusterById.get(leftNode.id);
      const rightCluster = clusterById.get(rightNode.id);

      if (!leftCluster || !rightCluster) {
        continue;
      }

      const sharedEntities = entityIntersection(leftCluster.entities, rightCluster.entities);
      const adjacency = topicSimilarity(
        leftCluster.topicWeights,
        rightCluster.topicWeights,
        leftCluster.dominantTopic,
        rightCluster.dominantTopic,
      );
      const chainScore = eventChainScore(leftCluster, rightCluster);

      if (sharedEntities.length === 0 && adjacency < 0.46 && chainScore < 0.42) {
        continue;
      }

      edgeCandidates.push({
        source: leftNode,
        target: rightNode,
        sharedEntities,
        eventChain: chainScore >= 0.42,
        marketAdjacency: adjacency,
      });
    }
  }

  return buildRelationshipGraphResponse({
    nodes,
    edgeCandidates,
    window: options.window,
    generatedAt: options.generatedAt,
    maxVisibleEdges: options.maxVisibleEdges ?? Math.min(Math.max(8, Math.round(nodes.length * 0.3)), 14),
  });
}

export function projectRelationshipGraphLayout(
  nodes: RelationshipGraphNode[],
  options: RelationshipGraphLayoutOptions,
): Map<string, RelationshipGraphPosition> {
  const padding = options.padding ?? 72;
  const width = Math.max(options.width, padding * 2 + 1);
  const height = Math.max(options.height, padding * 2 + 1);
  const centerX = width / 2;
  const centerY = height / 2;
  const radiusX = Math.max((width - padding * 2) / 2, 120);
  const radiusY = Math.max((height - padding * 2) / 2, 90);

  const uniqueTopics = Array.from(
    new Set(nodes.map((node) => node.dominantTopic)),
  ).sort((left, right) => {
    const indexDelta = topicSortIndex(left) - topicSortIndex(right);
    return indexDelta !== 0 ? indexDelta : left.localeCompare(right);
  });
  const topicAnchorByTopic = new Map<string, { x: number; y: number }>();

  uniqueTopics.forEach((topic, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(uniqueTopics.length, 1) - Math.PI / 2;
    topicAnchorByTopic.set(topic, {
      x: centerX + Math.cos(angle) * radiusX * 0.96,
      y: centerY + Math.sin(angle) * radiusY * 0.94,
    });
  });

  const nodesByTopic = new Map<string, RelationshipGraphNode[]>();
  for (const node of nodes) {
    const topicNodes = nodesByTopic.get(node.dominantTopic) ?? [];
    topicNodes.push(node);
    nodesByTopic.set(node.dominantTopic, topicNodes);
  }

  for (const topicNodes of nodesByTopic.values()) {
    topicNodes.sort((left, right) => {
      if (right.importance !== left.importance) {
        return right.importance - left.importance;
      }
      if (right.coverageCount !== left.coverageCount) {
        return right.coverageCount - left.coverageCount;
      }
      return left.id.localeCompare(right.id);
    });
  }

  const positions = new Map<string, RelationshipGraphPosition>();

  for (const node of nodes) {
    const anchor = topicAnchorByTopic.get(node.dominantTopic) ?? { x: centerX, y: centerY };
    const topicNodes = nodesByTopic.get(node.dominantTopic) ?? [node];
    const topicIndex = topicNodes.findIndex((candidate) => candidate.id === node.id);
    const baseAngle = Math.atan2(anchor.y - centerY, anchor.x - centerX);
    const importance = clamp01(node.importance);
    const centerPull = 0.06 + importance * 0.22;
    const continuityBlend = 0.12;
    const seedX = padding + node.positionSeed.x * (width - padding * 2);
    const seedY = padding + node.positionSeed.y * (height - padding * 2);
    const jitter = hashString(node.id);
    const jitterX = ((jitter % 17) - 8) * 4.5;
    const jitterY = (((Math.floor(jitter / 17)) % 17) - 8) * 4;
    const sectorSpread = Math.min((Math.PI / Math.max(uniqueTopics.length, 2)) * 1.1, 1.4);
    const angleOffset = topicNodes.length <= 1
      ? 0
      : ((topicIndex / Math.max(topicNodes.length - 1, 1)) - 0.5) * sectorSpread;
    const orbitalAngle = baseAngle + angleOffset;
    const localOrbitRadius = 72 + topicIndex * 38 + (1 - importance) * 110;

    const x = anchor.x * (1 - centerPull)
      + centerX * centerPull
      + Math.cos(orbitalAngle) * localOrbitRadius
      + (seedX - centerX) * continuityBlend
      + jitterX;
    const y = anchor.y * (1 - centerPull)
      + centerY * centerPull
      + Math.sin(orbitalAngle) * localOrbitRadius * 0.86
      + (seedY - centerY) * continuityBlend
      + jitterY;

    positions.set(node.id, {
      x: Math.max(padding, Math.min(width - padding, x)),
      y: Math.max(padding, Math.min(height - padding, y)),
    });
  }

  // Edge-aware refinement: nudge edge-connected nodes closer within their sectors.
  // Uses a short force simulation anchored strongly to the sector positions so the
  // overall topic layout is preserved, while linked nodes drift toward each other.
  const edges = options.edges ?? [];
  if (edges.length > 0 && nodes.length > 1) {
    const nodeIdSet = new Set(nodes.map((n) => n.id));
    const relevantEdges = edges.filter(
      (e) => nodeIdSet.has(e.source) && nodeIdSet.has(e.target),
    );

    if (relevantEdges.length > 0) {
      const forceNodes: ForceNode[] = nodes.map((node) => {
        const pos = positions.get(node.id)!;
        return {
          id: node.id,
          dominantTopic: node.dominantTopic,
          importance: clamp01(node.importance),
          radius: 10 + clamp01(node.importance) * 20,
          topicAnchorX: pos.x,
          topicAnchorY: pos.y,
          x: pos.x,
          y: pos.y,
          vx: 0,
          vy: 0,
        };
      });

      const forceLinks: ForceLink[] = relevantEdges.map((edge) => ({
        source: edge.source,
        target: edge.target,
        score: edge.score,
      }));

      const simulation = forceSimulation<ForceNode>(forceNodes)
        .force('link', forceLink<ForceNode, ForceLink>(forceLinks)
          .id((d) => d.id)
          .distance((d) => 140 - (d as ForceLink).score * 80)
          .strength((d) => 0.15 + (d as ForceLink).score * 0.25),
        )
        .force('anchor-x', forceX<ForceNode>()
          .x((d) => d.topicAnchorX)
          .strength(0.6),
        )
        .force('anchor-y', forceY<ForceNode>()
          .y((d) => d.topicAnchorY)
          .strength(0.6),
        )
        .force('collide', forceCollide<ForceNode>()
          .radius((d) => d.radius + 14)
          .strength(0.8)
          .iterations(2),
        )
        .stop();

      simulation.tick(80);

      for (const forceNode of forceNodes) {
        positions.set(forceNode.id, {
          x: Math.max(padding, Math.min(width - padding, forceNode.x!)),
          y: Math.max(padding, Math.min(height - padding, forceNode.y!)),
        });
      }
    }
  }

  // Overlap resolution for any remaining tight pairs
  const minGap = 52;
  const minGapSq = minGap * minGap;
  const nodeIds = [...positions.keys()];

  for (let pass = 0; pass < 6; pass += 1) {
    for (let i = 0; i < nodeIds.length; i += 1) {
      const posA = positions.get(nodeIds[i])!;
      for (let j = i + 1; j < nodeIds.length; j += 1) {
        const posB = positions.get(nodeIds[j])!;
        const dx = posB.x - posA.x;
        const dy = posB.y - posA.y;
        const distSq = dx * dx + dy * dy;

        if (distSq >= minGapSq || distSq < 0.01) {
          continue;
        }

        const dist = Math.sqrt(distSq);
        const overlap = (minGap - dist) / 2;
        const nx = dx / dist;
        const ny = dy / dist;

        posA.x = Math.max(padding, Math.min(width - padding, posA.x - nx * overlap));
        posA.y = Math.max(padding, Math.min(height - padding, posA.y - ny * overlap));
        posB.x = Math.max(padding, Math.min(width - padding, posB.x + nx * overlap));
        posB.y = Math.max(padding, Math.min(height - padding, posB.y + ny * overlap));
      }
    }
  }

  return positions;
}

export function mergeRelationshipGraphPositionOverrides(
  current: Record<string, RelationshipGraphPosition>,
  nodeId: string,
  position: RelationshipGraphPosition,
): Record<string, RelationshipGraphPosition> {
  return {
    ...current,
    [nodeId]: {
      x: Number(position.x.toFixed(3)),
      y: Number(position.y.toFixed(3)),
    },
  };
}

export function applyRelationshipGraphPositionOverrides(
  positions: Map<string, RelationshipGraphPosition>,
  overrides: Record<string, RelationshipGraphPosition>,
): Map<string, RelationshipGraphPosition> {
  const next = new Map(positions);

  for (const [nodeId, position] of Object.entries(overrides)) {
    next.set(nodeId, position);
  }

  return next;
}

export function resolveRelationshipGraphZoomLevel(scale: number): RelationshipGraphZoomLevel {
  if (scale >= 1.4) {
    return 'detail';
  }
  if (scale >= 0.75) {
    return 'cluster';
  }
  return 'overview';
}

export function resolveNodeTopicColor(topic: string): string {
  return `--relationship-graph-topic-${normalizeTopicToken(topic)}`;
}

export function buildRelationshipGraphVisuals(
  nodes: RelationshipGraphNode[],
): Map<string, RelationshipGraphNodeVisual> {
  const visuals = new Map<string, RelationshipGraphNodeVisual>();

  for (const node of nodes) {
    const renderPriority = Number((
      node.importance * 1000
      + node.coverageCount * 8
      + node.sourcesCount * 4
      + node.velocity * 6
      + node.maxGlobalScore * 0.5
    ).toFixed(3));

    visuals.set(node.id, {
      nodeId: node.id,
      renderPriority,
      labelPriority: Number((renderPriority + node.coverageCount * 2).toFixed(3)),
      topicColorToken: resolveNodeTopicColor(node.dominantTopic),
    });
  }

  return visuals;
}

export function pickVisibleNodeLabels(
  nodes: RelationshipGraphNode[],
  visuals: Map<string, RelationshipGraphNodeVisual>,
  options: PickVisibleNodeLabelsOptions,
): string[] {
  const sortedNodes = [...nodes].sort((left, right) => {
    const leftVisual = visuals.get(left.id);
    const rightVisual = visuals.get(right.id);
    const priorityDelta = (rightVisual?.labelPriority ?? 0) - (leftVisual?.labelPriority ?? 0);

    if (priorityDelta !== 0) {
      return priorityDelta;
    }

    return left.id.localeCompare(right.id);
  });

  const zoomQuota = (() => {
    switch (options.zoomLevel) {
      case 'detail':
        return sortedNodes.length;
      case 'cluster':
        return Math.max(4, Math.ceil(sortedNodes.length * 0.5));
      case 'overview':
      default:
        return Math.max(2, Math.ceil(sortedNodes.length * 0.25));
    }
  })();

  const pinnedIds = new Set<string>([
    ...(options.selectedNodeIds ?? []),
    ...(options.focusedNodeIds ?? []),
    ...sortedNodes
      .filter((node) => node.importance >= 0.82)
      .map((node) => node.id),
  ]);

  for (const node of sortedNodes) {
    if (pinnedIds.size >= zoomQuota) {
      break;
    }
    pinnedIds.add(node.id);
  }

  return [...pinnedIds].sort((leftId, rightId) => {
    const leftVisual = visuals.get(leftId);
    const rightVisual = visuals.get(rightId);
    const priorityDelta = (rightVisual?.labelPriority ?? 0) - (leftVisual?.labelPriority ?? 0);

    if (priorityDelta !== 0) {
      return priorityDelta;
    }

    return leftId.localeCompare(rightId);
  });
}

export function computeGraphViewport(
  positions: Map<string, RelationshipGraphPosition>,
  options: ComputeGraphViewportOptions,
): RelationshipGraphViewport {
  if (positions.size === 0) {
    const emptyBounds: RelationshipGraphBounds = {
      minX: 0,
      minY: 0,
      maxX: 0,
      maxY: 0,
      width: 0,
      height: 0,
    };

    return {
      scale: 1,
      translateX: 0,
      translateY: 0,
      bounds: emptyBounds,
    };
  }

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const position of positions.values()) {
    minX = Math.min(minX, position.x);
    minY = Math.min(minY, position.y);
    maxX = Math.max(maxX, position.x);
    maxY = Math.max(maxY, position.y);
  }

  const bounds: RelationshipGraphBounds = {
    minX,
    minY,
    maxX,
    maxY,
    width: Math.max(maxX - minX, 1),
    height: Math.max(maxY - minY, 1),
  };

  const padding = options.padding ?? 64;
  const innerWidth = Math.max(options.width - padding * 2, 1);
  const innerHeight = Math.max(options.height - padding * 2, 1);
  const scale = Math.min(innerWidth / bounds.width, innerHeight / bounds.height);
  const boundsCenterX = bounds.minX + bounds.width / 2;
  const boundsCenterY = bounds.minY + bounds.height / 2;

  return {
    scale,
    translateX: options.width / 2 - boundsCenterX * scale,
    translateY: options.height / 2 - boundsCenterY * scale,
    bounds,
  };
}

export function resolveRelationshipGraphEdgeTier(
  edge: RelationshipGraphEdge,
  options: ResolveRelationshipGraphEdgeTierOptions = {},
): 'hidden' | 'default' | 'focused' {
  const focusedEdgeIds = new Set(options.focusedEdgeIds ?? []);

  if (focusedEdgeIds.has(edge.id)) {
    return 'focused';
  }

  const focusedNodeIds = new Set(options.focusedNodeIds ?? []);
  if (focusedNodeIds.has(edge.source) || focusedNodeIds.has(edge.target)) {
    return 'focused';
  }

  return edge.hiddenByDefault ? 'hidden' : 'default';
}

export function resolveVisibleGraphError<T extends GraphSnapshotStatus>(
  window: RelationshipGraphWindow,
  snapshots: Partial<Record<RelationshipGraphWindow, T>>,
  errors: Partial<Record<RelationshipGraphWindow, string | null>>,
): string | null {
  if (snapshots[window]) {
    return null;
  }

  return errors[window] ?? null;
}
