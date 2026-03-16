import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { drag, easeCubicOut, select, zoom, zoomIdentity } from 'd3';
import type { D3DragEvent, ZoomBehavior, ZoomTransform } from 'd3';
import type { Language, RelationshipGraphResponse } from '@/types';
import {
  type RelationshipGraphPosition,
  applyRelationshipGraphPositionOverrides,
  buildLocalNeighborhood,
  buildRelationshipGraphVisuals,
  computeGraphViewport,
  mergeRelationshipGraphPositionOverrides,
  pickVisibleNodeLabels,
  projectRelationshipGraphLayout,
  resolveRelationshipGraphEdgeTier,
  resolveRelationshipGraphZoomLevel,
} from '@/lib/relationshipGraph';
import { getTrustLabel, getUiText } from '@/i18n';

interface RelationshipGraphCanvasV2Props {
  graph: RelationshipGraphResponse;
  selectedClusterId: string | null;
  onSelectCluster: (id: string) => void;
  language: Language;
}

const GRAPH_PADDING = 76;
const LAYOUT_SCALE = 2.0;

function resolveNodeRadius(importance: number): number {
  return 10 + importance * 20;
}

const RelationshipGraphCanvasV2: React.FC<RelationshipGraphCanvasV2Props> = ({
  graph,
  selectedClusterId,
  onSelectCluster,
  language,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const nodeElementRefs = useRef(new Map<string, HTMLButtonElement>());
  const zoomBehaviorRef = useRef<ZoomBehavior<HTMLDivElement, unknown> | null>(null);
  const viewTransformRef = useRef<ZoomTransform>(zoomIdentity);
  const projectedPositionsRef = useRef<Map<string, RelationshipGraphPosition>>(new Map());
  const [dimensions, setDimensions] = useState({ width: 960, height: 620 });
  const [hoveredClusterId, setHoveredClusterId] = useState<string | null>(null);
  const [draggedClusterId, setDraggedClusterId] = useState<string | null>(null);
  const [positionOverrides, setPositionOverrides] = useState<Record<string, RelationshipGraphPosition>>({});
  const [viewTransform, setViewTransform] = useState<ZoomTransform>(zoomIdentity);
  const edgeOpacitiesRef = useRef(new Map<string, number>());
  const edgeRafRef = useRef(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return undefined;
    }

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setDimensions({ width, height });
        }
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const visuals = useMemo(
    () => buildRelationshipGraphVisuals(graph.nodes),
    [graph.nodes],
  );

  const positions = useMemo(
    () => projectRelationshipGraphLayout(graph.nodes, {
      width: dimensions.width * LAYOUT_SCALE,
      height: dimensions.height * LAYOUT_SCALE,
      padding: GRAPH_PADDING * LAYOUT_SCALE,
      edges: graph.edges,
    }),
    [dimensions.height, dimensions.width, graph.nodes, graph.edges],
  );

  const projectedPositions = useMemo(
    () => applyRelationshipGraphPositionOverrides(positions, positionOverrides),
    [positionOverrides, positions],
  );

  const baseViewport = useMemo(
    () => computeGraphViewport(positions, {
      width: dimensions.width,
      height: dimensions.height,
      padding: GRAPH_PADDING,
    }),
    [dimensions.height, dimensions.width, positions],
  );

  const fitViewport = useMemo(
    () => computeGraphViewport(projectedPositions, {
      width: dimensions.width,
      height: dimensions.height,
      padding: GRAPH_PADDING,
    }),
    [dimensions.height, dimensions.width, projectedPositions],
  );

  const zoomLevel = useMemo(
    () => resolveRelationshipGraphZoomLevel(viewTransform.k),
    [viewTransform.k],
  );

  const focusClusterId = hoveredClusterId ?? selectedClusterId;
  const focusNeighborhood = useMemo(
    () => (
      focusClusterId
        ? buildLocalNeighborhood(focusClusterId, graph.edges, { maxEdges: 8 })
        : null
    ),
    [focusClusterId, graph.edges],
  );

  const visibleLabelIds = useMemo(
    () => new Set(pickVisibleNodeLabels(graph.nodes, visuals, {
      zoomLevel,
      selectedNodeIds: selectedClusterId ? [selectedClusterId] : [],
      focusedNodeIds: focusNeighborhood ? [...focusNeighborhood.nodeIds] : (hoveredClusterId ? [hoveredClusterId] : []),
    })),
    [focusNeighborhood, graph.nodes, hoveredClusterId, selectedClusterId, visuals, zoomLevel],
  );

  useEffect(() => {
    setPositionOverrides({});
  }, [graph.generatedAt, graph.window]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return undefined;
    }

    const zoomBehavior = zoom<HTMLDivElement, unknown>()
      .scaleExtent([0.15, 10])
      .filter((event) => {
        const target = event.target as HTMLElement | null;
        if (!target) {
          return true;
        }

        if (event.type === 'wheel') {
          return true;
        }

        return !target.closest('button');
      })
      .on('zoom', (event) => {
        setViewTransform(event.transform);
      });

    zoomBehaviorRef.current = zoomBehavior;
    const selection = select(container);
    selection.call(zoomBehavior);

    return () => {
      selection.on('.zoom', null);
    };
  }, []);

  useEffect(() => {
    viewTransformRef.current = viewTransform;
  }, [viewTransform]);

  useEffect(() => {
    projectedPositionsRef.current = projectedPositions;
  }, [projectedPositions]);

  useEffect(() => {
    const container = containerRef.current;
    const zoomBehavior = zoomBehaviorRef.current;

    if (!container || !zoomBehavior) {
      return;
    }

    select(container).call(
      zoomBehavior.transform,
      zoomIdentity.translate(baseViewport.translateX, baseViewport.translateY).scale(baseViewport.scale),
    );
  }, [baseViewport.scale, baseViewport.translateX, baseViewport.translateY, graph.generatedAt, graph.window]);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay) {
      return undefined;
    }

    const cleanupCallbacks: Array<() => void> = [];
    const dragBehavior = drag<HTMLButtonElement, string>()
      .container(() => overlay)
      .subject((_, nodeId) => {
        const position = projectedPositionsRef.current.get(nodeId);
        const transform = viewTransformRef.current;
        return {
          x: position ? position.x * transform.k + transform.x : 0,
          y: position ? position.y * transform.k + transform.y : 0,
        };
      })
      .on('start', (event: D3DragEvent<HTMLButtonElement, string, { x: number; y: number }>, nodeId) => {
        event.sourceEvent.stopPropagation();
        setDraggedClusterId(nodeId);
        setHoveredClusterId(nodeId);
      })
      .on('drag', (event: D3DragEvent<HTMLButtonElement, string, { x: number; y: number }>, nodeId) => {
        const transform = viewTransformRef.current;
        const worldX = (event.x - transform.x) / transform.k;
        const worldY = (event.y - transform.y) / transform.k;

        setPositionOverrides((current) => mergeRelationshipGraphPositionOverrides(current, nodeId, {
          x: worldX,
          y: worldY,
        }));
      })
      .on('end', () => {
        setDraggedClusterId(null);
      });

    for (const [nodeId, element] of nodeElementRefs.current.entries()) {
      const selection = select(element).datum(nodeId);
      selection.call(dragBehavior);
      cleanupCallbacks.push(() => selection.on('.drag', null));
    }

    return () => {
      cleanupCallbacks.forEach((callback) => callback());
    };
  }, [graph.nodes]);

  const drawEdges = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return false;

    const context = canvas.getContext('2d');
    if (!context) return false;

    const dpr = window.devicePixelRatio || 1;
    const w = dimensions.width;
    const h = dimensions.height;
    canvas.width = Math.max(1, Math.floor(w * dpr));
    canvas.height = Math.max(1, Math.floor(h * dpr));
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;

    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, w, h);

    context.save();
    context.translate(viewTransform.x, viewTransform.y);
    context.scale(viewTransform.k, viewTransform.k);
    context.lineCap = 'round';

    const inverseScale = 1 / viewTransform.k;
    const focusedEdgeIds = focusNeighborhood ? focusNeighborhood.edges.map((c) => c.id) : [];
    const focusedNodeIds = focusClusterId ? [focusClusterId] : [];
    let needsAnotherFrame = false;

    for (const edge of graph.edges) {
      const source = projectedPositions.get(edge.source);
      const target = projectedPositions.get(edge.target);
      if (!source || !target) continue;

      const tier = resolveRelationshipGraphEdgeTier(edge, { focusedEdgeIds, focusedNodeIds });
      const targetAlpha = tier === 'hidden' ? 0 : tier === 'focused' ? 0.92 : 0.42;
      const targetWidth = tier === 'focused' ? 2.4 : 1.4;
      const currentAlpha = edgeOpacitiesRef.current.get(edge.id) ?? targetAlpha;
      const diff = targetAlpha - currentAlpha;
      const lerpedAlpha = Math.abs(diff) < 0.01 ? targetAlpha : currentAlpha + diff * 0.14;
      edgeOpacitiesRef.current.set(edge.id, lerpedAlpha);

      if (Math.abs(lerpedAlpha - targetAlpha) > 0.01) {
        needsAnotherFrame = true;
      }

      if (lerpedAlpha < 0.01) continue;

      context.beginPath();
      context.moveTo(source.x, source.y);
      context.lineTo(target.x, target.y);

      if (edge.type === 'follow-up') {
        context.setLineDash([14 * inverseScale, 6 * inverseScale]);
      } else if (edge.type === 'reaction') {
        context.setLineDash([6 * inverseScale, 4 * inverseScale, 14 * inverseScale, 4 * inverseScale]);
      } else if (edge.type === 'competing') {
        context.setLineDash([3 * inverseScale, 6 * inverseScale]);
      } else if (edge.type === 'event-chain') {
        context.setLineDash([10 * inverseScale, 8 * inverseScale]);
      } else if (edge.type === 'market-adjacency') {
        context.setLineDash([4 * inverseScale, 10 * inverseScale]);
      } else {
        context.setLineDash([]);
      }

      context.lineWidth = targetWidth * inverseScale;
      context.globalAlpha = lerpedAlpha;
      context.strokeStyle = edge.type === 'follow-up'
        ? 'rgba(34, 139, 230, 0.86)'
        : edge.type === 'reaction'
          ? 'rgba(168, 85, 247, 0.86)'
          : edge.type === 'competing'
            ? 'rgba(239, 68, 68, 0.86)'
            : edge.type === 'event-chain'
              ? 'rgba(255, 106, 0, 0.86)'
              : edge.type === 'market-adjacency'
                ? 'rgba(17, 17, 17, 0.26)'
                : 'rgba(17, 17, 17, 0.72)';
      context.stroke();
    }

    context.restore();
    context.setLineDash([]);
    context.globalAlpha = 1;

    return needsAnotherFrame;
  }, [dimensions.height, dimensions.width, focusClusterId, focusNeighborhood, graph.edges, projectedPositions, viewTransform.k, viewTransform.x, viewTransform.y]);

  useEffect(() => {
    cancelAnimationFrame(edgeRafRef.current);

    const animate = () => {
      const needsMore = drawEdges();
      if (needsMore) {
        edgeRafRef.current = requestAnimationFrame(animate);
      }
    };

    edgeRafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(edgeRafRef.current);
  }, [drawEdges]);

  const visibleEdgeIds = useMemo(
    () => graph.edges
      .filter((edge) => resolveRelationshipGraphEdgeTier(edge, {
        focusedEdgeIds: focusNeighborhood ? focusNeighborhood.edges.map((candidate) => candidate.id) : [],
        focusedNodeIds: focusClusterId ? [focusClusterId] : [],
      }) !== 'hidden')
      .map((edge) => edge.id),
    [focusClusterId, focusNeighborhood, graph.edges],
  );

  const applyZoomFactor = (factor: number) => {
    const container = containerRef.current;
    const zoomBehavior = zoomBehaviorRef.current;

    if (!container || !zoomBehavior) {
      return;
    }

    select(container)
      .transition()
      .duration(350)
      .ease(easeCubicOut)
      .call(zoomBehavior.scaleBy as any, factor);
  };

  const fitGraph = () => {
    const container = containerRef.current;
    const zoomBehavior = zoomBehaviorRef.current;

    if (!container || !zoomBehavior) {
      return;
    }

    select(container)
      .transition()
      .duration(600)
      .ease(easeCubicOut)
      .call(
        zoomBehavior.transform as any,
        zoomIdentity.translate(baseViewport.translateX, baseViewport.translateY).scale(baseViewport.scale),
      );
  };

  const fitCurrentGraph = () => {
    const container = containerRef.current;
    const zoomBehavior = zoomBehaviorRef.current;

    if (!container || !zoomBehavior) {
      return;
    }

    select(container)
      .transition()
      .duration(600)
      .ease(easeCubicOut)
      .call(
        zoomBehavior.transform as any,
        zoomIdentity.translate(fitViewport.translateX, fitViewport.translateY).scale(fitViewport.scale),
      );
  };

  if (graph.nodes.length === 0) {
    return (
      <div className="relationship-graph relationship-graph--empty wf-outline">
        <p className="relationship-graph-empty-copy">
          {getUiText(language, 'relationshipGraphEmpty')}
        </p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relationship-graph relationship-graph-v2"
      data-testid="relationship-graph-canvas"
      data-renderer="v2"
      data-scale={viewTransform.k.toFixed(3)}
      data-window={graph.window}
    >
      <div className="relationship-graph-v2__controls wf-panel" role="toolbar" aria-label={getUiText(language, 'relationshipGraph')}>
        <button type="button" className="relationship-graph-v2__control" aria-label="Zoom in" onClick={() => applyZoomFactor(1.2)}>
          +
        </button>
        <button type="button" className="relationship-graph-v2__control" aria-label="Zoom out" onClick={() => applyZoomFactor(1 / 1.2)}>
          -
        </button>
        <button type="button" className="relationship-graph-v2__control relationship-graph-v2__control--wide" aria-label="Reset view" onClick={fitGraph}>
          Reset
        </button>
        <button type="button" className="relationship-graph-v2__control relationship-graph-v2__control--wide" aria-label="Fit graph" onClick={fitCurrentGraph}>
          Fit
        </button>
      </div>
      <canvas
        ref={canvasRef}
        className="relationship-graph-v2__canvas"
        aria-hidden="true"
      />
      <div className="relationship-graph-v2__edge-markers" aria-hidden="true">
        {visibleEdgeIds.map((edgeId) => (
          <span key={edgeId} data-testid={`graph-edge-${edgeId}`} />
        ))}
      </div>
      <div ref={overlayRef} className="relationship-graph-v2__overlay">
        {graph.nodes.map((node) => {
          const position = projectedPositions.get(node.id);
          const visual = visuals.get(node.id);

          if (!position || !visual) {
            return null;
          }

          const isSelected = selectedClusterId === node.id;
          const isHovered = hoveredClusterId === node.id;
          const showLabel = visibleLabelIds.has(node.id);
          const radius = resolveNodeRadius(node.importance);
          const screenX = position.x * viewTransform.k + viewTransform.x;
          const screenY = position.y * viewTransform.k + viewTransform.y;

          return (
            <button
              key={node.id}
              type="button"
              className={[
                'relationship-graph-v2__node',
                isSelected ? 'relationship-graph-v2__node--selected' : '',
                isHovered ? 'relationship-graph-v2__node--hovered' : '',
                focusNeighborhood?.nodeIds.has(node.id) ? 'relationship-graph-v2__node--context' : '',
                draggedClusterId === node.id ? 'relationship-graph-v2__node--dragging' : '',
              ].filter(Boolean).join(' ')}
              data-testid={`graph-node-${node.id}`}
              data-screen-x={screenX.toFixed(2)}
              data-screen-y={screenY.toFixed(2)}
              aria-pressed={isSelected ? 'true' : 'false'}
              aria-label={`${node.headline}, ${node.coverageCount} ${getUiText(language, 'articles')}, ${getTrustLabel(language, node.trustLabel)}`}
              ref={(element) => {
                if (element) {
                  nodeElementRefs.current.set(node.id, element);
                  return;
                }
                nodeElementRefs.current.delete(node.id);
              }}
              style={{
                left: `${screenX}px`,
                top: `${screenY}px`,
                width: `${radius * 2 + 18}px`,
                height: `${radius * 2 + 18}px`,
                zIndex: isHovered || isSelected ? 100 : undefined,
                ['--relationship-node-accent' as string]: `var(${visual.topicColorToken}, var(--accent))`,
              }}
              onClick={() => onSelectCluster(node.id)}
              onMouseEnter={() => setHoveredClusterId(node.id)}
              onMouseLeave={() => setHoveredClusterId((current) => (current === node.id ? null : current))}
              onFocus={() => setHoveredClusterId(node.id)}
              onBlur={() => setHoveredClusterId((current) => (current === node.id ? null : current))}
            >
              <span className="relationship-graph-v2__node-dot" aria-hidden="true" />
              {showLabel && (
                <span className="relationship-graph-v2__label" aria-hidden="true">
                  <strong>{node.headline.length > 28 ? `${node.headline.slice(0, 28)}…` : node.headline}</strong>
                  <span>{`${node.coverageCount} ${getUiText(language, 'articles')}`}</span>
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default RelationshipGraphCanvasV2;
