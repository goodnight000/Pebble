import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type {
  Language,
  RelationshipGraphWindow,
  SignalMapCluster,
  SignalMapViewMode,
  TopicTrendItem,
} from '@/types';
import { AIService } from '@/services/aiService';
import SignalMapCanvas from '@/components/SignalMapCanvas';
import RelationshipGraphCanvasV2 from '@/components/RelationshipGraphCanvasV2';
import RelationshipGraphPanel from '@/components/RelationshipGraphPanel';
import TopicSidebar from '@/components/TopicSidebar';
import ClusterDrawer from '@/components/ClusterDrawer';
import SignalMapList from '@/components/SignalMapList';
import { RefreshCcw } from 'lucide-react';
import { getUiText } from '@/i18n';
import {
  buildRelationshipGraph,
  DEFAULT_SIGNAL_MAP_VIEW_MODE,
  RELATIONSHIP_GRAPH_WINDOW_HOURS,
  RELATIONSHIP_GRAPH_WINDOWS,
  resolveVisibleGraphError,
  SIGNAL_MAP_VIEW_MODES,
} from '@/components/relationshipGraph';

interface SignalMapProps {
  aiService: AIService;
  language: Language;
  isActive: boolean;
}

const useMediaQuery = (query: string): boolean => {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false,
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
};

interface SignalMapSnapshot {
  clusters: SignalMapCluster[];
  projectionSeed: string;
  generatedAt: string;
}

const SignalMap: React.FC<SignalMapProps> = ({ aiService, language, isActive }) => {
  const [clusters, setClusters] = useState<SignalMapCluster[]>([]);
  const [topicTrends, setTopicTrends] = useState<TopicTrendItem[]>([]);
  const [projectionSeed, setProjectionSeed] = useState('');
  const [viewMode, setViewMode] = useState<SignalMapViewMode>(DEFAULT_SIGNAL_MAP_VIEW_MODE);
  const [graphWindow, setGraphWindow] = useState<RelationshipGraphWindow>('7d');
  const [graphSnapshots, setGraphSnapshots] = useState<Partial<Record<RelationshipGraphWindow, SignalMapSnapshot>>>({});
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);
  const [mapLoading, setMapLoading] = useState(false);
  const [graphLoading, setGraphLoading] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [graphErrors, setGraphErrors] = useState<Partial<Record<RelationshipGraphWindow, string | null>>>({});

  const isDesktop = useMediaQuery('(min-width: 1024px)');

  const fetchData = useCallback(async () => {
    setMapLoading(true);
    setMapError(null);
    try {
      const [mapData, trendsData] = await Promise.all([
        aiService.fetchSignalMap(48, language),
        aiService.fetchTopicTrends(language),
      ]);
      setClusters(mapData.clusters);
      setProjectionSeed(mapData.projectionSeed);
      setTopicTrends(trendsData.topics);
    } catch (err) {
      console.error('Failed to fetch signal map data', err);
      setMapError(getUiText(language, 'signalMapError'));
    } finally {
      setMapLoading(false);
    }
  }, [aiService, language]);

  const fetchGraphSnapshot = useCallback(async (window: RelationshipGraphWindow) => {
    setGraphLoading(true);
    setGraphErrors((current) => ({
      ...current,
      [window]: null,
    }));
    try {
      const hours = RELATIONSHIP_GRAPH_WINDOW_HOURS[window];
      const graphData = await aiService.fetchSignalMap(hours, language);
      setGraphSnapshots((current) => ({
        ...current,
        [window]: {
          clusters: graphData.clusters,
          projectionSeed: graphData.projectionSeed,
          generatedAt: graphData.generatedAt,
        },
      }));
      setGraphErrors((current) => ({
        ...current,
        [window]: null,
      }));
    } catch (err) {
      console.error('Failed to fetch relationship graph data', err);
      setGraphErrors((current) => ({
        ...current,
        [window]: getUiText(language, 'relationshipGraphError'),
      }));
    } finally {
      setGraphLoading(false);
    }
  }, [aiService, language]);

  // Fetch on mount and when tab becomes active
  useEffect(() => {
    if (isActive) {
      fetchData();
    }
  }, [isActive, fetchData]);

  useEffect(() => {
    setGraphSnapshots({});
    setGraphErrors({});
  }, [language]);

  useEffect(() => {
    if (!isActive || viewMode !== 'graph' || graphSnapshots[graphWindow]) {
      return;
    }
    void fetchGraphSnapshot(graphWindow);
  }, [fetchGraphSnapshot, graphSnapshots, graphWindow, isActive, viewMode]);

  const handleSelectCluster = useCallback((id: string) => {
    setSelectedClusterId((prev) => (prev === id ? null : id));
  }, []);

  const handleCloseDrawer = useCallback(() => {
    setSelectedClusterId(null);
  }, []);

  // Close drawer on outside click (only relevant for desktop)
  const handleCanvasClick = useCallback((e: React.MouseEvent) => {
    if (viewMode === 'graph') {
      return;
    }

    const target = e.target as HTMLElement;

    // Only close if clicking the visualization background, not an interactive node.
    if (target.tagName === 'svg' || target.tagName === 'CANVAS') {
      setSelectedClusterId(null);
    }
  }, [viewMode]);

  const activeGraphSnapshot = graphSnapshots[graphWindow];
  const activeClusters = viewMode === 'graph'
    ? activeGraphSnapshot?.clusters ?? []
    : clusters;
  const selectedCluster = useMemo(
    () => activeClusters.find((cluster) => cluster.id === selectedClusterId) ?? null,
    [activeClusters, selectedClusterId],
  );
  const graphPanelOpen = viewMode === 'graph' && Boolean(selectedClusterId) && Boolean(selectedCluster);
  const activeGraphError = resolveVisibleGraphError(graphWindow, graphSnapshots, graphErrors);
  const relationshipGraph = useMemo(
    () => buildRelationshipGraph({
      clusters: activeGraphSnapshot?.clusters ?? [],
      window: graphWindow,
      generatedAt: activeGraphSnapshot?.generatedAt ?? new Date().toISOString(),
    }),
    [activeGraphSnapshot?.clusters, activeGraphSnapshot?.generatedAt, graphWindow],
  );

  const loading = mapLoading || graphLoading;
  const graphModeLoading = viewMode === 'graph' && !activeGraphSnapshot && graphLoading;
  const mapModeLabelKey = viewMode === 'map' ? 'signalMap' : 'relationshipGraph';
  const graphRefresh = useCallback(() => {
    if (viewMode === 'graph') {
      void fetchGraphSnapshot(graphWindow);
      return;
    }
    void fetchData();
  }, [fetchData, fetchGraphSnapshot, graphWindow, viewMode]);

  if (mapLoading && clusters.length === 0) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <div className="h-12 w-12 rounded-full border-2 border-[var(--ink)] border-t-[var(--accent)] animate-spin" />
        <span className="text-xs font-bold uppercase tracking-widest text-[var(--muted)]">
          {getUiText(language, 'signalMapLoading')}
        </span>
      </div>
    );
  }

  if (mapError && clusters.length === 0) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <span className="text-sm text-[var(--muted)]">{mapError}</span>
        <button onClick={viewMode === 'graph' ? () => void fetchGraphSnapshot(graphWindow) : fetchData} className="wf-button flex items-center gap-2">
          <RefreshCcw className="w-3.5 h-3.5" />
          <span className="text-xs font-bold uppercase tracking-widest">
            {getUiText(language, 'retry')}
          </span>
        </button>
      </div>
    );
  }

  // Mobile: ranked list
  if (!isDesktop) {
    return (
      <div className="p-4">
        <div className="signal-map-mobile-header">
          <span className="wf-chip">{getUiText(language, mapModeLabelKey)}</span>
          <div className="signal-map-toggle" role="group" aria-label={getUiText(language, 'signalMapViewMode')}>
            {SIGNAL_MAP_VIEW_MODES.map((mode) => (
              <button
                key={mode}
                type="button"
                className={`signal-map-toggle__button${viewMode === mode ? ' signal-map-toggle__button--active' : ''}`}
                onClick={() => {
                  setViewMode(mode);
                  setSelectedClusterId(null);
                }}
              >
                {getUiText(language, mode === 'map' ? 'signalMap' : 'relationshipGraph')}
              </button>
            ))}
          </div>
          <button
            onClick={graphRefresh}
            disabled={loading}
            className="wf-button flex items-center gap-2 disabled:opacity-50"
          >
            <RefreshCcw className={`w-3.5 h-3.5 ${viewMode === 'graph' ? (graphLoading ? 'animate-spin' : '') : (mapLoading ? 'animate-spin' : '')}`} />
          </button>
        </div>
        {viewMode === 'graph' && (
          <div className="signal-map-mobile-window" role="group" aria-label={getUiText(language, 'relationshipGraphWindow')}>
            {RELATIONSHIP_GRAPH_WINDOWS.map((window) => (
              <button
                key={window}
                type="button"
                className={`signal-map-window-button${graphWindow === window ? ' signal-map-window-button--active' : ''}`}
                onClick={() => setGraphWindow(window)}
              >
                {window.toUpperCase()}
              </button>
            ))}
          </div>
        )}
        {viewMode === 'map' ? (
          <>
            <SignalMapList
              clusters={clusters}
              onSelectCluster={handleSelectCluster}
              language={language}
            />
            <ClusterDrawer
              cluster={selectedCluster}
              onClose={handleCloseDrawer}
              language={language}
            />
          </>
        ) : (
          <div className="signal-map-mobile-graph">
            {graphModeLoading ? (
              <div className="relationship-graph-loading">
                {getUiText(language, 'relationshipGraphLoading')}
              </div>
            ) : activeGraphError ? (
              <div className="relationship-graph-loading relationship-graph-loading--error">
                {activeGraphError}
              </div>
            ) : (
              <RelationshipGraphCanvasV2
                graph={relationshipGraph}
                selectedClusterId={selectedClusterId}
                onSelectCluster={handleSelectCluster}
                language={language}
              />
            )}
          </div>
        )}
      </div>
    );
  }

  // Desktop: full layout
  return (
    <div className={`signal-map-layout${viewMode === 'graph' ? ' signal-map-layout--graph' : ''}`} style={{ height: 'calc(100vh - 65px)' }}>
      {viewMode === 'map' && <TopicSidebar topics={topicTrends} language={language} />}
      <div
        className={[
          'signal-map-canvas',
          viewMode === 'graph' ? 'signal-map-canvas--graph' : '',
          graphPanelOpen ? 'signal-map-canvas--graph-panel-open' : '',
        ].filter(Boolean).join(' ')}
        onClick={handleCanvasClick}
        style={{ position: 'relative' }}
      >
        <div className="signal-map-hud">
          <div className="signal-map-hud__copy">
            <div className="signal-map-hud__meta">
              <span className="wf-chip">{getUiText(language, mapModeLabelKey)}</span>
              <div className="signal-map-toggle" role="group" aria-label={getUiText(language, 'signalMapViewMode')}>
                {SIGNAL_MAP_VIEW_MODES.map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className={`signal-map-toggle__button${viewMode === mode ? ' signal-map-toggle__button--active' : ''}`}
                    onClick={() => {
                      setViewMode(mode);
                      setSelectedClusterId(null);
                    }}
                  >
                    {getUiText(language, mode === 'map' ? 'signalMap' : 'relationshipGraph')}
                  </button>
                ))}
              </div>
              {viewMode === 'graph' && (
                <div className="signal-map-window-group" role="group" aria-label={getUiText(language, 'relationshipGraphWindow')}>
                  {RELATIONSHIP_GRAPH_WINDOWS.map((window) => (
                    <button
                      key={window}
                      type="button"
                      className={`signal-map-window-button${graphWindow === window ? ' signal-map-window-button--active' : ''}`}
                      onClick={() => setGraphWindow(window)}
                    >
                      {window.toUpperCase()}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="signal-map-hud__legend">
              {viewMode === 'map' ? (
                <>
                  <span className="signal-map-hud__legend-item">
                    <span className="signal-map-hud__legend-scale" aria-hidden="true">
                      <span className="signal-map-hud__legend-scale-dot signal-map-hud__legend-scale-dot--sm" />
                      <span className="signal-map-hud__legend-scale-dot signal-map-hud__legend-scale-dot--lg" />
                    </span>
                    {getUiText(language, 'coverage')}
                  </span>
                  <span className="signal-map-hud__legend-item">
                    <span className="signal-map-hud__legend-velocity" aria-hidden="true">
                      <span className="signal-map-hud__legend-velocity-core" />
                      <span className="signal-map-hud__legend-velocity-ring" />
                    </span>
                    {getUiText(language, 'velocity')}
                  </span>
                </>
              ) : (
                <>
                  <span className="signal-map-hud__legend-item signal-map-hud__legend-item--edge">
                    <span className="signal-map-hud__legend-line signal-map-hud__legend-line--shared-entity" aria-hidden="true" />
                    {getUiText(language, 'graphSharedEntity')}
                  </span>
                  <span className="signal-map-hud__legend-item signal-map-hud__legend-item--edge">
                    <span className="signal-map-hud__legend-line signal-map-hud__legend-line--event-chain" aria-hidden="true" />
                    {getUiText(language, 'graphEventChain')}
                  </span>
                  <span className="signal-map-hud__legend-item signal-map-hud__legend-item--edge">
                    <span className="signal-map-hud__legend-line signal-map-hud__legend-line--market-adjacency" aria-hidden="true" />
                    {getUiText(language, 'graphMarketAdjacency')}
                  </span>
                </>
              )}
            </div>
          </div>
          <button
            onClick={graphRefresh}
            disabled={loading}
            className="wf-button flex items-center gap-2 disabled:opacity-50 signal-map-hud__refresh"
          >
            <RefreshCcw className={`w-3.5 h-3.5 ${viewMode === 'graph' ? (graphLoading ? 'animate-spin' : '') : (mapLoading ? 'animate-spin' : '')}`} />
            <span className="text-[10px] font-bold uppercase tracking-widest">
              {getUiText(language, 'refresh')}
            </span>
          </button>
        </div>
        {viewMode === 'map' ? (
          <SignalMapCanvas
            clusters={clusters}
            projectionSeed={projectionSeed}
            selectedClusterId={selectedClusterId}
            onSelectCluster={handleSelectCluster}
            language={language}
          />
        ) : graphModeLoading ? (
          <div className="relationship-graph-loading">
            {getUiText(language, 'relationshipGraphLoading')}
          </div>
        ) : activeGraphError ? (
          <div className="relationship-graph-loading relationship-graph-loading--error">
            {activeGraphError}
          </div>
        ) : (
          <RelationshipGraphCanvasV2
            graph={relationshipGraph}
            selectedClusterId={selectedClusterId}
            onSelectCluster={handleSelectCluster}
            language={language}
          />
        )}
      </div>
      {viewMode === 'map' && (
        <ClusterDrawer
          cluster={selectedCluster}
          onClose={handleCloseDrawer}
          language={language}
        />
      )}
      {viewMode === 'graph' && graphPanelOpen && (
        <RelationshipGraphPanel
          cluster={selectedCluster}
          graph={relationshipGraph}
          language={language}
          onClose={handleCloseDrawer}
        />
      )}
    </div>
  );
};

export default SignalMap;
