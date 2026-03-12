import React from 'react';
import { Language, NewsItem } from '@/types';
import { Share2, ExternalLink, Zap, Star, ShieldCheck, Shield, ShieldAlert, ShieldQuestion } from 'lucide-react';
import { getCategoryConfig } from '@/config/constants';
import { getCategoryLabel, getTrustLabel, getUiText } from '@/i18n';

const TRUST_CONFIG: Record<string, { color: string; icon: React.ReactNode }> = {
  official: { color: '#22c55e', icon: <ShieldCheck className="w-3 h-3" /> },
  confirmed: { color: '#3b82f6', icon: <ShieldCheck className="w-3 h-3" /> },
  likely: { color: '#14b8a6', icon: <Shield className="w-3 h-3" /> },
  developing: { color: '#eab308', icon: <ShieldQuestion className="w-3 h-3" /> },
  unverified: { color: '#6b7280', icon: <ShieldAlert className="w-3 h-3" /> },
  disputed: { color: '#ef4444', icon: <ShieldAlert className="w-3 h-3" /> },
};

const TrustBadge: React.FC<{ item: NewsItem; language: Language }> = ({ item, language }) => {
  if (!item.trustLabel) return null;
  const cfg = TRUST_CONFIG[item.trustLabel];
  if (!cfg) return null;

  return (
    <span
      className="wf-trust-badge"
      style={{ color: cfg.color, borderColor: cfg.color }}
    >
      {cfg.icon}
      {getTrustLabel(language, item.trustLabel)}
    </span>
  );
};

interface NewsCardProps {
  item: NewsItem;
  language: Language;
  featured?: boolean;
}

const formatTimestamp = (timestamp: string) =>
  new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

const tightenSummary = (summary: string, maxLength = 150) => {
  const compact = summary.replace(/\s+/g, ' ').trim();
  if (compact.length <= maxLength) return compact;

  const clipped = compact.slice(0, maxLength);
  const sentenceBreak = Math.max(clipped.lastIndexOf('. '), clipped.lastIndexOf('; '));
  const safeCut = sentenceBreak >= 90 ? sentenceBreak + 1 : clipped.lastIndexOf(' ');
  return `${clipped.slice(0, safeCut > 0 ? safeCut : maxLength).trimEnd()}...`;
};

const NewsCard: React.FC<NewsCardProps> = ({ item, language, featured = false }) => {
  const cat = getCategoryConfig(item.category);
  const isGitHub = item.contentType === 'github';
  const isHigh = item.significanceScore >= 85;
  const primarySource = item.sources?.[0];
  const maxVisibleTags = 4;
  const visibleTags = item.tags.slice(0, maxVisibleTags);
  const hiddenTagCount = Math.max(0, item.tags.length - visibleTags.length);

  const getScoreColor = (score: number) => {
    if (score >= 85) return { color: cat.color, bg: cat.bgMuted, border: cat.borderColor };
    if (score >= 75) return { color: 'var(--ink)', bg: 'transparent', border: 'var(--ink)' };
    return { color: 'var(--muted)', bg: 'transparent', border: 'var(--ink)' };
  };

  const scoreStyle = getScoreColor(item.significanceScore);

  const shareStory = async (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    const url = primarySource?.uri;
    if (!url) return;

    try {
      if (navigator.share) {
        await navigator.share({
          title: item.title,
          text: tightenSummary(item.summary),
          url,
        });
        return;
      }

      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
        return;
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return;
      }
    }

    window.prompt(getUiText(language, 'copyStoryLink'), url);
  };

  return (
    <div
      className={`news-card-wf ${featured ? 'news-card-wf--feature' : ''} group relative flex min-h-[372px] flex-col overflow-hidden rounded-2xl border-2 border-dashed bg-[var(--panel)]`}
      style={
        {
          '--wf-accent': cat.borderColor,
          '--wf-accent-muted': cat.bgMuted,
          borderColor: cat.borderColor,
          borderLeftWidth: '4px',
          borderLeftStyle: 'solid',
          borderLeftColor: cat.borderColor,
        } as React.CSSProperties
      }
    >
      <div className={`flex flex-1 flex-col ${featured ? 'p-7 md:p-8' : 'p-6'}`}>
        <div className="wf-card-header mb-5">
          <div className="wf-card-header__top">
            <div className="wf-card-header__left">
              <span className="wf-chip wf-chip--category" style={{ borderColor: cat.color, color: cat.color, background: cat.bgMuted }}>
                {getCategoryLabel(language, item.category)}
              </span>
              {primarySource?.title && <span className="wf-card-source">{primarySource.title}</span>}
            </div>
            <div className="wf-card-header__right">
              <TrustBadge item={item} language={language} />
            </div>
          </div>
          <div className="wf-card-header__bottom">
            <span className="wf-card-time mono">{formatTimestamp(item.timestamp)}</span>
            <div
              className="wf-signal-pill"
              style={{
                color: scoreStyle.color,
                borderColor: scoreStyle.border,
                background: scoreStyle.bg,
              }}
            >
              {isGitHub ? (
                <Star
                  className="w-3 h-3"
                  fill={isHigh ? cat.color : 'none'}
                  style={{ color: isHigh ? cat.color : undefined }}
                />
              ) : (
                <Zap
                  className="w-3 h-3"
                  fill={isHigh ? cat.color : 'none'}
                  style={{ color: isHigh ? cat.color : undefined }}
                />
              )}
              <span className="wf-signal-pill__label">{getUiText(language, 'signal')}</span>
              <span className="wf-signal-pill__value mono">{item.significanceScore}</span>
            </div>
          </div>
        </div>

        <h3 className={`wf-card-title ${featured ? 'wf-card-title--feature' : ''} mb-3 transition-colors duration-200 ${featured ? 'line-clamp-4' : 'line-clamp-3'}`}>
          {primarySource?.uri ? (
            <a
              href={primarySource.uri}
              target="_blank"
              rel="noopener noreferrer"
              className="transition-colors duration-200"
            >
              {item.title}
            </a>
          ) : (
            item.title
          )}
        </h3>

        <p className={`wf-card-summary ${featured ? 'wf-card-summary--feature line-clamp-4' : 'line-clamp-3'} mb-6 flex-1`}>
          {item.summary}
        </p>

        <div className="wf-card-footer">
          <div className="wf-card-footer__info">
            {visibleTags.map((tag) => (
              <span key={tag} className="wf-card-tag">
                {tag}
              </span>
            ))}
            {hiddenTagCount > 0 && <span className="wf-card-tag wf-card-tag--overflow">+{hiddenTagCount}</span>}
          </div>
          <div className="wf-card-footer__utility">
            {primarySource?.uri && (
              <a
                href={primarySource.uri}
                target="_blank"
                rel="noopener noreferrer"
                className="wf-card-link"
              >
                <ExternalLink className="w-3 h-3" />
                <span>{getUiText(language, 'readSource')}</span>
              </a>
            )}
            <button
              type="button"
              onClick={shareStory}
              className="wf-card-share"
              aria-label={getUiText(language, 'shareStory')}
            >
              <Share2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default NewsCard;
