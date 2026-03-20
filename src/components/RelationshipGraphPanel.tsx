import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Info, ShieldCheck, Shield, ShieldQuestion, ShieldAlert } from 'lucide-react';
import type {
  Language,
  RelationshipEdgeType,
  RelationshipGraphResponse,
  GraphCluster,
} from '@/types';
import { getTrustLabel, getUiText } from '@/i18n';

const TRUST_CONFIG: Record<string, { color: string; icon: React.ReactNode }> = {
  official: { color: '#22c55e', icon: <ShieldCheck className="w-3 h-3" /> },
  confirmed: { color: '#3b82f6', icon: <ShieldCheck className="w-3 h-3" /> },
  likely: { color: '#14b8a6', icon: <Shield className="w-3 h-3" /> },
  developing: { color: '#eab308', icon: <ShieldQuestion className="w-3 h-3" /> },
  unverified: { color: '#6b7280', icon: <ShieldAlert className="w-3 h-3" /> },
  disputed: { color: '#ef4444', icon: <ShieldAlert className="w-3 h-3" /> },
  verified_artifact: { color: '#16a34a', icon: <ShieldCheck className="w-3 h-3" /> },
  official_statement: { color: '#15803d', icon: <ShieldCheck className="w-3 h-3" /> },
  corroborated_report: { color: '#2563eb', icon: <Shield className="w-3 h-3" /> },
  single_source_report: { color: '#0f766e', icon: <Shield className="w-3 h-3" /> },
  community_signal: { color: '#6b7280', icon: <ShieldQuestion className="w-3 h-3" /> },
  corrected_or_retracted: { color: '#dc2626', icon: <ShieldAlert className="w-3 h-3" /> },
};

interface RelationshipGraphPanelProps {
  cluster: GraphCluster | null;
  graph: RelationshipGraphResponse;
  language: Language;
  onClose: () => void;
}

const EDGE_TYPE_LABEL_KEY: Record<RelationshipEdgeType, string> = {
  'shared-entity': 'graphSharedEntity',
  'event-chain': 'graphEventChain',
  'market-adjacency': 'graphMarketAdjacency',
  'embedding-similarity': 'graphEmbeddingSimilarity',
  'follow-up': 'graphFollowUp',
  'reaction': 'graphReaction',
  'competing': 'graphCompeting',
};

function formatHoursAgo(hoursAgo: number): string {
  if (hoursAgo < 1) {
    return `${Math.round(hoursAgo * 60)}m ago`;
  }
  if (hoursAgo < 24) {
    return `${hoursAgo.toFixed(1)}h ago`;
  }
  return `${(hoursAgo / 24).toFixed(1)}d ago`;
}

const STAT_DESCRIPTIONS: Record<string, string> = {
  score:
    'Significance score (0\u2013100) based on editorial importance, source credibility, and topic relevance. 85+ is urgent, 55+ appears in the feed.',
  connections:
    'Number of relationship edges linking this cluster to other stories in the graph — shared entities, event chains, or market adjacency.',
  published:
    'How long ago this story was first reported, measured from the earliest article in the cluster to now.',
  avgSimilarity:
    'Mean relationship strength across all edges to connected clusters. Higher values mean this story is tightly woven into the broader narrative.',
};

const StatInfoTip: React.FC<{ statKey: string }> = ({ statKey }) => {
  const triggerRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  const toggle = useCallback(() => {
    if (visible) {
      setVisible(false);
      return;
    }
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setPos({ top: rect.top, left: rect.left + rect.width / 2 });
    setVisible(true);
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (triggerRef.current && !triggerRef.current.contains(e.target as Node)) {
        setVisible(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [visible]);

  const tooltip = visible && pos
    ? createPortal(
        <div className="stat-tooltip" style={{ top: pos.top, left: pos.left }}>
          <p>{STAT_DESCRIPTIONS[statKey]}</p>
        </div>,
        document.body,
      )
    : null;

  return (
    <div ref={triggerRef} className="stat-info-tip__trigger" onClick={toggle} role="button" tabIndex={0} aria-label={`Info about ${statKey}`}>
      <Info size={10} />
      {tooltip}
    </div>
  );
};

const RelationshipGraphPanel: React.FC<RelationshipGraphPanelProps> = ({
  cluster,
  graph,
  language,
  onClose,
}) => {
  const nodeMap = useMemo(
    () => new Map(graph.nodes.map((node) => [node.id, node])),
    [graph.nodes],
  );

  const relatedEdges = useMemo(() => {
    if (!cluster) {
      return [];
    }

    return graph.edges
      .filter((edge) => edge.source === cluster.id || edge.target === cluster.id)
      .sort((left, right) => right.score - left.score);
  }, [cluster, graph.edges]);

  const groupedEdges = useMemo(() => {
    const groups: Record<RelationshipEdgeType, typeof relatedEdges> = {
      'follow-up': [],
      'reaction': [],
      'competing': [],
      'shared-entity': [],
      'event-chain': [],
      'market-adjacency': [],
      'embedding-similarity': [],
    };

    for (const edge of relatedEdges) {
      groups[edge.type].push(edge);
    }

    return groups;
  }, [relatedEdges]);

  const connectionCount = relatedEdges.length;

  const avgEdgeScore = useMemo(() => {
    if (relatedEdges.length === 0) return 0;
    const sum = relatedEdges.reduce((acc, edge) => acc + edge.score, 0);
    return sum / relatedEdges.length;
  }, [relatedEdges]);

  const publishedHoursAgo = useMemo(() => {
    if (!cluster?.firstSeenAt) return 0;
    const firstSeen = new Date(cluster.firstSeenAt).getTime();
    const now = Date.now();
    return (now - firstSeen) / (1000 * 60 * 60);
  }, [cluster?.firstSeenAt]);

  const supportingArticles = useMemo(
    () => (
      cluster
        ? [...cluster.articles].sort((left, right) => right.globalScore - left.globalScore).slice(0, 6)
        : []
    ),
    [cluster],
  );

  if (!cluster) {
    return null;
  }

  return (
    <aside
      className="relationship-graph-panel custom-scrollbar"
      data-testid="relationship-graph-panel"
    >
      <div className="relationship-graph-panel__header">
        <div className="relationship-graph-panel__header-top">
          <button
            type="button"
            className="cluster-drawer-close"
            onClick={onClose}
            aria-label={getUiText(language, 'closeRelationshipPanel')}
          >
            <X size={14} />
          </button>
          {(() => {
            const cfg = TRUST_CONFIG[cluster.trustLabel];
            if (!cfg) return null;
            return (
              <span
                className="wf-trust-badge"
                style={{ color: cfg.color, borderColor: cfg.color }}
              >
                {cfg.icon}
                {getTrustLabel(language, cluster.trustLabel)}
              </span>
            );
          })()}
        </div>
        <h3 className="relationship-graph-panel__headline">{cluster.headline}</h3>
      </div>

      <section className="relationship-graph-panel__section">
        <p className="relationship-graph-panel__section-title">
          {getUiText(language, 'whyThisClusterMatters')}
        </p>
        <p className="relationship-graph-panel__narrative">
          {`This ${cluster.dominantTopic} story has a significance score of ${cluster.maxGlobalScore} and connects to ${connectionCount} other ${connectionCount === 1 ? 'cluster' : 'clusters'} in the ${graph.window.toUpperCase()} rolling view.`}
        </p>
        <div className="relationship-graph-panel__stats">
          {([
            { key: 'score', label: getUiText(language, 'score'), value: cluster.maxGlobalScore },
            { key: 'connections', label: getUiText(language, 'connections'), value: connectionCount },
            { key: 'published', label: getUiText(language, 'published'), value: formatHoursAgo(publishedHoursAgo) },
            { key: 'avgSimilarity', label: getUiText(language, 'avgSimilarity'), value: connectionCount > 0 ? `${Math.round(avgEdgeScore * 100)}%` : '—' },
          ] as const).map((stat) => (
            <div key={stat.key} className="relationship-graph-panel__stat">
              <span className="stat-label-row">
                {stat.label}
                <StatInfoTip statKey={stat.key} />
              </span>
              <strong>{stat.value}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="relationship-graph-panel__section">
        <p className="relationship-graph-panel__section-title">
          {getUiText(language, 'relationshipEvidence')}
        </p>
        {(['shared-entity', 'event-chain', 'market-adjacency'] as RelationshipEdgeType[]).map((type) => (
          groupedEdges[type].length > 0 ? (
            <div key={type} className="relationship-graph-panel__group">
              <p className="relationship-graph-panel__group-title">
                {getUiText(language, EDGE_TYPE_LABEL_KEY[type])}
              </p>
              {groupedEdges[type].slice(0, 3).map((edge) => {
                const connectedId = edge.source === cluster.id ? edge.target : edge.source;
                const connectedNode = nodeMap.get(connectedId);

                return (
                  <article key={edge.id} className="relationship-graph-panel__connection">
                    <div className="relationship-graph-panel__connection-head">
                      <strong>{connectedNode?.headline ?? connectedId}</strong>
                      <span>{Math.round(edge.score * 100)}</span>
                    </div>
                    {edge.evidence.map((evidence) => (
                      <p key={evidence} className="relationship-graph-panel__connection-evidence">
                        {evidence}
                      </p>
                    ))}
                  </article>
                );
              })}
            </div>
          ) : null
        ))}
      </section>

      <section className="relationship-graph-panel__section">
        <p className="relationship-graph-panel__section-title">
          {getUiText(language, 'supportingCoverage')}
        </p>
        {supportingArticles.map((article) => (
          <article key={article.id} className="relationship-graph-panel__article">
            <a href={article.url} target="_blank" rel="noreferrer">
              {article.title}
            </a>
            <div className="relationship-graph-panel__article-meta">
              <span>{article.source}</span>
              <span>{article.globalScore}</span>
            </div>
          </article>
        ))}
      </section>
    </aside>
  );
};

export default RelationshipGraphPanel;
