import assert from 'node:assert/strict';

import { CATEGORY_LABELS, LOCALE_STORAGE_KEY, TRUST_LABELS } from '../src/i18n/messages';
import { readStoredLanguage, writeStoredLanguage } from '../src/i18n/index';

class MemoryStorage {
  private readonly store = new Map<string, string>();

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }

  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }
}

const localStorage = new MemoryStorage();

Object.assign(globalThis, {
  window: {
    localStorage,
  },
});

assert.equal(
  LOCALE_STORAGE_KEY,
  'pebble-language',
  'consolidated i18n should preserve the active storage key',
);

localStorage.setItem('pebble-language', 'zh');
assert.equal(
  readStoredLanguage(),
  'zh',
  'readStoredLanguage should continue reading the active storage key',
);

localStorage.removeItem('pebble-language');
localStorage.setItem('pebble-locale', 'zh');
assert.equal(
  readStoredLanguage(),
  'zh',
  'readStoredLanguage should also accept the legacy i18n directory storage key during migration',
);

writeStoredLanguage('en');
assert.equal(
  localStorage.getItem('pebble-language'),
  'en',
  'writeStoredLanguage should persist to the active storage key',
);

assert.equal(
  TRUST_LABELS.confirmed.zh,
  '已确认',
  'confirmed trust label should preserve the active Chinese copy',
);
assert.equal(
  TRUST_LABELS.likely.zh,
  '较可信',
  'likely trust label should preserve the active Chinese copy',
);

assert.deepEqual(
  {
    Industry: CATEGORY_LABELS.Industry?.zh,
    Startup: CATEGORY_LABELS.Startup?.zh,
    Trend: CATEGORY_LABELS.Trend?.zh,
  },
  {
    Industry: '行业',
    Startup: '创业',
    Trend: '趋势',
  },
  'messages catalog should include the active category labels before removing src/i18n.ts',
);

console.log('i18n consolidation verification passed');
