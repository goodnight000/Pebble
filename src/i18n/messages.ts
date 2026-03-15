import type { ContentType, Language } from '@/types';

type MessageValue = {
  en: string;
  zh: string;
};

export const LOCALE_STORAGE_KEY = 'pebble-language';
export const LEGACY_LOCALE_STORAGE_KEYS = ['pebble-locale'] as const;

export const NAV_LABELS = {
  digest: { en: 'Daily Digest', zh: '每日简报' },
  live: { en: 'Live Intelligence', zh: '实时情报' },
  weekly: { en: 'Weekly Signal', zh: '周度信号' },
  history: { en: 'History', zh: '历史存档' },
  map: { en: 'Relationship Graph', zh: '关系图谱' },
} as const;

export const CONTENT_TYPE_LABELS: Record<ContentType, MessageValue> = {
  all: { en: 'All', zh: '全部' },
  news: { en: 'News', zh: '新闻' },
  research: { en: 'Research', zh: '研究' },
  github: { en: 'GitHub', zh: 'GitHub' },
};

export const TRUST_LABELS: Record<string, MessageValue> = {
  official: { en: 'Official', zh: '官方' },
  confirmed: { en: 'Confirmed', zh: '已确认' },
  likely: { en: 'Likely', zh: '较可信' },
  developing: { en: 'Developing', zh: '发展中' },
  unverified: { en: 'Unverified', zh: '未验证' },
  disputed: { en: 'Disputed', zh: '有争议' },
};

export const CATEGORY_LABELS: Record<string, MessageValue> = {
  Research: { en: 'Research', zh: '研究' },
  Industry: { en: 'Industry', zh: '行业' },
  Startup: { en: 'Startup', zh: '创业' },
  Trend: { en: 'Trend', zh: '趋势' },
  Product: { en: 'Product', zh: '产品' },
  Company: { en: 'Company', zh: '公司' },
  Funding: { en: 'Funding', zh: '融资' },
  Policy: { en: 'Policy', zh: '政策' },
  'Open Source': { en: 'Open Source', zh: '开源' },
  Hardware: { en: 'Hardware', zh: '硬件' },
  Security: { en: 'Security', zh: '安全' },
  General: { en: 'General', zh: '综合' },
};

export const TOPIC_LABELS: Record<string, MessageValue> = {
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
  mixed: { en: 'Mixed', zh: '综合' },
};

export const UI_MESSAGES = {
  brand: { en: 'Pebble', zh: 'Pebble' },
  digestRefresh: { en: 'Real-time Scanner', zh: '实时扫描器' },
  autoRefresh: { en: 'Monitoring Active', zh: '监控运行中' },
  signalDigest: { en: 'Live Signal Stream', zh: '实时信号流' },
  lastDeepScan: { en: 'Last Deep Scan: ', zh: '深度扫描于: ' },
  languageToggleEn: { en: 'EN / 中', zh: 'EN / 中' },
  languageToggleZh: { en: '中 / EN', zh: '中 / EN' },
  refresh: { en: 'Refresh', zh: '刷新' },
  contentFilters: { en: 'Content filters', zh: '内容筛选' },
  todaysBriefing: { en: 'Today’s Briefing', zh: '今日简报' },
  feedSuffix: { en: 'feed', zh: '流' },
  storiesSuffix: { en: 'stories', zh: '条内容' },
  updatedAt: { en: 'Updated', zh: '更新于' },
  llmAuthored: { en: 'LLM-authored', zh: 'LLM 撰写' },
  llmOffline: { en: 'LLM offline', zh: 'LLM 离线' },
  verifiedRecencyToday: { en: 'Verified Recency: Today', zh: '时效验证：今日' },
  weeklySignal: { en: 'Weekly Signal', zh: '周度信号' },
  topSignificance: { en: 'Top Significance', zh: '高影响' },
  last7Days: { en: 'Last 7 Days', zh: '过去 7 天' },
  noWeeklyHighlights: { en: 'No weekly highlights yet.', zh: '暂无周度高影响内容。' },
  processingLanguage: { en: 'Processing Language', zh: '处理中英切换' },
  synthesizingDevelopments: { en: 'Synthesizing developments', zh: '正在整合动态' },
  gatheringInsights: { en: 'Gathering Insights', zh: '采集情报中' },
  distillingSignal: { en: 'Distilling Signal', zh: '提炼信号中' },
  translatingDigest: { en: 'Translating Digest', zh: '翻译摘要中' },
  signalDisruption: { en: 'Signal Disruption', zh: '信号中断' },
  initializingSystem: { en: 'Initializing System', zh: '初始化系统中' },
  reestablishUplink: { en: 'Re-establish Uplink', zh: '重新连接' },
  curatingGlobalSignals: { en: 'Curating Global Signals // Distilling Clarity', zh: '汇聚全球信号 // 提炼清晰洞察' },
  readSource: { en: 'Read source', zh: '查看来源' },
  shareStory: { en: 'Share story', zh: '分享内容' },
  copyStoryLink: { en: 'Copy story link', zh: '复制内容链接' },
  breakingIntelligence: { en: 'Breaking Intelligence', zh: '突发情报' },
  sourceLabel: { en: 'Source', zh: '来源' },
  viewSource: { en: 'View Source', zh: '查看来源' },
  signal: { en: 'Signal', zh: '信号' },
  relationshipGraphError: { en: 'Failed to load relationship graph.', zh: '关系图加载失败。' },
  relationshipGraphLoading: { en: 'Linking Story Clusters', zh: '构建关系图谱' },
  relationshipGraphEmpty: { en: 'No relationship clusters available for this window.', zh: '当前时间窗口暂无可用关系簇。' },
  retry: { en: 'Retry', zh: '重试' },
  relationshipGraph: { en: 'Relationship Graph', zh: '关系图谱' },
  relationshipGraphWindow: { en: 'Rolling Window', zh: '滚动时间窗' },
  graphConnections: { en: 'connections', zh: '个连接' },
  graphRelationshipEvidence: { en: 'Connection evidence available', zh: '可查看关联证据' },
  graphSharedEntity: { en: 'Shared Entity', zh: '共享实体' },
  graphEventChain: { en: 'Event Chain', zh: '事件链' },
  graphMarketAdjacency: { en: 'Market Adjacency', zh: '市场邻接' },
  graphEmbeddingSimilarity: { en: 'Embedding Similarity', zh: '嵌入相似度' },
  graphFollowUp: { en: 'Follow-up', zh: '后续报道' },
  graphReaction: { en: 'Reaction', zh: '回应' },
  graphCompeting: { en: 'Competing', zh: '竞争' },
  relationshipGraphZoomIn: { en: 'Zoom in', zh: '放大' },
  relationshipGraphZoomOut: { en: 'Zoom out', zh: '缩小' },
  relationshipGraphResetView: { en: 'Reset view', zh: '重置视图' },
  relationshipGraphFitGraph: { en: 'Fit graph', zh: '适配图谱' },
  closeRelationshipPanel: { en: 'Close relationship panel', zh: '关闭关系面板' },
  whyThisClusterMatters: { en: 'Why This Cluster Matters', zh: '这个簇为何重要' },
  relationshipEvidence: { en: 'Relationship Evidence', zh: '关系证据' },
  supportingCoverage: { en: 'Supporting Coverage', zh: '支撑报道' },
  coverage: { en: 'Coverage', zh: '报道量' },
  articles: { en: 'articles', zh: '篇' },
  articlesDetailed: { en: 'articles', zh: '篇报道' },
  sources: { en: 'Sources', zh: '来源' },
  sourcesSuffix: { en: 'sources', zh: '个来源' },
  velocity: { en: 'Velocity', zh: '速率' },
  age: { en: 'Age', zh: '时长' },
  keyEntities: { en: 'KEY ENTITIES', zh: '关键实体' },
  sevenDayTrend: { en: '7-DAY TREND', zh: '7 日趋势' },
  coverageWithCount: { en: 'COVERAGE', zh: '报道' },
  localeUnavailable: { en: 'Translation unavailable for this digest.', zh: '此简报暂无翻译。' },
} as const;

export function pickMessage(language: Language, value: MessageValue): string {
  return value[language];
}
