import React, { useState, useEffect, useCallback } from 'react';
import { AppStatus, ContentType, DigestResponse, Language, NewsItem } from '@/types';
import { AIService } from '@/services/aiService';
import NewsCard from '@/components/NewsCard';
import BreakingAlert from '@/components/BreakingAlert';
import RelationshipGraph from '@/components/RelationshipGraph';
import {
  CONTENT_TYPE_LABELS,
  getNavLabel,
  getUiText,
  readStoredLanguage,
  writeStoredLanguage,
} from '@/i18n';
import DailyDigestPage from '@/components/DailyDigestPage';
import {
  RefreshCcw,
  Calendar,
  Compass,
  BrainCircuit,
  Network,
  Languages,
  Layers,
  Newspaper,
  FlaskConical,
  Github,
  BookOpen,
} from 'lucide-react';

const DIGEST_REFRESH_INTERVAL_MS = 5 * 60 * 1000;

type AppTab = 'digest' | 'live' | 'weekly' | 'map';

interface NavDef {
  id: AppTab;
  icon: React.ReactNode;
  color: string;
}

const NAV_ITEMS: NavDef[] = [
  { id: 'digest', icon: <BookOpen className="w-4 h-4" />, color: '#ff6a00' },
  { id: 'live', icon: <Compass className="w-4 h-4" />, color: '#10b981' },
  { id: 'weekly', icon: <Calendar className="w-4 h-4" />, color: '#8b5cf6' },
  { id: 'map', icon: <Network className="w-4 h-4" />, color: '#3b82f6' },
];

const CONTENT_TABS: { id: ContentType; icon: React.ReactNode; color: string }[] = [
  { id: 'all', icon: <Layers className="w-3.5 h-3.5" />, color: 'var(--accent)' },
  { id: 'news', icon: <Newspaper className="w-3.5 h-3.5" />, color: 'var(--cat-industry)' },
  { id: 'research', icon: <FlaskConical className="w-3.5 h-3.5" />, color: 'var(--cat-research)' },
  { id: 'github', icon: <Github className="w-3.5 h-3.5" />, color: 'var(--cat-startup)' },
];

const formatClock = (date: Date) =>
  date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

const App: React.FC = () => {
  const [status, setStatus] = useState<AppStatus>(AppStatus.IDLE);
  const [digest, setDigest] = useState<DigestResponse | null>(null);
  const [language, setLanguage] = useState<Language>(() => readStoredLanguage());
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [weeklyTop, setWeeklyTop] = useState<NewsItem[]>([]);
  const [activeTab, setActiveTab] = useState<AppTab>('live');
  const [contentFilter, setContentFilter] = useState<ContentType>('all');

  const aiService = React.useMemo(() => new AIService(), []);
  const hasDigestRef = React.useRef(false);
  const hasExpandedWeeklyRef = React.useRef(false);

  const loadWeeklyTop = useCallback(async (locale: Language) => {
    const weekly = await aiService.fetchWeeklyTop(hasExpandedWeeklyRef.current ? 12 : 6, locale);
    setWeeklyTop(weekly);
  }, [aiService]);

  const loadNewsForLocale = useCallback(async (locale: Language, options?: { refresh?: boolean; resetContent?: boolean }) => {
    const refresh = options?.refresh ?? false;
    const resetContent = options?.resetContent ?? false;
    try {
      setStatus(locale === 'zh' ? AppStatus.TRANSLATING : AppStatus.FETCHING);
      if (resetContent) {
        setDigest(null);
        setWeeklyTop([]);
      }
      const data = refresh ? await aiService.refreshDigest(locale) : await aiService.fetchDigest(locale);
      setDigest(data);
      hasDigestRef.current = true;
      setLastUpdated(new Date());
      setStatus(AppStatus.READY);
    } catch (error) {
      console.error(refresh ? 'Failed to load intelligence:' : 'Failed to load initial intelligence:', error);
      setStatus(hasDigestRef.current ? AppStatus.READY : AppStatus.ERROR);
    }
  }, [aiService]);

  const refreshNews = useCallback(async () => {
    await loadNewsForLocale(language, { refresh: true });
    if (activeTab === 'weekly') {
      try {
        await loadWeeklyTop(language);
      } catch (error) {
        console.error('Failed to refresh weekly items', error);
      }
    }
  }, [activeTab, language, loadNewsForLocale, loadWeeklyTop]);

  const loadWeekly = useCallback(async () => {
    try {
      hasExpandedWeeklyRef.current = true;
      await loadWeeklyTop(language);
    } catch (error) {
      console.error('Failed to load weekly items', error);
    }
  }, [language, loadWeeklyTop]);

  const toggleLanguage = () => {
    const nextLanguage: Language = language === 'en' ? 'zh' : 'en';
    setStatus(nextLanguage === 'zh' ? AppStatus.TRANSLATING : AppStatus.FETCHING);
    setDigest(null);
    setWeeklyTop([]);
    setLanguage(nextLanguage);
  };

  useEffect(() => {
    writeStoredLanguage(language);
  }, [language]);

  useEffect(() => {
    void loadNewsForLocale(language);

    const unsubscribe = aiService.subscribe((event) => {
      if (event.type === 'digest') {
        setDigest(event.data);
        setLastUpdated(new Date());
      }
    });

    // Fallback polling in case realtime and SSE both fail silently
    const intervalId = window.setInterval(() => {
      void loadNewsForLocale(language);
    }, DIGEST_REFRESH_INTERVAL_MS);

    return () => {
      unsubscribe();
      window.clearInterval(intervalId);
    };
  }, [language, loadNewsForLocale, aiService]);

  useEffect(() => {
    if (activeTab === 'weekly' && weeklyTop.length === 0) {
      loadWeekly();
    }
  }, [activeTab, weeklyTop.length, loadWeekly]);

  const currentDigest = digest;
  const hasDigest = Boolean(currentDigest);

  const filteredItems = currentDigest
    ? (contentFilter === 'all'
      ? [...currentDigest.items]
      : currentDigest.items.filter((item) => item.contentType === contentFilter)
    ).sort((a, b) => b.significanceScore - a.significanceScore)
    : [];

  const showBreaking = contentFilter === 'all' || contentFilter === 'news';

  return (
    <div className="app-shell wireframe-grid flex h-screen overflow-hidden text-[var(--ink)]">
      <aside className="app-sidebar hidden lg:flex w-64 shrink-0 sticky top-0 h-screen self-start flex-col overflow-hidden border-r-2 border-[var(--ink)] bg-[var(--panel)]">
        <div className="flex h-full flex-col">
          <div className="p-6">
            <div className="mb-8 flex items-center gap-3">
              <div className="rounded-lg border-2 border-[var(--ink)] bg-[var(--paper)] p-2">
                <img src="/logo.png" alt="Pebble Logo" className="w-6 h-6" />
              </div>
              <h1 className="text-2xl font-black uppercase tracking-[0.2em]">{getUiText(language, 'brand')}</h1>
            </div>

            <nav className="space-y-1">
              {NAV_ITEMS.map((nav) => {
                const isActive = activeTab === nav.id;
                return (
                  <button
                    key={nav.id}
                    type="button"
                    onClick={() => setActiveTab(nav.id)}
                    className={`group flex w-full items-center gap-3 rounded-xl border-2 px-4 py-3 text-left transition-all ${
                      isActive
                        ? 'bg-[var(--paper)]'
                        : 'border-dashed border-[var(--ink)] text-[var(--muted)] hover:bg-[var(--panel)] hover:text-[var(--ink)]'
                    }`}
                    style={isActive ? { borderColor: nav.color, borderStyle: 'solid' } : undefined}
                  >
                    <div style={{ color: isActive ? nav.color : undefined }}>{nav.icon}</div>
                    <span className="text-sm font-semibold uppercase tracking-[0.08em]">{getNavLabel(language, nav.id)}</span>
                    {isActive && <div className="ml-auto h-2 w-2 rounded-full" style={{ background: nav.color }} />}
                  </button>
                );
              })}
            </nav>
          </div>

          <div className="mt-auto p-6">
            <div className="wf-outline bg-[var(--paper)] p-4">
              <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[var(--muted)]">
                {getUiText(language, 'digestRefresh')}
              </p>
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-[var(--accent)]"></div>
                <span className="text-xs font-medium text-[var(--muted)]">
                  {getUiText(language, 'autoRefresh')}
                </span>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <main className="app-main relative flex min-h-0 flex-1 flex-col overflow-hidden">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b-2 border-[var(--ink)] bg-[var(--paper)]/90 px-6 py-4 backdrop-blur">
          <div className="flex items-center gap-4">
            <div className="rounded-lg border-2 border-[var(--ink)] bg-[var(--paper)] p-2 lg:hidden">
              <img src="/logo.png" alt="Pebble Logo" className="w-5 h-5" />
            </div>
            <div>
              <div className="mb-0.5 flex items-center gap-2">
                <BrainCircuit className="w-3 h-3 text-[var(--accent)]" />
                <h2 className="text-sm font-bold uppercase leading-none tracking-[0.2em]">
                  {getUiText(language, 'signalDigest')}
                </h2>
              </div>
              <p className="text-[10px] font-bold uppercase leading-none tracking-widest text-[var(--muted)]">
                {getUiText(language, 'lastDeepScan')}
                {formatClock(lastUpdated)}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-4">
            <button
              onClick={toggleLanguage}
              disabled={status === AppStatus.FETCHING || status === AppStatus.ANALYZING || status === AppStatus.TRANSLATING}
              className={`wf-button flex items-center gap-2 disabled:opacity-50 ${language === 'zh' ? 'bg-[var(--accent-muted)]' : 'bg-[var(--panel)]'}`}
            >
              <Languages className="w-3.5 h-3.5" />
              <span className="text-[10px] font-black uppercase tracking-widest">
                {language === 'en' ? getUiText(language, 'languageToggleEn') : getUiText(language, 'languageToggleZh')}
              </span>
            </button>

            <button
              onClick={refreshNews}
              disabled={status === AppStatus.FETCHING || status === AppStatus.ANALYZING || status === AppStatus.TRANSLATING}
              className="wf-button flex items-center gap-2 disabled:opacity-50"
            >
              <RefreshCcw className={`w-3.5 h-3.5 ${status === AppStatus.FETCHING || status === AppStatus.ANALYZING ? 'animate-spin' : ''}`} />
              <span className="hidden text-xs font-bold uppercase tracking-widest sm:inline">
                {getUiText(language, 'refresh')}
              </span>
            </button>
          </div>
        </header>

        {activeTab === 'map' && (
          <RelationshipGraph
            aiService={aiService}
            language={language}
            isActive={activeTab === 'map'}
          />
        )}

        {activeTab !== 'map' && (
        <div className="custom-scrollbar flex-1 min-h-0 overflow-y-auto">
          <div className="mx-auto max-w-5xl space-y-8 p-6">
            {activeTab === 'digest' && (
              <DailyDigestPage aiService={aiService} language={language} />
            )}

            {activeTab !== 'digest' && (
              <>
            {hasDigest ? (
              <>
                {activeTab === 'live' && (
                  <>
                    <section className="wf-reveal space-y-5 pt-4" style={{ '--delay': '0ms' } as React.CSSProperties}>
                      <div className="ct-segmented" role="group" aria-label={getUiText(language, 'contentFilters')}>
                        <div
                          className="ct-indicator"
                          style={{
                            '--ct-index': CONTENT_TABS.findIndex((tab) => tab.id === contentFilter),
                            '--ct-color': CONTENT_TABS.find((tab) => tab.id === contentFilter)?.color ?? 'var(--accent)',
                          } as React.CSSProperties}
                        />
                        {CONTENT_TABS.map((tab) => {
                          const active = contentFilter === tab.id;
                          const count = tab.id === 'all'
                            ? currentDigest?.items.length ?? 0
                            : currentDigest?.items.filter((item) => item.contentType === tab.id).length ?? 0;
                          return (
                            <button
                              key={tab.id}
                              type="button"
                              aria-pressed={active}
                              onClick={() => setContentFilter(tab.id)}
                              className={`ct-tab ${active ? 'ct-tab--active' : ''}`}
                              style={active ? ({ '--tab-color': tab.color } as React.CSSProperties) : undefined}
                            >
                              <span className="ct-tab-icon" style={active ? { color: tab.color } : undefined}>
                                {tab.icon}
                              </span>
                              <span className="ct-tab-label">{CONTENT_TYPE_LABELS[tab.id][language]}</span>
                              <span className={`ct-tab-count ${active ? 'ct-tab-count--active' : ''}`}>{count}</span>
                            </button>
                          );
                        })}
                      </div>
                    </section>

                    {showBreaking && currentDigest.breakingAlert && (
                      <div className="wf-reveal" style={{ '--delay': '120ms' } as React.CSSProperties}>
                        <BreakingAlert item={currentDigest.breakingAlert} language={language} />
                      </div>
                    )}

                    <div className="news-grid news-grid--wireframe grid grid-cols-1 gap-6 md:grid-cols-2">
                      {filteredItems.map((item, idx) => (
                        <div
                          key={item.id}
                          className={`wf-reveal ${idx === 0 ? 'md:col-span-2' : ''}`}
                          style={{ '--delay': `${150 + idx * 60}ms` } as React.CSSProperties}
                        >
                          <NewsCard item={item} language={language} featured={idx === 0} />
                        </div>
                      ))}
                      {filteredItems.length === 0 && (
                        <div className="col-span-2 wf-panel p-6 text-center text-[var(--muted)]">
                          {language === 'en'
                            ? 'No significant news today.'
                            : '今日暂无重要新闻。'}
                        </div>
                      )}
                    </div>
                  </>
                )}

                {activeTab === 'weekly' && (
                  <section className="wf-reveal space-y-6 pt-4" style={{ '--delay': '0ms' } as React.CSSProperties}>
                    <div className="flex flex-wrap items-center gap-2 text-[var(--ink)]">
                      <span className="wf-chip">{getUiText(language, 'weeklySignal')}</span>
                      <span className="wf-chip border-[var(--muted)] text-[var(--muted)]">{getUiText(language, 'topSignificance')}</span>
                      <span className="wf-chip">{getUiText(language, 'last7Days')}</span>
                    </div>
                    {weeklyTop.length === 0 ? (
                      <div className="wf-panel p-6 text-[var(--muted)]">
                        {getUiText(language, 'noWeeklyHighlights')}
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                        {weeklyTop.map((item, idx) => (
                          <div key={item.id} className="wf-reveal" style={{ '--delay': `${80 + idx * 60}ms` } as React.CSSProperties}>
                            <NewsCard item={item} language={language} />
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                )}

                <footer className="flex flex-col items-center gap-4 pb-12 pt-20 text-center text-[10px] font-bold uppercase tracking-[0.3em] opacity-60">
                  <div className="h-[2px] w-12 bg-[var(--ink)]"></div>
                  <span>{getUiText(language, 'curatingGlobalSignals')}</span>
                </footer>
              </>
            ) : (
              <div className="flex min-h-[70vh] flex-col items-center justify-center space-y-8 text-center">
                <div className="relative">
                  <div className="flex h-28 w-28 items-center justify-center rounded-full border-2 border-[var(--ink)] bg-[var(--panel)]">
                    <div className="absolute inset-0 animate-spin rounded-full border-t-2 border-[var(--accent)]"></div>
                    <img src="/logo.png" alt="Pebble Logo" className="w-12 h-12" />
                  </div>
                </div>
                <div className="space-y-4">
                  <div className="inline-flex items-center gap-2 wf-chip bg-[var(--panel)]">
                    <span className="h-2 w-2 rounded-full bg-[var(--accent)] animate-ping"></span>
                    <span>{status === AppStatus.TRANSLATING ? getUiText(language, 'processingLanguage') : getUiText(language, 'synthesizingDevelopments')}</span>
                  </div>
                  <h3 className="text-3xl font-black uppercase tracking-[0.2em]">
                    {status === AppStatus.FETCHING
                      ? getUiText(language, 'gatheringInsights')
                      : status === AppStatus.ANALYZING
                        ? getUiText(language, 'distillingSignal')
                        : status === AppStatus.TRANSLATING
                          ? getUiText(language, 'translatingDigest')
                          : status === AppStatus.ERROR
                            ? getUiText(language, 'signalDisruption')
                            : getUiText(language, 'initializingSystem')}
                  </h3>
                  <div className="mx-auto max-w-xs space-y-2 text-[11px] text-[var(--muted)]">
                    <p className="flex justify-between"><span>X/TWITTER:</span> <span className="text-[var(--accent)]">SCANNING</span></p>
                    <p className="flex justify-between"><span>REDDIT/LATEST:</span> <span className="text-[var(--accent)]">PARSING</span></p>
                    <p className="flex justify-between"><span>ARXIV/NEW:</span> <span className="text-[var(--accent)]">FETCHING</span></p>
                  </div>
                </div>
                {status === AppStatus.ERROR && (
                  <button onClick={refreshNews} className="wf-button">
                    {getUiText(language, 'reestablishUplink')}
                  </button>
                )}
              </div>
            )}
              </>
            )}
          </div>
        </div>
        )}
      </main>
    </div>
  );
};

export default App;
