import assert from 'node:assert/strict';

import { AIService } from '../src/services/aiService';
import {
  buildRealtimeChannelSpecs,
  createRealtimeSubscription,
  getPublicRealtimeEnv,
  type FrontendRealtimeConfig,
  type FrontendRealtimeEnv,
} from '../src/services/realtimeService';

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

async function testMissingEnvSkipsRealtime() {
  const env = getPublicRealtimeEnv({});
  assert.equal(env, null);

  const subscription = await createRealtimeSubscription({
    env: null,
    fetchImpl: async () => jsonResponse({ enabled: true, channels: {} }),
    createClient: () => {
      throw new Error('should not create supabase client without env');
    },
    onSignal: () => undefined,
  });

  assert.equal(subscription.mode, 'disabled');
}

async function testStableChannelMapping() {
  const config: FrontendRealtimeConfig = {
    enabled: true,
    channels: {
      urgent: 'alerts',
      clusters: 'cluster-live',
      digests: 'daily-digests',
    },
  };

  const specs = buildRealtimeChannelSpecs(config);
  assert.deepEqual(specs, [
    { channel: 'alerts', event: 'urgent_update' },
    { channel: 'cluster-live', event: 'new_cluster' },
    { channel: 'daily-digests', event: 'digest_refresh' },
  ]);
}

async function testSupabaseSubscriptionAndSseFallbackCoexist() {
  const env: FrontendRealtimeEnv = {
    url: 'https://project.supabase.co',
    anonKey: 'anon-key',
  };

  const handlers = new Map<string, (payload: { payload?: unknown }) => void>();
  const removedChannels: string[] = [];

  const fakeClient = {
    channel(name: string) {
      return {
        on(_kind: string, filter: { event: string }, handler: (payload: { payload?: unknown }) => void) {
          handlers.set(filter.event, handler);
          return this;
        },
        subscribe() {
          return this;
        },
      };
    },
    removeChannel(_channel: unknown) {
      removedChannels.push('removed');
    },
  };

  const signals: Array<{ event: string; payload: unknown }> = [];

  const realtimeSubscription = await createRealtimeSubscription({
    env,
    fetchImpl: async () =>
      jsonResponse({
        enabled: true,
        channels: {
          urgent: 'alerts',
          clusters: 'cluster-live',
          digests: 'daily-digests',
        },
      }),
    createClient: () => fakeClient,
    onSignal: (signal) => {
      signals.push(signal);
    },
  });

  assert.equal(realtimeSubscription.mode, 'supabase');
  handlers.get('digest_refresh')?.({ payload: { user_id: 'user-1' } });
  handlers.get('urgent_update')?.({ payload: { article_id: 'article-1' } });
  assert.deepEqual(signals, [
    { event: 'digest_refresh', payload: { user_id: 'user-1' } },
    { event: 'urgent_update', payload: { article_id: 'article-1' } },
  ]);

  realtimeSubscription.unsubscribe();
  assert.equal(removedChannels.length, 3);
}

async function testAiServiceFallsBackToSseAfterRealtimeError() {
  const createdStreams: string[] = [];
  const cleanupCalls: string[] = [];

  class ErrorFallbackEventSource {
    constructor(public url: string) {
      createdStreams.push(url);
    }

    addEventListener() {
      return undefined;
    }

    close() {
      cleanupCalls.push('sse');
    }
  }

  const aiService = new AIService({
    fetchImpl: async (input) => {
      const url = String(input);
      if (url === '/api/digest/today') {
        return jsonResponse({
          digests: {
            all: { headline: 'Daily AI Pulse', executiveSummary: 'Summary' },
            news: { headline: 'Daily AI Pulse', executiveSummary: 'Summary' },
            research: { headline: 'Daily AI Pulse', executiveSummary: 'Summary' },
            github: { headline: 'Daily AI Pulse', executiveSummary: 'Summary' },
          },
          headline: 'Daily AI Pulse',
          executiveSummary: 'Summary',
          items: [],
          breakingAlert: null,
        });
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    },
    createRealtimeSubscription: async ({ onError }) => {
      queueMicrotask(() => onError?.(new Error('channel failed')));
      return {
        mode: 'supabase',
        unsubscribe: () => {
          cleanupCalls.push('realtime');
        },
      };
    },
    eventSourceFactory: (url) => new ErrorFallbackEventSource(url) as unknown as EventSource,
  });

  const unsubscribe = aiService.subscribe(() => undefined);
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(createdStreams, ['/api/stream']);

  unsubscribe();
  assert.deepEqual(cleanupCalls.sort(), ['realtime', 'sse']);
}

async function testSseFallbackStillWorksWhenRealtimeIsDisabled() {
  const sseOnlyCreatedStreams: string[] = [];

  class DisabledRealtimeEventSource {
    url: string;
    onerror: (() => void) | null = null;
    listeners = new Map<string, Array<(event: MessageEvent) => void>>();

    constructor(url: string) {
      this.url = url;
      sseOnlyCreatedStreams.push(url);
    }

    addEventListener(type: string, listener: (event: MessageEvent) => void) {
      const existing = this.listeners.get(type) ?? [];
      existing.push(listener);
      this.listeners.set(type, existing);
    }

    close() {
      sseOnlyCreatedStreams.push('closed');
    }
  }

  const aiService = new AIService({
    fetchImpl: async (input) => {
      const url = String(input);
      if (url === '/api/news/realtime/config') {
        return jsonResponse({ enabled: false, channels: {} });
      }
      if (url === '/api/digest/today') {
        return jsonResponse({
          digests: {
            all: { headline: 'Daily AI Pulse', executiveSummary: 'Summary' },
            news: { headline: 'Daily AI Pulse', executiveSummary: 'Summary' },
            research: { headline: 'Daily AI Pulse', executiveSummary: 'Summary' },
            github: { headline: 'Daily AI Pulse', executiveSummary: 'Summary' },
          },
          headline: 'Daily AI Pulse',
          executiveSummary: 'Summary',
          items: [],
          breakingAlert: null,
        });
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    },
    createRealtimeSubscription: async () => ({ mode: 'disabled', unsubscribe: () => undefined }),
    eventSourceFactory: (url) => new DisabledRealtimeEventSource(url) as unknown as EventSource,
  });

  const unsubscribe = aiService.subscribe(() => undefined);
  await Promise.resolve();

  assert.deepEqual(sseOnlyCreatedStreams, ['/api/stream']);

  unsubscribe();
  assert.deepEqual(sseOnlyCreatedStreams, ['/api/stream', 'closed']);
}

async function main() {
  await testMissingEnvSkipsRealtime();
  await testStableChannelMapping();
  await testSupabaseSubscriptionAndSseFallbackCoexist();
  await testAiServiceFallsBackToSseAfterRealtimeError();
  await testSseFallbackStillWorksWhenRealtimeIsDisabled();
  console.log('realtime service verification passed');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
