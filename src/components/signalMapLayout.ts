import * as d3 from 'd3';
import type { SignalMapCluster } from '@/types';

export interface Point {
  x: number;
  y: number;
}

interface FitOptions {
  width: number;
  height: number;
  padding: number;
  gap?: number;
}

interface TooltipSize {
  width: number;
  height: number;
}

interface ViewportSize {
  width: number;
  height: number;
}

const MIN_RADIUS = 18;
const MAX_RADIUS = 62;
const MIN_SPAN = 0.08;
const LABEL_COLLISION_RADIUS = 72;
const DEFAULT_GAP = 10;
const TOOLTIP_MARGIN = 12;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const normalizedExtent = (values: number[]): [number, number] => {
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return [0, 1];
  }
  if (max - min < MIN_SPAN) {
    const center = (min + max) / 2;
    return [center - MIN_SPAN / 2, center + MIN_SPAN / 2];
  }
  return [min, max];
};

const clusterPriority = (cluster: SignalMapCluster): number =>
  cluster.coverageCount * 2 +
  cluster.maxGlobalScore * 0.75 +
  cluster.sourcesCount * 1.25 +
  cluster.velocity * 3 +
  (cluster.pulsing ? 20 : 0);

export const resolveBubbleRadius = (
  coverageCount: number,
  clusters: SignalMapCluster[],
): number => {
  const maxCoverage = Math.max(...clusters.map((cluster) => cluster.coverageCount), 1);
  return d3
    .scaleSqrt<number, number>()
    .domain([1, maxCoverage])
    .range([MIN_RADIUS, MAX_RADIUS])(Math.max(1, coverageCount));
};

export const fitClusterPositions = (
  clusters: SignalMapCluster[],
  options: FitOptions,
): Map<string, Point> => {
  const { width, height, padding, gap = DEFAULT_GAP } = options;
  const innerWidth = Math.max(1, width - padding * 2);
  const innerHeight = Math.max(1, height - padding * 2);

  const xs = clusters.map((cluster) => cluster.x);
  const ys = clusters.map((cluster) => cluster.y);
  const [minX, maxX] = normalizedExtent(xs);
  const [minY, maxY] = normalizedExtent(ys);

  const xScale = d3.scaleLinear().domain([minX, maxX]).range([padding, padding + innerWidth]);
  const yScale = d3.scaleLinear().domain([minY, maxY]).range([padding, padding + innerHeight]);

  const positions = new Map<string, Point>();
  for (const cluster of clusters) {
    positions.set(cluster.id, {
      x: xScale(cluster.x),
      y: yScale(cluster.y),
    });
  }

  for (let iteration = 0; iteration < 80; iteration += 1) {
    let moved = false;

    for (let index = 0; index < clusters.length; index += 1) {
      for (let nextIndex = index + 1; nextIndex < clusters.length; nextIndex += 1) {
        const a = clusters[index];
        const b = clusters[nextIndex];
        const pointA = positions.get(a.id);
        const pointB = positions.get(b.id);
        if (!pointA || !pointB) continue;

        let dx = pointB.x - pointA.x;
        let dy = pointB.y - pointA.y;
        let distance = Math.hypot(dx, dy);
        const minDistance =
          resolveBubbleRadius(a.coverageCount, clusters) +
          resolveBubbleRadius(b.coverageCount, clusters) +
          gap;

        if (distance === 0) {
          dx = 1;
          dy = 0;
          distance = 1;
        }

        if (distance >= minDistance) {
          continue;
        }

        const overlap = (minDistance - distance) / 2;
        const unitX = dx / distance;
        const unitY = dy / distance;

        pointA.x -= unitX * overlap;
        pointA.y -= unitY * overlap;
        pointB.x += unitX * overlap;
        pointB.y += unitY * overlap;
        moved = true;
      }
    }

    for (const cluster of clusters) {
      const point = positions.get(cluster.id);
      if (!point) continue;
      const radius = resolveBubbleRadius(cluster.coverageCount, clusters);
      point.x = clamp(point.x, padding + radius, width - padding - radius);
      point.y = clamp(point.y, padding + radius, height - padding - radius);
    }

    if (!moved) {
      break;
    }
  }

  return positions;
};

export const pickVisibleLabels = (
  clusters: SignalMapCluster[],
  positions: Map<string, Point>,
  selectedClusterId: string | null,
  maxLabels: number,
): Set<string> => {
  const visibleIds = new Set<string>();

  if (selectedClusterId) {
    visibleIds.add(selectedClusterId);
  }

  const ranked = [...clusters].sort((left, right) => clusterPriority(right) - clusterPriority(left));
  for (const cluster of ranked) {
    if (visibleIds.size >= maxLabels) {
      break;
    }
    if (visibleIds.has(cluster.id)) {
      continue;
    }

    const point = positions.get(cluster.id);
    if (!point) {
      continue;
    }

    const collides = [...visibleIds].some((visibleId) => {
      const otherPoint = positions.get(visibleId);
      if (!otherPoint) {
        return false;
      }
      return Math.hypot(point.x - otherPoint.x, point.y - otherPoint.y) < LABEL_COLLISION_RADIUS;
    });

    if (!collides) {
      visibleIds.add(cluster.id);
    }
  }

  return visibleIds;
};

export const clampTooltipPosition = (
  cursor: Point,
  tooltipSize: TooltipSize,
  viewport: ViewportSize,
): { left: number; top: number } => {
  const idealLeft = cursor.x + TOOLTIP_MARGIN;
  const idealTop = cursor.y - TOOLTIP_MARGIN;

  const left = clamp(
    idealLeft,
    TOOLTIP_MARGIN,
    viewport.width - tooltipSize.width - TOOLTIP_MARGIN,
  );
  const top = clamp(
    idealTop,
    TOOLTIP_MARGIN,
    viewport.height - tooltipSize.height - TOOLTIP_MARGIN,
  );

  return { left, top };
};
