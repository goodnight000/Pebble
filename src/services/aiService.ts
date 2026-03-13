import { DigestResponse, GraphResponse, Language, NewsItem } from '@/types';
import { createRealtimeSubscription, type RealtimeSubscription } from '@/services/realtimeService';

export type LiveEvent =
  | { type: 'news'; data: NewsItem }
  | { type: 'digest'; data: DigestResponse };

type EventSourceFactory = (url: string) => EventSource;

interface AIServiceOptions {
  fetchImpl?: typeof fetch;
  eventSourceFactory?: EventSourceFactory;
  createRealtimeSubscription?: typeof createRealtimeSubscription;
}

const failWithResponse = async (response: Response, context: string): Promise<never> => {
  const body = (await response.text().catch(() => '')).trim();
  const suffix = body ? `: ${body.slice(0, 200)}` : '';
  throw new Error(`${context} (${response.status})${suffix}`);
};

export class AIService {
  private readonly fetchImpl: typeof fetch;
  private readonly eventSourceFactory: EventSourceFactory;
  private readonly createRealtimeSubscription: typeof createRealtimeSubscription;

  constructor(options: AIServiceOptions = {}) {
    this.fetchImpl = options.fetchImpl ?? fetch.bind(window);
    this.eventSourceFactory = options.eventSourceFactory ?? ((url) => new EventSource(url));
    this.createRealtimeSubscription = options.createRealtimeSubscription ?? createRealtimeSubscription;
  }

  async fetchDigest(locale: Language = 'en'): Promise<DigestResponse> {
    const response = await this.fetchImpl(`/api/digest/today?locale=${locale}`);
    if (!response.ok) {
      await failWithResponse(response, 'Failed to fetch digest');
    }
    return response.json();
  }

  async refreshDigest(locale: Language = 'en'): Promise<DigestResponse> {
    await this.fetchImpl('/api/refresh', { method: 'POST' }).catch(() => undefined);
    return this.fetchDigest(locale);
  }

  async fetchLatestNews(limit = 30): Promise<NewsItem[]> {
    const response = await this.fetchImpl(`/api/news?limit=${limit}`);
    if (!response.ok) {
      await failWithResponse(response, 'Failed to fetch news');
    }
    const data = await response.json();
    return data.items ?? [];
  }

  async fetchWeeklyTop(limit = 8, locale: Language = 'en'): Promise<NewsItem[]> {
    const response = await this.fetchImpl(`/api/news/weekly?limit=${limit}&locale=${locale}`);
    if (!response.ok) {
      await failWithResponse(response, 'Failed to fetch weekly news');
    }
    const data = await response.json();
    return data.items ?? [];
  }

  private subscribeWithSse(callback: (event: LiveEvent) => void): () => void {
    const stream = this.eventSourceFactory('/api/stream');

    const handle = (event: MessageEvent, type: LiveEvent['type']) => {
      try {
        const data = JSON.parse(event.data);
        callback({ type, data } as LiveEvent);
      } catch (error) {
        console.warn('Failed to parse stream event', error);
      }
    };

    stream.addEventListener('news', (event) => handle(event as MessageEvent, 'news'));
    stream.addEventListener('digest', (event) => handle(event as MessageEvent, 'digest'));

    stream.onerror = () => {
      // Browser will retry automatically; keep UI responsive.
    };

    return () => {
      stream.close();
    };
  }

  subscribe(callback: (event: LiveEvent) => void): () => void {
    let sseUnsubscribe: (() => void) | null = null;
    let realtimeUnsubscribe: (() => void) | null = null;
    let closed = false;
    let refreshInFlight: Promise<void> | null = null;

    const ensureDigestRefresh = () => {
      if (refreshInFlight) {
        return;
      }

      refreshInFlight = (async () => {
        try {
          const digest = await this.fetchDigest();
          if (!closed) {
            callback({ type: 'digest', data: digest });
          }
        } catch (error) {
          console.warn('Failed to refresh digest from Realtime event', error);
        } finally {
          refreshInFlight = null;
        }
      })();
    };

    const startSseFallback = () => {
      if (closed || sseUnsubscribe) {
        return;
      }
      sseUnsubscribe = this.subscribeWithSse(callback);
    };

    void this.createRealtimeSubscription({
      fetchImpl: this.fetchImpl,
      onSignal: () => ensureDigestRefresh(),
      onError: (error) => {
        console.warn('Supabase Realtime unavailable, falling back to SSE', error);
        startSseFallback();
      },
    })
      .then((result) => {
        if (closed) {
          result.unsubscribe();
          return;
        }

        if (result.mode === 'disabled') {
          startSseFallback();
          return;
        }

        realtimeUnsubscribe = result.unsubscribe;
      })
      .catch((error) => {
        console.warn('Supabase Realtime setup failed, falling back to SSE', error);
        startSseFallback();
      });

    return () => {
      closed = true;
      realtimeUnsubscribe?.();
      sseUnsubscribe?.();
    };
  }

  async fetchRelationshipGraph(hours = 48, locale: Language = 'en'): Promise<GraphResponse> {
    const response = await this.fetchImpl(`/v1/graph?hours=${hours}&locale=${locale}`);
    if (!response.ok) {
      await failWithResponse(response, 'Failed to fetch relationship graph');
    }
    const raw = await response.json();
    return {
      clusters: (raw.clusters ?? []).map((c: any) => ({
        id: c.id,
        headline: c.headline,
        x: c.x,
        y: c.y,
        coverageCount: c.coverage_count,
        sourcesCount: c.sources_count,
        maxGlobalScore: c.max_global_score,
        velocity: c.velocity,
        pulsing: c.pulsing,
        trustScore: c.trust_score,
        trustLabel: c.trust_label,
        dominantTopic: c.dominant_topic,
        topicWeights: c.topic_weights,
        dominantEventType: c.dominant_event_type,
        entities: c.entities,
        sparkline: c.sparkline,
        firstSeenAt: c.first_seen_at,
        lastSeenAt: c.last_seen_at,
        ageHours: c.age_hours,
        articles: (c.articles ?? []).map((a: any) => ({
          id: a.id,
          title: a.title,
          url: a.url,
          source: a.source,
          publishedAt: a.published_at,
          globalScore: a.global_score,
          trustLabel: a.trust_label,
          eventType: a.event_type,
          summary: a.summary,
        })),
      })),
      edges: (raw.edges ?? []).map((e: any) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: e.type,
        score: e.score,
        evidence: e.evidence,
        embeddingSimilarity: e.embedding_similarity,
        ...(e.llm_type && { llmType: e.llm_type }),
        ...(e.llm_strength != null && { llmStrength: e.llm_strength }),
        ...(e.llm_explanation && { llmExplanation: e.llm_explanation }),
      })),
      projectionSeed: raw.projection_seed,
      generatedAt: raw.generated_at,
      locale: raw.locale,
      sourceLocale: raw.source_locale,
      translationStatus: raw.translation_status,
    };
  }

}
