import React from 'react';
import { Language, NewsItem } from '@/types';
import { AlertCircle, ArrowRight, Shield, ShieldCheck, ShieldAlert, ShieldQuestion } from 'lucide-react';
import { getTrustLabel, getUiText } from '@/i18n';

const TRUST_CONFIG: Record<string, { color: string; icon: React.ReactNode }> = {
  official: { color: '#22c55e', icon: <ShieldCheck className="w-3 h-3" /> },
  confirmed: { color: '#3b82f6', icon: <ShieldCheck className="w-3 h-3" /> },
  likely: { color: '#14b8a6', icon: <Shield className="w-3 h-3" /> },
  developing: { color: '#eab308', icon: <ShieldQuestion className="w-3 h-3" /> },
  unverified: { color: '#6b7280', icon: <ShieldAlert className="w-3 h-3" /> },
  disputed: { color: '#ef4444', icon: <ShieldAlert className="w-3 h-3" /> },
};

const TRUSTED_LABELS = new Set<string | undefined>(['official', 'confirmed', 'likely', undefined]);

interface BreakingAlertProps {
  item: NewsItem;
  language: Language;
}

const formatTimestamp = (timestamp: string) =>
  new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

const tightenSummary = (summary: string, maxLength = 180) => {
  const compact = summary.replace(/\s+/g, ' ').trim();
  if (compact.length <= maxLength) return compact;

  const clipped = compact.slice(0, maxLength);
  const safeCut = clipped.lastIndexOf(' ');
  return `${clipped.slice(0, safeCut > 0 ? safeCut : maxLength).trimEnd()}...`;
};

const BreakingAlert: React.FC<BreakingAlertProps> = ({ item, language }) => {
  if (!TRUSTED_LABELS.has(item.trustLabel)) {
    return null;
  }

  const trustCfg = item.trustLabel ? TRUST_CONFIG[item.trustLabel] : null;
  const primarySource = item.sources?.[0];

  return (
    <div className="group relative overflow-hidden rounded-2xl border-2 border-[var(--accent)] bg-[var(--panel)] shadow-[6px_6px_0_var(--ink)]">
      <div
        className="absolute inset-0 opacity-10"
        style={{
          backgroundImage:
            'repeating-linear-gradient(135deg, var(--accent) 0px, var(--accent) 2px, transparent 2px, transparent 10px)',
        }}
      />
      <div className="relative flex flex-col gap-5 rounded-2xl p-6 md:p-8">
        <div className="wf-breaking-meta">
          <span className="wf-breaking-label">{getUiText(language, 'breakingIntelligence')}</span>
          {primarySource?.title && (
            <>
              <span className="wf-breaking-separator" />
              <span className="wf-breaking-source">{getUiText(language, 'sourceLabel')}: {primarySource.title}</span>
            </>
          )}
          <span className="wf-breaking-separator" />
          <span className="wf-breaking-time mono">{formatTimestamp(item.timestamp)}</span>
        </div>

        <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
          <div className="flex min-w-0 items-start gap-5">
            <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl border-2 border-[var(--accent)] bg-[var(--paper)]">
              <AlertCircle className="w-6 h-6 animate-pulse text-[var(--accent)]" />
            </div>
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span
                  className="wf-signal-pill"
                  style={{ borderColor: 'var(--accent)', color: 'var(--accent)', background: 'rgba(255,106,0,0.12)' }}
                >
                  <span className="wf-signal-pill__label">{getUiText(language, 'signal')}</span>
                  <span className="wf-signal-pill__value mono">{item.significanceScore}</span>
                </span>
                {trustCfg && (
                  <span
                    className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide"
                    style={{ color: trustCfg.color }}
                  >
                    {trustCfg.icon}
                    {getTrustLabel(language, item.trustLabel)}
                  </span>
                )}
              </div>
              <h2 className="wf-breaking-title">{item.title}</h2>
              <p className="wf-breaking-summary">{tightenSummary(item.summary)}</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 md:justify-end">
            {primarySource?.uri && (
              <button
                type="button"
                className="wf-button flex items-center gap-2"
                onClick={() => window.open(primarySource.uri, '_blank', 'noopener,noreferrer')}
              >
                {getUiText(language, 'viewSource')}
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default BreakingAlert;
