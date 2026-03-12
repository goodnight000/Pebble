import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import NewsCard from '../src/components/NewsCard';
import BreakingAlert from '../src/components/BreakingAlert';
import { getCategoryConfig } from '../src/config/constants';
import type { NewsItem } from '../src/types';

const sampleItem: NewsItem = {
  id: 'wireframe-test',
  title: 'OPENAI RELEASES GPT-5.4 THINKING MODEL WITH STRONGER TOOL USE',
  summary:
    'OpenAI published GPT-5.4 with stronger tool use and coding support. The update also shipped with documentation and benchmark context for developers evaluating the model today.',
  significanceScore: 96,
  category: 'Product',
  contentType: 'news',
  timestamp: '2026-03-05T18:00:00Z',
  tags: ['LLMs', 'Agents', 'Coding', 'Developer Tools'],
  sources: [
    { title: 'OpenAI Blog', uri: 'https://openai.com/blog/gpt-5-4' },
    { title: 'System Card', uri: 'https://openai.com/index/gpt-5-4-system-card' },
  ],
  trustLabel: 'official',
};

const socialItem: NewsItem = {
  ...sampleItem,
  id: 'social-wireframe-test',
  title: 'AI GLASSES & PRIVACY: A GROWING CONCERN # AI # PRIVACY # DIGITALRIGHTS # TECHETHICS',
  summary:
    'AI Glasses & Privacy: A Growing Concern. New consumer wearables keep triggering debate around surveillance, public consent, and digital-rights enforcement in everyday environments.',
  significanceScore: 32,
  category: 'General',
  contentType: 'news',
  tags: ['Consumer', 'Security', 'Governance', 'Vision'],
  trustLabel: 'likely',
  sources: [
    { title: 'Mastodon AI Hashtags', uri: 'https://mastodon.social/tags/ai' },
  ],
};

const githubItem: NewsItem = {
  ...sampleItem,
  id: 'github-wireframe-test',
  title: 'CIFLOW/XPU/174188',
  summary: 'Add xpu smoke test',
  significanceScore: 33,
  category: 'Open Source',
  contentType: 'github',
  tags: ['Developer Tools', 'Infrastructure', 'Hardware', 'Coding'],
  trustLabel: undefined,
  sources: [
    { title: 'GitHub Releases: PyTorch', uri: 'https://github.com/pytorch/pytorch/pull/174188' },
  ],
};

const cardMarkup = renderToStaticMarkup(
  <NewsCard item={sampleItem} featured />
);

assert.match(cardMarkup, /news-card-wf--feature/, 'featured wireframe card should render a feature class');
assert.match(
  cardMarkup,
  /border-color:\s*#ef4444/i,
  'wireframe card should keep its category border color at rest instead of reverting to the default ink border'
);
assert.match(
  cardMarkup,
  /wf-chip wf-chip--category" style="border-color:#ef4444;color:#ef4444;background:rgba\(239,\s*68,\s*68,\s*0\.(?:12|2)\)"/i,
  'wireframe card should use a tinted category chip background so main categories read with more color'
);
assert.match(cardMarkup, /wf-signal-pill__value/, 'wireframe card should render a stable signal value slot');
assert.match(cardMarkup, /wf-card-header/, 'wireframe card should render the new header shell');
assert.match(cardMarkup, /wf-card-header__top/, 'wireframe card should render a dedicated top metadata row');
assert.match(cardMarkup, /wf-card-header__bottom/, 'wireframe card should render a dedicated bottom metadata row');
assert.match(cardMarkup, /OpenAI Blog/, 'wireframe card should surface the primary source in the scan layer');
assert.match(cardMarkup, /LLMs/, 'wireframe card should retain semantic topic chips');
assert.match(cardMarkup, /Developer Tools/, 'wireframe card should keep the full four-chip set visible');
assert.doesNotMatch(cardMarkup, /\+1/, 'wireframe card should not collapse a four-chip footer into overflow');
assert.equal(
  (cardMarkup.match(/OpenAI Blog/g) ?? []).length,
  1,
  'wireframe card should not duplicate the primary source label in multiple rails'
);
assert.match(
  cardMarkup,
  /wf-card-footer__utility/,
  'wireframe card should group the source action and share control into one utility rail'
);

const breakingMarkup = renderToStaticMarkup(
  <BreakingAlert item={sampleItem} />
);

assert.match(breakingMarkup, /OpenAI published GPT-5\.4/, 'wireframe breaking alert should include a readable summary line');
assert.match(breakingMarkup, /Source: OpenAI Blog/, 'wireframe breaking alert should surface the primary source label');
assert.match(breakingMarkup, /View Source/, 'wireframe breaking alert should keep the source CTA');

const appSource = fs.readFileSync(path.join(process.cwd(), 'src', 'App.tsx'), 'utf8');
const cssSource = fs.readFileSync(path.join(process.cwd(), 'src', 'styles', 'global.css'), 'utf8');
assert.match(
  cssSource,
  /\.wf-card-footer\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto;[\s\S]*align-items:\s*center;/,
  'wireframe footer should keep tags on the left and a single centered utility rail on the right'
);
assert.doesNotMatch(
  cssSource,
  /\.news-card-wf::before\s*\{/,
  'wireframe cards should not render the top accent strip'
);
assert.notEqual(
  getCategoryConfig('Product').color,
  getCategoryConfig('Security').color,
  'wireframe category colors should stay distinct across primary categories'
);
assert.notEqual(
  getCategoryConfig('Funding').color,
  getCategoryConfig('Hardware').color,
  'wireframe funding and hardware colors should stay distinct from each other'
);
assert.match(
  cssSource,
  /\.wf-chip--category\s*\{[\s\S]*border-radius:\s*10px;/,
  'wireframe primary category chip should use a squarer shape than the other pills'
);
assert.match(
  appSource,
  /<aside className="app-sidebar hidden lg:flex w-64 shrink-0 sticky top-0 h-screen self-start flex-col overflow-hidden border-r-2 border-\[var\(--ink\)\] bg-\[var\(--panel\)\]">/,
  'desktop sidebar should be sticky for the full viewport height'
);
assert.match(
  appSource,
  /<aside className="app-sidebar[\s\S]*?<div className="flex h-full flex-col">/s,
  'desktop sidebar should use a non-scrolling full-height inner column'
);
assert.match(
  appSource,
  /<div className=\"app-shell wireframe-grid flex h-screen overflow-hidden text-\[var\(--ink\)\]\">/,
  'app shell should be locked to the wireframe layout and viewport height'
);
assert.match(
  appSource,
  /<main className=\"app-main relative flex min-h-0 flex-1 flex-col overflow-hidden\">/,
  'main column should allow its feed scroller to shrink within the viewport'
);
assert.match(
  appSource,
  /<div className=\"custom-scrollbar flex-1 min-h-0 overflow-y-auto\">/,
  'feed scroller should own vertical scrolling inside the viewport-locked app shell'
);

if (process.argv.includes('--write-fixture')) {
  const rootDir = process.cwd();
  const distAssetsDir = path.join(rootDir, 'dist', 'assets');
  const cssAsset = fs.readdirSync(distAssetsDir).find((file) => file.endsWith('.css'));

  if (!cssAsset) {
    throw new Error('No built CSS asset found in dist/assets. Run `npm run build` first.');
  }

  const fixtureMarkup = renderToStaticMarkup(
    <main className="wireframe-grid min-h-screen p-10">
      <div className="mx-auto max-w-[1800px] space-y-8">
        <BreakingAlert item={sampleItem} />
        <section className="grid grid-cols-2 gap-8">
          <NewsCard item={sampleItem} featured />
          <NewsCard item={socialItem} />
          <NewsCard item={githubItem} />
          <NewsCard item={sampleItem} />
        </section>
      </div>
    </main>
  );

  const fixtureHtml = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Wireframe Fixture</title>
    <link rel="stylesheet" href="${path.join(rootDir, 'dist', 'assets', cssAsset)}" />
  </head>
  <body>${fixtureMarkup}</body>
</html>`;

  fs.writeFileSync('/tmp/wireframe-fixture.html', fixtureHtml, 'utf8');
  console.log('fixture written to /tmp/wireframe-fixture.html');
}

console.log('wireframe readability render checks passed');
