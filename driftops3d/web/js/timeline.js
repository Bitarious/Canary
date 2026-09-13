import { esc } from './panel.js';

const COLORS = { healthy: '#22c55e', watch: '#eab308', elevated: '#f97316', critical: '#ef4444' };
const STACK = ['watch', 'elevated', 'critical'];
const JUMPS = [['−30d', -29], ['−7d', -7], ['Now', 0], ['+1d', 1], ['+3d', 3], ['+7d', 7]];
const STEP_MS = 260;

const dayLabel = d => (d === 0 ? 'NOW' : `T${d < 0 ? '−' : '+'}${Math.abs(d)}d`);

/**
 * Time machine scrubber: replay the model's day-by-day view of the past 30 days and scrub into
 * a projected horizon. Emits the selected day index; the owner re-colours the twin.
 */
export class Timeline {
  constructor(el, { onChange = () => {}, onEvent = () => {} } = {}) {
    this.el = el;
    this.onChange = onChange;
    this.onEvent = onEvent;
    this.data = null;
    this.index = 0;
    this.enabled = true;
    this.timer = null;

    el.addEventListener('input', e => {
      if (e.target.classList.contains('tl-range')) { this.pause(); this.set(Number(e.target.value)); }
    });
    el.addEventListener('click', e => {
      const jump = e.target.closest('[data-jump]');
      if (jump) { this.pause(); return this.setDay(Number(jump.dataset.jump)); }
      if (e.target.closest('.tl-play')) return this.timer ? this.pause() : this.play();
      const mark = e.target.closest('[data-event]');
      if (mark) {
        this.pause();
        const ev = this.data.events[Number(mark.dataset.event)];
        this.setDay(ev.day);
        this.onEvent(ev);
      }
    });
  }

  load(data, { keepDay = false } = {}) {
    const day = keepDay && this.data ? this.day : 0;
    this.data = data;
    this.index = Math.max(0, data.days.indexOf(day));
    this._render();
    this._update();
  }

  get day() { return this.data ? this.data.days[this.index] : 0; }
  get isNow() { return !!this.data && this.index === this.data.now_index; }
  get isProjected() { return this.day > 0; }

  setEnabled(on) {
    this.enabled = on;
    this.el.classList.toggle('disabled', !on);
    if (!on) this.pause();
  }

  setDay(day) {
    const i = this.data?.days.indexOf(day);
    if (i >= 0) this.set(i);
  }

  set(i) {
    if (!this.data || !this.enabled) return;
    const next = Math.max(0, Math.min(this.data.days.length - 1, i));
    if (next === this.index) return this._update();
    this.index = next;
    this._update();
    this.onChange(this.index);
  }

  step(delta) { this.pause(); this.set(this.index + delta); }

  /** Play from the selected day to the end of the horizon, holding briefly at NOW. */
  play() {
    if (!this.data || !this.enabled) return;
    if (this.index >= this.data.days.length - 1) this.set(0);
    this.el.classList.add('playing');
    const tick = () => {
      if (this.index >= this.data.days.length - 1) return this.pause();
      this.set(this.index + 1);
      this.timer = setTimeout(tick, this.isNow ? STEP_MS * 5 : STEP_MS);
    };
    this.timer = setTimeout(tick, STEP_MS);
    this._update();
  }

  pause() {
    clearTimeout(this.timer);
    this.timer = null;
    this.el.classList.remove('playing');
    if (this.data) this._update();
  }

  // ------------------------------------------------------------------------------ rendering

  _render() {
    const { days, devices, events, now_index: nowI } = this.data;
    const n = days.length;
    const counts = days.map((_, i) => {
      const c = { watch: 0, elevated: 0, critical: 0 };
      for (const dev of Object.values(devices)) {
        const f = dev.frames[i];
        if (f && c[f.s] !== undefined) c[f.s] += 1;
      }
      return c;
    });
    const max = Math.max(3, ...counts.map(c => c.watch + c.elevated + c.critical));
    const bars = counts.map((c, i) => {
      let y = 1;
      return STACK.map(s => {
        const h = (c[s] / max) * 0.92;
        y -= h;
        return h ? `<rect x="${i + 0.18}" y="${y}" width="0.64" height="${h}" fill="${COLORS[s]}"
          opacity="${i > nowI ? 0.45 : 0.8}"${i > nowI ? ' filter="url(#tlGhost)"' : ''}/>` : '';
      }).join('');
    }).join('');
    const pos = i => `${((i + 0.5) / n) * 100}%`;
    // One marker per day and kind, so busy days stay readable; the first event of the group is the target.
    const seen = new Set();
    const marks = events.map((e, k) => {
      const i = days.indexOf(e.day);
      const slot = `${i}:${e.kind}`;
      if (i < 0 || seen.has(slot)) return '';
      seen.add(slot);
      const same = events.filter(x => x.day === e.day && x.kind === e.kind);
      const title = same.map(x => `${x.text}${x.signal ? ` — ${x.signal}` : ''}`).join('\n');
      return `<button class="tl-mark ${e.kind}" data-event="${k}" style="left:${pos(i)};--c:${COLORS[e.status] || COLORS.watch}"
        title="${esc(`${dayLabel(e.day)}\n${title}`)}"></button>`;
    }).join('');
    const TICKS = new Set([days[0], -21, -14, -7, 0, 3, days[n - 1]]);
    const ticks = days.map((d, i) => TICKS.has(d)
      ? `<span style="left:${pos(i)}" class="${d === 0 ? 'now' : ''}">${d === 0 ? 'NOW' : `${d > 0 ? '+' : '−'}${Math.abs(d)}d`}</span>` : '').join('');

    this.el.innerHTML = `
      <button class="tl-play" title="Play the last 30 days and the projected week">
        <span class="i-play">▶</span><span class="i-pause">❚❚</span></button>
      <div class="tl-read">
        <div class="tl-day"></div>
        <div class="tl-date"></div>
        <div class="tl-mode"></div>
      </div>
      <div class="tl-main">
        <div class="tl-caption"></div>
        <div class="tl-track">
          <div class="tl-future" style="left:${(nowI + 1) / n * 100}%"></div>
          <svg class="tl-bars" viewBox="0 0 ${n} 1" preserveAspectRatio="none">
            <defs><filter id="tlGhost"><feGaussianBlur stdDeviation="0.02"/></filter></defs>${bars}</svg>
          <div class="tl-nowline" style="left:${pos(nowI)}"></div>
          <div class="tl-cursor"></div>
          <input class="tl-range" type="range" min="0" max="${n - 1}" step="1" value="${this.index}" aria-label="Timeline day">
          <div class="tl-marks">${marks}</div>
        </div>
        <div class="tl-ticks">${ticks}</div>
      </div>
      <div class="tl-jumps">${JUMPS.map(([l, d]) => `<button data-jump="${d}">${l}</button>`).join('')}</div>`;
    this.n = n;
  }

  _update() {
    if (!this.data || !this.el.querySelector('.tl-range')) return;
    const { days, events, now } = this.data;
    const d = this.day;
    const $ = s => this.el.querySelector(s);
    $('.tl-range').value = this.index;
    $('.tl-cursor').style.left = `${((this.index + 0.5) / this.n) * 100}%`;
    $('.tl-day').textContent = dayLabel(d);
    const date = new Date(new Date(now).getTime() + d * 86400000);
    $('.tl-date').textContent = date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
    $('.tl-mode').textContent = d < 0 ? 'Replay · model as of that day' : d === 0 ? 'Live' : 'Projected · current trends';
    this.el.classList.toggle('projected', d > 0);
    this.el.classList.toggle('replay', d < 0);
    this.el.querySelectorAll('[data-jump]').forEach(b => b.classList.toggle('active', Number(b.dataset.jump) === d));
    this.el.querySelectorAll('.tl-mark').forEach(m => {
      m.classList.toggle('passed', days.indexOf(events[Number(m.dataset.event)].day) <= this.index);
      m.classList.toggle('here', events[Number(m.dataset.event)].day === d);
    });
    // Caption: what happened on this day, else the most recent thing within the last three days.
    const recent = events.filter(e => e.day <= d && e.day > d - 3);
    const today = recent.filter(e => e.day === d);
    const pick = (today.length ? today : recent.slice(-1))
      .sort((a, b) => (b.kind === 'onset') - (a.kind === 'onset'))[0];
    const more = today.length > 1 ? ` <span class="tl-more">+${today.length - 1} more</span>` : '';
    $('.tl-caption').innerHTML = pick
      ? `<span class="tl-ev ${pick.kind}" style="--c:${COLORS[pick.status] || COLORS.watch}"></span>
         <b>${pick.day === d ? '' : `${dayLabel(pick.day)} · `}${esc(pick.text)}</b>${pick.signal ? ` <span>${esc(pick.signal)}</span>` : ''}${more}`
      : `<span class="tl-quiet">${d > 0 ? 'No new status changes projected for this day' : d < 0 ? 'No new deviations on this day' : 'Current state'}</span>`;
  }
}
