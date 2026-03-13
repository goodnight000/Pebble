import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type {
  Language,
  RelationshipGraphWindow,
  SignalMapCluster,
  SignalMapEdge,
} from '@/types';
import { AIService } from '@/services/aiService';
import RelationshipGraphCanvasV2 from '@/components/RelationshipGraphCanvasV2';
import RelationshipGraphPanel from '@/components/RelationshipGraphPanel';
import { RefreshCcw } from 'lucide-react';
import { getUiText } from '@/i18n';
import {
  buildRelationshipGraph,
  RELATIONSHIP_GRAPH_WINDOW_HOURS,
  RELATIONSHIP_GRAPH_WINDOWS,
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

interface GraphSnapshot {
  clusters: SignalMapCluster[];
  edges?: SignalMapEdge[];
  projectionSeed: string;
  generatedAt: string;
}

const SignalMap: React.FC<SignalMapProps> = ({ aiService, language, isActive }) => {
  const [graphWindow, setGraphWindow] = useState<RelationshipGraphWindow>('7d');
  const [graphSnapshots, setGraphSnapshots] = useState<Partial<Record<RelationshipGraphWindow, GraphSnapshot>>>({});
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphErrors, setGraphErrors] = useState<Partial<Record<RelationshipGraphWindow, string | null>>>({});

  const isDesktop = useMediaQuery('(min-width: 1024px)');

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
          edges: graphData.edges,
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

  useEffect(() => {
    setGraphSnapshots({});
    setGraphErrors({});
  }, [language]);

  useEffect(() => {
    if (!isActive || graphSnapshots[graphWindow]) {
      return;
    }
    void fetchGraphSnapshot(graphWindow);
  }, [fetchGraphSnapshot, graphSnapshots, graphWindow, isActive]);

  const handleSelectCluster = useCallback((id: string) => {
    setSelectedClusterId((prev) => (prev === id ? null : id));
  }, []);

  const handleClosePanel = useCallback(() => {
    setSelectedClusterId(null);
  }, []);

  const activeGraphSnapshot = graphSnapshots[graphWindow];
  const activeClusters = activeGraphSnapshot?.clusters ?? [];
  const selectedCluster = useMemo(
    () => activeClusters.find((cluster) => cluster.id === selectedClusterId) ?? null,
    [activeClusters, selectedClusterId],
  );
  const graphPanelOpen = Boolean(selectedClusterId) && Boolean(selectedCluster);
  const activeGraphError = (() => {
    if (activeGraphSnapshot) return null;
    return graphErrors[graphWindow] ?? null;
  })();
  const relationshipGraph = useMemo(
    () => buildRelationshipGraph({
      clusters: activeGraphSnapshot?.clusters ?? [],
      window: graphWindow,
      generatedAt: activeGraphSnapshot?.generatedAt ?? new Date().toISOString(),
      serverEdges: activeGraphSnapshot?.edges,
    }),
    [activeGraphSnapshot?.clusters, activeGraphSnapshot?.edges, activeGraphSnapshot?.generatedAt, graphWindow],
  );

  const graphModeLoading = !activeGraphSnapshot && graphLoading;

  const graphRefresh = useCallback(() => {
    void fetchGraphSnapshot(graphWindow);
  }, [fetchGraphSnapshot, graphWindow]);

  if (!activeGraphSnapshot && graphLoading) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <div className="h-12 w-12 rounded-full border-2 border-[var(--ink)] border-t-[var(--accent)] animate-spin" />
        <span className="text-xs font-bold uppercase tracking-widest text-[var(--muted)]">
          {getUiText(language, 'relationshipGraphLoading')}
        </span>
      </div>
    );
  }

  if (activeGraphError && !activeGraphSnapshot) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <span className="text-sm text-[var(--muted)]">{activeGraphError}</span>
        <button onClick={graphRefresh} className="wf-button flex items-center gap-2">
          <RefreshCcw className="w-3.5 h-3.5" />
          <span className="text-xs font-bold uppercase tracking-widest">
            {getUiText(language, 'retry')}
          </span>
        </button>
      </div>
    );
  }

  // Mobile layout
  if (!isDesktop) {
    return (
      <div className="p-4">
        <div className="signal-map-mobile-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
            <span className="wf-chip">{getUiText(language, 'relationshipGraph')}</span>
          </div>
          <button
            onClick={graphRefresh}
            disabled={graphLoading}
            className="wf-button flex items-center gap-2 disabled:opacity-50"
          >
            <RefreshCcw className={`w-3.5 h-3.5 ${graphLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
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
      </div>
    );
  }

  // Desktop layout
  return (
    <div className="signal-map-layout signal-map-layout--graph" style={{ height: 'calc(100vh - 65px)' }}>
      <div
        className={[
          'signal-map-canvas signal-map-canvas--graph',
          graphPanelOpen ? 'signal-map-canvas--graph-panel-open' : '',
        ].filter(Boolean).join(' ')}
        style={{ position: 'relative' }}
      >
        <div className="signal-map-hud">
          <div className="signal-map-hud__copy">
            <div className="signal-map-hud__meta">
              <span className="wf-chip">{getUiText(language, 'relationshipGraph')}</span>
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
            </div>
            <div className="signal-map-hud__legend">
              <span className="signal-map-hud__legend-item signal-map-hud__legend-item--edge">
                <span className="signal-map-hud__legend-line signal-map-hud__legend-line--follow-up" aria-hidden="true" />
                {getUiText(language, 'graphFollowUp')}
              </span>
              <span className="signal-map-hud__legend-item signal-map-hud__legend-item--edge">
                <span className="signal-map-hud__legend-line signal-map-hud__legend-line--reaction" aria-hidden="true" />
                {getUiText(language, 'graphReaction')}
              </span>
              <span className="signal-map-hud__legend-item signal-map-hud__legend-item--edge">
                <span className="signal-map-hud__legend-line signal-map-hud__legend-line--competing" aria-hidden="true" />
                {getUiText(language, 'graphCompeting')}
              </span>
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
            </div>
          </div>
          {graphLoading && (
            <span className="signal-map-hud__loading" aria-label={getUiText(language, 'relationshipGraphLoading')}>
              <RefreshCcw className="w-3.5 h-3.5 animate-spin text-[var(--muted)]" />
            </span>
          )}
        </div>
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
      {graphPanelOpen && (
        <RelationshipGraphPanel
          cluster={selectedCluster}
          graph={relationshipGraph}
          language={language}
          onClose={handleClosePanel}
        />
      )}
    </div>
  );
};

export default SignalMap;
