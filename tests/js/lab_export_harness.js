'use strict';
/**
 * Loads the REAL inline <script> block from intelligence-lab/static/index.html
 * into a Node vm context, so tests exercise the actual production export
 * mapper (exportCSV()'s `cols` array and its helper functions) rather than a
 * reimplementation of it.
 *
 * The script is written for a browser; at *load* time (top-level statements:
 * variable declarations, function declarations, and the final
 * `window.addEventListener('DOMContentLoaded', boot)` registration) it never
 * touches the DOM, so a minimal stub of `window`/`document` is enough to eval
 * it without a real browser. Nothing in this harness calls boot() or renders
 * anything — it only needs the function *definitions* to exist on the
 * context so tests can call them directly with constructed row objects.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const INDEX_HTML = path.join(__dirname, '..', '..', 'intelligence-lab', 'static', 'index.html');

function extractInlineScript(html) {
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  if (!scripts.length) throw new Error('No inline <script> block found in index.html');
  // The app logic is the largest inline block; the sector-ui-patch tag is external (src=...), not inline.
  return scripts.reduce((a, b) => (a[1].length >= b[1].length ? a : b))[1];
}

function loadLabExportContext() {
  const html = fs.readFileSync(INDEX_HTML, 'utf8');
  const src = extractInlineScript(html);

  const noop = () => {};
  const stubEl = {
    addEventListener: noop, appendChild: noop, removeChild: noop,
    classList: { add: noop, remove: noop, toggle: noop },
    style: {}, innerHTML: '', textContent: '',
  };
  const sandbox = {
    window: { addEventListener: noop, location: { href: '' } },
    document: {
      addEventListener: noop,
      getElementById: () => stubEl,
      querySelectorAll: () => [],
      createElement: () => ({ ...stubEl, click: noop, href: '', download: '' }),
      body: stubEl,
    },
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    URL: { createObjectURL: () => '', revokeObjectURL: noop },
    Blob: function Blob() {},
    console,
    alert: noop,
  };
  sandbox.globalThis = sandbox;
  const ctx = vm.createContext(sandbox);
  vm.runInContext(src, ctx, { filename: 'index.html-inline-script' });
  return ctx;
}

module.exports = { loadLabExportContext };
