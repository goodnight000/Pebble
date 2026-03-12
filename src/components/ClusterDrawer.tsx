import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import type { SignalMapCluster, Language } from '@/types';
import { getTrustLabel, getUiText } from '@/i18n';

interface ClusterDrawerProps {
  cluster: SignalMapCluster | null;
  onClose: () => void;
  language: Language;
}

const formatRelativeTime = (iso: string | null): string => {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const hours = diff / (1000 * 60 * 60);
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
};

const formatAge = (ageHours: number): string => {
  if (ageHours < 24) return `${ageHours.toFixed(1)}h`;
  return `${(ageHours / 24).toFixed(1)}d`;
};

const tierClass = (tier: number | null): string => {
  if (tier === 1) return 't1';
  if (tier === 2) return 't2';
  if (tier === 3) return 't3';
  return 'unknown';
};

const ClusterDrawer: React.FC<ClusterDrawerProps> = ({ cluster, onClose, language }) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const sortedArticles = cluster
    ? [...cluster.articles].sort((a, b) => b.globalScore - a.globalScore)
    : [];

  const sparklinePoints = cluster
    ? (() => {
        const values = cluster.sparkline;
        const max = Math.max(...values, 1);
        const padding = 4;
        const height = 40;
        const usableHeight = height - padding * 2;
        return values
          .map((v, i) => {
            const x = values.length > 1 ? (i / (values.length - 1)) * 100 : 50;
            const y = padding + usableHeight - (v / max) * usableHeight;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
          })
          .join(' ');
      })()
    : '';

  return (
    <div className={`cluster-drawer custom-scrollbar${cluster ? ' cluster-drawer--open' : ''}`}>
      {cluster && (
        <>
          {/* Header */}
          <div className="cluster-drawer-header" style={{ position: 'relative' }}>
            <button
              type="button"
              className="cluster-drawer-close"
              onClick={onClose}
              aria-label="Close drawer"
            >
              <X size={14} />
            </button>
            <span className={`trust-badge trust-badge--${cluster.trustLabel}`}>
              {getTrustLabel(language, cluster.trustLabel)}
            </span>
            <h3 className="cluster-drawer-headline">{cluster.headline}</h3>
          </div>

          {/* Stats grid */}
          <div className="cluster-drawer-stats">
            <div className="cluster-drawer-stat">
              <span className="cluster-drawer-stat-label">
                {getUiText(language, 'coverage')}
              </span>
              <span className="cluster-drawer-stat-value">
                {cluster.coverageCount} {getUiText(language, 'articles')}
              </span>
            </div>
            <div className="cluster-drawer-stat">
              <span className="cluster-drawer-stat-label">
                {getUiText(language, 'sources')}
              </span>
              <span className="cluster-drawer-stat-value">
                {cluster.sourcesCount} {getUiText(language, 'sourcesSuffix')}
              </span>
            </div>
            <div className="cluster-drawer-stat">
              <span className="cluster-drawer-stat-label">
                {getUiText(language, 'velocity')}
              </span>
              <span className="cluster-drawer-stat-value">
                {cluster.velocity.toFixed(1)} art/hr
              </span>
            </div>
            <div className="cluster-drawer-stat">
              <span className="cluster-drawer-stat-label">
                {getUiText(language, 'age')}
              </span>
              <span className="cluster-drawer-stat-value">{formatAge(cluster.ageHours)}</span>
            </div>
          </div>

          {/* Entities section */}
          <div className="cluster-drawer-section">
            <div className="cluster-drawer-section-title">
              {getUiText(language, 'keyEntities')}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
              {cluster.entities.map((entity) => (
                <span
                  key={entity.name}
                  className={`entity-badge entity-badge--${tierClass(entity.tier)}`}
                >
                  {entity.name}
                </span>
              ))}
            </div>
          </div>

          {/* Sparkline section */}
          <div className="cluster-drawer-section">
            <div className="cluster-drawer-section-title">
              {getUiText(language, 'sevenDayTrend')}
            </div>
            <svg
              width="100%"
              height="40"
              viewBox="0 0 100 40"
              preserveAspectRatio="none"
              style={{ display: 'block' }}
            >
              <polyline className="cluster-sparkline" points={sparklinePoints} />
            </svg>
          </div>

          {/* Articles section */}
          <div className="cluster-drawer-section">
            <div className="cluster-drawer-section-title">
              {`${getUiText(language, 'coverageWithCount')} (${sortedArticles.length})`}
            </div>
            {sortedArticles.map((article) => (
              <div key={article.id} className="drawer-article-card">
                <div className="drawer-article-title">
                  <a href={article.url} target="_blank" rel="noopener noreferrer">
                    {article.title}
                  </a>
                </div>
                <div className="drawer-article-meta">
                  <span>{article.source}</span>
                  <span>{formatRelativeTime(article.publishedAt)}</span>
                  <span className="drawer-article-score">{article.globalScore}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

export default ClusterDrawer;
