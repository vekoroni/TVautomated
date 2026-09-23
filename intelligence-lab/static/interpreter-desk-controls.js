/* Advisory Lab-to-Interpreter workflow. No screenshots, broker tools or capital actions. */
const INTERPRETER_SELECTED = new Set();
let INTERPRETER_BUSY = false;

function updateInterpreterSelection() {
  const button = document.getElementById('interpreter-launch');
  if (!button) return;
  button.textContent = `Interpreter reports (${INTERPRETER_SELECTED.size}/5)`;
  button.disabled = INTERPRETER_BUSY;
}

function clearInterpreterSelection() {
  INTERPRETER_SELECTED.clear();
  document.querySelectorAll('input[data-interpreter-ticker]').forEach(input => { input.checked = false; });
  const panel = document.getElementById('interpreter-panel');
  if (panel) { panel.replaceChildren(); panel.style.display = 'none'; }
  const status = document.getElementById('interpreter-status');
  if (status) status.textContent = '';
  updateInterpreterSelection();
}

function selectInterpreterTicker(input) {
  const ticker = input.dataset.interpreterTicker;
  const status = document.getElementById('interpreter-status');
  if (input.checked && INTERPRETER_SELECTED.size >= 5) {
    input.checked = false;
    status.textContent = 'Select at most five Interpreter tickers.';
    return;
  }
  if (input.checked) INTERPRETER_SELECTED.add(ticker);
  else INTERPRETER_SELECTED.delete(ticker);
  updateInterpreterSelection();
  status.textContent = INTERPRETER_SELECTED.size
    ? `Selected for advisory reports: ${[...INTERPRETER_SELECTED].join(', ')}`
    : 'Select one to five tickers from the Lab table.';
}

async function interpreterRequest(path, body) {
  const response = await fetch(`/api/interpreter/${path}`, body ? {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  } : {});
  let data;
  try { data = await response.json(); }
  catch (_) { throw new Error('Interpreter service returned invalid JSON.'); }
  if (!response.ok) throw new Error(data.error || `Interpreter request failed (${response.status}).`);
  return data;
}

function interpreterText(parent, tag, content) {
  const element = document.createElement(tag);
  element.textContent = content == null ? '' : String(content);
  parent.appendChild(element);
  return element;
}

function showInterpreterReport(report) {
  const panel = document.getElementById('interpreter-panel');
  panel.style.display = 'block';
  const card = document.createElement('section');
  card.style.cssText = 'border:1px solid var(--border);padding:12px;margin-bottom:12px;white-space:pre-wrap';
  interpreterText(card, 'h3', `${report.ticker} · ${report.phase} · ${report.source_action || 'UNKNOWN'}`);
  interpreterText(card, 'p', 'ADVISORY ONLY — not trading or capital permission. Evening thesis remains frozen; Morning evidence is a separate update.');
  if (report.evidence_digest && report.evidence_digest.eod_technical_health !== 'PASS')
    interpreterText(card, 'p', `Evening technical health: ${report.evidence_digest.eod_technical_health}. Review source gaps before acting.`);
  if (report.evidence_digest) {
    const facts = document.createElement('details');
    interpreterText(facts, 'summary', 'Governed source facts and evidence cutoff');
    interpreterText(facts, 'p', `Cutoff: ${report.evidence_digest.evidence_cutoff_utc || 'unknown'} · EOD bundle: ${report.eod_bundle_id || 'unknown'} · Morning bundle: ${report.morning_bundle_id || 'none'}`);
    interpreterText(facts, 'pre', JSON.stringify({
      eod: report.evidence_digest.eod_fields,
      morning: report.evidence_digest.morning_evidence,
      omitted: report.evidence_digest.omitted_fields
    }, null, 2));
    card.appendChild(facts);
  }
  interpreterText(card, 'p', report.executive_summary);
  for (const section of report.sections || []) {
    const details = document.createElement('details');
    const summary = interpreterText(details, 'summary', `${section.key.toUpperCase()} · ${section.evidence_class} · ${section.evidence_refs.join(', ')}`);
    summary.style.cursor = 'pointer';
    interpreterText(details, 'p', section.text);
    card.appendChild(details);
  }
  if ((report.external_events || []).length) {
    interpreterText(card, 'h4', 'Sourced external events');
    interpreterText(card, 'small', `Provider retrieval: ${report.provider_retrieved_at_utc || 'unknown'}`);
    for (const event of report.external_events)
      interpreterText(card, 'p', `${event.asof_utc} · ${event.summary} · ${event.url}`);
  }
  if ((report.unresolved || []).length) interpreterText(card, 'p', `Unresolved: ${report.unresolved.join(' · ')}`);
  const label = interpreterText(card, 'label', `Ask about ${report.ticker} (e.g. crowd near a wall, buyers/sellers, evidence conflict): `);
  const input = document.createElement('input');
  input.type = 'text'; input.maxLength = 500; input.style.cssText = 'width:70%;margin:8px;background:var(--bg);color:var(--text);border:1px solid var(--border);padding:7px';
  label.appendChild(input);
  const ask = interpreterText(card, 'button', 'Ask GPT');
  ask.className = 'fb';
  const answer = document.createElement('div');
  answer.style.cssText = 'padding:8px;color:var(--text2)';
  ask.onclick = async () => {
    if (!input.value.trim()) return;
    if (!window.confirm(`Ask GPT about ${report.ticker}? This is a paid advisory request using the frozen report; no trading authority is granted.`)) return;
    ask.disabled = true; answer.textContent = 'Checking the frozen report and its evidence…';
    try {
      const result = await interpreterRequest('ask', {
        run_id: report.run_id, ticker: report.ticker,
        report_id: report.report_id, question: input.value.trim(), confirmed: true
      });
      answer.replaceChildren();
      interpreterText(answer, 'p', `${result.evidence_class}: ${result.answer}`);
      if (result.limitations.length) interpreterText(answer, 'p', `Limits: ${result.limitations.join(' · ')}`);
      interpreterText(answer, 'small', `Evidence: ${result.evidence_refs.join(', ') || 'none'}`);
    } catch (error) { answer.textContent = error.message; }
    finally { ask.disabled = false; }
  };
  card.appendChild(answer);
  panel.appendChild(card);
}

async function previewInterpreterDesk() {
  if (INTERPRETER_BUSY) return;
  const status = document.getElementById('interpreter-status');
  const run = RUN_DATA && RUN_DATA.run_id;
  const tickers = [...INTERPRETER_SELECTED];
  if (!run || !tickers.length || tickers.length > 5) {
    status.textContent = 'Load a run and select one to five tickers.'; return;
  }
  INTERPRETER_BUSY = true; updateInterpreterSelection();
  try {
    const control = await interpreterRequest('control');
    const preview = await interpreterRequest('preview', {run_id: run, tickers});
    const cost = preview.batch_cost_bound_usd == null
      ? 'Unavailable until model and tool pricing are configured'
      : `Configured conservative bound $${preview.batch_cost_bound_usd.toFixed(4)} for this batch (not a billing guarantee)`;
    const message = `Run ${run}\n${preview.entries.map(e => `${e.ticker}: ${e.phase}, ${e.source_action}, ${e.input_chars} input characters`).join('\n')}\n` +
      `Model: ${control.model_id}\nCost: ${cost}. This will make paid provider calls.\n` +
      'Reports are advisory only; no screenshots, orders, or capital permission.';
    status.textContent = message;
    if (!control.provider_ready) throw new Error('GPT provider is not configured on this machine. Configure OPENAI_API_KEY and AVSHUNTER_INTERPRETER_MODEL locally.');
    if (!window.confirm(message + '\n\nLaunch these reports?')) return;
    if (!RUN_DATA || RUN_DATA.run_id !== run) throw new Error('Displayed run changed; select again.');
    status.textContent = `Generating ${tickers.length} report(s), one ticker at a time. Do not resubmit if connection is interrupted.`;
    const result = await interpreterRequest('reports', {run_id: run, tickers, confirmed: true});
    const panel = document.getElementById('interpreter-panel');
    panel.replaceChildren();
    let completed = 0;
    for (const item of result.results) {
      if (item.status === 'COMPLETE') { showInterpreterReport(item); completed++; }
      else interpreterText(panel, 'p', `${item.ticker}: ${item.status} — ${item.error || 'report unavailable'}`);
    }
    panel.style.display = 'block';
    const unresolved = result.results.length - completed;
    status.textContent = unresolved
      ? `${completed}/${tickers.length} advisory reports complete for run ${run}; ${unresolved} require review. No automatic retry.`
      : `${completed}/${tickers.length} advisory reports complete. Results stay bound to run ${run}.`;
  } catch (error) { status.textContent = error.message; }
  finally { INTERPRETER_BUSY = false; updateInterpreterSelection(); }
}

window.addEventListener('load', updateInterpreterSelection);
