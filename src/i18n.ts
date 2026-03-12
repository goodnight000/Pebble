import type { ContentType, Language } from '@/types';

const STORAGE_KEY = 'pebble-language';

export function readStoredLanguage(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'zh') return 'zh';
  } catch { /* ignore */ }
  return 'en';
}

export function writeStoredLanguage(language: Language): void {
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch { /* ignore */ }
}

export const CONTENT_TYPE_LABELS: Record<ContentType, Record<Language, string>> = {
  all: { en: 'All', zh: '全部' },
  news: { en: 'News', zh: '新闻' },
  research: { en: 'Research', zh: '研究' },
  github: { en: 'GitHub', zh: 'GitHub' },
};

const NAV_LABELS: Record<string, Record<Language, string>> = {
  live: { en: 'Live Intelligence', zh: '实时情报' },
  weekly: { en: 'Weekly Signal', zh: '周度信号' },
  history: { en: 'History', zh: '历史存档' },
  map: { en: 'Relationship Graph', zh: '关系图谱' },
};

export function getNavLabel(language: Language, navId: string): string {
  return NAV_LABELS[navId]?.[language] ?? navId;
}

const UI_TEXT: Record<string, Record<Language, string>> = {
  brand: { en: 'Pebble', zh: 'Pebble' },
  signalDigest: { en: 'Live Signal Stream', zh: '实时信号流' },
  lastDeepScan: { en: 'Last Deep Scan: ', zh: '深度扫描于: ' },
  digestRefresh: { en: 'Real-time Scanner', zh: '实时扫描器' },
  autoRefresh: { en: 'Monitoring Active', zh: '监控运行中' },
  contentFilters: { en: 'Content filters', zh: '内容筛选' },
  todaysBriefing: { en: "Today\u2019s Briefing", zh: '今日简报' },
  feedSuffix: { en: 'feed', zh: '流' },
  storiesSuffix: { en: 'stories', zh: '条内容' },
  updatedAt: { en: 'Updated', zh: '更新于' },
  llmAuthored: { en: 'LLM-authored', zh: 'LLM 撰写' },
  llmOffline: { en: 'LLM offline', zh: 'LLM 离线' },
  verifiedRecencyToday: { en: 'Verified Recency: Today', zh: '时效验证：今日' },
  localeUnavailable: { en: 'Translation unavailable for this digest.', zh: '此简报暂无翻译。' },
  weeklySignal: { en: 'Weekly Signal', zh: '周度信号' },
  topSignificance: { en: 'Top Significance', zh: '高影响' },
  last7Days: { en: 'Last 7 Days', zh: '过去 7 天' },
  noWeeklyHighlights: { en: 'No weekly highlights yet.', zh: '暂无周度高影响内容。' },
  curatingGlobalSignals: { en: 'Curating Global Signals // Distilling Clarity', zh: '汇聚全球信号 // 提炼清晰洞察' },
  processingLanguage: { en: 'Processing Language', zh: '语言处理中' },
  synthesizingDevelopments: { en: 'Synthesizing developments', zh: '综合动态中' },
  gatheringInsights: { en: 'Gathering Insights', zh: '收集洞察' },
  distillingSignal: { en: 'Distilling Signal', zh: '提炼信号' },
  translatingDigest: { en: 'Translating Digest', zh: '翻译简报' },
  signalDisruption: { en: 'Signal Disruption', zh: '信号中断' },
  initializingSystem: { en: 'Initializing System', zh: '系统初始化' },
  reestablishUplink: { en: 'Re-establish Uplink', zh: '重新连接' },
  languageToggleEn: { en: 'EN / 中', zh: 'EN / 中' },
  languageToggleZh: { en: '中 / EN', zh: '中 / EN' },
  refresh: { en: 'Refresh', zh: '刷新' },
  retry: { en: 'Retry', zh: '重试' },
  relationshipGraph: { en: 'Relationship Graph', zh: '关系图谱' },
  relationshipGraphLoading: { en: 'Linking Story Clusters', zh: '构建关系图谱' },
  relationshipGraphError: { en: 'Failed to load relationship graph.', zh: '关系图加载失败。' },
  relationshipGraphWindow: { en: 'Rolling Window', zh: '滚动时间窗' },
  graphSharedEntity: { en: 'Shared Entity', zh: '共享实体' },
  graphEventChain: { en: 'Event Chain', zh: '事件链' },
  graphMarketAdjacency: { en: 'Market Adjacency', zh: '市场邻接' },
  graphEmbeddingSimilarity: { en: 'Embedding Similarity', zh: '嵌入相似度' },
};

export function getUiText(language: Language, key: string): string {
  return UI_TEXT[key]?.[language] ?? UI_TEXT[key]?.en ?? key;
}

const TRUST_LABELS: Record<string, Record<Language, string>> = {
  official: { en: 'Official', zh: '官方' },
  confirmed: { en: 'Confirmed', zh: '已确认' },
  likely: { en: 'Likely', zh: '较可信' },
  developing: { en: 'Developing', zh: '发展中' },
  unverified: { en: 'Unverified', zh: '未验证' },
  disputed: { en: 'Disputed', zh: '有争议' },
};

export function getTrustLabel(language: Language, trustLabel: string | undefined | null): string {
  if (!trustLabel) return '';
  return TRUST_LABELS[trustLabel]?.[language] ?? trustLabel;
}

const CATEGORY_LABELS: Record<string, Record<Language, string>> = {
  Research: { en: 'Research', zh: '研究' },
  Industry: { en: 'Industry', zh: '行业' },
  Startup: { en: 'Startup', zh: '创业' },
  Policy: { en: 'Policy', zh: '政策' },
  Trend: { en: 'Trend', zh: '趋势' },
  Product: { en: 'Product', zh: '产品' },
  Company: { en: 'Company', zh: '公司' },
  Funding: { en: 'Funding', zh: '融资' },
  'Open Source': { en: 'Open Source', zh: '开源' },
  Hardware: { en: 'Hardware', zh: '硬件' },
  Security: { en: 'Security', zh: '安全' },
  General: { en: 'General', zh: '综合' },
};

export function getCategoryLabel(language: Language, category: string): string {
  return CATEGORY_LABELS[category]?.[language] ?? category;
}

const TOPIC_LABELS: Record<string, Record<Language, string>> = {
  llms: { en: 'LLM', zh: '大模型' },
  multimodal: { en: 'Multimodal', zh: '多模态' },
  agents: { en: 'Agents', zh: '智能体' },
  robotics: { en: 'Robotics', zh: '机器人' },
  vision: { en: 'Vision', zh: '视觉' },
  audio_speech: { en: 'Audio', zh: '语音' },
  hardware_chips: { en: 'Hardware', zh: '硬件' },
  open_source: { en: 'Open Source', zh: '开源' },
  startups_funding: { en: 'Funding', zh: '融资' },
  enterprise_apps: { en: 'Enterprise', zh: '企业' },
  safety_policy: { en: 'Policy', zh: '政策' },
  research_methods: { en: 'Research', zh: '研究' },
};

export function getTopicLabel(language: Language, topicKey: string, fallback?: string): string {
  return TOPIC_LABELS[topicKey]?.[language] ?? fallback ?? topicKey;
}
