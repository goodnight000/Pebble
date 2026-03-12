import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const appPath = path.resolve(__dirname, '../src/App.tsx');
const i18nPath = path.resolve(__dirname, '../src/i18n/index.ts');
const appSource = readFileSync(appPath, 'utf8');
const i18nSource = readFileSync(i18nPath, 'utf8');

assert.doesNotMatch(
  appSource,
  /aiService\.subscribe\s*\(/,
  'App should not subscribe to live frontend monitoring',
);

assert.match(
  appSource,
  /30\s*\*\s*60\s*\*\s*1000/,
  'App should refresh on a 30 minute interval',
);

assert.match(
  appSource,
  /fetchWeeklyTop\(hasExpandedWeeklyRef\.current \? 12 : 6,\s*locale\)/,
  'App should preserve the expanded weekly list after background refreshes',
);

assert.doesNotMatch(
  appSource,
  /setLanguage\('en'\)/,
  'App should not force the locale back to English during refresh flows',
);

assert.match(
  appSource,
  /readStoredLanguage|writeStoredLanguage/,
  'App should persist the selected locale locally',
);

assert.match(
  i18nSource,
  /localStorage/,
  'Locale helpers should use localStorage persistence',
);

assert.doesNotMatch(
  appSource,
  /chineseDigest/,
  'App should not maintain a separate client-side translated digest cache',
);

assert.doesNotMatch(
  appSource,
  /Real-time Scanner|Monitoring Active|Live Signal Stream/,
  'App should not advertise live monitoring after it has been removed',
);

console.log('app refresh policy verification passed');
