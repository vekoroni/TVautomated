/**
 * AVSHUNTER Intelligence Lab — Sector UI Patch v1.0
 * ═══════════════════════════════════════════════════════════════════════════
 * DROP THIS INTO: intelligence-lab/static/
 * ADD TO index.html <head>: <script src="sector_patch.js" defer></script>
 *
 * What this adds without modifying index.html internals:
 *   1. Sector colour-coded badges in the signals table
 *   2. Sector column header injected next to TICKER
 *   3. Sector summary concentration panel above the signals table
 *   4. Regime alerts panel for open positions (when alerts exist)
 *   5. Dynamic hold display alongside static time stop in order cards
 *   6. Sector filter dropdown in the filter bar
 * ═══════════════════════════════════════════════════════════════════════════
 */

(function() {
  'use strict';

  // ── SECTOR COLOUR MAP ────────────────────────────────────────────────────
  const SECTOR_COLOURS = {
    'TECH': { bg: '#1e3a5f', text: '#60a5fa', border: '#3b82f6' },
    'HLTH': { bg: '#1a4731', text: '#34d399', border: '#10b981' },
    'FINL': { bg: '#3b2f00', text: '#fbbf24', border: '#f59e0b' },
    'ENRG': { bg: '#3b1a00', text: '#fb923c', border: '#f97316' },
    'UTIL': { bg: '#2d1f5e', text: '#a78bfa', border: '#8b5cf6' },
    'REIT': { bg: '#3b2a2a', text: '#f87171', border: '#ef4444' },
    'DISC': { bg: '#1a3a3a', text: '#22d3ee', border: '#06b6d4' },
    'STPL': { bg: '#2a3a1a', text: '#86efac', border: '#4ade80' },
    'COMM': { bg: '#3a1a3a', text: '#e879f9', border: '#d946ef' },
    'MATL': { bg: '#2a2a1a', text: '#d4d496', border: '#a3a319' },
    'INDS': { bg: '#1a2a3a', text: '#7dd3fc', border: '#38bdf8' },
    'ETF':  { bg: '#1a1a2a', text: '#94a3b8', border: '#475569' },
    'N/A':  { bg: '#1a1a1a', text: '#6b7280', border: '#374151' },
  };

  function sectorBadgeHTML(short) {
    const c = SECTOR_COLOURS[short] || SECTOR_COLOURS['N/A'];
    return `<span style="
      display:inline-block;padding:2px 7px;border-radius:3px;
      font-size:10px;font-weight:700;letter-spacing:.05em;
      font-family:'Courier New',monospace;
      background:${c.bg};color:${c.text};border:1px solid ${c.border};
      white-space:nowrap;
    ">${short || 'N/A'}</span>`;
  }

  // ── CSS INJECTION ────────────────────────────────────────────────────────
  const style = document.createElement('style');
  style.textContent = `
    .avs-sector-panel {
      background:#111827;border:1px solid #1f2937;border-radius:6px;
      padding:12px 16px;margin:0 0 16px 0;
    }
    .avs-sector-panel h4 {
      margin:0 0 10px;font-size:11px;font-weight:700;letter-spacing:.1em;
      color:#6b7280;text-transform:uppercase;
    }
    .avs-sector-row {
      display:flex;align-items:center;gap:10px;padding:4px 0;
      border-bottom:1px solid #1f2937;font-size:12px;
    }
    .avs-sector-row:last-child { border-bottom:none; }
    .avs-sector-name { flex:1;color:#d1d5db;font-size:11px; }
    .avs-sector-count { min-width:80px;color:#9ca3af;font-size:11px; }
    .avs-sector-ev { min-width:70px;font-size:11px; }
    .avs-ev-pos { color:#34d399; }
    .avs-ev-neg { color:#f87171; }
    .avs-conc-normal  { color:#6b7280;font-size:11px; }
    .avs-conc-medium  { color:#fbbf24;font-size:11px; }
    .avs-conc-high    { color:#ef4444;font-size:11px;font-weight:700; }
    .avs-regime-panel {
      background:#1a0f0f;border:1px solid #7f1d1d;border-radius:6px;
      padding:12px 16px;margin:0 0 16px 0;
    }
    .avs-regime-panel h4 { margin:0 0 10px;font-size:11px;font-weight:700;
      letter-spacing:.1em;color:#ef4444;text-transform:uppercase; }
    .avs-regime-alert { padding:6px 0;border-bottom:1px solid #2d1515;font-size:12px; }
    .avs-regime-alert:last-child { border-bottom:none; }
    .avs-alert-high   { color:#f87171; }
    .avs-alert-medium { color:#fbbf24; }
    .avs-alert-info   { color:#60a5fa; }
    .avs-dyn-hold { font-size:11px;color:#9ca3af;margin-top:2px; }
    .avs-dyn-viable   { color:#34d399; }
    .avs-dyn-tight    { color:#fbbf24; }
    .avs-dyn-imminent { color:#ef4444;font-weight:700; }
    .avs-sector-filter { margin-left:8px; }
    .avs-sector-filter select {
      background:#1f2937;color:#d1d5db;border:1px solid #374151;
      border-radius:4px;padding:4px 8px;font-size:12px;
    }
  `;
  document.head.appendChild(style);

  // ── UTILITY: wait for an element matching selector ───────────────────────
  function waitFor(selector, cb, maxMs = 8000) {
    const start = Date.now();
    const check = () => {
      const el = document.querySelector(selector);
      if (el) { cb(el); return; }
      if (Date.now() - start < maxMs) setTimeout(check, 300);
    };
    check();
  }

  // ── SECTOR SUMMARY PANEL ─────────────────────────────────────────────────
  function renderSectorPanel(data) {
    const existing = document.getElementById('avs-sector-panel');
    if (existing) existing.remove();

    if (!data || !data.sector_summary || data.total_execute === 0) return;

    const panel = document.createElement('div');
    panel.id = 'avs-sector-panel';
    panel.className = 'avs-sector-panel';

    const rows = data.sector_summary
      .filter(s => s.execute_count > 0)
      .sort((a, b) => b.execute_count - a.execute_count);

    const highConc = rows.filter(r => r.concentration_flag === 'HIGH');
    const titleExtra = highConc.length
      ? ` — ⚠️ HIGH CONCENTRATION: ${highConc.map(r => r.sector_short).join(', ')}`
      : '';

    panel.innerHTML = `
      <h4>Sector Distribution — ${data.total_execute} Execute Signals
          Across ${data.sectors_represented} Sectors${titleExtra}</h4>
      ${rows.map(s => `
        <div class="avs-sector-row">
          ${sectorBadgeHTML(s.sector_short)}
          <span class="avs-sector-name">${s.sector}</span>
          <span class="avs-sector-count">${s.execute_count}E ${s.ewr_count > 0 ? '+' + s.ewr_count + 'EWR' : ''} | ${s.put_count}P/${s.call_count}C</span>
          <span class="avs-sector-ev ${s.avg_ev > 0 ? 'avs-ev-pos' : 'avs-ev-neg'}">
            Legacy EV ${s.avg_ev > 0 ? '+' : ''}${s.avg_ev.toFixed(3)}
          </span>
          <span class="avs-conc-${s.concentration_flag.toLowerCase()}">
            ${s.concentration_pct}%${s.concentration_flag === 'HIGH' ? ' ⚠' : ''}
          </span>
          ${s.sector_etf ? `<span style="color:#4b5563;font-size:10px">${s.sector_etf}</span>` : ''}
        </div>
      `).join('')}
    `;

    // Insert above the signals table or at the top of the main content
    const target = document.querySelector(
      '[data-section="signals"], .signals-section, #signals-section, table, .signal-table'
    );
    if (target) {
      target.parentNode.insertBefore(panel, target);
    } else {
      document.body.appendChild(panel);
    }
  }

  // ── REGIME ALERTS PANEL ──────────────────────────────────────────────────
  function renderRegimePanel(data) {
    const existing = document.getElementById('avs-regime-panel');
    if (existing) existing.remove();

    if (!data || !data.alerts || data.alerts.length === 0) return;

    const panel = document.createElement('div');
    panel.id = 'avs-regime-panel';
    panel.className = 'avs-regime-panel';

    panel.innerHTML = `
      <h4>🚨 Regime Alerts — ${data.alert_count} Open Position(s) Flagged
          | Current: ${data.current_regime}</h4>
      ${data.alerts.map(a => `
        <div class="avs-regime-alert">
          <span class="avs-alert-${a.severity.toLowerCase()}">
            <strong>${a.ticker}</strong> ${a.direction} — ${a.alert_type}
          </span><br/>
          <span style="color:#9ca3af;font-size:11px">${a.message}</span><br/>
          <span style="color:#6b7280;font-size:11px">→ ${a.recommended_action}</span>
        </div>
      `).join('')}
    `;

    const sectorPanel = document.getElementById('avs-sector-panel');
    if (sectorPanel) {
      sectorPanel.parentNode.insertBefore(panel, sectorPanel);
    } else {
      const target = document.querySelector('[data-section="signals"], table, .signal-table');
      if (target) target.parentNode.insertBefore(panel, target);
    }
  }

  // ── SECTOR COLUMN INJECTION ──────────────────────────────────────────────
  // Observes for signal table rows being rendered and injects sector badge
  let lastSignalData = null;

  function injectSectorIntoTable() {
    // Find table rows that have ticker data
    const rows = document.querySelectorAll('tr[data-ticker], [class*="signal-row"], [class*="ticker-row"]');
    rows.forEach(row => {
      if (row.getAttribute('data-sector-injected')) return;
      const ticker = row.getAttribute('data-ticker') ||
                     row.querySelector('[class*="ticker"]')?.textContent?.trim();
      if (!ticker || !lastSignalData) return;

      const sig = lastSignalData.find(s => s.ticker === ticker);
      if (!sig) return;

      const short = sig.sector_short || 'N/A';
      const badge = document.createElement('td');
      badge.innerHTML = sectorBadgeHTML(short);
      badge.style.padding = '4px 8px';
      badge.title = `${sig.sector || 'Unknown'} | ${sig.industry || ''}`;

      const firstTd = row.querySelector('td');
      if (firstTd) {
        row.insertBefore(badge, firstTd.nextSibling);
        row.setAttribute('data-sector-injected', '1');
      }
    });
  }

  // ── SECTOR FILTER ────────────────────────────────────────────────────────
  function injectSectorFilter() {
    const existing = document.getElementById('avs-sector-filter');
    if (existing) return;

    const filterBar = document.querySelector(
      '[class*="filter-bar"], [class*="filters"], .filter-row, [data-section="filters"]'
    );
    if (!filterBar) return;

    const wrapper = document.createElement('span');
    wrapper.className = 'avs-sector-filter';
    wrapper.id = 'avs-sector-filter';
    wrapper.innerHTML = `
      <select id="avs-sector-select" title="Filter by sector">
        <option value="">All Sectors</option>
        <option value="TECH">Technology</option>
        <option value="HLTH">Health Care</option>
        <option value="FINL">Financials</option>
        <option value="ENRG">Energy</option>
        <option value="UTIL">Utilities</option>
        <option value="REIT">Real Estate</option>
        <option value="DISC">Consumer Disc.</option>
        <option value="STPL">Consumer Staples</option>
        <option value="COMM">Communication</option>
        <option value="MATL">Materials</option>
        <option value="INDS">Industrials</option>
      </select>
    `;

    wrapper.querySelector('select').addEventListener('change', (e) => {
      const selected = e.target.value;
      document.querySelectorAll('tr[data-ticker]').forEach(row => {
        const ticker = row.getAttribute('data-ticker');
        if (!ticker || !lastSignalData) { row.style.display = ''; return; }
        const sig = lastSignalData.find(s => s.ticker === ticker);
        if (!selected || !sig) { row.style.display = ''; return; }
        row.style.display = sig.sector_short === selected ? '' : 'none';
      });
    });

    filterBar.appendChild(wrapper);
  }

  // ── FETCH AND INITIALISE ─────────────────────────────────────────────────
  function fetchAndRender() {
    // Sector summary
    fetch('/api/sector_summary')
      .then(r => r.ok ? r.json() : {ok:false})
      .then(data => { if (data.ok) renderSectorPanel(data); })
      .catch(() => {});

    // Regime alerts
    fetch('/api/regime_alerts')
      .then(r => r.ok ? r.json() : {ok:false})
      .then(data => { if (data.ok && data.alert_count > 0) renderRegimePanel(data); })
      .catch(() => {});

    // Main lab boot owns /api/run loading. Avoid duplicate heavy run fetch here.
  }

  // ── MUTATION OBSERVER — re-inject when table updates ────────────────────
  function startObserver() {
    const observer = new MutationObserver(() => {
      if (lastSignalData) {
        injectSectorIntoTable();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // ── BOOT ─────────────────────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      fetchAndRender();
      setTimeout(fetchAndRender, 15000);
      startObserver();
    });
  } else {
    fetchAndRender();
    setTimeout(fetchAndRender, 15000);
    startObserver();
  }

  // Refresh panels every 5 minutes (in case run updates)
  setInterval(fetchAndRender, 300_000);

  console.log('[AVSHUNTER Sector Patch] v1.0 loaded');
})();
