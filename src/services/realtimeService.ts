import { createClient } from '@supabase/supabase-js';

export type RealtimeChannelKey = 'urgent' | 'clusters' | 'digests';
export type RealtimeEventName = 'urgent_update' | 'new_cluster' | 'digest_refresh';

export interface FrontendRealtimeEnv {
  url: string;
  anonKey: string;
}

export interface FrontendRealtimeConfig {
  enabled: boolean;
  channels: Partial<Record<RealtimeChannelKey, string>>;
}

export interface RealtimeSignal {
  event: RealtimeEventName;
  payload: unknown;
}

export interface RealtimeSubscription {
  mode: 'disabled' | 'supabase';
  unsubscribe: () => void;
}

interface BroadcastPayload {
  payload?: unknown;
}

interface SubscriptionOptions {
  env?: FrontendRealtimeEnv | null;
  fetchImpl?: typeof fetch;
  createClient?: typeof createClient;
  onSignal: (signal: RealtimeSignal) => void;
  onError?: (error: unknown) => void;
}

interface RealtimeChannelSpec {
  channel: string;
  event: RealtimeEventName;
}

type ChannelStatus = 'SUBSCRIBED' | 'CHANNEL_ERROR' | 'TIMED_OUT' | 'CLOSED' | string;

const EVENT_MAP: Array<{ key: RealtimeChannelKey; event: RealtimeEventName }> = [
  { key: 'urgent', event: 'urgent_update' },
  { key: 'clusters', event: 'new_cluster' },
  { key: 'digests', event: 'digest_refresh' },
];

const normalizePayload = (payload: BroadcastPayload | unknown) =>
  payload && typeof payload === 'object' && 'payload' in (payload as BroadcastPayload)
    ? (payload as BroadcastPayload).payload
    : payload;

export const getPublicRealtimeEnv = (
  env: Record<string, unknown> = (import.meta as ImportMeta & { env?: Record<string, unknown> }).env ?? {},
): FrontendRealtimeEnv | null => {
  const url = typeof env.VITE_SUPABASE_URL === 'string' ? env.VITE_SUPABASE_URL.trim() : '';
  const anonKey = typeof env.VITE_SUPABASE_ANON_KEY === 'string' ? env.VITE_SUPABASE_ANON_KEY.trim() : '';
  if (!url || !anonKey) {
    return null;
  }
  return { url, anonKey };
};

export const buildRealtimeChannelSpecs = (config: FrontendRealtimeConfig): RealtimeChannelSpec[] => {
  if (!config.enabled) {
    return [];
  }

  return EVENT_MAP.flatMap(({ key, event }) => {
    const channel = config.channels[key];
    return channel ? [{ channel, event }] : [];
  });
};

export const fetchRealtimeConfig = async (fetchImpl: typeof fetch = fetch): Promise<FrontendRealtimeConfig> => {
  const response = await fetchImpl('/api/news/realtime/config');
  if (!response.ok) {
    throw new Error(`Failed to fetch realtime config (${response.status})`);
  }

  const data = (await response.json()) as {
    enabled?: boolean;
    channels?: Partial<Record<RealtimeChannelKey, string>>;
  };

  return {
    enabled: Boolean(data.enabled),
    channels: data.channels ?? {},
  };
};

export const createRealtimeSubscription = async ({
  env = getPublicRealtimeEnv(),
  fetchImpl = fetch,
  createClient: createRealtimeClient = createClient,
  onSignal,
  onError,
}: SubscriptionOptions): Promise<RealtimeSubscription> => {
  if (!env) {
    return { mode: 'disabled', unsubscribe: () => undefined };
  }

  const config = await fetchRealtimeConfig(fetchImpl);
  const specs = buildRealtimeChannelSpecs(config);
  if (!config.enabled || specs.length === 0) {
    return { mode: 'disabled', unsubscribe: () => undefined };
  }

  const supabase = createRealtimeClient(env.url, env.anonKey);
  const channels = new Map<string, ReturnType<typeof supabase.channel>>();

  for (const { channel, event } of specs) {
    let realtimeChannel = channels.get(channel);
    if (!realtimeChannel) {
      realtimeChannel = supabase.channel(channel, {
        config: { broadcast: { ack: true, self: false } },
      });
      channels.set(channel, realtimeChannel);
    }

    realtimeChannel.on('broadcast', { event }, (payload: BroadcastPayload) => {
      onSignal({ event, payload: normalizePayload(payload) });
    });
  }

  for (const [channel, realtimeChannel] of channels) {
    realtimeChannel.subscribe((status: ChannelStatus) => {
      if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') {
        onError?.(new Error(`Supabase Realtime failed for channel ${channel}: ${status}`));
      }
    });
  }

  return {
    mode: 'supabase',
    unsubscribe: () => {
      for (const realtimeChannel of channels.values()) {
        void supabase.removeChannel(realtimeChannel);
      }
    },
  };
};
