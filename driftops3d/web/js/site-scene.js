import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { Tweens, ease, STATUS_HEX } from './scene.js';

const RW = 0.9, RH = 2.1, RD = 1.1;       // rack cabinet size
const PITCH_X = 1.75, PITCH_Z = 4.2;      // rack spacing (aisles between rows)
const SLAB_EMISSIVE = { healthy: 0.14, watch: 0.4, elevated: 0.55, critical: 0.75 };
const HALO = { healthy: 0, watch: 0.3, elevated: 0.5, critical: 0.75 };
const BG = new THREE.Color(0x0b1320);
const NEUTRAL = new THREE.Color(0x3a4452);
const SCAN = new THREE.Color(0x38bdf8);
const CHASSIS = new THREE.Color(0xa7b0bd);   // device-view shell colour
const sleep = ms => new Promise(r => setTimeout(r, ms));

function box(w, h, d, m, x = 0, y = 0, z = 0) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
  mesh.position.set(x, y, z);
  mesh.castShadow = mesh.receiveShadow = true;
  return mesh;
}

function slabColor(status) {
  const c = new THREE.Color(STATUS_HEX[status] || STATUS_HEX.healthy);
  return status === 'healthy' ? c.lerp(BG, 0.4) : c;
}

let haloTexture;
function halo() {
  if (!haloTexture) {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 128;
    const g = cv.getContext('2d');
    const grd = g.createRadialGradient(64, 64, 8, 64, 64, 64);
    grd.addColorStop(0, 'rgba(255,255,255,1)');
    grd.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, 128, 128);
    haloTexture = new THREE.CanvasTexture(cv);
  }
  return haloTexture;
}

export class SiteScene {
  constructor(container, labelContainer) {
    this.container = container;
    this.tweens = new Tweens();
    this.racks = new Map();     // rackId -> { group, data, frameMats, haloMat, labelEl }
    this.slabs = new Map();     // deviceId -> { mesh, mat, ledMat, data, rackId }
    this.onRackSelect = () => {};
    this.onDeviceOpen = () => {};
    this.selectedRack = null;
    this.hover = null;
    this.siteId = null;

    const r = (this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }));
    r.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(r.domElement);
    this.labelRenderer = new CSS2DRenderer({ element: labelContainer });

    const scene = (this.scene = new THREE.Scene());
    scene.environment = new THREE.PMREMGenerator(r).fromScene(new RoomEnvironment(r), 0.04).texture;
    this.camera = new THREE.PerspectiveCamera(35, 1, 0.1, 300);
    const controls = (this.controls = new OrbitControls(this.camera, r.domElement));
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI * 0.46;
    controls.minDistance = 2;
    controls.maxDistance = 60;

    scene.add(new THREE.HemisphereLight(0xbfd8ff, 0x0b1320, 0.5));
    const key = (this.key = new THREE.DirectionalLight(0xffffff, 1.8));
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.bias = -0.0005;
    scene.add(key, key.target);
    const rim = new THREE.DirectionalLight(0x38bdf8, 0.7);
    rim.position.set(-10, 6, -8);
    scene.add(rim);

    this.floor = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.ShadowMaterial({ opacity: 0.4 }));
    this.floor.rotation.x = -Math.PI / 2;
    this.floor.receiveShadow = true;
    scene.add(this.floor);
    this.grid = new THREE.GridHelper(80, 132, 0x1e3a5f, 0x13233a);
    this.grid.material.transparent = true;
    this.grid.material.opacity = 0.5;
    scene.add(this.grid);

    this.root = new THREE.Group();
    scene.add(this.root);

    // Floating tooltip for hovered servers.
    this.tipEl = document.createElement('div');
    this.tipEl.className = 'twin-tip';
    this.tip = new CSS2DObject(this.tipEl);
    this.tip.visible = false;
    scene.add(this.tip);

    // Scan beam used by "Analyze site / rack".
    this.beam = new THREE.Group();
    this.beamPlane = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({
      color: SCAN, transparent: true, opacity: 0.16, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.beamPlane.add(new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(1, 1)),
      new THREE.LineBasicMaterial({ color: 0xbae6fd, transparent: true, opacity: 0.9, depthWrite: false })));
    this.beam.add(this.beamPlane);
    this.beam.visible = false;
    scene.add(this.beam);
    this.scanState = null;

    this.selBox = null;
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this._bindPointer();
    window.addEventListener('resize', () => this.resize());
    this.clock = new THREE.Clock();
    this.setActive(true);
  }

  setActive(on) {
    // A running scan keeps animating in the background so its promise always settles.
    this._stopAfterScan = !on && !!this.scanState;
    if (this._stopAfterScan) return;
    this.renderer.setAnimationLoop(on ? t => this._frame(t) : null);
    if (on) { this.clock.getDelta(); this.resize(); }
  }

  _scanFinished() {
    this.scanState = null;
    if (this._stopAfterScan) {
      this._stopAfterScan = false;
      this.renderer.setAnimationLoop(null);
    }
  }

  resize() {
    const w = this.container.clientWidth || 1, h = this.container.clientHeight || 1;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    this.labelRenderer.setSize(w, h);
  }

  // ------------------------------------------------------------------------------ build

  load(site, { animate = true } = {}) {
    const sameSite = this.siteId === site.id;
    const ids = site.racks.flatMap(r => r.devices.map(d => d.id)).join();
    if (sameSite && ids === this._ids) return this.refresh(site);
    this._clear();
    this.siteId = site.id;
    this._ids = ids;

    const cols = Math.max(...site.racks.map(r => r.col)) + 1;
    const rows = Math.max(...site.racks.map(r => r.row)) + 1;
    const ox = ((cols - 1) * PITCH_X) / 2, oz = ((rows - 1) * PITCH_Z) / 2;
    site.racks.forEach((rack, i) => {
      const g = this._buildRack(rack);
      g.position.set(rack.col * PITCH_X - ox, 0, rack.row * PITCH_Z - oz);
      this.root.add(g);
      if (animate) {
        g.scale.y = 0.001;
        this.tweens.add(700, k => { g.scale.y = Math.max(0.001, k); }, { delay: 120 + i * 70, easing: ease.out });
      }
    });

    const bounds = new THREE.Box3().setFromObject(this.root);
    const size = bounds.getSize(new THREE.Vector3());
    this.center = bounds.getCenter(new THREE.Vector3()).setY(0.6);
    const extent = Math.max(size.x, size.z * 0.9, 4);
    this.overview = {
      target: this.center.clone(),
      pos: this.center.clone().add(new THREE.Vector3(extent * 0.75 + 2, extent * 0.8 + 3.5, extent * 0.95 + 4)),
    };
    this.key.position.copy(this.center).add(new THREE.Vector3(6, 14, 8));
    this.key.target.position.copy(this.center);
    const sc = this.key.shadow.camera;
    sc.left = sc.bottom = -extent;
    sc.right = sc.top = extent;
    sc.updateProjectionMatrix();

    this.selectedRack = null;
    if (animate) {
      this.camera.position.copy(this.overview.pos).multiplyScalar(1.35);
      this.controls.target.copy(this.overview.target);
      this._cameraTo(this.overview.pos, this.overview.target, 1400);
    } else if (!sameSite) {
      this.camera.position.copy(this.overview.pos);
      this.controls.target.copy(this.overview.target);
    }
  }

  _buildRack(rack) {
    const g = new THREE.Group();
    g.userData.rackId = rack.id;
    const frameMat = new THREE.MeshStandardMaterial({ color: 0x1f2835, metalness: 0.7, roughness: 0.45, transparent: true });
    const sideMat = new THREE.MeshStandardMaterial({ color: 0x121923, metalness: 0.5, roughness: 0.6, transparent: true, opacity: 0.94 });
    const glassMat = new THREE.MeshPhysicalMaterial({ color: 0x9bd3ff, transparent: true, opacity: 0.07, roughness: 0.1, depthWrite: false });
    const parts = [];
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) parts.push(box(0.05, RH, 0.05, frameMat, sx * (RW / 2 - 0.025), RH / 2, sz * (RD / 2 - 0.025)));
    parts.push(box(RW, 0.06, RD, frameMat, 0, RH - 0.03, 0), box(RW, 0.1, RD, frameMat, 0, 0.05, 0));
    for (const sx of [-1, 1]) parts.push(box(0.02, RH - 0.16, RD - 0.04, sideMat, sx * (RW / 2 - 0.01), RH / 2, 0));
    parts.push(box(RW - 0.04, RH - 0.16, 0.02, sideMat, 0, RH / 2, -(RD / 2 - 0.01)));
    const glass = box(RW - 0.04, RH - 0.16, 0.01, glassMat, 0, RH / 2, RD / 2 - 0.005);
    glass.castShadow = false;
    parts.push(glass);
    for (const p of parts) { p.userData.rackId = rack.id; g.add(p); }

    const stripMat = new THREE.MeshBasicMaterial({ color: STATUS_HEX[rack.status] });
    const strip = box(RW - 0.1, 0.025, 0.02, stripMat, 0, RH - 0.09, RD / 2 + 0.01);
    strip.userData.rackId = rack.id;
    g.add(strip);

    const haloMat = new THREE.MeshBasicMaterial({ map: halo(), color: STATUS_HEX[rack.status], transparent: true,
      opacity: HALO[rack.status], blending: THREE.AdditiveBlending, depthWrite: false });
    const haloMesh = new THREE.Mesh(new THREE.PlaneGeometry(RW + 1.6, RD + 1.8), haloMat);
    haloMesh.rotation.x = -Math.PI / 2;
    haloMesh.position.y = 0.01;
    g.add(haloMesh);

    const cap = Math.max(12, rack.devices.length);
    const unit = (RH - 0.32) / cap;
    const used = new Set(rack.devices.map((d, i) => Math.min(cap - 1, Math.max(0, (d.slot || i + 1) - 1))));
    const blankMat = new THREE.MeshStandardMaterial({ color: 0x151c27, metalness: 0.6, roughness: 0.5, transparent: true });
    r_blank: for (let idx = 0; idx < cap; idx++) {
      if (used.has(idx)) continue r_blank;
      const blank = box(RW - 0.1, unit * 0.9, 0.03, blankMat, 0, 0.16 + idx * unit + unit / 2, (RD - 0.18) / 2);
      blank.userData.rackId = rack.id;
      g.add(blank);
    }
    rack.devices.forEach((d, i) => {
      const idx = Math.min(cap - 1, Math.max(0, (d.slot || i + 1) - 1));
      const y = 0.16 + idx * unit + unit / 2;
      // Servers start neutral: health colours are revealed by the scan animation.
      const mat = new THREE.MeshStandardMaterial({ color: NEUTRAL.clone(), emissive: new THREE.Color(0),
        emissiveIntensity: 0, metalness: 0.35, roughness: 0.5, transparent: true });
      const mesh = box(RW - 0.12, unit * 0.74, RD - 0.18, mat, 0, y, -0.02);
      const bezelMat = new THREE.MeshStandardMaterial({ color: 0x0d131c, metalness: 0.6, roughness: 0.4, transparent: true });
      const bezel = box(RW - 0.12, unit * 0.74, 0.02, bezelMat, 0, y, (RD - 0.18) / 2 - 0.01);
      const ledMat = new THREE.MeshBasicMaterial({ color: NEUTRAL.clone(), transparent: true });
      const led = box(0.05, unit * 0.22, 0.012, ledMat, RW / 2 - 0.13, y, (RD - 0.18) / 2 + 0.005);
      for (const m of [mesh, bezel, led]) { m.userData.deviceId = d.id; m.userData.rackId = rack.id; g.add(m); }
      this.slabs.set(d.id, { mesh, mat, bezelMat, ledMat, data: d, rackId: rack.id, y, revealed: false, glow: null, scanGlow: 0 });
    });

    const el = document.createElement('div');
    el.className = 'rack-label';
    el.addEventListener('click', e => { e.stopPropagation(); this.onRackSelect(rack.id); });
    const label = new CSS2DObject(el);
    label.position.set(0, RH + 0.22, 0);
    g.add(label);
    stripMat.color.copy(NEUTRAL);
    this.racks.set(rack.id, { group: g, data: rack, frameMats: [frameMat, sideMat, glassMat, stripMat], stripMat, haloMat,
      blankMat, labelEl: el, label, revealed: false });
    this._paintRackLabel(rack.id);
    return g;
  }

  _paintRackLabel(id) {
    const r = this.racks.get(id);
    const d = r.data;
    const scanning = this.scanState && (!this.scanState.rackId || this.scanState.rackId === id);
    r.labelEl.style.color = r.revealed ? `#${new THREE.Color(STATUS_HEX[d.status]).getHexString()}` : scanning ? '#38bdf8' : '#8b9bb0';
    r.labelEl.innerHTML = `<span class="ld"></span><span class="ln">${d.name}</span><b>${r.revealed ? Math.round(d.health) : scanning ? 'scan' : '—'}</b>`;
    r.labelEl.classList.toggle('selected', this.selectedRack === id);
  }

  /** Update data in place after a refresh (same set of devices); colours only change on revealed servers. */
  refresh(site) {
    for (const rack of site.racks) {
      const r = this.racks.get(rack.id);
      if (!r) continue;
      r.data = rack;
      if (r.revealed) r.stripMat.color.setHex(STATUS_HEX[rack.status]);
      r.haloMat.color.setHex(STATUS_HEX[rack.status]);
      this._paintRackLabel(rack.id);
      for (const d of rack.devices) {
        const s = this.slabs.get(d.id);
        if (!s) continue;
        s.data = d;
        if (s.revealed) {
          s.mat.color.copy(slabColor(d.status));
          s.mat.emissive.setHex(STATUS_HEX[d.status]);
          s.ledMat.color.setHex(STATUS_HEX[d.status]);
        }
      }
    }
  }

  // ------------------------------------------------------------------------------ scan ("Analyze")

  /**
   * Sweep a scan beam over the whole site (rackId = null) or one rack, wait for fresh model results,
   * then reveal each server's health colour one by one. Resolves with the site data (null if interrupted).
   */
  async scan(rackId, dataPromise) {
    if (this.scanState) return null;
    const token = (this._scanToken = (this._scanToken || 0) + 1);
    const axis = rackId ? 'y' : 'x';
    const scope = [...this.slabs.values()].filter(s => !rackId || s.rackId === rackId);
    for (const s of scope) {
      s.revealed = false;
      s.glow = null;
      s.scanGlow = 0;
      s.world = s.mesh.getWorldPosition(new THREE.Vector3());
      s.mat.color.copy(NEUTRAL);
      s.ledMat.color.copy(NEUTRAL);
    }
    this.scanState = { rackId, axis, ids: new Set(scope.map(s => s.data.id)) };
    for (const [id, r] of this.racks) {
      if (rackId && id !== rackId) continue;
      r.revealed = false;
      r.stripMat.color.copy(SCAN);
      this._paintRackLabel(id);
    }

    // Beam geometry: a vertical sheet crossing the hall, or a horizontal sheet rising through the rack.
    const bounds = new THREE.Box3().setFromObject(rackId ? this.racks.get(rackId).group : this.root);
    const size = bounds.getSize(new THREE.Vector3()), center = bounds.getCenter(new THREE.Vector3());
    let from, to, set;
    if (axis === 'x') {
      this.beam.rotation.set(0, Math.PI / 2, 0);
      this.beamPlane.scale.set(size.z + 1.5, RH + 0.8, 1);
      this.beamPlane.position.set(0, (RH + 0.8) / 2, 0);
      this.beam.position.set(0, 0, center.z);
      [from, to] = [bounds.min.x - 0.6, bounds.max.x + 0.6];
      set = v => { this.beam.position.x = v; };
    } else {
      this.beam.rotation.set(-Math.PI / 2, 0, 0);
      this.beamPlane.scale.set(RW + 0.5, RD + 0.5, 1);
      this.beamPlane.position.set(0, 0, 0);
      this.beam.position.set(center.x, 0, center.z);
      [from, to] = [0.05, RH + 0.05];
      set = v => { this.beam.position.y = v; };
    }
    this.beam.visible = true;
    const passMs = axis === 'x' ? 1500 : 1000;
    const sweep = (async () => {
      await this.tweens.add(passMs, k => set(from + (to - from) * k));
      await this.tweens.add(passMs, k => set(to + (from - to) * k));
    })();

    let site;
    try {
      [site] = await Promise.all([dataPromise, sweep]);
    } catch (err) {
      this.beam.visible = false;
      await this._revealAll(scope, rackId, 0);
      this._scanFinished();
      throw err;
    }
    this.beam.visible = false;
    if (token !== this._scanToken || !this.slabs.size) { this._scanFinished(); return null; }
    this.refresh(site);
    const order = scope.sort((a, b) => (axis === 'x' ? a.world.x - b.world.x || a.y - b.y : a.y - b.y));
    await this._revealAll(order, rackId, axis === 'x' ? Math.max(8, 1400 / order.length) : 70);
    this._scanFinished();
    for (const id of this.racks.keys()) this._paintRackLabel(id);
    return site;
  }

  async _revealAll(order, rackId, stagger) {
    await Promise.all(order.map((s, i) => sleep(i * stagger).then(() => {
      const target = slabColor(s.data.status), st = new THREE.Color(STATUS_HEX[s.data.status]);
      s.revealing = true;
      return this.tweens.add(550, k => {
        s.mat.color.copy(NEUTRAL).lerp(target, k);
        s.ledMat.color.copy(SCAN).lerp(st, k);
        s.mat.emissive.copy(SCAN).lerp(st, k);
        s.glow = 1.3 * (1 - k) + SLAB_EMISSIVE[s.data.status] * k;
      }, { easing: ease.out }).then(() => { s.revealing = false; s.revealed = true; s.glow = null; });
    })));
    for (const [id, r] of this.racks) {
      if (rackId && id !== rackId) continue;
      r.revealed = true;
      r.stripMat.color.setHex(STATUS_HEX[r.data.status]);
      this._paintRackLabel(id);
    }
  }

  _clear() {
    for (const tw of this.tweens.list) tw.resolve();  // let pending animations finish their awaits
    this._scanToken = (this._scanToken || 0) + 1;
    this.scanState = null;
    this.zoomed = null;
    this.key.castShadow = true;
    this.beam.visible = false;
    this.root.traverse(o => {
      if (o.geometry) o.geometry.dispose();
      if (o.material && o.material.map !== haloTexture) o.material.dispose?.();
      if (o.isCSS2DObject) o.element.remove();
    });
    this.root.clear();
    this.racks.clear();
    this.slabs.clear();
    this._clearSelBox();
    this.tweens.list = [];
  }

  // ------------------------------------------------------------------------------ selection

  selectRack(id, { fly = true } = {}) {
    const rack = id ? this.racks.get(id) : null;
    this.selectedRack = rack ? id : null;
    for (const [rid, r] of this.racks) {
      const dim = rack && rid !== id;
      const to = dim ? 0.22 : 1;
      const mats = [...r.frameMats.slice(0, 2), r.stripMat];
      const slabMats = [...this.slabs.values()].filter(s => s.rackId === rid).flatMap(s => [s.mat, s.bezelMat, s.ledMat]);
      for (const m of [...mats, ...slabMats]) {
        const from = m.opacity;
        m.transparent = true;
        this.tweens.add(350, k => { m.opacity = from + (to - from) * k; m.depthWrite = m.opacity > 0.95; });
      }
      r.labelEl.style.opacity = dim ? 0.35 : 1;
      this._paintRackLabel(rid);
    }
    if (!fly || !this.overview) return;
    if (rack) {
      const p = rack.group.position;
      const target = new THREE.Vector3(p.x, 1.05, p.z);
      this._cameraTo(target.clone().add(new THREE.Vector3(2.6, 1.7, 5.6)), target, 1000);
    } else {
      this._cameraTo(this.overview.pos, this.overview.target, 1000);
    }
  }

  // ------------------------------------------------------------------------------ zoom into a server

  /** Hide everything except the chosen server, slide it out of its rack and fly the camera to it. */
  async zoomToDevice(id, framing = null, shiftPx = 0) {
    const s = this.slabs.get(id);
    if (!s || this.zoomed) return;
    this._clearSelBox();
    this.tip.visible = false;
    this.hover = null;
    const others = [];
    for (const r of this.racks.values()) {
      others.push(...r.frameMats, r.blankMat);
      r.labelEl.style.opacity = 0;
    }
    for (const o of this.slabs.values()) if (o !== s) others.push(o.mat, o.bezelMat, o.ledMat);
    const mine = [s.mat, s.bezelMat, s.ledMat];
    const faded = others.map(m => ({ m, from: m.opacity }));
    const world = s.mesh.getWorldPosition(new THREE.Vector3());   // resting position, before the slide
    const meshes = s.mesh.parent.children.filter(c => c.userData.deviceId === id);
    const start = meshes.map(m => ({ m, z: m.position.z }));
    this.zoomed = { id, rackId: s.rackId, faded, start, mine };
    this.key.castShadow = false;   // hidden racks must not leave shadows on the floor

    for (const m of [...others, ...mine]) m.transparent = true;
    const fade = this.tweens.add(650, k => {
      for (const { m, from } of faded) { m.opacity = from * (1 - k); m.depthWrite = m.opacity > 0.95; }
      for (const m of mine) { m.opacity = Math.max(m.opacity, k); m.depthWrite = true; }
    });
    // Blend the slab towards the device chassis colour so the crossfade reads as one object.
    const fromColor = s.mat.color.clone(), fromEmissive = s.mat.emissive.clone();
    this.zoomed.colors = { fromColor, fromEmissive };
    const slide = this.tweens.add(900, k => {
      for (const { m, z } of start) m.position.z = z + 0.95 * k;
      s.mat.color.copy(fromColor).lerp(CHASSIS, k * 0.85);
      s.zoomGlow = Math.sin(Math.PI * k) * 0.8;
      s.zoomBlend = k;
    }, { delay: 250, easing: ease.inOut });

    // End on the same framing the device view starts with: same view direction, and a distance at which
    // the slab covers as many pixels as the device chassis will (pixel size ∝ size / (distance · tan(fov/2))).
    const tanHere = Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    let dir = new THREE.Vector3(0.75, 0.55, 2.2).normalize(), dist = 2.4;
    if (framing) {
      s.mesh.geometry.computeBoundingBox();
      const slabSize = s.mesh.geometry.boundingBox.getSize(new THREE.Vector3()).length();
      dir = framing.dir.clone();
      dist = (slabSize * framing.dist * Math.tan(THREE.MathUtils.degToRad(framing.fov / 2))) / (framing.size * tanHere);
    }
    const target = world.clone().add(new THREE.Vector3(0, 0, 0.95));
    if (shiftPx) {
      // The twin canvas is narrower than the device canvas; shift so the server lands where the chassis will.
      const perPx = (2 * dist * tanHere) / (this.container.clientHeight || 1);
      const right = new THREE.Vector3().crossVectors(dir.clone().negate(), new THREE.Vector3(0, 1, 0)).normalize();
      target.addScaledVector(right, -shiftPx * perPx);
    }
    this.controls.minDistance = 0.2;
    const cam = this._cameraTo(target.clone().addScaledVector(dir, dist), target, 1300);
    await Promise.all([fade, slide, cam]);
  }

  /** Reverse of zoomToDevice: put the server back and bring the rest of the hall back. */
  async restoreZoom() {
    const z = this.zoomed;
    if (!z) return;
    this.zoomed = null;
    this.key.castShadow = true;
    this.controls.minDistance = 2;
    const s = this.slabs.get(z.id);
    for (const r of this.racks.values()) r.labelEl.style.opacity = '';
    await this.tweens.add(600, k => {
      for (const { m, from } of z.faded) { m.opacity = from * k; m.depthWrite = m.opacity > 0.95; }
      for (const { m, z: z0 } of z.start) m.position.z = z0 + 0.95 * (1 - k);
      if (s) {
        s.zoomGlow = 0;
        s.zoomBlend = 1 - k;
        s.mat.color.copy(CHASSIS).lerp(z.colors.fromColor, 0.15 + 0.85 * k);
      }
    });
    if (s) { s.mat.color.copy(z.colors.fromColor); s.zoomBlend = 0; }
    for (const { m, z: z0 } of z.start) m.position.z = z0;
  }

  focusDevice(id) {
    this._clearSelBox();
    const s = id && this.slabs.get(id);
    if (!s) return;
    const box3 = new THREE.Box3().setFromObject(s.mesh).expandByScalar(0.03);
    this.selBox = new THREE.Box3Helper(box3, 0x38bdf8);
    this.selBox.material.depthTest = false;
    this.selBox.material.transparent = true;
    this.scene.add(this.selBox);
  }

  _clearSelBox() {
    if (!this.selBox) return;
    this.scene.remove(this.selBox);
    this.selBox.geometry.dispose();
    this.selBox.material.dispose();
    this.selBox = null;
  }

  _cameraTo(pos, target, ms) {
    const p0 = this.camera.position.clone(), t0 = this.controls.target.clone();
    return this.tweens.add(ms, k => {
      this.camera.position.lerpVectors(p0, pos, k);
      this.controls.target.lerpVectors(t0, target, k);
    });
  }

  // ------------------------------------------------------------------------------ pointer

  _bindPointer() {
    const el = this.renderer.domElement;
    let down = null;
    el.addEventListener('pointerdown', e => { down = { x: e.clientX, y: e.clientY }; });
    el.addEventListener('pointermove', e => { this._move = e; });
    el.addEventListener('pointerleave', () => { this._move = null; this._setHover(null); });
    el.addEventListener('pointerup', e => {
      if (!down || this.zoomed || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
      const hit = this._pick(e);
      if (!hit) return this.onRackSelect(null);
      if (hit.deviceId && this.selectedRack === hit.rackId) return this.onDeviceOpen(hit.deviceId);
      this.onRackSelect(hit.rackId, hit.deviceId);
    });
  }

  _pick(e) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hits = this.raycaster.intersectObjects(this.root.children, true);
    // With a rack selected, dimmed racks in front of it must not steal the click.
    const sel = this.selectedRack && hits.filter(h => h.object.userData.rackId === this.selectedRack);
    const pool = sel && sel.length ? sel : hits;
    const hit = pool.find(h => h.object.userData.deviceId) || pool.find(h => h.object.userData.rackId);
    return hit ? hit.object.userData : null;
  }

  _setHover(h) {
    const prev = this.hover;
    this.hover = h;
    if (prev?.rackId !== h?.rackId || prev?.deviceId !== h?.deviceId) {
      const s = h?.deviceId && this.slabs.get(h.deviceId);
      if (s) {
        const d = s.data;
        const inSel = this.selectedRack === s.rackId;
        this.tipEl.innerHTML = s.revealed ? `<b>${d.label}</b> <span class="s-${d.status}">${Math.round(d.health)}</span>
          <div>${d.status === 'healthy' ? 'healthy' : `${d.worst.name.split('·')[0].trim()} · ${d.worst.signal || d.status}`}</div>`
          : `<b>${d.label}</b><div>not analyzed yet — press Analyze</div>`;
        this.tipEl.innerHTML += `
          <div class="tip-hint">${inSel ? 'click to open in 3D' : 'click to inspect rack'}</div>`;
        this.tip.position.set(0, 0, 0);
        s.mesh.getWorldPosition(this.tip.position);
        this.tip.position.x += RW / 2 + 0.1;
        this.tip.visible = true;
      } else {
        this.tip.visible = false;
      }
      this.renderer.domElement.style.cursor = h ? 'pointer' : '';
    }
  }

  // ------------------------------------------------------------------------------ loop

  _frame(now) {
    const dt = Math.min(0.05, this.clock.getDelta());
    this.tweens.update(now);
    this.controls.update();
    if (this._move && !this.zoomed) {
      this._setHover(this._pick(this._move));
      this._move = null;
    }
    const t = now / 1000;
    for (const [id, r] of this.racks) {
      const drifting = r.data.drifting > 0 && r.data.status !== 'healthy';
      const base = r.revealed && !this.zoomed ? HALO[r.data.status] * (this.selectedRack && this.selectedRack !== id ? 0.3 : 1) : 0;
      r.haloMat.opacity = base * (drifting ? 0.7 + 0.3 * Math.sin(t * 2.5) : 1) + (this.hover?.rackId === id ? 0.12 : 0);
    }
    const sc = this.scanState;
    for (const [id, s] of this.slabs) {
      const d = s.data;
      let e;
      if (s.glow !== null) {
        e = s.glow;                                             // revealing
      } else if (sc && sc.ids.has(id) && !s.revealed) {
        const dist = sc.axis === 'x' ? Math.abs(this.beam.position.x - s.world.x) : Math.abs(this.beam.position.y - s.y);
        s.scanGlow = Math.max(s.scanGlow * 0.93, Math.max(0, 1 - dist / (sc.axis === 'x' ? 0.8 : 0.2)));
        s.mat.emissive.copy(SCAN);
        e = 0.08 + 0.1 * (0.5 + 0.5 * Math.sin(t * 6 + s.y * 5)) + s.scanGlow * 1.2;
      } else if (!s.revealed) {
        e = 0;
      } else {
        e = SLAB_EMISSIVE[d.status];
        if (d.drifting && d.status !== 'healthy') e += (d.status === 'critical' ? 0.45 : 0.2) * (0.5 + 0.5 * Math.sin(t * (d.status === 'critical' ? 5 : 3)));
      }
      if (this.hover?.deviceId === id) e += 0.5;
      if (this.selectedRack && this.selectedRack !== s.rackId) e *= 0.2;
      if (s.zoomBlend) e *= 1 - 0.9 * s.zoomBlend;   // fade the status glow as the slab turns into the chassis
      if (s.zoomGlow) e += 0.6 * s.zoomGlow;
      s.mat.emissiveIntensity = e;
    }
    if (this.selBox) this.selBox.material.opacity = 0.6 + 0.4 * Math.sin(t * 5);
    void dt;
    this.renderer.render(this.scene, this.camera);
    this.labelRenderer.render(this.scene, this.camera);
  }
}
