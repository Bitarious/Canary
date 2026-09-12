import { HardwareScene, deviceFraming } from './scene.js';
import { SiteScene } from './site-scene.js';
import { renderOverview, renderComponent, esc } from './panel.js';
import { renderSidebar, renderTwinHead, Copilot, renderFleet, renderIncidents } from './twin.js';

const $ = id => document.getElementById(id);
const els = {
  analyze: $('analyzeBtn'), bench: $('benchBtn'), crumbs: $('crumbs'), siteHealth: $('siteHealth'), incCount: $('incCount'),
  overview: $('overview'), panel: $('panel'), toast: $('toast'), drop: $('drop'), loading: $('loading'),
  sidebar: $('sidebar'), twinHead: $('twinHead'), twinFoot: $('twinFoot'),
  jobBar: $('jobBar'), jobText: $('jobText'), jobPct: $('jobPct'), jobFill: $('jobFill'),
  views: { twin: $('twinView'), device: $('deviceView'), fleet: $('fleetView'), incidents: $('incidentsView') },
};

const state = {
  view: null, sites: [], site: null, rackId: null, lastTwin: null,
  current: null, analysis: null, selected: null, sim: {}, scanning: false, benchmarking: false,
  fleetRows: [], fleetFilter: {}, deviceCount: 0,
};

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

let toastTimer;
function toast(msg, error = false, ms = 4500) {
  els.toast.innerHTML = msg;
  els.toast.classList.toggle('error', error);
  els.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { els.toast.hidden = true; }, ms);
}

// ------------------------------------------------------------------------------------ scenes (created lazily)

let siteScene, deviceScene, copilot;
function getSiteScene() {
  if (!siteScene) {
    siteScene = new SiteScene($('siteStage'), $('siteLabels'));
    siteScene.onRackSelect = (rackId, deviceId) => go(`#/site/${state.site.id}${rackId ? `/rack/${rackId}` : ''}`, { focusDevice: deviceId });
    siteScene.onDeviceOpen = id => openDeviceAnimated(id);
  }
  return siteScene;
}
function getDeviceScene() {
  if (!deviceScene) {
    deviceScene = new HardwareScene($('stage'), $('labels'));
    deviceScene.onSelect = id => selectComponent(id);
  }
  return deviceScene;
}

let xfTimer;
/** Switch views; with crossfade the previous view keeps rendering underneath while the new one fades in. */
function showView(name, { crossfade = false } = {}) {
  if (state.view === name) return;
  const from = state.view;
  state.view = name;
  const fade = crossfade && from && els.views[from] && !els.views[from].hidden;
  for (const [k, el] of Object.entries(els.views)) {
    el.hidden = k !== name && !(fade && k === from);
    el.classList.remove('xf-in', 'xf-out');
  }
  siteScene?.setActive(name === 'twin' || (fade && from === 'twin'));
  deviceScene?.setActive(name === 'device' || (fade && from === 'device'));
  clearTimeout(xfTimer);
  if (fade) {
    const toEl = els.views[name], fromEl = els.views[from];
    void toEl.offsetWidth;   // restart CSS animations
    toEl.classList.add('xf-in');
    fromEl.classList.add('xf-out');
    xfTimer = setTimeout(() => {
      toEl.classList.remove('xf-in');
      fromEl.classList.remove('xf-out');
      if (state.view === from) return;
      fromEl.hidden = true;
      if (from === 'twin') siteScene?.setActive(false);
      if (from === 'device') deviceScene?.setActive(false);
    }, 900);
  }
  const tab = name === 'device' ? 'twin' : name;
  document.querySelectorAll('.tabs a').forEach(a => a.classList.toggle('active', a.dataset.tab === tab));
  els.analyze.hidden = name !== 'device' && name !== 'twin';
  els.siteHealth.hidden = name !== 'twin';
  els.crumbs.hidden = name !== 'device';
}

// ------------------------------------------------------------------------------------ router

let pendingOpts = {};
function go(hash, opts = {}) {
  pendingOpts = opts;
  if (location.hash === hash) route(); else location.hash = hash;
}

async function route() {
  const opts = pendingOpts;
  pendingOpts = {};
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  try {
    if (parts[0] === 'device' && parts[1]) return await openDevice(decodeURIComponent(parts[1]), opts);
    if (parts[0] === 'fleet') return await openFleet();
    if (parts[0] === 'incidents') return await openIncidents();
    if (parts[0] === 'site' && parts[1]) return await openSite(parts[1], parts[2] === 'rack' ? parts[3] : null, opts);
    const fallback = state.lastTwin || (state.sites[0] && `#/site/${state.sites[0].id}`);
    if (fallback) location.replace(fallback);
  } catch (err) {
    toast(esc(err.message), true);
  }
}
window.addEventListener('hashchange', route);

// ------------------------------------------------------------------------------------ twin (site / rack)

async function refreshSites() {
  state.sites = await api('/api/sites');
  const inc = state.sites.reduce((n, s) => n + s.counts.critical + s.counts.elevated, 0);
  els.incCount.textContent = inc || '';
  return state.sites;
}

async function openSite(siteId, rackId, opts = {}) {
  showView('twin', { crossfade: state.view === 'device' && !!siteScene?.zoomed });
  const scene = getSiteScene();
  if (!copilot) copilot = new Copilot($('copilot'), { api, onOpenDevice: id => openDeviceAnimated(id), onFocus: onCopilotFocus });
  let freshSite = false;
  if (!state.site || state.site.id !== siteId) {
    state.site = await api(`/api/sites/${siteId}`);
    scene.load(state.site);
    freshSite = true;
  }
  const rackChanged = state.rackId !== (rackId || null);
  state.rackId = rackId || null;
  state.lastTwin = location.hash;
  const wasZoomed = !!scene.zoomed;
  if (wasZoomed) scene.restoreZoom();   // coming back from a device: put the server back into its rack
  scene.selectRack(state.rackId, { fly: rackChanged || opts.fly || wasZoomed });
  scene.focusDevice(opts.focusDevice || null);
  paintTwin();
  // A newly opened site is scanned once so its health colours are revealed by the model.
  if (freshSite) analyzeTwin({ scope: null, data: new Promise(r => setTimeout(() => r(state.site), 700)), quiet: true });
  copilot.setSite(state.site);
  copilot.setContext({ rack_id: state.rackId, device_id: opts.focusDevice || null });
  const rack = state.site.racks.find(r => r.id === state.rackId);
  if (opts.ask) copilot.ask(opts.ask);
  else if (rack && rackChanged) copilot.ask(`Status of ${rack.name}?`);
}

/** From the twin, zoom into the server first (others hide, server slides out), then show the device view. */
async function openDeviceAnimated(id) {
  if (state.view === 'twin' && siteScene?.slabs.has(id) && !state.twinScanning && !state.zooming) {
    state.zooming = true;
    try {
      siteScene.focusDevice(null);
      const slab = siteScene.slabs.get(id);
      // The device view spans the full width; the twin canvas sits between the sidebar and the copilot.
      const r = siteScene.container.getBoundingClientRect();
      const shift = window.innerWidth / 2 - (r.left + r.width / 2);
      await siteScene.zoomToDevice(id, deviceFraming(slab.data.form_factor), shift);
    } finally {
      state.zooming = false;
    }
    return go(`#/device/${id}`, { crossfade: true });
  }
  go(`#/device/${id}`);
}

function paintTwin() {
  renderSidebar(els.sidebar, { sites: state.sites, site: state.site, rackId: state.rackId });
  renderTwinHead(els.twinHead, els.twinFoot, state.site, state.rackId);
  const s = state.site;
  els.siteHealth.innerHTML = s ? `<span>Site health</span><b class="s-${s.health >= 80 ? 'healthy' : s.health >= 65 ? 'watch' : 'elevated'}">${Math.round(s.health)}</b><span>/100</span>
    ${s.live ? '<span class="chip">live devices</span>' : '<span class="chip demo-chip">demo data</span>'}` : '';
  if (state.view === 'twin' && !state.twinScanning) {
    const rack = s?.racks.find(r => r.id === state.rackId);
    els.analyze.innerHTML = `<span class="ico">◎</span> Analyze ${rack ? esc(rack.name) : 'site'}`;
    els.analyze.title = rack ? `Re-run the model on every device in ${rack.name}` : 'Re-run the model on every device at this site';
  }
}

/** Twin analysis: sweep the scan beam over the site or selected rack and reveal fresh model results. */
async function analyzeTwin({ scope = state.rackId, data, quiet = false } = {}) {
  if (!state.site || state.twinScanning) return;
  const siteId = state.site.id;
  const rack = state.site.racks.find(r => r.id === scope);
  state.twinScanning = true;
  els.analyze.disabled = true;
  els.analyze.classList.add('busy');
  els.analyze.innerHTML = `<span class="spinner"></span> Scanning ${rack ? esc(rack.name) : 'site'}…`;
  try {
    const site = await siteScene.scan(scope || null, data || api(`/api/sites/${siteId}`));
    if (!site || state.site?.id !== siteId) return;
    state.site = site;
    if (quiet) return;
    if (rack) {
      copilot.ask(`Status of ${rack.name}?`);
    } else {
      const c = site.counts;
      toast(c.critical + c.elevated
        ? `<b class="s-${site.status}">${site.name}: ${c.critical} critical, ${c.elevated} elevated, ${c.watch} watch</b> — see Drifting now.`
        : `${esc(site.name)}: no elevated or critical devices.`);
    }
  } catch (err) {
    toast(`Analysis failed: ${esc(err.message)}`, true);
  } finally {
    state.twinScanning = false;
    els.analyze.disabled = false;
    els.analyze.classList.remove('busy');
    if (state.view === 'twin') paintTwin();
  }
}

function onCopilotFocus(focus) {
  if (!focus || state.view !== 'twin' || focus.site_id !== state.site?.id) return;
  if (focus.rack_id && focus.rack_id !== state.rackId) {
    go(`#/site/${focus.site_id}/rack/${focus.rack_id}`, { focusDevice: focus.device_id });
  } else if (focus.device_id) {
    siteScene.focusDevice(focus.device_id);
  }
}

els.sidebar.addEventListener('click', e => {
  const t = e.target.closest('button');
  if (!t) return;
  if (t.dataset.site) return go(`#/site/${t.dataset.site}`);
  if (t.dataset.clearRack !== undefined) return go(`#/site/${state.site.id}`);
  if (t.dataset.open) return openDeviceAnimated(t.dataset.open);
  if (t.dataset.drift) {
    const d = state.site.drifting.find(x => x.id === t.dataset.drift);
    return go(`#/site/${state.site.id}/rack/${t.dataset.rack}`, { focusDevice: d.id, ask: `Status of ${d.label}?` });
  }
  if (t.dataset.rackPattern) return go(`#/site/${state.site.id}/rack/${t.dataset.rackPattern}`, { ask: 'What should I do?' });
});
els.sidebar.addEventListener('mouseover', e => {
  const row = e.target.closest('[data-hover-device]');
  if (row && siteScene) siteScene.focusDevice(row.dataset.hoverDevice);
});

// ------------------------------------------------------------------------------------ device view

async function openDevice(id, opts = {}) {
  const reuse = state.current?.id === id && state.current.machine && !opts.crossfade;
  const record = reuse ? state.current : await api(`/api/machines/${encodeURIComponent(id)}`);
  showView('device', { crossfade: !!opts.crossfade });
  const scene = getDeviceScene();
  if (reuse) { paintCrumbs(); return; }
  state.current = record;
  state.analysis = null;
  state.sim = {};
  selectComponent(null);
  els.analyze.disabled = false;
  els.analyze.innerHTML = '<span class="ico">◎</span> Analyze';
  scene.load(record.machine, record.components, { intro: opts.crossfade ? 'match' : undefined });
  paintCrumbs();
  drawOverview();
}

function paintCrumbs() {
  const s = state.current?.summary;
  if (!s) return;
  const back = `#/site/${s.site_id}/rack/${s.rack_id}`;
  els.crumbs.innerHTML = `<a class="back" href="${back}" title="Back to rack">←</a>
    <a href="#/site/${esc(s.site_id)}">${esc(s.site_name)}</a><span>›</span>
    <a href="${back}">${esc(s.rack_name)}</a><span>›</span><b>${esc(s.label)}</b>`;
}

function drawOverview(error) {
  renderOverview(els.overview, { machine: state.current, analysis: state.analysis, scanning: state.scanning, error });
}

async function analyze() {
  if (!state.current || state.scanning) return;
  state.scanning = true;
  state.analysis = null;
  selectComponent(null);
  els.analyze.disabled = true;
  els.analyze.classList.add('busy');
  els.analyze.innerHTML = '<span class="spinner"></span> Analyzing…';
  drawOverview();
  const machineId = state.current.id;
  try {
    const analysis = await deviceScene.playAnalysis(api('/api/analyze', { machine_id: machineId }));
    if (!analysis || state.current?.id !== machineId) return;
    state.analysis = analysis;
    const o = analysis.overall;
    toast(o.counts.critical + o.counts.elevated
      ? `<b class="s-${o.status}">${esc(o.headline)}</b> — click a highlighted component for details.`
      : 'All components look healthy. Click any component for its summary.');
  } catch (err) {
    toast(`Analysis failed: ${esc(err.message)}`, true);
  } finally {
    state.scanning = false;
    els.analyze.disabled = false;
    els.analyze.classList.remove('busy');
    els.analyze.innerHTML = state.analysis ? '<span class="ico">↻</span> Re-analyze' : '<span class="ico">◎</span> Analyze';
    drawOverview();
  }
}

function selectComponent(id) {
  const comp = id && state.analysis?.components.find(c => c.id === id);
  state.selected = comp ? id : null;
  deviceScene?.select(comp ? id : null);
  if (!comp) { els.panel.hidden = true; return; }
  const scroll = els.panel.hidden || els.panel.dataset.id !== id ? 0 : els.panel.scrollTop;
  renderComponent(els.panel, comp, state.sim[id]);
  els.panel.dataset.id = id;
  els.panel.hidden = false;
  els.panel.scrollTop = scroll;
}

els.panel.addEventListener('click', e => {
  if (e.target.closest('.close')) return selectComponent(null);
  const tab = e.target.closest('.sim-tab');
  if (tab && state.selected) {
    state.sim[state.selected] = Number(tab.dataset.sim);
    const scroll = els.panel.scrollTop;
    renderComponent(els.panel, state.analysis.components.find(c => c.id === state.selected), state.sim[state.selected]);
    els.panel.scrollTop = scroll;
  }
});
els.overview.addEventListener('click', e => {
  const item = e.target.closest('button.item');
  if (item) selectComponent(item.dataset.id);
});
els.analyze.addEventListener('click', () => (state.view === 'twin' ? analyzeTwin() : analyze()));
window.addEventListener('keydown', e => {
  if (e.target.matches('input, select, textarea')) return;
  if (e.key === 'Escape') {
    if (state.view === 'device' && state.selected) selectComponent(null);
    else if (state.view === 'device' && !state.scanning && state.current) location.hash = els.crumbs.querySelector('.back').getAttribute('href');
    else if (state.view === 'twin' && state.rackId) go(`#/site/${state.site.id}`);
  }
  if (e.key === 'Enter' && !els.analyze.disabled) {
    if (state.view === 'device') analyze();
    else if (state.view === 'twin') analyzeTwin();
  }
});

// ------------------------------------------------------------------------------------ fleet & incidents

async function openFleet() {
  showView('fleet');
  state.fleetRows = await api('/api/fleet');
  renderFleet(els.views.fleet, state.fleetRows, state.sites, state.fleetFilter);
}

els.views.fleet.addEventListener('input', e => {
  if (e.target.id === 'fleetSearch') state.fleetFilter.q = e.target.value;
  if (e.target.id === 'fleetSite') state.fleetFilter.site = e.target.value;
  renderFleet(els.views.fleet, state.fleetRows, state.sites, state.fleetFilter);
});
els.views.fleet.addEventListener('click', e => {
  const seg = e.target.closest('[data-status]');
  if (seg) {
    state.fleetFilter.status = seg.dataset.status;
    return renderFleet(els.views.fleet, state.fleetRows, state.sites, state.fleetFilter);
  }
  const row = e.target.closest('[data-open]');
  if (row) go(`#/device/${row.dataset.open}`);
});

async function openIncidents() {
  showView('incidents');
  renderIncidents(els.views.incidents, await api('/api/incidents'));
}
els.views.incidents.addEventListener('click', e => {
  const open = e.target.closest('[data-open]');
  if (open) return go(`#/device/${open.dataset.open}`);
  const rack = e.target.closest('[data-site-rack]');
  if (rack) {
    const [site, r] = rack.dataset.siteRack.split('|');
    go(`#/site/${site}/rack/${r}`, { ask: 'What should I do?' });
  }
});

// ------------------------------------------------------------------------------------ benchmark this device

els.bench.addEventListener('click', async () => {
  if (state.benchmarking) return;
  state.benchmarking = true;
  els.bench.disabled = true;
  els.jobBar.hidden = false;
  els.jobText.textContent = 'Starting the agent on the computer running DriftOps…';
  els.jobPct.textContent = '';
  els.jobFill.style.width = '2%';
  try {
    let job = await api('/api/benchmark', { rounds: 20 });
    while (job.status === 'running') {
      await new Promise(r => setTimeout(r, 700));
      job = await api(`/api/jobs/${job.id}`);
      els.jobText.textContent = job.message;
      els.jobPct.textContent = `${Math.round(job.progress * 100)}%`;
      els.jobFill.style.width = `${Math.max(2, job.progress * 100)}%`;
    }
    if (job.status !== 'done') throw new Error(job.message || 'benchmark failed');
    // Stay on the current view: the measured computer lands in "Local devices".
    await refreshSites();
    if (state.current?.id === job.machine_id) state.current = null;
    if (state.view === 'twin' && state.site?.id === 'local') { state.site = null; route(); }
    else if (state.view === 'twin') paintTwin();
    toast(`Benchmark saved for this computer (<b>${esc(job.machine_id)}</b>, Local devices).
      <a class="link" href="#/device/${esc(job.machine_id)}">Open &amp; analyze it →</a>`, false, 9000);
  } catch (err) {
    toast(`Benchmark failed: ${esc(err.message)}`, true, 7000);
  } finally {
    state.benchmarking = false;
    els.bench.disabled = false;
    els.jobBar.hidden = true;
  }
});

async function afterNewTelemetry(machineId) {
  await refreshSites();
  state.site = null;           // force the twin to reload with the new device
  state.current = null;
  go(`#/device/${machineId}`);
}

// ------------------------------------------------------------------------------------ drag & drop telemetry

let dragDepth = 0;
window.addEventListener('dragenter', e => { e.preventDefault(); dragDepth++; els.drop.hidden = false; });
window.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; els.drop.hidden = true; } });
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', async e => {
  e.preventDefault();
  dragDepth = 0;
  els.drop.hidden = true;
  const file = e.dataTransfer.files[0];
  if (!file) return;
  try {
    const { machine_id } = await api('/api/telemetry', JSON.parse(await file.text()));
    await afterNewTelemetry(machine_id);
    toast(`Imported telemetry for <b>${esc(machine_id)}</b>. Press <b>Analyze</b>.`);
  } catch (err) {
    toast(`Could not import ${esc(file.name)}: ${esc(err.message)}`, true);
  }
});

// ------------------------------------------------------------------------------------ boot

async function boot() {
  try {
    let status = await api('/api/status');
    if (!status.ready) {
      els.loading.hidden = false;
      $('loadingText').textContent = `Running the model over ${status.devices} devices…`;
      while (!status.ready) {
        await new Promise(r => setTimeout(r, 800));
        status = await api('/api/status');
      }
      els.loading.hidden = true;
    }
    state.deviceCount = status.devices;
    await refreshSites();
    await route();
  } catch (err) {
    els.loading.hidden = true;
    showView('device');
    drawOverview(err.message);
    els.bench.disabled = true;
    return;
  }

  // Pick up telemetry pushed by agents on other machines.
  setInterval(async () => {
    if (state.scanning || state.benchmarking || document.hidden) return;
    try {
      const status = await api('/api/status');
      if (status.devices === state.deviceCount) return;
      state.deviceCount = status.devices;
      await refreshSites();
      toast('New device telemetry received — see <b>Local devices</b> in the site list.');
      if (state.view === 'twin' && state.site) {
        state.site = await api(`/api/sites/${state.site.id}`);
        siteScene.load(state.site, { animate: false });
        siteScene.selectRack(state.rackId, { fly: false });
        paintTwin();
        if ([...siteScene.slabs.values()].some(s => !s.revealed)) {
          analyzeTwin({ scope: null, data: Promise.resolve(state.site), quiet: true });
        }
      }
    } catch { /* server briefly unavailable */ }
  }, 8000);
}

// Debug handle for the browser console.
window.driftops = { state, openDevice: openDeviceAnimated, get siteScene() { return siteScene; }, get deviceScene() { return deviceScene; } };

boot();
