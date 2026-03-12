import type { Language } from '@/types';
import {
  CATEGORY_LABELS,
  CONTENT_TYPE_LABELS,
  LOCALE_STORAGE_KEY,
  NAV_LABELS,
  pickMessage,
  TOPIC_LABELS,
  TRUST_LABELS,
  UI_MESSAGES,
} from './messages';

export { CONTENT_TYPE_LABELS, LOCALE_STORAGE_KEY, NAV_LABELS, UI_MESSAGES } from './messages';

export function isLanguage(value: string | null | undefined): value is Language {
  return value === 'en' || value === 'zh';
}

export function readStoredLanguage(): Language {
  if (typeof window === 'undefined') {
    return 'en';
  }
  const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
  return isLanguage(stored) ? stored : 'en';
}

export function writeStoredLanguage(language: Language): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(LOCALE_STORAGE_KEY, language);
}

export function getUiText(language: Language, key: keyof typeof UI_MESSAGES): string {
  return pickMessage(language, UI_MESSAGES[key]);
}

export function getTrustLabel(language: Language, trustLabel: string | null | undefined): string {
  if (!trustLabel || !TRUST_LABELS[trustLabel]) {
    return trustLabel ?? '';
  }
  return pickMessage(language, TRUST_LABELS[trustLabel]);
}

export function getCategoryLabel(language: Language, category: string): string {
  if (!CATEGORY_LABELS[category]) {
    return category;
  }
  return pickMessage(language, CATEGORY_LABELS[category]);
}

export function getTopicLabel(language: Language, topic: string, fallback?: string): string {
  if (TOPIC_LABELS[topic]) {
    return pickMessage(language, TOPIC_LABELS[topic]);
  }
  return fallback ?? topic;
}

export function getNavLabel(language: Language, key: keyof typeof NAV_LABELS): string {
  return pickMessage(language, NAV_LABELS[key]);
}
