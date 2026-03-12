import React from 'react';
import type { SignalMapCluster, Language } from '@/types';
import { getTrustLabel, getUiText } from '@/i18n';

const TOPIC_COLORS: Record<string, string> = {
  llms: '#3b82f6',
  multimodal: '#8b5cf6',
  agents: '#10b981',
  robotics: '#f59e0b',
  vision: '#ec4899',
  audio_speech: '#06b6d4',
  hardware_chips: '#ef4444',
  open_source: '#84cc16',
  startups_funding: '#a855f7',
  enterprise_apps: '#14b8a6',
  safety_policy: '#f97316',
  research_methods: '#6366f1',
  mixed: '#6d6d6d',
};

interface SignalMapListProps {
  clusters: SignalMapCluster[];
  onSelectCluster: (id: string) => void;
  language: Language;
}

const SignalMapList: React.FC<SignalMapListProps> = ({ clusters, onSelectCluster, language }) => {
  const sorted = [...clusters].sort((a, b) => b.maxGlobalScore - a.maxGlobalScore);

  return (
    <div className="signal-map-list">
      {sorted.map((cluster) => (
        <div
          key={cluster.id}
          className="wf-panel signal-map-list-card"
          onClick={() => onSelectCluster(cluster.id)}
        >
          <div
            className="signal-map-topic-dot"
            style={{ background: TOPIC_COLORS[cluster.dominantTopic] || '#6d6d6d' }}
          />
          <div className="signal-map-list-content">
            <h3 className="signal-map-list-headline">{cluster.headline}</h3>
            <div className="signal-map-list-meta">
              <span className="wf-chip">
                {cluster.coverageCount} {getUiText(language, 'articlesDetailed')}
              </span>
              <span className={`trust-badge trust-badge--${cluster.trustLabel}`}>
                {getTrustLabel(language, cluster.trustLabel)}
              </span>
              {cluster.pulsing && (
                <span
                  className="wf-chip"
                  style={{ borderColor: '#ff6a00', color: '#ff6a00' }}
                >
                  {cluster.velocity.toFixed(1)} art/hr
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default SignalMapList;
