import React, { useMemo } from 'react';
import { X } from 'lucide-react';
import type {
  Language,
  RelationshipEdgeType,
  RelationshipGraphResponse,
  SignalMapCluster,
} from '@/types';
import { getTrustLabel, getUiText } from '@/i18n';

interface RelationshipGraphPanelProps {
  cluster: SignalMapCluster | null;
  graph: RelationshipGraphResponse;
  language: Language;
  onClose: () => void;
}

const EDGE_TYPE_LABEL_KEY: Record<RelationshipEdgeType, 'graphSharedEntity' | 'graphEventChain' | 'graphMarketAdjacency' | 'graphEmbeddingSimilarity'> = {
  'shared-entity': 'graphSharedEntity',
  'event-chain': 'graphEventChain',
  'market-adjacency': 'graphMarketAdjacency',
  'embedding-similarity': 'graphEmbeddingSimilarity',
};

function formatAge(ageHours: number): string {
  if (ageHours < 24) {
    return `${ageHours.toFixed(1)}h`;
  }
  return `${(ageHours / 24).toFixed(1)}d`;
}

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
        <button
          type="button"
          className="cluster-drawer-close"
          onClick={onClose}
          aria-label={getUiText(language, 'closeRelationshipPanel')}
        >
          <X size={14} />
        </button>
        <span className={`trust-badge trust-badge--${cluster.trustLabel}`}>
          {getTrustLabel(language, cluster.trustLabel)}
        </span>
        <h3 className="relationship-graph-panel__headline">{cluster.headline}</h3>
      </div>

      <section className="relationship-graph-panel__section">
        <p className="relationship-graph-panel__section-title">
          {getUiText(language, 'whyThisClusterMatters')}
        </p>
        <p className="relationship-graph-panel__narrative">
          {`${cluster.coverageCount} ${getUiText(language, 'articlesDetailed')} across ${cluster.sourcesCount} ${getUiText(language, 'sourcesSuffix')} are converging around ${cluster.dominantTopic}. The cluster is moving at ${cluster.velocity.toFixed(1)} articles per hour and sits inside the ${graph.window.toUpperCase()} rolling view.`}
        </p>
        <div className="relationship-graph-panel__stats">
          <div className="relationship-graph-panel__stat">
            <span>{getUiText(language, 'coverage')}</span>
            <strong>{cluster.coverageCount}</strong>
          </div>
          <div className="relationship-graph-panel__stat">
            <span>{getUiText(language, 'sources')}</span>
            <strong>{cluster.sourcesCount}</strong>
          </div>
          <div className="relationship-graph-panel__stat">
            <span>{getUiText(language, 'velocity')}</span>
            <strong>{cluster.velocity.toFixed(1)}</strong>
          </div>
          <div className="relationship-graph-panel__stat">
            <span>{getUiText(language, 'age')}</span>
            <strong>{formatAge(cluster.ageHours)}</strong>
          </div>
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
