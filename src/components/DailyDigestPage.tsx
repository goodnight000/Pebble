import React, { useState, useEffect } from 'react';
import DOMPurify from 'dompurify';
import { AIService } from '@/services/aiService';
import { DigestArchiveEntry, Language, LongformDigest } from '@/types';
import { ChevronLeft, ChevronRight, CalendarDays, BookOpen } from 'lucide-react';

interface DailyDigestPageProps {
  aiService: AIService;
  language: Language;
}

const formatDisplayDate = (dateStr: string, language: Language): string => {
  const date = new Date(dateStr + 'T00:00:00');
  if (language === 'zh') {
    return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });
  }
  return date.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
};

const todayStr = () => {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
};

const sanitizeHtml = (html: string): string => {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['h1', 'h2', 'h3', 'p', 'a', 'strong', 'em', 'ul', 'li', 'br'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
  });
};

const DailyDigestPage: React.FC<DailyDigestPageProps> = ({ aiService, language }) => {
  const [digest, setDigest] = useState<LongformDigest | null>(null);
  const [archive, setArchive] = useState<DigestArchiveEntry[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>(todayStr());
  const [loading, setLoading] = useState(true);
  const [showArchive, setShowArchive] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    aiService.fetchDailyDigest(selectedDate, language).then((data) => {
      if (!cancelled) setDigest(data);
    }).catch((err) => {
      console.error('Failed to load digest', err);
      // Keep existing digest on error so we don't flash "no digest"
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [selectedDate, language, aiService]);

  useEffect(() => {
    aiService.fetchDigestArchive().then(setArchive).catch((err) => {
      console.error('Failed to load archive', err);
    });
  }, [aiService, selectedDate]);

  // Build a navigable date list: archive dates plus selectedDate if missing
  const navDates = React.useMemo(() => {
    const dates = archive.map(a => a.date);
    if (selectedDate && !dates.includes(selectedDate)) {
      // Insert selectedDate in sorted desc position
      dates.push(selectedDate);
      dates.sort((a, b) => b.localeCompare(a));
    }
    return dates;
  }, [archive, selectedDate]);

  const navigateDate = (direction: -1 | 1) => {
    const idx = navDates.indexOf(selectedDate);
    if (idx === -1) {
      if (navDates.length > 0) setSelectedDate(navDates[0]);
      return;
    }
    const newIdx = idx - direction; // list is desc, so -1 = newer, +1 = older
    if (newIdx >= 0 && newIdx < navDates.length) {
      setSelectedDate(navDates[newIdx]);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="space-y-4 text-center">
          <div className="mx-auto h-16 w-16 rounded-full border-2 border-[var(--ink)] bg-[var(--panel)] flex items-center justify-center">
            <BookOpen className="w-7 h-7 text-[var(--accent)] animate-pulse" />
          </div>
          <p className="text-sm font-bold uppercase tracking-widest text-[var(--muted)]">
            {language === 'en' ? 'Loading digest...' : '\u52A0\u8F7D\u4E2D...'}
          </p>
        </div>
      </div>
    );
  }

  if (!digest?.available) {
    return (
      <div className="mx-auto max-w-3xl space-y-8 p-6 pt-8">
        <div className="wf-panel p-8 text-center space-y-4">
          <CalendarDays className="w-10 h-10 mx-auto text-[var(--muted)]" />
          <h2 className="text-xl font-bold">
            {language === 'en' ? 'No digest available for this date' : '\u8BE5\u65E5\u671F\u6682\u65E0\u7B80\u62A5'}
          </h2>
          <p className="text-sm text-[var(--muted)]">
            {language === 'en'
              ? 'The daily digest is generated at 6:00 AM UTC each day. Check back later or browse the archive.'
              : '\u6BCF\u65E5\u7B80\u62A5\u4E8E UTC 6:00 \u751F\u6210\u3002\u8BF7\u7A0D\u540E\u67E5\u770B\u6216\u6D4F\u89C8\u5B58\u6863\u3002'}
          </p>
          {archive.length > 0 && (
            <button
              onClick={() => setSelectedDate(archive[0].date)}
              className="wf-button mt-4"
            >
              {language === 'en' ? 'View latest digest' : '\u67E5\u770B\u6700\u65B0\u7B80\u62A5'}
            </button>
          )}
        </div>

        {archive.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-widest text-[var(--muted)]">
              {language === 'en' ? 'Recent Digests' : '\u8FD1\u671F\u7B80\u62A5'}
            </h3>
            {archive.slice(0, 7).map((entry) => (
              <button
                key={entry.date}
                onClick={() => setSelectedDate(entry.date)}
                className={`w-full text-left wf-panel p-4 hover:bg-[var(--panel)] transition-colors ${
                  entry.date === selectedDate ? 'border-[var(--accent)]' : ''
                }`}
              >
                <p className="text-xs font-bold uppercase tracking-widest text-[var(--muted)]">
                  {formatDisplayDate(entry.date, language)}
                </p>
                <p className="text-sm font-semibold mt-1">{entry.headline}</p>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Content is sanitized via DOMPurify.sanitize() in sanitizeHtml() above
  const sanitizedContent = sanitizeHtml(digest.longformHtml ?? '');

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6 pt-8">
      {/* Date navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigateDate(-1)}
          className="wf-button flex items-center gap-1 text-xs"
          disabled={navDates.indexOf(selectedDate) >= navDates.length - 1}
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">{language === 'en' ? 'Older' : '\u66F4\u65E9'}</span>
        </button>

        <button
          onClick={() => setShowArchive(!showArchive)}
          className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-[var(--muted)] hover:text-[var(--ink)] transition-colors"
        >
          <CalendarDays className="w-3.5 h-3.5" />
          {formatDisplayDate(selectedDate, language)}
        </button>

        <button
          onClick={() => navigateDate(1)}
          className="wf-button flex items-center gap-1 text-xs"
          disabled={navDates.indexOf(selectedDate) <= 0}
        >
          <span className="hidden sm:inline">{language === 'en' ? 'Newer' : '\u66F4\u65B0'}</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Archive dropdown */}
      {showArchive && archive.length > 0 && (
        <div className="wf-panel p-4 space-y-2">
          <h3 className="text-xs font-bold uppercase tracking-widest text-[var(--muted)] mb-3">
            {language === 'en' ? 'Archive' : '\u5B58\u6863'}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-64 overflow-y-auto custom-scrollbar">
            {archive.map((entry) => (
              <button
                key={entry.date}
                onClick={() => { setSelectedDate(entry.date); setShowArchive(false); }}
                className={`text-left p-3 rounded-lg border-2 transition-all text-xs ${
                  entry.date === selectedDate
                    ? 'border-[var(--accent)] bg-[var(--accent-muted)]'
                    : 'border-[var(--grid)] hover:border-[var(--muted)]'
                }`}
              >
                <span className="font-bold uppercase tracking-wider">
                  {formatDisplayDate(entry.date, language)}
                </span>
                <span className="block mt-1 text-[var(--muted)] truncate">{entry.headline}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Digest content -- sanitized with DOMPurify */}
      <article
        className="digest-longform wf-panel p-6 md:p-10"
        dangerouslySetInnerHTML={{ __html: sanitizedContent }}
      />

      {/* Meta footer */}
      <div className="flex items-center justify-center gap-4 text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--muted)] pb-12">
        <span>{digest.llmAuthored ? (language === 'en' ? 'AI-authored digest' : 'AI \u64B0\u5199') : ''}</span>
        <span>&middot;</span>
        <span>{formatDisplayDate(selectedDate, language)}</span>
      </div>
    </div>
  );
};

export default DailyDigestPage;
