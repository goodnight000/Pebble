
export type Language = 'en' | 'zh';
export type TranslationStatus = 'ready' | 'unavailable';

export type ContentType = 'all' | 'news' | 'research' | 'github';

export interface DigestCopy {
  headline: string;
  executiveSummary: string;
  llmAuthored?: boolean;
}

export interface NewsItem {
  id: string;
  title: string;
  summary: string;
  significanceScore: number;
  category: 'Research' | 'Product' | 'Company' | 'Funding' | 'Policy' | 'Open Source' | 'Hardware' | 'Security' | 'General';
  contentType: 'news' | 'research' | 'github';
  timestamp: string;
  tags: string[];
  sources: GroundingSource[];
  trustLabel?: 'official' | 'confirmed' | 'likely' | 'developing' | 'unverified' | 'disputed';
  verificationState?:
    | 'verified_artifact'
    | 'official_statement'
    | 'corroborated_report'
    | 'single_source_report'
    | 'community_signal'
    | 'disputed'
    | 'corrected_or_retracted';
  verificationConfidence?: number;
  freshnessState?: 'fresh' | 'maturing' | 'stable';
  trustComponents?: {
    corroboration: number;
    official_confirmation: number;
    source_trust: number;
    claim_quality: number;
    primary_document: number;
    confirmation_level: string;
    hedging_ratio: number;
    attribution_ratio: number;
    specificity_score: number;
  };
  finalScore?: number;
  editorialRank?: number;
  urgent?: boolean;
}

export interface GroundingSource {
  title: string;
  uri: string;
  source?: string;
  viaSource?: string;
  discoverySource?: string;
}

export interface DigestResponse {
  digests: Record<ContentType, DigestCopy>;
  headline: string;
  executiveSummary: string;
  items: NewsItem[];
  breakingAlert: NewsItem | null;
  llmAuthored?: boolean;
  locale?: Language;
  sourceLocale?: Language;
  translationStatus?: TranslationStatus;
}

export enum AppStatus {
  IDLE = 'IDLE',
  FETCHING = 'FETCHING',
  ANALYZING = 'ANALYZING',
  TRANSLATING = 'TRANSLATING',
  READY = 'READY',
  ERROR = 'ERROR'
}

// ── Cluster / Graph types ──

export interface GraphEntity {
  name: string;
  weight: number;
  tier: number | null;
}

export interface GraphArticle {
  id: string;
  title: string;
  url: string;
  source: string;
  publishedAt: string | null;
  globalScore: number;
  trustLabel: string | null;
  eventType: string;
  summary: string | null;
}

export interface GraphCluster {
  id: string;
  headline: string;
  x: number;
  y: number;
  coverageCount: number;
  sourcesCount: number;
  maxGlobalScore: number;
  velocity: number;
  pulsing: boolean;
  trustScore: number;
  trustLabel: string;
  dominantTopic: string;
  topicWeights: Record<string, number>;
  dominantEventType: string;
  entities: GraphEntity[];
  sparkline: number[];
  firstSeenAt: string;
  lastSeenAt: string;
  ageHours: number;
  articles: GraphArticle[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: RelationshipEdgeType;
  score: number;
  evidence: string[];
  embeddingSimilarity: number;
  llmType?: string;
  llmStrength?: number;
  llmExplanation?: string;
}

export interface GraphResponse {
  clusters: GraphCluster[];
  edges?: GraphEdge[];
  projectionSeed: string;
  generatedAt: string;
  locale?: Language;
  sourceLocale?: Language;
  translationStatus?: TranslationStatus;
}


export type RelationshipGraphWindow = '7d' | '30d';

export type RelationshipGraphZoomLevel = 'overview' | 'cluster' | 'detail';

export interface RelationshipGraphBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  width: number;
  height: number;
}

export interface RelationshipGraphViewport {
  scale: number;
  translateX: number;
  translateY: number;
  bounds: RelationshipGraphBounds;
}

export interface RelationshipGraphNodeVisual {
  nodeId: string;
  renderPriority: number;
  labelPriority: number;
  topicColorToken: string;
}

export type RelationshipEdgeType =
  | 'shared-entity'
  | 'event-chain'
  | 'market-adjacency'
  | 'embedding-similarity'
  | 'follow-up'
  | 'reaction'
  | 'competing';

export interface RelationshipGraphNode {
  id: string;
  clusterId: string;
  headline: string;
  dominantTopic: string;
  dominantEventType: string;
  importance: number;
  coverageCount: number;
  sourcesCount: number;
  velocity: number;
  ageHours: number;
  trustLabel: string;
  maxGlobalScore: number;
  keyEntities: string[];
  positionSeed: {
    x: number;
    y: number;
  };
}

export interface RelationshipGraphEdge {
  id: string;
  source: string;
  target: string;
  type: RelationshipEdgeType;
  score: number;
  evidence: string[];
  hiddenByDefault: boolean;
}

export interface RelationshipGraphEdgeCandidate {
  source: RelationshipGraphNode;
  target: RelationshipGraphNode;
  sharedEntities: string[];
  eventChain: boolean;
  marketAdjacency: number;
}

export interface RelationshipGraphResponse {
  nodes: RelationshipGraphNode[];
  edges: RelationshipGraphEdge[];
  window: RelationshipGraphWindow;
  generatedAt: string;
}

export interface LongformDigest {
  date: string;
  headline: string | null;
  subtitle: string | null;
  longformHtml: string | null;
  llmAuthored: boolean;
  locale: Language;
  available: boolean;
}

export interface DigestArchiveEntry {
  date: string;
  headline: string;
  subtitle: string;
}

export interface DigestArchiveResponse {
  digests: DigestArchiveEntry[];
}
