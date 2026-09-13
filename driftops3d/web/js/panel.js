const COLORS = { healthy: '#22c55e', watch: '#eab308', elevated: '#f97316', critical: '#ef4444' };
const EXPOSURE_STATUS = { LOW: 'healthy', MEDIUM: 'watch', HIGH: 'critical' };
const TYPE_LABEL = { cpu: 'Processor', gpu: 'Graphics', memory: 'Memory', storage: 'Storage', battery: 'Battery', cooling: 'Cooling', power: 'Power' };

export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (x, d = 0) => `${(x * 100).toFixed(x < 0.01 && x > 0 ? 1 : d)}%`;
const statusOf = h => (h >= 80 ? 'healthy' : h >= 65 ? 'watch' : h >= 45 ? 'elevated' : 'critical');
const cap = s => (s ? s[0].toUpperCase() + s.slice(1) : '');

export function timeAgo(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (!isFinite(s)) return '';
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 1.5) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

function ring(value, status, size = 92) {
  const r = size / 2 - 7, c = 2 * Math.PI * r;
  const color = COLORS[status] || '#8b9bb0';
  return `<div class="ring" style="width:${size}px;height:${size}px">
    <svg width="${size}" height="${size}">
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="rgba(148,178,214,.14)" stroke-width="7"/>
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="7" stroke-linecap="round"
        stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - value / 100)}" style="filter:drop-shadow(0 0 6px ${color}88);transition:stroke-dashoffset .8s ease"/>
    </svg>
    <div class="val"><div><div class="num">${Math.round(value)}</div><div class="of">/ 100</div></div></div>
  </div>`;
}

function badge(status, text) {
  return `<span class="badge s-${status}">${esc(text || status)}</span>`;
}

// ------------------------------------------------------------------------------------ overview

export function renderOverview(el, { machine, analysis, readings, scanning, error }) {
  if (error) {
    el.innerHTML = `<div class="eyebrow">Connection</div><h2>Server not reachable</h2>
      <p class="empty">${esc(error)}</p><p class="empty">Start it with <span class="mono">python server.py</span> and open
      <span class="mono">http://127.0.0.1:8765</span>.</p>`;
    return;
  }
  if (!machine) {
    el.innerHTML = `<div class="eyebrow">DriftOps</div><h2>No devices yet</h2>
      <p class="empty">Click <b>Benchmark this computer</b>, run <span class="mono">agent/collect.py</span> on another machine, or drop a telemetry JSON here.</p>`;
    return;
  }
  const m = machine.machine || {};
  const head = `<div class="eyebrow">${esc(cap(m.form_factor || 'device'))} · ${esc(m.role || '')}</div>
    <h2>${esc(m.label || m.hostname || machine.id)}</h2>
    <div class="sub">${esc([m.model, m.os].filter(Boolean).join(' · '))}</div>
    <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
      ${machine.source === 'demo' ? '<span class="chip demo-chip">demo data</span>' : '<span class="chip">live benchmark</span>'}
      <span class="chip">${machine.runs} run${machine.runs === 1 ? '' : 's'}</span>
      <span class="chip">last ${esc(timeAgo(machine.last_run))}</span>
    </div>`;

  if (scanning) {
    el.innerHTML = `${head}<div class="scan-state"><div class="spinner"></div>Scanning ${machine.components.length} components through the model…</div>`;
    return;
  }
  if (!analysis) {
    el.innerHTML = `${head}<h3>Components reported</h3>
      <div class="list">${machine.components.map(c => `<div class="item" style="cursor:default">
        <span class="dot" style="background:#5d6c80"></span>
        <div class="grow"><div class="name">${esc(c.name)}</div><div class="meta">${esc(TYPE_LABEL[c.type] || c.type)}</div></div></div>`).join('')}
      </div>
      <p class="empty" style="margin-top:14px">Press <b>Analyze</b> to run this telemetry through the DriftOps model.</p>`;
    return;
  }

  const o = analysis.overall;
  const byId = Object.fromEntries(analysis.components.map(c => [c.id, c]));
  const priority = analysis.priority.map(id => byId[id]).filter(Boolean).slice(0, 5);
  el.innerHTML = `${head}
    <div class="ring-row">${ring(o.health, o.status)}
      <div class="ring-meta"><div class="stage s-${o.status}">${esc(o.stage)}</div>
      <div class="sub">${esc(o.headline)}</div></div></div>
    <div class="counts">
      <div><b class="s-critical">${o.counts.critical}</b><span>Critical</span></div>
      <div><b class="s-elevated">${o.counts.elevated}</b><span>Elevated</span></div>
      <div><b class="s-watch">${o.counts.watch}</b><span>Watch</span></div>
      <div><b class="s-healthy">${o.counts.healthy}</b><span>Healthy</span></div>
    </div>
    <h3>${priority.length ? 'Fix first' : 'Components'}</h3>
    <div class="list">${(priority.length ? priority : analysis.components).map((c, i) => `
      <button class="item" data-id="${esc(c.id)}">
        <span class="rank">${priority.length ? i + 1 : '•'}</span>
        <div class="grow"><div class="name">${esc(c.name)}</div>
          <div class="meta">${pct(c.risk_7d)} 7-day risk · ${esc(c.failure_window.label)}</div></div>
        <span class="score s-${c.status}">${Math.round(c.health)}</span>
      </button>`).join('')}
    </div>
    ${readingsOverview(readings, analysis)}
    ${analysis.findings.length ? `<h3>Cross-component findings</h3>${analysis.findings.map(f => `<div class="finding"><b>${esc(f.title)}</b>${esc(f.text)}</div>`).join('')}` : ''}
    <p class="sub" style="margin-top:16px">Health and risk: <span class="mono">${esc(analysis.model)}</span> (rules) · ${analysis.runs_used} run${analysis.runs_used === 1 ? '' : 's'} of history · fleet percentiles use illustrative reference baselines.</p>`;
}

// ------------------------------------------------------------------------------------ component

export function renderComponent(el, c, simIndex, readings) {
  const conf = { high: 'High', medium: 'Medium', low: 'Low' }[c.confidence] || c.confidence;
  const fleet = c.evidence.find(e => e.fleet_percentile != null && e.impact > 0) || c.evidence.find(e => e.fleet_percentile != null);
  const trendArrow = c.trend === 'improving' ? '↗' : c.trend.includes('deteriorating') ? (c.accelerating ? '↓↓' : '↘') : c.trend === 'baseline' ? '•' : '→';
  const sim = c.wait_simulation;
  const si = simIndex ?? Math.max(0, sim.findIndex(w => w.recommended));
  const sel = sim[si];
  const maxRisk = Math.max(0.05, ...sim.map(w => w.risk));

  el.innerHTML = `
    <button class="close" aria-label="Close">✕</button>
    <div class="eyebrow">${esc(TYPE_LABEL[c.type] || c.type)} · priority #${c.priority_rank}</div>
    <h2>${esc(c.name)}</h2>
    ${badge(c.status)}
    <div class="ring-row">${ring(c.health, c.status)}
      <div class="ring-meta">
        <div class="stage s-${c.status}">${esc(c.stage)}</div>
        <div class="sub">Trajectory ${trendArrow} ${esc(c.trend)}${c.slope_per_day && c.trend !== 'baseline' ? ` (${c.slope_per_day > 0 ? '+' : ''}${c.slope_per_day}/day)` : ''}</div>
      </div>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="k">7-day failure risk</div><div class="v s-${riskStatus(c.risk_7d)}">${pct(c.risk_7d)}</div></div>
      <div class="kpi"><div class="k">Failure window</div><div class="v">${esc(c.failure_window.label)}</div></div>
      <div class="kpi"><div class="k">Confidence</div><div class="v">${esc(conf)}</div></div>
      <div class="kpi"><div class="k">Fleet percentile</div><div class="v">${fleet ? `${fleet.fleet_percentile}<small class="sub">th · ${esc(fleet.signal.toLowerCase())}</small>` : '—'}</div></div>
    </div>

    <h3>Health trajectory</h3>
    ${trajectoryChart(c)}

    <h3>Why</h3>
    <p class="narrative">${esc(c.summary)}</p>

    <h3>Evidence</h3>
    <div class="evidence">${c.evidence.length ? c.evidence.map(evidenceRow).join('') : '<div class="empty">No signals exposed for this component.</div>'}</div>

    ${modelReading(readings, c.id)}

    ${c.signals.length ? `<h3>Benchmark signals (latest run)</h3>${c.signals.map(s => sparkline(s, COLORS[c.status])).join('')}` : ''}

    <h3>Recommended action</h3>
    <div class="action"><div class="eyebrow">Next step</div>${esc(c.action)}</div>

    <h3>What happens if I wait?</h3>
    <div class="sim-tabs">${sim.map((w, i) => `<button class="sim-tab ${i === si ? 'active' : ''}" data-sim="${i}">
      ${w.recommended ? '<span class="rec">✓</span>' : ''}${esc(w.label.replace('In ', ''))}</button>`).join('')}</div>
    <div class="sim-out">
      <div class="kpi"><div class="k">Failure before maintenance</div><div class="v s-${riskStatus(sel.risk)}">${pct(sel.risk, 1)}</div></div>
      <div class="kpi"><div class="k">Operational exposure</div><div class="v s-${EXPOSURE_STATUS[sel.exposure]}">${esc(sel.exposure)}</div></div>
    </div>
    <div class="sim-bars">${sim.map((w, i) => `<div class="${i === si ? 'active' : ''}" title="${esc(w.label)}: ${pct(w.risk, 1)}"
      style="height:${Math.max(4, (w.risk / maxRisk) * 100)}%;background:${COLORS[EXPOSURE_STATUS[w.exposure]]}"></div>`).join('')}</div>
    <p class="sub" style="margin-top:8px">${simSentence(sim, sel)}</p>
    ${c.associations.length ? `<h3>Associated with</h3>${c.associations.map(a => `<div class="finding"><b>${esc(a.title)}</b>${esc(a.text)}</div>`).join('')}` : ''}
  `;
}

// ------------------------------------------------------------------------------------ trained model readings

const PATTERN_ICON = { constant: '→', rising: '↗', falling: '↘', 'fluctuating without a clear net trend': '∿', 'counter reset or decrease': '↺' };
const RUN_LABEL = { hdd: 'HDD', cpu: 'CPU', gpu: 'GPU' };

function parsePatterns(text) {
  return Object.fromEntries(String(text || '').replace(/\.$/, '').split(';').map(p => p.split(':').map(x => x.trim()))
    .filter(([k, v]) => k && v));
}

function readingsOverview(readings, analysis) {
  if (!readings) return '';
  if (readings.loading) return `<h3>Trained model readings</h3><div class="scan-state small"><div class="spinner"></div>Sending benchmark windows to the OpenTSLM component models…</div>`;
  if (readings.error) return `<h3>Trained model readings</h3><p class="empty">Model worker error: ${esc(readings.error)}</p>`;
  const names = Object.fromEntries(analysis.components.map(c => [c.id, c.name]));
  const rows = Object.entries(readings);
  if (!rows.length) return `<h3>Trained model readings</h3><p class="empty">No component of this device matches a released model (HDD, CPU, GPU).</p>`;
  return `<h3>Trained model readings</h3><div class="list">${rows.map(([id, r]) => `
    <button class="item" data-id="${esc(id)}">
      <span class="mr-dot ${esc(r.status)}"></span>
      <div class="grow"><div class="name">${esc(names[id] || id)}</div>
        <div class="meta">${r.status === 'ok' ? esc(r.channels.map(ch => `${ch.replace(/_/g, ' ')}: ${r.patterns[ch] || 'no answer'}`).join('; ')) : esc(r.status === 'insufficient' ? 'not enough samples' : 'model unavailable')}</div></div>
      <span class="chip">${esc(RUN_LABEL[r.component] || r.component)}</span>
    </button>`).join('')}</div>`;
}

function modelReading(readings, id) {
  if (!readings) return '';
  const head = '<h3>Trained model reading <span class="chip mr-chip">OpenTSLM</span></h3>';
  if (readings.loading) return `${head}<div class="scan-state small"><div class="spinner"></div>Running the trained model on this benchmark…</div>`;
  if (readings.error) return `${head}<p class="empty">Model worker error: ${esc(readings.error)}</p>`;
  const r = readings[id];
  if (!r) return '';
  if (r.status !== 'ok') {
    return `${head}<div class="model-reading muted"><div class="mr-status">${r.status === 'insufficient' ? 'Not enough data for the model' : 'Model unavailable'}</div>
      <div class="detail">${esc(r.reason)}</div><div class="mr-foot">${esc(r.scope)}</div></div>`;
  }
  const model = r.patterns || parsePatterns(r.answer), rules = parsePatterns(r.reference);
  const rows = r.channels.map((ch, i) => {
    const got = model[ch] || 'no answer', ref = rules[ch];
    const vals = r.values[i], min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
    const path = vals.map((v, j) => `${j ? 'L' : 'M'}${(j / 27 * 120).toFixed(1)},${(22 - (v - min) / span * 20).toFixed(1)}`).join('');
    return `<div class="mr-row">
      <span class="mr-ch">${esc(ch.replace(/_/g, ' '))}</span>
      <svg viewBox="0 0 120 24" class="mr-spark"><path d="${path}"/></svg>
      <span class="mr-pat" title="model answer">${PATTERN_ICON[got] || '?'} ${esc(got)}</span>
      ${ref && ref !== got ? `<span class="mr-ref" title="rule-based reference label">rules: ${esc(ref)}</span>` : ''}
    </div>`;
  }).join('');
  return `${head}<div class="model-reading">
    ${rows}
    <div class="mr-foot">
      <b>${esc(r.run)}</b> · ${r.agrees_with_rules ? 'matches the rule reference' : 'differs from the rule reference'} · ${esc(r.latency_ms)} ms on CPU<br>
      ${esc(r.note)}${r.skipped?.length ? ` Skipped: ${esc(r.skipped.join('; '))}.` : ''}${r.extra_output?.length ? ` The model also emitted an entry for an unsupplied channel (${esc(r.extra_output.join(', '))}); ignored.` : ''}<br>
      ${esc(r.scope)} Held-out channel accuracy vs. rule labels: ${r.channel_accuracy != null ? `${(r.channel_accuracy * 100).toFixed(1)}%` : 'n/a'} ·
      checkpoint <span class="mono">${esc(r.checkpoint_sha256.slice(0, 12))}</span> · input <span class="mono">${esc(r.input_hash.slice(0, 12))}</span>
    </div></div>`;
}

function riskStatus(r) {
  return r < 0.03 ? 'healthy' : r < 0.1 ? 'watch' : r < 0.3 ? 'elevated' : 'critical';
}

function simSentence(sim, sel) {
  const rec = sim.find(w => w.recommended);
  const base = sel.days === 0 ? 'Acting now avoids the exposure entirely.'
    : `Waiting ${sel.label.toLowerCase().replace('in ', '')} gives a ${pct(sel.risk, 1)} chance the component fails before it is serviced.`;
  if (!rec) return base;
  return rec.days >= 14 ? `${base} No maintenance is needed within the next two weeks.` : `${base} Latest low-risk window: <b>${esc(rec.label.toLowerCase())}</b>.`;
}

function evidenceRow(e) {
  const bad = e.impact > 0;
  const arrow = e.direction === 'up' ? '↑' : e.direction === 'down' ? '↓' : bad ? '!' : '✓';
  return `<div class="ev">
    <div class="arrow ${bad ? 'bad' : 'ok'}">${arrow}</div>
    <div><div class="title"><span>${esc(e.signal)}</span>${e.fleet_percentile != null ? `<small>P${e.fleet_percentile}</small>` : ''}</div>
      <div class="detail">${esc(e.detail)}</div>
      ${bad ? `<div class="impact"><i style="width:${Math.min(100, e.impact * 3)}%"></i></div>` : ''}</div>
  </div>`;
}

function trajectoryChart(c) {
  const W = 360, H = 150, pl = 28, pr = 10, pt = 10, pb = 22;
  const pts = c.trajectory.map(p => ({ t: new Date(p.t).getTime(), h: p.health }));
  const last = pts[pts.length - 1];
  const day = 86400000;
  const project = c.trend !== 'baseline' && c.slope_per_day < 0;
  const tMin = Math.min(pts[0].t, last.t - 7 * day);
  const tMax = last.t + 7 * day;
  const x = t => pl + ((t - tMin) / (tMax - tMin || 1)) * (W - pl - pr);
  const y = h => pt + (1 - h / 100) * (H - pt - pb);
  const bands = [[100, 80, 'healthy'], [80, 65, 'watch'], [65, 45, 'elevated'], [45, 0, 'critical']]
    .map(([a, b, s]) => `<rect x="${pl}" y="${y(a)}" width="${W - pl - pr}" height="${y(b) - y(a)}" fill="${COLORS[s]}" opacity=".07"/>`).join('');
  const grid = [0, 45, 65, 80, 100].map(v => `<text x="${pl - 6}" y="${y(v) + 3}" text-anchor="end">${v}</text>`).join('');
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.h).toFixed(1)}`).join('');
  const dots = pts.map(p => `<circle cx="${x(p.t)}" cy="${y(p.h)}" r="3" fill="${COLORS[statusOf(p.h)]}" stroke="#0b1320" stroke-width="1.5"/>`).join('');
  const endH = Math.max(0, last.h + c.slope_per_day * 7);
  const proj = project ? `<path d="M${x(last.t)},${y(last.h)} L${x(tMax)},${y(endH)}" stroke="${COLORS[statusOf(endH)]}" stroke-width="2" stroke-dasharray="4 4" fill="none"/>
    <circle cx="${x(tMax)}" cy="${y(endH)}" r="3" fill="none" stroke="${COLORS[statusOf(endH)]}" stroke-width="1.5"/>` : '';
  const nowX = x(last.t);
  const fmt = t => new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Health trajectory">
    ${bands}${grid}
    <line x1="${nowX}" x2="${nowX}" y1="${pt}" y2="${H - pb}" stroke="rgba(148,178,214,.35)" stroke-dasharray="2 3"/>
    ${pts.length > 1 ? `<path d="${line}" fill="none" stroke="${COLORS[c.status]}" stroke-width="2.2" stroke-linejoin="round"/>` : ''}
    ${proj}${dots}
    <text x="${pl}" y="${H - 6}">${fmt(tMin)}</text>
    <text x="${nowX - 4}" y="${H - 6}" text-anchor="end">now</text>
    <text x="${W - pr}" y="${H - 6}" text-anchor="end">+7d${project ? ' proj.' : ''}</text>
  </svg>
  ${c.trend === 'baseline' ? '<p class="sub">Not enough history yet — the trajectory builds as the benchmark is repeated over days.</p>' : ''}`;
}

function sparkline(s, color) {
  const W = 360, H = 38, v = s.values;
  const min = Math.min(...v), max = Math.max(...v), span = max - min || 1;
  const x = i => (i / (v.length - 1)) * W;
  const y = val => H - 3 - ((val - min) / span) * (H - 6);
  const d = v.map((val, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(val).toFixed(1)}`).join('');
  const lastV = v[v.length - 1];
  const change = v[0] ? ((lastV - v[0]) / Math.abs(v[0])) * 100 : 0;
  const fmt = n => (Math.abs(n) >= 1000 ? Math.round(n).toLocaleString() : Math.abs(n) >= 10 ? n.toFixed(0) : n.toFixed(2));
  return `<div class="spark"><span class="lbl">${esc(s.label)}</span>
    <span class="last">${fmt(lastV)} ${esc(s.unit)} <span class="sub">${change >= 0 ? '+' : ''}${change.toFixed(0)}%</span></span>
    <svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px">
      <path d="${d} L${W},${H} L0,${H} Z" fill="${color}" opacity=".12"/>
      <path d="${d}" fill="none" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>
    </svg></div>`;
}
