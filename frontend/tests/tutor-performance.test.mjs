import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { buildSync } from 'esbuild';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const require = createRequire(import.meta.url);
const compiled = buildSync({ entryPoints: [fileURLToPath(new URL('../src/TutorPerformance.tsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react/jsx-runtime'] });
const module = { exports: {} };
new Function('require', 'module', 'exports', compiled.outputFiles[0].text)(require, module, module.exports);
const { TutorPerformance } = module.exports;
const render = props => renderToStaticMarkup(React.createElement(TutorPerformance, props));

test('old answers without metrics remain compatible', () => {
  assert.equal(render({}), '');
});

test('missing values are unavailable; a measured zero is shown as zero', () => {
  const html = render({ data: { model: 'Test', provider: 'ollama', cache_ratio: 0, load_seconds: 0 } });
  assert.match(html, /Prompt-Cache<\/dt><dd>0 %/);
  assert.match(html, /Modell laden<\/dt><dd>0 s/);
  assert.match(html, /Prefill<\/dt><dd>nicht verfügbar/);
  assert.doesNotMatch(html, /<details[^>]*open/);
});

test('browser arrival, visible hub text and thinking arrival stay separate', () => {
  const html = render({ arrival: 8, data: { model: 'Test', provider: 'bonsai', ttft_seconds: 7,
    first_token_seconds: 2, cache_ratio: NaN, decode_tokens_per_second: Infinity } });
  assert.match(html, /Erster Antworttext im Browser<\/dt><dd>8 s/);
  assert.match(html, /TTFT\)<\/dt><dd>7 s/);
  assert.match(html, /inkl. Nachdenken\)<\/dt><dd>2 s/);
  assert.doesNotMatch(html, /NaN|Infinity/);
});
