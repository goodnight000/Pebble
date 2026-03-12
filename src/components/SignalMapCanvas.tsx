import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { SignalMapCluster, Language } from '@/types';
import { getTrustLabel } from '@/i18n';
import {
  clampTooltipPosition,
  fitClusterPositions,
  pickVisibleLabels,
  resolveBubbleRadius,
} from '@/components/signalMapLayout';

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

interface SignalMapCanvasProps {
  clusters: SignalMapCluster[];
  projectionSeed: string;
  selectedClusterId: string | null;
  onSelectCluster: (id: string) => void;
  language: Language;
}

const PADDING = 60;
const DEFAULT_TOOLTIP_SIZE = { width: 240, height: 92 };

function topicColor(topic: string): string {
  return TOPIC_COLORS[topic] ?? TOPIC_COLORS.mixed;
}

function truncateLabel(text: string, max = 20): string {
  return text.length > max ? text.slice(0, max) + '\u2026' : text;
}

const SignalMapCanvas: React.FC<SignalMapCanvasProps> = ({
  clusters,
  projectionSeed,
  selectedClusterId,
  onSelectCluster,
  language,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const lastSeedRef = useRef<string>('');
  const tooltipRafRef = useRef<number | null>(null);
  const pendingTooltipRef = useRef<{
    x: number;
    y: number;
    cluster: SignalMapCluster;
  } | null>(null);
  const tooltipSizeRef = useRef(DEFAULT_TOOLTIP_SIZE);

  const [tooltip, setTooltip] = useState<{
    visible: boolean;
    left: number;
    top: number;
    cursorX: number;
    cursorY: number;
    cluster: SignalMapCluster | null;
  }>({ visible: false, left: 0, top: 0, cursorX: 0, cursorY: 0, cluster: null });

  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  const layout = useMemo(() => {
    const positions = fitClusterPositions(clusters, {
      width: dimensions.width,
      height: dimensions.height,
      padding: PADDING,
      gap: 14,
    });
    const preferredLabelCount = dimensions.width >= 1400 ? 8 : dimensions.width >= 1100 ? 6 : 4;
    const visibleLabelIds = pickVisibleLabels(
      clusters,
      positions,
      selectedClusterId,
      preferredLabelCount,
    );
    return { positions, visibleLabelIds };
  }, [clusters, dimensions.height, dimensions.width, selectedClusterId]);

  // ── ResizeObserver ──
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

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

  // ── Tooltip handlers (stable refs) ──
  const flushTooltipUpdate = useCallback(() => {
    tooltipRafRef.current = null;
    const pending = pendingTooltipRef.current;
    if (!pending) {
      return;
    }

    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const nextPosition = clampTooltipPosition(
      { x: pending.x, y: pending.y },
      tooltipSizeRef.current,
      viewport,
    );

    setTooltip((prev) => ({
      visible: true,
      left: nextPosition.left,
      top: nextPosition.top,
      cursorX: pending.x,
      cursorY: pending.y,
      cluster: pending.cluster,
    }));
  }, []);

  const queueTooltipUpdate = useCallback(
    (x: number, y: number, cluster: SignalMapCluster) => {
      pendingTooltipRef.current = { x, y, cluster };
      if (tooltipRafRef.current !== null) {
        return;
      }
      tooltipRafRef.current = window.requestAnimationFrame(flushTooltipUpdate);
    },
    [flushTooltipUpdate],
  );

  const handleMouseEnter = useCallback(
    (event: MouseEvent, cluster: SignalMapCluster) => {
      queueTooltipUpdate(event.clientX, event.clientY, cluster);
    },
    [queueTooltipUpdate],
  );

  const handleMouseMove = useCallback(
    (event: MouseEvent, cluster: SignalMapCluster) => {
      queueTooltipUpdate(event.clientX, event.clientY, cluster);
    },
    [queueTooltipUpdate],
  );

  const handleMouseLeave = useCallback(() => {
    pendingTooltipRef.current = null;
    if (tooltipRafRef.current !== null) {
      window.cancelAnimationFrame(tooltipRafRef.current);
      tooltipRafRef.current = null;
    }
    setTooltip({ visible: false, left: 0, top: 0, cursorX: 0, cursorY: 0, cluster: null });
  }, []);

  useEffect(() => {
    return () => {
      if (tooltipRafRef.current !== null) {
        window.cancelAnimationFrame(tooltipRafRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!tooltip.visible || !tooltip.cluster || !tooltipRef.current) {
      return;
    }

    const rect = tooltipRef.current.getBoundingClientRect();
    tooltipSizeRef.current = {
      width: rect.width || tooltipSizeRef.current.width,
      height: rect.height || tooltipSizeRef.current.height,
    };

    const nextPosition = clampTooltipPosition(
      { x: tooltip.cursorX, y: tooltip.cursorY },
      tooltipSizeRef.current,
      { width: window.innerWidth, height: window.innerHeight },
    );

    setTooltip((prev) =>
      prev.left === nextPosition.left && prev.top === nextPosition.top
        ? prev
        : { ...prev, left: nextPosition.left, top: nextPosition.top },
    );
  }, [tooltip.cluster, tooltip.cursorX, tooltip.cursorY, tooltip.top, tooltip.left, tooltip.visible]);

  // ── D3 rendering ──
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    if (!svgRef.current) return;

    const { width, height } = dimensions;

    svg.attr('viewBox', `0 0 ${width} ${height}`);

    // Determine whether seed changed (need transition)
    const seedChanged = lastSeedRef.current !== '' && lastSeedRef.current !== projectionSeed;
    lastSeedRef.current = projectionSeed;

    // ── Data join ──
    const groups = svg
      .selectAll<SVGGElement, SignalMapCluster>('g.signal-bubble')
      .data(clusters, (d) => (d as SignalMapCluster).id);

    // EXIT
    groups.exit().transition().duration(400).style('opacity', 0).remove();

    // ENTER
    const enter = groups
      .enter()
      .append('g')
      .attr('class', 'signal-bubble')
      .style('opacity', 0);

    // Pulse circle (behind main circle)
    enter
      .append('circle')
      .attr('class', 'signal-pulse-circle');

    // Main circle
    enter
      .append('circle')
      .attr('class', 'signal-bubble-circle');

    // Label
    enter
      .append('text')
      .attr('class', 'signal-bubble-label');

    // Fade in
    enter.transition().duration(400).style('opacity', 1);

    // ENTER + UPDATE (merge)
    const merged = enter.merge(groups);

    merged
      .attr('class', (d) =>
        `signal-bubble${d.id === selectedClusterId ? ' signal-bubble--selected' : ''}`,
      )
      .attr('tabindex', 0)
      .attr('role', 'button')
      .attr('aria-pressed', (d) => (d.id === selectedClusterId ? 'true' : 'false'))
      .attr(
        'aria-label',
        (d) =>
          `${d.headline}. ${d.coverageCount} coverage. ${d.sourcesCount} sources. ${getTrustLabel(language, d.trustLabel)}.`,
      );

    // Position groups
    merged.each(function (d: SignalMapCluster) {
      const pos = layout.positions.get(d.id);
      if (!pos) return;
      const g = d3.select(this);

      if (seedChanged) {
        g.transition()
          .duration(800)
          .ease(d3.easeCubicInOut)
          .attr('transform', `translate(${pos.x}, ${pos.y})`);
      } else {
        g.attr('transform', `translate(${pos.x}, ${pos.y})`);
      }
    });

    // Update pulse circles
    merged.each(function (d: SignalMapCluster) {
      const g = d3.select(this);
      const r = resolveBubbleRadius(d.coverageCount, clusters);
      const fill = topicColor(d.dominantTopic);
      const showLabel = layout.visibleLabelIds.has(d.id) || d.id === selectedClusterId;

      g.select('circle.signal-pulse-circle')
        .attr('r', r)
        .attr('fill', fill)
        .attr('stroke', 'none')
        .attr('class', d.pulsing ? 'signal-pulse-circle signal-pulse-group' : 'signal-pulse-circle')
        .style('display', d.pulsing ? null : 'none');

      const solidClass = (d.trustLabel === 'official' || d.trustLabel === 'confirmed')
        ? 'signal-bubble-circle signal-bubble-circle--solid'
        : 'signal-bubble-circle';

      g.select('circle.signal-bubble-circle')
        .attr('r', r)
        .attr('fill', fill)
        .attr('fill-opacity', d.id === selectedClusterId ? 0.74 : 0.64)
        .attr('class', solidClass)
        .attr('stroke', d.id === selectedClusterId ? '#ff6a00' : 'var(--ink)')
        .attr('stroke-width', d.id === selectedClusterId ? 3 : 1.75);

      g.select('text.signal-bubble-label')
        .attr(
          'class',
          `signal-bubble-label${showLabel ? ' signal-bubble-label--visible' : ''}`,
        )
        .attr('y', r + 14)
        .text(truncateLabel(d.headline));
    });

    // ── Event handlers ──
    merged
      .on('mouseenter', function (event: MouseEvent, d: SignalMapCluster) {
        handleMouseEnter(event, d);
      })
      .on('mousemove', function (event: MouseEvent, d: SignalMapCluster) {
        handleMouseMove(event, d);
      })
      .on('mouseleave', function () {
        handleMouseLeave();
      })
      .on('focus', function (_event: FocusEvent, d: SignalMapCluster) {
        const bounds = (this as SVGGElement).getBoundingClientRect();
        queueTooltipUpdate(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2, d);
      })
      .on('blur', function () {
        handleMouseLeave();
      })
      .on('keydown', function (event: KeyboardEvent, d: SignalMapCluster) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelectCluster(d.id);
        }
      })
      .on('click', function (_event: MouseEvent, d: SignalMapCluster) {
        onSelectCluster(d.id);
      });
  }, [
    clusters,
    language,
    layout.positions,
    layout.visibleLabelIds,
    projectionSeed,
    selectedClusterId,
    dimensions,
    handleMouseEnter,
    handleMouseMove,
    handleMouseLeave,
    onSelectCluster,
  ]);

  return (
    <div ref={containerRef} className="signal-map-surface">
      <svg ref={svgRef} />
      {tooltip.visible && tooltip.cluster && (
        <div
          ref={tooltipRef}
          className="signal-tooltip"
          style={{ left: tooltip.left, top: tooltip.top }}
        >
          <div className="signal-tooltip-headline">
            {tooltip.cluster.headline}
          </div>
          <div className="signal-tooltip-meta">
            <span
              className={`trust-badge trust-badge--${tooltip.cluster.trustLabel}`}
            >
              {getTrustLabel(language, tooltip.cluster.trustLabel)}
            </span>
            <span>{tooltip.cluster.velocity.toFixed(1)} art/hr</span>
            <span>{tooltip.cluster.sourcesCount} sources</span>
          </div>
          {tooltip.cluster.entities.length > 0 && (
            <div style={{ marginTop: 4, fontSize: 9, opacity: 0.8 }}>
              {tooltip.cluster.entities
                .slice(0, 3)
                .map((e) => e.name)
                .join(' \u00b7 ')}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SignalMapCanvas;
