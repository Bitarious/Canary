import { esc } from './panel.js';

const TITLES = { 'hdd-rising': 'Rising signal', 'hdd-stable': 'Stable control', 'hdd-model_mismatch': 'Model mismatch' };
const CHANNEL_LABELS = { smart_5_raw: 'Reallocated sectors', smart_187_raw: 'Reported uncorrectable errors', smart_194_raw: 'Temperature counter', smart_197_raw: 'Pending sectors' };

function chart(channel, dates, index) {
  const values = channel.values;
  const low = Math.min(...values), high = Math.max(...values), span = high - low || 1;
  const y = v => 108 - ((v - low) / span) * 94;
  const points = values.map((v, i) => `${4 + i * 492 / (values.length - 1)},${y(v)}`).join(' ');
  const summary = `${values.length} daily raw observations. First ${values[0]}, last ${values.at(-1)}, minimum ${low}, maximum ${high}.`;
  return `<figure class="raw-chart"><figcaption><strong>${esc(CHANNEL_LABELS[channel.name])}</strong><code>${esc(channel.name)}</code></figcaption>
    <div class="chart-plot"><div class="chart-values" aria-hidden="true"><span>${high}</span><span>${low}</span></div>
    <svg viewBox="0 0 500 120" role="img" aria-labelledby="chart-title-${index} chart-desc-${index}"><title id="chart-title-${index}">${esc(channel.name)} raw measurements</title><desc id="chart-desc-${index}">${summary} From ${dates[0]} to ${dates.at(-1)}.</desc>
      <path d="M4 14V108H496" fill="none" stroke="currentColor" opacity=".3"/><path d="M4 61H496M4 14H496" stroke="currentColor" opacity=".1"/>
      <polyline points="${points}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>
    </svg></div><div class="chart-dates" aria-hidden="true"><span>${dates[0]}</span><span>${dates.at(-1)}</span></div>
    <p>${summary} Raw source units.</p></figure>`;
}

export async function renderEvidence(el, id, api) {
  const restoreCaseFocus = !!document.activeElement.closest?.('.case-tabs, .evidence-recovery');
  const status = document.getElementById('viewStatus');
  status.textContent = 'Checking saved HDD evidence.';
  const request = Symbol();
  el._request = request;
  el.innerHTML = '<div class="evidence-wrap"><p role="status">Checking saved HDD evidence…</p></div>';
  try {
    const [catalog, detail] = await Promise.all([api('/api/cases'), api(`/api/cases/${encodeURIComponent(id)}`)]);
    if (el._request !== request) return;
    const c = detail.case, m = detail.model, e = detail.evaluation;
    const mismatch = !c.evaluation_reference.exact_match;
    el.innerHTML = `<div class="evidence-wrap">
      <div class="evidence-heading"><div><div class="eyebrow">Released test · Backblaze HDD</div><h1>Real signals. Saved model output.</h1><p>Inspect one unseen drive, its numerical input, and the exact saved answer.</p></div><a class="btn ghost" href="#/site/site-a">Open synthetic 3D twin →</a></div>
      <nav class="case-tabs" aria-label="Saved HDD cases">${catalog.cases.map(item => `<a class="${item.case_id === id ? 'selected' : ''}" ${item.case_id === id ? 'aria-current="page"' : ''} href="#/evidence/${item.case_id}">${TITLES[item.case_id]}</a>`).join('')}</nav>
      <div class="case-meta"><h2>${TITLES[id]}</h2><span>${esc(c.source.drive_id)}</span><span>${esc(c.window.start)} to ${esc(c.window.as_of)}</span><span>Input cutoff ${esc(c.window.as_of)}</span></div>
      <div class="evidence-columns"><div class="raw-charts">${c.window.channels.map((ch, i) => chart(ch, c.window.dates, i)).join('')}</div>
      <div class="model-answer"><div class="eyebrow">Saved model output</div><h2>${esc(m.name)}</h2><p class="answer-source">Saved inference from the selected trained checkpoint. No inference runs in this demo.</p><blockquote>${esc(c.inference.output_text)}</blockquote>
      <div class="reference ${mismatch ? 'mismatch' : ''}"><h3>${mismatch ? 'Model–reference mismatch' : 'Matches the weak reference'}</h3><p>${mismatch ? 'The model calls smart_194_raw falling. The weak reference calls it fluctuating without a clear net trend.' : 'This saved answer matches the separate weak-rule target for these channels.'}</p><details ${mismatch ? 'open' : ''}><summary>Separate evaluation reference</summary><p>${esc(c.evaluation_reference.weak_rule_target)}</p><p>This weak-rule label is separate from the model input. It is not a failure outcome.</p></details></div>
      <p class="evidence-limit">${esc(detail.limitation)} No failure probability, failure window, or confidence is supplied for this case.</p></div></div>
      <details class="provenance"><summary>Source, exact model input, and checkpoint provenance</summary><dl><dt>Dataset</dt><dd>Backblaze Drive Stats · released test</dd><dt>Source manifest SHA-256</dt><dd><code>${esc(c.source.dataset_manifest_sha256)}</code></dd><dt>Input SHA-256, recomputed</dt><dd><code>${esc(c.inference.input_sha256)}</code></dd><dt>Checkpoint SHA-256, recorded provenance</dt><dd><code>${esc(c.inference.checkpoint_sha256)}</code></dd><dt>Case bundle SHA-256, verified</dt><dd><code>${esc(detail.integrity.bundle_sha256)}</code></dd></dl><p>The server verifies the source bundle and all three input hashes. It does not rehash checkpoint weights.</p><h3>Exact numerical model input</h3><pre>${esc(JSON.stringify(c.model_inputs, null, 2))}</pre></details>
      <section class="evidence-evaluation"><h2>What the frozen HDD test measured</h2><div class="eval-stats"><div><strong>${e.channel_agreement_percent}%</strong><span>channel agreement with weak labels</span></div><div><strong>${e.channel_labels.toLocaleString()}</strong><span>channel labels · ${e.unseen_drives.toLocaleString()} unseen drives</span></div><div><strong>${e.zero_input_percent}%</strong><span>zero-input result · ${e.constant_baseline_percent}% constant baseline</span></div></div><p>${m.total_parameters.toLocaleString()} total parameters. ${m.trainable_parameters.toLocaleString()} trained parameters in the ${esc(m.trainable_scope)}.</p><p>${esc(detail.selection)}</p><p>Signal descriptions are evaluated. Failure prediction and maintenance timing remain unvalidated.</p></section>
    </div>`;
    status.textContent = `${TITLES[id]} loaded. Saved model output. ${mismatch ? 'The model differs from the weak reference.' : 'The answer matches the weak reference.'}`;
    if (restoreCaseFocus && document.activeElement === document.body && !el.hidden) {
      el.querySelector('.case-tabs [aria-current="page"]')?.focus({ preventScroll: true });
    }
  } catch (error) {
    if (el._request !== request) return;
    el.innerHTML = `<div class="evidence-wrap"><h1>Saved evidence unavailable</h1><p role="alert">${esc(error.message)}</p><div class="evidence-recovery"><button class="btn primary" data-retry-evidence>Retry saved evidence</button><a class="btn ghost" href="#/site/site-a">Return to Twin</a></div></div>`;
    status.textContent = 'Saved evidence unavailable. Retry or return to Twin.';
    if (restoreCaseFocus && document.activeElement === document.body && !el.hidden) el.querySelector('[data-retry-evidence]').focus();
    el.querySelector('[data-retry-evidence]').addEventListener('click', () => renderEvidence(el, id, api));
  }
}
