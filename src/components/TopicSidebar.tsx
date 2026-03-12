import React from 'react';
import { TopicTrendItem, Language } from '@/types';
import { getTopicLabel, getUiText } from '@/i18n';

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

interface TopicSidebarProps {
  topics: TopicTrendItem[];
  language: Language;
}

const TopicSidebar: React.FC<TopicSidebarProps> = ({ topics, language }) => {
  const maxIntensity = Math.max(
    ...topics.flatMap((t) => t.dailyIntensity),
    0.01,
  );

  return (
    <div className="topic-sidebar">
      <div style={{ marginBottom: '1rem' }}>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.14em',
            color: 'var(--muted)',
          }}
        >
          {getUiText(language, 'sevenDayTopics')}
        </span>
      </div>
      {topics.map((topic) => (
        <div key={topic.topic} className="topic-sidebar-row">
          <span className="topic-sidebar-label">{getTopicLabel(language, topic.topic, topic.label)}</span>
          <div className="topic-sidebar-cells">
            {topic.dailyIntensity.map((intensity, i) => (
              <div
                key={i}
                className="topic-sidebar-cell"
                style={{
                  background: TOPIC_COLORS[topic.topic] ?? TOPIC_COLORS.mixed,
                  opacity: Math.max(0.08, intensity / maxIntensity),
                }}
                title={`Day ${i + 1}: ${intensity.toFixed(1)}`}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default TopicSidebar;
