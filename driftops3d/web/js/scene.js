import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export const STATUS_HEX = { healthy: 0x22c55e, watch: 0xeab308, elevated: 0xf97316, critical: 0xef4444 };
const NEUTRAL = new THREE.Color(0x8a94a3);
const SCAN = new THREE.Color(0x38bdf8);
const EMISSIVE_BASE = { healthy: 0.10, watch: 0.22, elevated: 0.34, critical: 0.5 };
const PULSE = { healthy: 0, watch: 0.05, elevated: 0.16, critical: 0.38 };
const FAN_SPEED = { idle: 14, healthy: 16, watch: 9, elevated: 5, critical: 1.6 };

export const ease = {
  inOut: t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  out: t => 1 - Math.pow(1 - t, 3),
  linear: t => t,
};

export class Tweens {
  constructor() { this.list = []; }
  add(duration, fn, { delay = 0, easing = ease.inOut } = {}) {
    return new Promise(resolve => this.list.push({ start: null, duration: Math.max(1, duration), delay, fn, easing, resolve }));
  }
  update(now) {
    this.list = this.list.filter(tw => {
      if (tw.start === null) tw.start = now + tw.delay;
      if (now < tw.start) return true;
      const k = Math.min(1, (now - tw.start) / tw.duration);
      tw.fn(tw.easing(k));
      if (k >= 1) { tw.resolve(); return false; }
      return true;
    });
  }
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

// ------------------------------------------------------------------------------------ geometry helpers

function box(w, h, d, m, x = 0, y = 0, z = 0) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
  mesh.position.set(x, y, z);
  mesh.castShadow = mesh.receiveShadow = true;
  return mesh;
}

function rbox(w, h, d, r, m, x = 0, y = 0, z = 0) {
  const mesh = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 4, r), m);
  mesh.position.set(x, y, z);
  mesh.castShadow = mesh.receiveShadow = true;
  return mesh;
}

function componentMaterials() {
  const main = new THREE.MeshStandardMaterial({ color: NEUTRAL.clone(), metalness: 0.25, roughness: 0.5, emissive: new THREE.Color(0), side: THREE.DoubleSide });
  const dark = new THREE.MeshStandardMaterial({ color: NEUTRAL.clone().multiplyScalar(0.45), metalness: 0.3, roughness: 0.6, emissive: new THREE.Color(0), side: THREE.DoubleSide });
  return { main, dark, list: [{ mat: main, k: 1 }, { mat: dark, k: 0.45 }] };
}

const parts = {
  chip(M, size = 0.36, h = 0.04) {
    const g = new THREE.Group();
    g.add(box(size, h, size, M.dark, 0, h / 2, 0));
    g.add(box(size * 0.62, h * 0.7, size * 0.62, M.main, 0, h + h * 0.35, 0));
    return g;
  },
  heatsink(M, w = 0.8, h = 0.45, d = 0.8) {
    const g = new THREE.Group();
    g.add(box(w, 0.06, d, M.dark, 0, 0.03, 0));
    const fins = 11;
    for (let i = 0; i < fins; i++) g.add(box(0.025, h - 0.06, d * 0.96, M.main, -w / 2 + 0.04 + i * ((w - 0.08) / (fins - 1)), 0.06 + (h - 0.06) / 2, 0));
    return g;
  },
  dimm(M, len = 0.85, h = 0.03, wid = 0.26, vertical = false) {
    const g = new THREE.Group();
    if (vertical) {
      g.add(box(0.035, h, len, M.main, 0, h / 2, 0));
      for (let i = 0; i < 8; i++) g.add(box(0.05, h * 0.3, len * 0.09, M.dark, 0, h * 0.55, -len / 2 + len * 0.08 + i * len * 0.12));
    } else {
      g.add(box(len, h, wid, M.main, 0, h / 2, 0));
      for (let i = 0; i < 6; i++) g.add(box(len * 0.11, h * 0.8, wid * 0.55, M.dark, -len / 2 + len * 0.1 + i * len * 0.16, h * 1.2, 0));
    }
    return g;
  },
  m2(M, len = 0.8, wid = 0.22) {
    const g = new THREE.Group();
    g.add(box(len, 0.02, wid, M.main, 0, 0.01, 0));
    for (let i = 0; i < 3; i++) g.add(box(len * 0.2, 0.025, wid * 0.7, M.dark, -len / 2 + len * 0.2 + i * len * 0.27, 0.03, 0));
    return g;
  },
  drive(M, w, h, d) {
    const g = new THREE.Group();
    g.add(box(w, h, d, M.main, 0, h / 2, 0));
    g.add(box(w * 1.02, h * 1.04, 0.05, M.dark, 0, h / 2, d / 2 + 0.02));
    g.add(box(w * 0.5, h * 0.12, 0.02, M.main, 0, h * 0.72, d / 2 + 0.05));
    return g;
  },
  battery(M, w = 2.7, h = 0.1, d = 0.72) {
    const g = new THREE.Group();
    const cells = 3;
    for (let i = 0; i < cells; i++) g.add(rbox(w / cells - 0.04, h, d, 0.03, M.main, -w / 2 + (i + 0.5) * (w / cells), h / 2, 0));
    g.add(box(w * 0.3, h * 0.5, 0.08, M.dark, 0, h * 0.3, -d / 2 - 0.02));
    return g;
  },
  fan(M, r, h, axis = 'y') {
    const g = new THREE.Group();
    const inner = new THREE.Group();
    const housing = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 36, 1, true), M.dark);
    housing.castShadow = true;
    const rotor = new THREE.Group();
    rotor.add(new THREE.Mesh(new THREE.CylinderGeometry(r * 0.3, r * 0.3, h * 0.8, 24), M.main));
    for (let i = 0; i < 9; i++) {
      const pivot = new THREE.Group();
      pivot.rotation.y = (i / 9) * Math.PI * 2;
      const blade = new THREE.Mesh(new THREE.BoxGeometry(r * 0.62, h * 0.06, r * 0.28), M.main);
      blade.position.x = r * 0.58;
      blade.rotation.x = 0.55;
      pivot.add(blade);
      rotor.add(pivot);
    }
    rotor.userData.spin = true;
    inner.add(housing, rotor);
    if (axis === 'z') inner.rotation.x = Math.PI / 2;
    g.add(inner);
    return { group: g, rotor };
  },
  psu(M, w = 0.75, h = 0.4, d = 1.1) {
    const g = new THREE.Group();
    g.add(box(w, h, d, M.main, 0, h / 2, 0));
    g.add(box(w * 0.9, h * 0.85, 0.03, M.dark, 0, h / 2, -d / 2 - 0.01));
    g.add(box(0.14, 0.1, 0.04, M.dark, w * 0.25, h * 0.7, -d / 2 - 0.03));
    return g;
  },
  gpuCard(M, len = 1.7, h = 0.32, t = 0.26) {
    const g = new THREE.Group();
    g.add(box(len, h, t, M.main, 0, h / 2, 0));
    for (const x of [-len * 0.25, len * 0.25]) {
      const f = new THREE.Mesh(new THREE.CylinderGeometry(h * 0.36, h * 0.36, 0.02, 24), M.dark);
      f.rotation.x = Math.PI / 2;
      f.position.set(x, h / 2, t / 2 + 0.01);
      g.add(f);
    }
    return g;
  },
};

function drawScreen(canvas, state, text = '') {
  const c = canvas.getContext('2d');
  const { width: w, height: h } = canvas;
  const grd = c.createLinearGradient(0, 0, w, h);
  grd.addColorStop(0, '#07182b');
  grd.addColorStop(1, '#0b2f45');
  c.fillStyle = grd;
  c.fillRect(0, 0, w, h);
  c.strokeStyle = 'rgba(56,189,248,.9)';
  c.lineWidth = 10;
  c.beginPath();
  const cx = w / 2, cy = h * 0.42;
  c.moveTo(cx - 170, cy + 40);
  c.bezierCurveTo(cx - 80, cy + 40, cx - 90, cy - 50, cx, cy - 50);
  c.bezierCurveTo(cx + 80, cy - 50, cx + 70, cy + 20, cx + 170, cy - 10);
  c.stroke();
  c.fillStyle = '#e6edf6';
  c.font = '600 54px Inter, sans-serif';
  c.textAlign = 'center';
  c.fillText('DriftOps agent', cx, h * 0.68);
  c.fillStyle = state === 'scanning' ? '#38bdf8' : state === 'done' ? '#86efac' : '#8b9bb0';
  c.font = '500 34px Inter, sans-serif';
  c.fillText(text || (state === 'scanning' ? 'Analyzing telemetry…' : 'Telemetry ready'), cx, h * 0.8);
}

// ------------------------------------------------------------------------------------ layouts

function laptopLayout(counts) {
  const L = { shell: [], internals: [], slots: {}, overflow: [], extras: {} };
  const shellMat = new THREE.MeshPhysicalMaterial({ color: 0xb4bcc8, metalness: 0.85, roughness: 0.32, clearcoat: 0.4, transparent: true });
  const keyMat = new THREE.MeshStandardMaterial({ color: 0x1b222d, roughness: 0.8, transparent: true });
  const root = new THREE.Group();

  const base = rbox(3.6, 0.22, 2.5, 0.07, shellMat, 0, 0.11, 0);
  root.add(base);
  L.shell.push(base);

  const keyGeo = new THREE.BoxGeometry(0.19, 0.03, 0.19);
  const keys = new THREE.InstancedMesh(keyGeo, keyMat, 14 * 5);
  const m4 = new THREE.Matrix4();
  let n = 0;
  for (let r = 0; r < 5; r++) for (let c = 0; c < 14; c++) {
    m4.makeTranslation(-1.43 + c * 0.22, 0.235, -1.0 + r * 0.22);
    keys.setMatrixAt(n++, m4);
  }
  root.add(keys);
  L.shell.push(keys);
  const pad = box(1.1, 0.012, 0.6, keyMat, 0, 0.226, 0.72);
  root.add(pad);
  L.shell.push(pad);

  // Lid hinged at the back edge.
  const hinge = new THREE.Group();
  hinge.position.set(0, 0.22, -1.22);
  const lid = rbox(3.6, 0.08, 2.45, 0.06, shellMat, 0, 0.04, 1.22);
  hinge.add(lid);
  L.shell.push(lid);
  const canvas = document.createElement('canvas');
  canvas.width = 1024; canvas.height = 640;
  drawScreen(canvas, 'idle');
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  const screenMat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, side: THREE.DoubleSide });
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(3.3, 2.1), screenMat);
  screen.rotation.x = Math.PI / 2;
  screen.position.set(0, -0.002, 1.22);
  hinge.add(screen);
  L.shell.push(screen);
  hinge.rotation.x = -1.95;
  root.add(hinge);
  L.extras = { hinge, screenCanvas: canvas, screenTex: tex, lidOpen: -1.95, lidWide: -2.25 };

  const board = box(3.4, 0.02, 2.3, new THREE.MeshStandardMaterial({ color: 0x0c3a2c, roughness: 0.75, metalness: 0.2 }), 0, 0.03, 0);
  root.add(board);
  L.internals.push(board);

  const V = (x, y, z) => new THREE.Vector3(x, y, z);
  L.slots.cpu = [{ pos: V(-0.25, 0.04, -0.55), build: M => parts.chip(M, 0.4) }];
  L.slots.gpu = [{ pos: V(0.5, 0.04, -0.55), build: M => parts.chip(M, 0.44) }];
  L.slots.memory = [
    { pos: V(-1.1, 0.04, -0.12), build: M => parts.dimm(M) },
    { pos: V(-1.1, 0.04, 0.2), build: M => parts.dimm(M) },
  ];
  L.slots.storage = [
    { pos: V(1.05, 0.04, -0.05), build: M => parts.m2(M) },
    { pos: V(1.05, 0.04, 0.28), build: M => parts.m2(M) },
  ];
  L.slots.battery = [{ pos: V(0, 0.04, 0.8), build: M => parts.battery(M) }];
  L.slots.power = [{ pos: V(-1.5, 0.04, 0.3), build: M => parts.chip(M, 0.22, 0.06) }];
  L.slots.cooling = [{
    pos: V(0, 0, 0),
    build: (M, fans) => {
      const g = new THREE.Group();
      for (const x of [-1.3, 1.3]) {
        const f = parts.fan(M, 0.3, 0.12);
        f.group.position.set(x, 0.1, -0.78);
        g.add(f.group);
        fans.push(f.rotor);
      }
      const copper = M.main;
      for (const [x, z] of [[-1.3, -0.78], [1.3, -0.78]]) {
        const curve = new THREE.CatmullRomCurve3([V(-0.25, 0.14, -0.55), V(x * 0.5, 0.15, -0.72), V(x * 0.82, 0.14, z)]);
        const pipe = new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.028, 8), copper);
        pipe.castShadow = true;
        g.add(pipe);
      }
      return g;
    },
  }];
  L.overflow = [V(-0.9, 0.04, -0.55), V(0.1, 0.04, 0.2), V(-0.4, 0.04, 0.2), V(1.4, 0.04, -0.5)];

  L.root = root;
  L.size = new THREE.Vector3(3.6, 2.6, 3.2);
  L.camera = { pos: V(4.7, 3.9, 5.7), target: V(0, 0.55, -0.35) };
  L.lift = 0.32;
  return L;
}

function serverLayout(counts) {
  const L = { shell: [], internals: [], slots: {}, overflow: [], extras: {} };
  const V = (x, y, z) => new THREE.Vector3(x, y, z);
  const root = new THREE.Group();
  const shellMat = new THREE.MeshPhysicalMaterial({ color: 0x9aa4b2, metalness: 0.8, roughness: 0.38, clearcoat: 0.25, transparent: true });
  const trimMat = new THREE.MeshStandardMaterial({ color: 0x1a212c, metalness: 0.6, roughness: 0.5, transparent: true });
  const W = 4.6, H = 0.9, D = 3.6;

  const chassis = rbox(W, H, D, 0.035, shellMat, 0, H / 2, 0);
  root.add(chassis);
  L.shell.push(chassis);
  for (const s of [-1, 1]) {
    const ear = box(0.16, H, 0.08, trimMat, s * (W / 2 + 0.08), H / 2, D / 2 - 0.04);
    const handle = box(0.06, H * 0.6, 0.16, trimMat, s * (W / 2 - 0.12), H / 2, D / 2 + 0.1);
    root.add(ear, handle);
    L.shell.push(ear, handle);
  }
  const ledMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true });
  const led = box(1.2, 0.03, 0.02, ledMat, 0, H - 0.08, D / 2 + 0.01);
  root.add(led);
  L.shell.push(led);

  const board = box(W - 0.3, 0.03, D - 0.3, new THREE.MeshStandardMaterial({ color: 0x0c3a2c, roughness: 0.75, metalness: 0.2 }), 0, 0.05, 0);
  root.add(board);
  L.internals.push(board);

  const nBays = Math.min(12, Math.max(4, counts.storage || 0));
  const cols = 4, rows = Math.ceil(nBays / cols);
  const dh = Math.min(0.32, (H - 0.2) / rows - 0.04);
  const dw = (W - 0.5) / cols - 0.06;
  L.slots.storage = [];
  for (let i = 0; i < nBays; i++) {
    const c = i % cols, r = Math.floor(i / cols);
    L.slots.storage.push({ pos: V(-(W - 0.5) / 2 + dw / 2 + 0.03 + c * (dw + 0.06), 0.08 + r * (dh + 0.04), 1.2), build: M => parts.drive(M, dw, dh, 1.0) });
  }
  L.emptyBay = (i) => {
    const blank = new THREE.MeshStandardMaterial({ color: 0x2a313c, metalness: 0.5, roughness: 0.6 });
    const s = L.slots.storage[i];
    const g = parts.drive({ main: blank, dark: blank }, dw, dh, 1.0);
    g.position.copy(s.pos);
    return g;
  };

  L.slots.cooling = [{
    pos: V(0, 0, 0),
    build: (M, fans) => {
      const g = new THREE.Group();
      for (let i = 0; i < 6; i++) {
        const f = parts.fan(M, 0.3, 0.22, 'z');
        f.group.position.set(-1.85 + i * 0.74, 0.42, 0.42);
        g.add(f.group);
        fans.push(f.rotor);
      }
      return g;
    },
  }];
  L.slots.cpu = [
    { pos: V(-1.0, 0.065, -0.45), build: M => parts.heatsink(M) },
    { pos: V(1.0, 0.065, -0.45), build: M => parts.heatsink(M) },
  ];
  L.slots.memory = [];
  for (const cx of [-1.0, 1.0]) for (const side of [-1, 1]) for (let i = 0; i < 3; i++) {
    L.slots.memory.push({ pos: V(cx + side * (0.52 + i * 0.09), 0.065, -0.45), build: M => parts.dimm(M, 0.9, 0.36, 0, true) });
  }
  L.slots.power = [
    { pos: V(-1.8, 0.065, -1.15), build: M => parts.psu(M) },
    { pos: V(1.8, 0.065, -1.15), build: M => parts.psu(M) },
  ];
  L.slots.gpu = [{ pos: V(0, 0.065, -1.3), build: M => parts.gpuCard(M) }];
  L.slots.battery = [{ pos: V(0, 0.065, 0.0), build: M => parts.chip(M, 0.18, 0.03) }];
  L.overflow = [V(0, 0.065, -0.1), V(-0.4, 0.065, -1.0), V(0.4, 0.065, -1.0)];

  L.root = root;
  L.size = new THREE.Vector3(W, H, D);
  L.camera = { pos: V(5.6, 3.9, 6.4), target: V(0, 0.35, 0) };
  L.lift = 0.55;
  return L;
}

// ------------------------------------------------------------------------------------ scene

export class HardwareScene {
  constructor(container, labelContainer) {
    this.container = container;
    this.tweens = new Tweens();
    this.components = new Map();
    this.fans = [];
    this.state = 'empty';
    this.onSelect = () => {};
    this.selected = null;
    this.hovered = null;

    const r = (this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }));
    r.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.toneMappingExposure = 1.05;
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(r.domElement);

    this.labelRenderer = new CSS2DRenderer({ element: labelContainer });

    const scene = (this.scene = new THREE.Scene());
    const pmrem = new THREE.PMREMGenerator(r);
    scene.environment = pmrem.fromScene(new RoomEnvironment(r), 0.04).texture;
    scene.environmentIntensity = 0.6;

    this.camera = new THREE.PerspectiveCamera(38, 1, 0.05, 200);
    this.camera.position.set(6, 4, 7);
    const controls = (this.controls = new OrbitControls(this.camera, r.domElement));
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.minDistance = 1.2;
    controls.maxDistance = 20;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.6;
    controls.addEventListener('start', () => { controls.autoRotate = false; });

    scene.add(new THREE.HemisphereLight(0xbfd8ff, 0x0b1320, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(4, 8, 5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.left = key.shadow.camera.bottom = -6;
    key.shadow.camera.right = key.shadow.camera.top = 6;
    key.shadow.radius = 6;
    key.shadow.bias = -0.0005;
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x38bdf8, 1.1);
    rim.position.set(-6, 3, -5);
    scene.add(rim);

    const floor = new THREE.Mesh(new THREE.CircleGeometry(12, 64), new THREE.ShadowMaterial({ opacity: 0.35 }));
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);
    const grid = new THREE.PolarGridHelper(9, 16, 8, 64, 0x1e3a5f, 0x14263d);
    grid.material.transparent = true;
    grid.material.opacity = 0.45;
    grid.position.y = 0.001;
    scene.add(grid);

    this.ring = new THREE.Mesh(new THREE.RingGeometry(1, 1.04, 96),
      new THREE.MeshBasicMaterial({ color: SCAN, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.ring.rotation.x = -Math.PI / 2;
    this.ring.position.y = 0.005;
    scene.add(this.ring);

    this.beam = new THREE.Group();
    const beamMat = new THREE.MeshBasicMaterial({ color: SCAN, transparent: true, opacity: 0.16, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false });
    const beamCore = new THREE.MeshBasicMaterial({ color: 0xbae6fd, transparent: true, opacity: 0.8, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false });
    this.beamPlane = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), beamMat);
    this.beamLine = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), beamCore);
    this.beam.add(this.beamPlane, this.beamLine);
    this.beam.rotation.y = Math.PI / 2;
    this.beam.visible = false;
    scene.add(this.beam);

    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.selectionBox = null;
    this._bindPointer();

    this.resize();
    window.addEventListener('resize', () => this.resize());
    this.clock = new THREE.Clock();
    this.setActive(true);
  }

  /** Only the visible view renders; hidden views stop their animation loop. */
  setActive(on) {
    this.renderer.setAnimationLoop(on ? t => this._frame(t) : null);
    if (on) { this.clock.getDelta(); this.resize(); }
  }

  resize() {
    const w = this.container.clientWidth || window.innerWidth;
    const h = this.container.clientHeight || window.innerHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    this.labelRenderer.setSize(w, h);
  }

  // -------------------------------------------------------------------------- build

  load(machine, components) {
    this._dispose();
    const counts = {};
    for (const c of components) counts[c.type] = (counts[c.type] || 0) + 1;
    const L = (this.layout = machine.form_factor === 'server' ? serverLayout(counts) : laptopLayout(counts));
    this.scene.add(L.root);
    for (const m of L.shell) {
      m.material.transparent = true;
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 35),
        new THREE.LineBasicMaterial({ color: SCAN, transparent: true, opacity: 0, depthWrite: false }));
      if (!(m instanceof THREE.InstancedMesh) && m.geometry.type !== 'PlaneGeometry') {
        m.add(edges);
        m.userData.edges = edges;
      }
    }

    // Assign layout slots to components of each type.
    const byType = {};
    for (const c of components) (byType[c.type] = byType[c.type] || []).push(c);
    let overflowIdx = 0;
    const usedStorage = new Set();
    for (const [type, list] of Object.entries(byType)) {
      const slots = L.slots[type] || [];
      const groups = list.map(() => []);
      if (slots.length) {
        const nSlots = type === 'storage' && L.emptyBay ? Math.min(slots.length, list.length) : slots.length;
        for (let s = 0; s < nSlots; s++) {
          const ci = list.length >= nSlots ? s : Math.floor((s * list.length) / nSlots);
          groups[ci].push(slots[s]);
          if (type === 'storage') usedStorage.add(s);
        }
      }
      list.forEach((c, i) => {
        const M = componentMaterials();
        const group = new THREE.Group();
        const mySlots = groups[i] || [];
        if (!mySlots.length) {
          const pos = L.overflow[overflowIdx++ % L.overflow.length];
          mySlots.push({ pos, build: m => parts.chip(m, 0.28) });
        }
        for (const slot of mySlots) {
          const obj = slot.build(M, this.fans);
          obj.position.add(slot.pos);
          group.add(obj);
        }
        group.traverse(o => { if (o.isMesh) o.userData.componentId = c.id; });
        L.root.add(group);
        this.components.set(c.id, { ...c, group, M, status: null, health: null, glow: 0, scanGlow: 0, lift: 0 });
      });
    }
    if (L.emptyBay) L.slots.storage.forEach((_, i) => { if (!usedStorage.has(i)) L.root.add(L.emptyBay(i)); });

    // Labels, staggered per type so neighbours do not overlap.
    const perType = {};
    for (const comp of this.components.values()) {
      const bbox = new THREE.Box3().setFromObject(comp.group);
      const center = bbox.getCenter(new THREE.Vector3());
      const k = (perType[comp.type] = (perType[comp.type] || 0) + 1) - 1;
      const el = document.createElement('div');
      el.className = 'label3d';
      el.innerHTML = `<span class="ld"></span><span class="ln"></span><span class="lh"></span>`;
      el.querySelector('.ln').textContent = shortName(comp);
      el.addEventListener('click', e => { e.stopPropagation(); this.onSelect(comp.id); });
      const label = new CSS2DObject(el);
      label.position.set(center.x, bbox.max.y + 0.12 + (k % 2) * 0.34, center.z);
      label.visible = false;
      comp.group.add(label);
      comp.label = label;
      comp.labelEl = el;
      comp.center = center;
    }

    this.state = 'idle';
    this.selected = null;
    this.ring.scale.setScalar(Math.max(L.size.x, L.size.z) * 0.75);
    this.controls.target.copy(L.camera.target);
    this.camera.position.copy(L.camera.pos).multiplyScalar(1.25);
    this.controls.autoRotate = true;
    this.tweens.add(1200, k => this.camera.position.lerpVectors(L.camera.pos.clone().multiplyScalar(1.25), L.camera.pos, k), { easing: ease.out });
  }

  _dispose() {
    if (this.layout) {
      this.layout.root.traverse(o => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => { m.map?.dispose(); m.dispose(); });
        if (o.isCSS2DObject) o.element.remove();
      });
      this.scene.remove(this.layout.root);
    }
    this._clearSelectionBox();
    this.components.clear();
    this.fans = [];
    this.layout = null;
    this.tweens.list = [];
  }

  // -------------------------------------------------------------------------- animation primitives

  setShellOpacity(o) {
    for (const m of this.layout.shell) {
      m.material.opacity = o;
      m.material.depthWrite = o > 0.97;
      if (m.userData.edges) m.userData.edges.material.opacity = (1 - o) * 0.55;
    }
  }

  _screen(state, text) {
    const x = this.layout?.extras;
    if (!x?.screenCanvas) return;
    drawScreen(x.screenCanvas, state, text);
    x.screenTex.needsUpdate = true;
  }

  async _sweep(duration) {
    const L = this.layout;
    const span = L.size.x * 0.62;
    this.beamPlane.scale.set(L.size.z * 1.5, L.size.y * 2.2 + 0.6, 1);
    this.beamPlane.position.y = (L.size.y * 2.2 + 0.6) / 2 - 0.1;
    this.beamLine.scale.set(L.size.z * 1.5, 0.025, 1);
    this.beamLine.position.y = 0.02;
    this.beam.visible = true;
    this.ring.material.opacity = 0.9;
    const pass = (from, to, ms) => this.tweens.add(ms, k => {
      this.beam.position.x = from + (to - from) * k;
      this.beamPlane.material.opacity = 0.16 * Math.sin(Math.PI * Math.min(1, k * 1.2));
    });
    await pass(-span, span, duration / 2);
    await pass(span, -span, duration / 2);
    this.beam.visible = false;
    this.tweens.add(600, k => { this.ring.material.opacity = 0.9 * (1 - k); });
  }

  _cameraTo(pos, target, ms = 1200) {
    const p0 = this.camera.position.clone();
    const t0 = this.controls.target.clone();
    return this.tweens.add(ms, k => {
      this.camera.position.lerpVectors(p0, pos, k);
      this.controls.target.lerpVectors(t0, target, k);
    });
  }

  // -------------------------------------------------------------------------- analysis flow

  async playAnalysis(analysisPromise) {
    if (this.state === 'empty' || this.state === 'scanning') return null;
    const L = this.layout;
    this.select(null);
    if (this.state === 'analyzed') await this._restore(500);
    this.state = 'scanning';
    this.controls.autoRotate = false;
    this._screen('scanning');

    const camPos = L.camera.pos.clone().multiplyScalar(0.95).add(new THREE.Vector3(0, 0.6, 0));
    const anims = [
      this._cameraTo(camPos, L.camera.target, 1300),
      this.tweens.add(1500, k => this.setShellOpacity(1 - 0.9 * k), { delay: 450 }),
      this._sweep(2600),
    ];
    if (L.extras.hinge) anims.push(this.tweens.add(1200, k => { L.extras.hinge.rotation.x = L.extras.lidOpen + (L.extras.lidWide - L.extras.lidOpen) * k; }, { delay: 300 }));

    let analysis;
    try {
      [analysis] = await Promise.all([analysisPromise, ...anims]);
    } catch (err) {
      await Promise.allSettled(anims);
      await this._restore(600);
      this.state = 'idle';
      this._screen('idle');
      throw err;
    }
    if (this.layout !== L) return null; // machine switched mid-animation

    await this.tweens.add(700, k => {
      for (const c of this.components.values()) {
        c.lift = k;
        c.group.position.y = L.lift * k;
      }
    });
    await this._colorize(analysis);
    this.state = 'analyzed';
    this._screen('done', `Overall health ${Math.round(analysis.overall.health)}/100`);
    return analysis;
  }

  async _colorize(analysis) {
    const results = new Map(analysis.components.map(r => [r.id, r]));
    const ordered = [...this.components.values()].sort((a, b) => a.center.x - b.center.x || a.center.z - b.center.z);
    const jobs = ordered.map((comp, i) => {
      const r = results.get(comp.id);
      if (!r) return Promise.resolve();
      const target = new THREE.Color(STATUS_HEX[r.status]);
      const tinted = NEUTRAL.clone().lerp(target, 0.88);
      return sleep(i * 120).then(() => {
        comp.status = r.status;
        comp.health = r.health;
        comp.labelEl.style.color = `#${target.getHexString()}`;
        comp.labelEl.querySelector('.lh').textContent = Math.round(r.health);
        comp.label.visible = true;
        requestAnimationFrame(() => comp.labelEl.classList.add('show'));
        return this.tweens.add(750, k => {
          for (const { mat, k: shade } of comp.M.list) {
            mat.color.copy(NEUTRAL).multiplyScalar(shade).lerp(tinted.clone().multiplyScalar(shade), k);
            mat.emissive.copy(SCAN).lerp(target, k);
          }
          comp.glow = 1.3 * (1 - k) + EMISSIVE_BASE[r.status] * k;
        }, { easing: ease.out });
      });
    });
    await Promise.all(jobs);
  }

  async _restore(ms) {
    const L = this.layout;
    for (const c of this.components.values()) {
      c.labelEl.classList.remove('show');
      c.label.visible = false;
    }
    const from = [...this.components.values()].map(c => ({ c, colors: c.M.list.map(x => x.mat.color.clone()), glow: c.glow }));
    await this.tweens.add(ms, k => {
      this.setShellOpacity(Math.min(1, this.layout.shell[0].material.opacity + (1 - this.layout.shell[0].material.opacity) * k));
      if (L.extras.hinge) L.extras.hinge.rotation.x += (L.extras.lidOpen - L.extras.hinge.rotation.x) * k;
      for (const { c, colors, glow } of from) {
        c.status = null;
        c.M.list.forEach((x, i) => x.mat.color.copy(colors[i]).lerp(NEUTRAL.clone().multiplyScalar(x.k), k));
        c.glow = glow * (1 - k);
        c.group.position.y = L.lift * (1 - k) * c.lift;
      }
    });
    for (const c of this.components.values()) c.lift = 0;
  }

  async reset() {
    if (!this.layout || this.state === 'scanning') return;
    this.select(null);
    await this._restore(600);
    this.state = 'idle';
    this._screen('idle');
  }

  // -------------------------------------------------------------------------- selection

  select(id) {
    const comp = id ? this.components.get(id) : null;
    this.selected = comp || null;
    this._clearSelectionBox();
    for (const c of this.components.values()) {
      const dim = comp && c !== comp;
      c.labelEl.classList.toggle('selected', c === comp);
      for (const { mat } of c.M.list) {
        mat.transparent = true;
        const to = dim ? 0.22 : 1;
        const from = mat.opacity;
        this.tweens.add(350, k => { mat.opacity = from + (to - from) * k; mat.depthWrite = mat.opacity > 0.95; });
      }
    }
    if (!this.layout) return;
    if (comp) {
      const bbox = new THREE.Box3().setFromObject(comp.group).expandByScalar(0.06);
      this.selectionBox = new THREE.Box3Helper(bbox, SCAN);
      this.selectionBox.material.transparent = true;
      this.selectionBox.material.depthTest = false;
      this.scene.add(this.selectionBox);
      const center = bbox.getCenter(new THREE.Vector3());
      const radius = bbox.getSize(new THREE.Vector3()).length();
      const dir = this.camera.position.clone().sub(this.controls.target).normalize();
      dir.y = Math.max(dir.y, 0.45);
      dir.normalize();
      // Shift the focus left so the component is not hidden behind the details panel.
      const right = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(0, 1, 0)).normalize();
      const dist = Math.max(3.4, radius * 3.2);
      const target = center.clone().add(right.multiplyScalar(window.innerWidth > 900 ? dist * 0.22 : 0));
      this._cameraTo(target.clone().add(dir.multiplyScalar(dist)), target, 900);
    } else if (this.state === 'analyzed') {
      const L = this.layout;
      this._cameraTo(L.camera.pos.clone().multiplyScalar(0.95).add(new THREE.Vector3(0, 0.6, 0)), L.camera.target, 900);
    }
  }

  _clearSelectionBox() {
    if (this.selectionBox) {
      this.scene.remove(this.selectionBox);
      this.selectionBox.geometry.dispose();
      this.selectionBox.material.dispose();
      this.selectionBox = null;
    }
  }

  _bindPointer() {
    const el = this.renderer.domElement;
    let down = null;
    el.addEventListener('pointerdown', e => { down = { x: e.clientX, y: e.clientY }; });
    el.addEventListener('pointermove', e => { this._pointerEvent = e; });
    el.addEventListener('pointerup', e => {
      if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
      const hit = this._pick(e);
      if (this.state !== 'analyzed') return;
      this.onSelect(hit ? hit : null);
    });
  }

  _pick(e) {
    if (!this.layout) return null;
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const meshes = [];
    for (const c of this.components.values()) c.group.traverse(o => { if (o.isMesh) meshes.push(o); });
    const hit = this.raycaster.intersectObjects(meshes, false)[0];
    return hit ? hit.object.userData.componentId : null;
  }

  // -------------------------------------------------------------------------- loop

  _frame(now) {
    const dt = Math.min(0.05, this.clock.getDelta());
    this.tweens.update(now);
    this.controls.update();

    if (this._pointerEvent && this.state === 'analyzed') {
      const id = this._pick(this._pointerEvent);
      this.hovered = id ? this.components.get(id) : null;
      this.renderer.domElement.style.cursor = id ? 'pointer' : '';
      this._pointerEvent = null;
    }

    const t = now / 1000;
    const cooling = [...this.components.values()].find(c => c.type === 'cooling');
    const speed = FAN_SPEED[cooling?.status || 'idle'];
    for (const rotor of this.fans) rotor.rotation.y += dt * speed;

    for (const c of this.components.values()) {
      let intensity = c.glow;
      if (this.state === 'scanning' && this.beam.visible) {
        const wx = c.center.x;
        c.scanGlow = Math.max(c.scanGlow * 0.93, Math.max(0, 1 - Math.abs(this.beam.position.x - wx) / 0.45));
        for (const { mat } of c.M.list) mat.emissive.copy(SCAN);
        intensity = 0.15 + 0.25 * (0.5 + 0.5 * Math.sin(t * 6 + c.center.x)) + c.scanGlow * 1.2;
      } else if (c.status) {
        intensity += PULSE[c.status] * (0.5 + 0.5 * Math.sin(t * (c.status === 'critical' ? 5 : 3)));
      }
      if (this.hovered === c) intensity += 0.35;
      if (this.selected && this.selected !== c) intensity *= 0.25;
      for (const { mat } of c.M.list) mat.emissiveIntensity = intensity;
    }
    if (this.selectionBox) this.selectionBox.material.opacity = 0.55 + 0.35 * Math.sin(t * 4);
    if (this.ring.material.opacity > 0.01) this.ring.rotation.z += dt * 0.6;

    this.renderer.render(this.scene, this.camera);
    this.labelRenderer.render(this.scene, this.camera);
  }
}

function shortName(c) {
  const name = c.name || c.id;
  return name.split('·')[0].trim() || name;
}
