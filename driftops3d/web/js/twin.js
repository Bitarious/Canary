import { esc, timeAgo } from './panel.js';

const COLORS = { healthy: '#22c55e', watch: '#eab308', elevated: '#f97316', critical: '#ef4444' };
const ORDER = { healthy: 0, watch: 1, elevated: 2, critical: 3 };
const TREND_ICON = t => (t === 'improving' ? '↗' : t?.includes('deteriorating') ? '↘' : t === 'baseline' ? '•' : '→');
const pct = x => `${(x * 100).toFixed(x > 0 && x < 0.01 ? 1 : 0)}%`;
const short = s => String(s || '').split('·')[0].trim();
const md = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');

// ------------------------------------------------------------------------------------ sidebar

export function renderSidebar(el, { sites, site, rackId }) {
  const rack = site?.racks.find(r => r.id === rackId);
  const counts = site?.counts || {};
  el.innerHTML = `
    <div class="side-sec">
      <div class="eyebrow">Sites</div>
      ${sites.map(s => `<button class="site-card ${s.id === site?.id ? 'active' : ''}" data-site="${esc(s.id)}">
        <div><div class="site-name">${esc(s.name)}${s.live ? ' <span class="chip">live</span>' : ''}</div>
        <div class="site-meta">${esc(s.region || s.kind)} · ${s.nodes} node${s.nodes === 1 ? '' : 's'}</div></div>
        <span class="sdot" style="background:${COLORS[s.status]}"></span></button>`).join('')}
    </div>
    ${site ? `
    <div class="side-sec">
      <div class="eyebrow">${esc(site.name)} · status</div>
      ${['critical', 'elevated', 'watch', 'healthy'].map(s => `<div class="count-row"><span class="sq" style="background:${COLORS[s]}"></span>
        <span>${s[0].toUpperCase() + s.slice(1)}</span><b>${counts[s] || 0}</b></div>`).join('')}
    </div>
    ${rack ? `
    <div class="side-sec">
      <div class="eyebrow row-between"><span>${esc(rack.name)} · ${rack.devices.length} devices</span><button class="link" data-clear-rack>✕ close</button></div>
      ${rack.devices.map(d => `<button class="dev-row" data-open="${esc(d.id)}" data-hover-device="${esc(d.id)}">
        <span class="slot">${d.slot ? `U${String(d.slot).padStart(2, '0')}` : '—'}</span>
        <span class="grow"><span class="dname">${esc(d.label)}</span><span class="dmeta">${esc(d.status === 'healthy' ? 'healthy' : short(d.worst.name) + ' · ' + (d.worst.signal || d.status))}</span></span>
        <span class="dtrend">${TREND_ICON(d.trend)}</span>
        <span class="dhealth s-${d.status}">${Math.round(d.health)}</span></button>`).join('')}
      <p class="side-hint">Click a server to open it in 3D and analyze it.</p>
    </div>` : ''}
    <div class="side-sec">
      <div class="eyebrow">Drifting now</div>
      ${site.drifting.length ? site.drifting.map(d => `<button class="drift-row" data-drift="${esc(d.id)}" data-rack="${esc(d.rack_id)}">
        <span class="grow"><span class="dname">${esc(d.rack_name)}</span><span class="dmeta">${esc(d.label)} · ${Math.round(d.health)}/100 · ${esc(short(d.worst.name))}</span></span>
        <span class="sdot" style="background:${COLORS[d.status]}"></span></button>`).join('') : '<p class="side-hint">Nothing is drifting at this site.</p>'}
    </div>
    ${site.patterns.length ? `<div class="side-sec"><div class="eyebrow">Rack-level patterns</div>
      ${site.patterns.map(p => `<button class="pattern" data-rack-pattern="${esc(p.rack_id)}"><b>${esc(p.title)}</b>${esc(p.text)}</button>`).join('')}</div>` : ''}
    ` : ''}`;
}

export function renderTwinHead(head, foot, site, rackId) {
  if (!site) { head.innerHTML = ''; foot.innerHTML = ''; return; }
  const rack = site.racks.find(r => r.id === rackId);
  head.innerHTML = `<h1>${esc(site.name)} — Digital Twin</h1>
    <div class="twin-sub">${site.racks.length} ${site.kind === 'office' ? 'groups' : 'racks'} · ${site.nodes} nodes · live temporal health</div>`;
  foot.innerHTML = `<span>${rack ? `${esc(rack.name)} selected · click a server to open it in 3D · ask "Why?" or "What if I wait?"`
    : 'Click a rack to inspect it · hover a server for details'}</span><span>colour = health · glow = drifting</span>`;
}

// ------------------------------------------------------------------------------------ copilot

const DEFAULT_CHIPS = ['What should I do?', 'Why?', 'What if I wait 7 days?', 'Show fleet comparison'];

export class Copilot {
  constructor(el, { api, onOpenDevice, onFocus }) {
    this.el = el;
    this.api = api;
    this.onOpenDevice = onOpenDevice;
    this.onFocus = onFocus;
    this.ctx = {};
    this.messages = [];
    this.chips = DEFAULT_CHIPS;
    this.busy = false;
    el.innerHTML = `
      <div class="cp-head"><span class="eyebrow">DriftOps copilot</span><span class="cp-watch"><i></i><span id="cpWatch"></span></span></div>
      <div class="cp-log" id="cpLog"></div>
      <div class="cp-foot">
        <div class="cp-chips" id="cpChips"></div>
        <form class="cp-form" id="cpForm"><input id="cpInput" placeholder="Ask about any rack, server or component…" autocomplete="off">
          <button aria-label="Send">→</button></form>
        <div class="cp-note">Answers are assembled from model outputs (rule-based, no LLM).</div>
      </div>`;
    this.log = el.querySelector('#cpLog');
    el.querySelector('#cpForm').addEventListener('submit', e => {
      e.preventDefault();
      const input = el.querySelector('#cpInput');
      if (input.value.trim()) this.ask(input.value.trim());
      input.value = '';
    });
    el.addEventListener('click', e => {
      const chip = e.target.closest('[data-chip]');
      if (chip) return this.ask(chip.dataset.chip);
      const open = e.target.closest('[data-open]');
      if (open) return this.onOpenDevice(open.dataset.open);
    });
    this._chips();
  }

  setSite(site) {
    if (this.siteId !== site.id) {
      this.siteId = site.id;
      this.messages = [];
      this.log.innerHTML = `<div class="cp-empty">Watching <b>${esc(site.name)}</b>. Select a rack or ask a question.</div>`;
      this.chips = DEFAULT_CHIPS;
      this._chips();
    }
    this.ctx = { ...this.ctx, site_id: site.id };
    this.el.querySelector('#cpWatch').textContent = `watching ${site.name}`;
  }

  setContext(ctx) { this.ctx = { ...this.ctx, ...ctx }; }

  async ask(question) {
    if (this.busy || (this.lastQ === question && Date.now() - this.lastAt < 1500)) return;
    this.lastQ = question;
    this.lastAt = Date.now();
    this.busy = true;
    if (!this.messages.length) this.log.innerHTML = '';
    this._append(`<div class="msg user">${esc(question)}</div>`);
    const pending = this._append('<div class="msg bot"><div class="bot-tag">◇ DriftOps</div><div class="typing"><i></i><i></i><i></i></div></div>');
    try {
      const r = await this.api('/api/copilot', { question, context: this.ctx });
      this.ctx = { ...this.ctx, ...r.focus };
      pending.outerHTML = this._render(r);
      this.chips = r.suggestions?.length ? r.suggestions : DEFAULT_CHIPS;
      this.onFocus?.(r.focus);
    } catch (err) {
      pending.outerHTML = `<div class="msg bot"><div class="bot-tag">◇ DriftOps</div><p class="s-critical">Could not answer: ${esc(err.message)}</p></div>`;
    } finally {
      this.busy = false;
      this._chips();
      this.log.scrollTop = this.log.scrollHeight;
    }
  }

  _append(html) {
    this.messages.push(html);
    this.log.insertAdjacentHTML('beforeend', html);
    this.log.scrollTop = this.log.scrollHeight;
    return this.log.lastElementChild;
  }

  _chips() {
    this.el.querySelector('#cpChips').innerHTML = this.chips.map(c => `<button class="chip-btn" data-chip="${esc(c)}">${esc(c)}</button>`).join('');
  }

  _render(r) {
    const tone = r.tone || 'healthy';
    let text = md(r.text);
    text = text.replace('<b>', `<b class="s-${tone}">`);
    const c = r.card;
    const card = c ? `
      <div class="cp-card">
        <div class="cp-card-head">
          <div><div class="cp-title">${esc(c.device_label)} · ${esc(c.component)}</div><div class="cp-sub">${esc(c.rack_name)} · ${esc(c.site_name)}</div></div>
          <span class="badge s-${c.status}">${c.status}</span>
        </div>
        <div class="cp-card-body">
          <div class="cp-kv"><div><div class="k">Health</div><div class="big">${c.health}<small>/100</small></div></div>
            <div style="text-align:right"><div class="k">Failure window</div><div class="mid">${esc(c.window)}</div></div></div>
          <div class="k">${esc(c.trajectory_label)}</div>
          ${area(c.trajectory, COLORS[c.status])}
          <button class="btn ghost small" data-open="${esc(c.device_id)}">Open ${esc(c.device_label)} in 3D →</button>
        </div>
      </div>` : '';
    const list = r.list?.length ? `<div class="cp-list">${r.list.map(i => `
      <div class="cp-li"><span class="sdot" style="background:${COLORS[i.status] || '#5d6c80'}"></span>
        <div class="grow"><div class="dname">${esc(i.label)}</div><div class="dmeta">${esc(i.meta)}</div></div>
        ${i.device_id ? `<button class="link" data-open="${esc(i.device_id)}">open →</button>` : ''}</div>`).join('')}</div>` : '';
    return `<div class="msg bot"><div class="bot-tag">◇ DriftOps</div><p>${text}</p>${list}${card}</div>`;
  }
}

function area(values, color) {
  if (!values || values.length < 2) return '<div class="cp-sub" style="margin:10px 0">Trajectory builds with repeated runs.</div>';
  const W = 320, H = 70;
  const x = i => (i / (values.length - 1)) * W;
  const y = v => 6 + (1 - v / 100) * (H - 12);
  const d = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const last = values[values.length - 1];
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" style="margin:8px 0 12px">
    <path d="${d} L${W},${H} L0,${H} Z" fill="${color}" opacity=".14"/>
    <path d="${d}" fill="none" stroke="${color}" stroke-width="2"/>
    <circle cx="${x(values.length - 1)}" cy="${y(last)}" r="4" fill="${color}"/></svg>`;
}

// ------------------------------------------------------------------------------------ fleet & incidents pages

export function renderFleet(el, rows, sites, filter) {
  if (!el.dataset.ready) {
    el.innerHTML = `<div class="page-inner">
      <div class="page-head"><div><h1>Fleet</h1><div class="twin-sub" id="fleetSub"></div></div>
        <div class="filters">
          <input id="fleetSearch" placeholder="Search devices, racks, issues…">
          <select id="fleetSite"></select>
          <div class="seg" id="fleetStatus">${['all', 'critical', 'elevated', 'watch', 'healthy'].map(s => `<button data-status="${s}">${s}</button>`).join('')}</div>
        </div></div>
      <div class="table-wrap"><table class="fleet">
        <thead><tr><th>Device</th><th>Site · rack</th><th>Health</th><th>Status</th><th>Trend</th><th>Top issue</th><th>7-day risk</th><th>Window</th><th>Last run</th></tr></thead>
        <tbody id="fleetBody"></tbody></table></div></div>`;
    el.dataset.ready = '1';
  }
  const siteSel = el.querySelector('#fleetSite');
  const opts = `<option value="">All sites</option>${sites.map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('')}`;
  if (siteSel.innerHTML !== opts) siteSel.innerHTML = opts;
  siteSel.value = filter.site || '';
  el.querySelector('#fleetSearch').value = filter.q || '';
  el.querySelectorAll('#fleetStatus button').forEach(b => b.classList.toggle('active', b.dataset.status === (filter.status || 'all')));

  const q = (filter.q || '').toLowerCase();
  const shown = rows.filter(r => (!filter.site || r.site_id === filter.site)
    && (!filter.status || filter.status === 'all' || r.status === filter.status)
    && (!q || `${r.label} ${r.hostname} ${r.rack_name} ${r.site_name} ${r.worst.name} ${r.worst.signal}`.toLowerCase().includes(q)))
    .sort((a, b) => ORDER[b.status] - ORDER[a.status] || b.priority - a.priority || a.label.localeCompare(b.label));
  el.querySelector('#fleetSub').textContent = `${shown.length} of ${rows.length} devices · sorted by status and priority`;
  el.querySelector('#fleetBody').innerHTML = shown.map(r => `
    <tr data-open="${esc(r.id)}">
      <td><div class="dname">${esc(r.label)} ${r.source !== 'demo' ? '<span class="chip">live</span>' : ''}</div><div class="dmeta">${esc(r.hostname || '')} · ${esc(r.form_factor || '')}</div></td>
      <td>${esc(r.site_name)} · ${esc(r.rack_name)}</td>
      <td><div class="hbar"><i style="width:${r.health}%;background:${COLORS[r.status]}"></i></div><span class="mono">${Math.round(r.health)}</span></td>
      <td><span class="badge s-${r.status}">${r.status}</span></td>
      <td>${TREND_ICON(r.trend)} ${esc(r.trend)}</td>
      <td>${r.status === 'healthy' ? '<span class="dmeta">—</span>' : `${esc(short(r.worst.name))}<div class="dmeta">${esc(r.worst.signal || '')}</div>`}</td>
      <td class="s-${r.worst.risk_7d >= 0.3 ? 'critical' : r.worst.risk_7d >= 0.1 ? 'elevated' : r.worst.risk_7d >= 0.03 ? 'watch' : 'healthy'}">${pct(r.worst.risk_7d)}</td>
      <td>${esc(r.worst.window)}</td>
      <td class="dmeta">${esc(timeAgo(r.last_run))}</td>
    </tr>`).join('') || '<tr><td colspan="9" class="dmeta">No devices match.</td></tr>';
}

export function renderIncidents(el, data) {
  const { items, patterns } = data;
  const counts = { critical: 0, elevated: 0, watch: 0 };
  items.forEach(i => { counts[i.component.status]++; });
  el.innerHTML = `<div class="page-inner">
    <div class="page-head"><div><h1>Incidents</h1>
      <div class="twin-sub">${items.length} components at risk across all sites · ranked by priority (risk × criticality × redundancy)</div></div>
      <div class="inc-counts">${['critical', 'elevated', 'watch'].map(s => `<span class="badge s-${s}">${counts[s]} ${s}</span>`).join('')}</div></div>
    ${patterns.length ? `<h3>Rack-level patterns</h3><div class="inc-grid">${patterns.map(p => `
      <div class="inc pattern-card"><div class="row-between"><span class="badge s-${p.severity}">pattern</span><button class="link" data-site-rack="${esc(p.site_id)}|${esc(p.rack_id)}">view rack →</button></div>
      <div class="inc-title">${esc(p.title)}</div><p class="dmeta">${esc(p.text)}</p></div>`).join('')}</div>` : ''}
    <h3>Components at risk</h3>
    <div class="inc-grid">${items.map((i, n) => {
      const c = i.component;
      return `<div class="inc">
        <div class="row-between"><span class="badge s-${c.status}">#${n + 1} · ${c.status}</span><span class="dmeta">${esc(i.site_name)} · ${esc(i.rack_name)}</span></div>
        <div class="inc-title">${esc(i.device_label)} · ${esc(short(c.name))}</div>
        ${i.evidence ? `<p class="dmeta"><b>${esc(i.evidence.signal)}:</b> ${esc(i.evidence.detail)}</p>` : ''}
        <div class="inc-kpis"><span><small>health</small>${Math.round(c.health)}</span><span><small>7-day risk</small>${pct(c.risk_7d)}</span>
          <span><small>window</small>${esc(c.failure_window.label)}</span><span><small>trend</small>${TREND_ICON(c.trend)} ${esc(c.trend)}</span></div>
        <div class="inc-action">${esc(c.action)}</div>
        ${i.associations.length ? `<div class="dmeta">Associated: ${i.associations.map(esc).join(', ')}</div>` : ''}
        <button class="btn ghost small" data-open="${esc(i.device_id)}">Open in 3D →</button>
      </div>`;
    }).join('')}</div></div>`;
}
