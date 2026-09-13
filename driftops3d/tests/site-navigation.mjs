/** Browser regression: run the app and Chrome with --remote-debugging-port=9223, then:
 * node driftops3d/tests/site-navigation.mjs http://127.0.0.1:8765 http://127.0.0.1:9223
 * Uses Node 22's built-in WebSocket; no test dependencies are required.
 */
import assert from 'node:assert/strict';

const base = process.argv[2] || 'http://127.0.0.1:8765';
const debug = process.argv[3] || 'http://127.0.0.1:9223';
const tabs = await (await fetch(`${debug}/json/list`)).json();
const socket = new WebSocket(tabs.find(t => t.type === 'page').webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
let sequence = 0;
const pending = new Map(), errors = [];
socket.onmessage = event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const p = pending.get(message.id);
    pending.delete(message.id);
    message.error ? p.reject(new Error(message.error.message)) : p.resolve(message.result);
  } else if (message.method === 'Runtime.exceptionThrown') {
    errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
  }
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++sequence;
  pending.set(id, { resolve, reject });
  socket.send(JSON.stringify({ id, method, params }));
});
const evaluate = async expression => {
  const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
};
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const waitFor = async expression => {
  const deadline = Date.now() + 45000;
  do {
    assert.deepEqual(errors, [], 'No browser exceptions');
    if (await evaluate(expression)) return;
    await sleep(150);
  } while (Date.now() < deadline);
  throw new Error(`Timed out: ${expression}`);
};
const check = async (expression, label) => {
  assert.ok(await evaluate(expression), label);
  console.log(`PASS: ${label}`);
};
const clickDevice = async id => {
  // Project a point on the actual screen/server front, then send real mouse input
  // through the page. Calling the scene's open callback would miss picking failures.
  const point = await evaluate(`(async () => {
    const THREE = await import('three');
    const scene = window.navigationScene, device = scene.slabs.get(${JSON.stringify(id)});
    const p = device.data.form_factor === 'laptop'
      ? new THREE.Vector3(0, 1.35, -1.67) : new THREE.Vector3(0, 0, 1.8);
    device.mesh.localToWorld(p).project(scene.camera);
    const rect = scene.renderer.domElement.getBoundingClientRect();
    return { x: rect.left + (p.x + 1) * rect.width / 2, y: rect.top + (1 - p.y) * rect.height / 2 };
  })()`);
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', ...point, button: 'left', clickCount: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', ...point, button: 'left', clickCount: 1 });
  await waitFor(`location.hash === ${JSON.stringify(`#/device/${id}`)} && !document.querySelector('#deviceView').hidden && document.querySelectorAll('#overview .item').length > 0`);
  await check(`navigationScene.zoomed?.id === ${JSON.stringify(id)} && navigationScene.camera.position.toArray().every(Number.isFinite)`, `${id} opens through a valid zoom transition`);
  if (id.startsWith('hq-')) {
    await check(`window.navigationMatch?.id === ${JSON.stringify(id)} && navigationMatch.sameGeometry && navigationMatch.pixelError < 0.5`, 'Laptop exterior and screen projection match across the view switch');
  }
};

try {
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Runtime.discardConsoleEntries');
  errors.length = 0;   // Runtime.enable can replay exceptions from the previous page.
  await send('Network.enable');
  await send('Network.setCacheDisabled', { cacheDisabled: true });
  await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 850, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: 'about:blank' });
  await waitFor('location.href === "about:blank"');
  await send('Page.navigate', { url: `${base}/#/site/hq` });
  await waitFor(`document.querySelector('#twinHead')?.innerText.includes('3 laptops') && !document.querySelector('#analyzeBtn').disabled`);
  await evaluate(`(async () => {
    const THREE = await import('three');
    const prototype = (await import('/js/site-scene.js')).SiteScene.prototype;
    const frame = prototype._frame;
    prototype._frame = function(now) { window.navigationScene = this; return frame.call(this, now); };
    const hardware = (await import('/js/scene.js')).HardwareScene.prototype;
    const load = hardware.load;
    hardware.load = function(machine, ...args) {
      const result = load.call(this, machine, ...args);
      const twin = window.navigationScene;
      if (machine.form_factor !== 'laptop' || twin?.zoomed?.id !== machine.id) return result;
      const outside = [];
      twin.slabs.get(machine.id).mesh.traverse(o => { if (o.isMesh) outside.push(o); });
      twin.root.updateMatrixWorld(true);
      this.layout.root.updateMatrixWorld(true);
      twin.camera.updateMatrixWorld(true);
      this.camera.updateMatrixWorld(true);
      const project = (point, mesh, scene) => {
        const p = point.clone().applyMatrix4(mesh.matrixWorld).project(scene.camera);
        const r = scene.renderer.domElement.getBoundingClientRect();
        return new THREE.Vector2(r.left + (p.x + 1) * r.width / 2, r.top + (1 - p.y) * r.height / 2);
      };
      let pixelError = 0, sameGeometry = outside.length === this.layout.shell.length;
      this.layout.shell.forEach((inside, i) => {
        const other = outside[i];
        if (!other) return;
        const a = inside.geometry.attributes.position, b = other.geometry.attributes.position;
        sameGeometry &&= a.count === b.count && a.array.every((v, j) => v === b.array[j]);
        inside.geometry.computeBoundingBox();
        const { min, max } = inside.geometry.boundingBox;
        for (const x of [min.x, max.x]) for (const y of [min.y, max.y]) for (const z of [min.z, max.z]) {
          const p = new THREE.Vector3(x, y, z);
          pixelError = Math.max(pixelError, project(p, inside, this).distanceTo(project(p, other, twin)));
        }
      });
      window.navigationMatch = { id: machine.id, pixelError, sameGeometry };
      return result;
    };
  })()`);
  await waitFor('window.navigationScene && !navigationScene.scanState && navigationScene.tweens.list.length === 0');
  const ids = await evaluate('[...navigationScene.slabs.keys()]');
  assert.equal(ids.length, 3);
  for (const id of ids) {
    await evaluate('location.hash = "#/site/hq"');
    await waitFor('!document.querySelector("#twinView").hidden && navigationScene.selectedRack === null && !navigationScene.zoomed && navigationScene.tweens.list.length === 0');
    await clickDevice(id);
    await check(`(() => {
      const materials = new Set();
      navigationScene.slabs.get(${JSON.stringify(id)}).mesh.traverse(o => { if (o.material) materials.add(o.material); });
      return [...materials].every(m => m.opacity > 0.99);
    })()`, 'Laptop screen, keyboard and chassis remain visible during zoom');
    if (id === ids[0]) {
      await evaluate('document.querySelector("#analyzeBtn").click()');
      await waitFor('!document.querySelector("#analyzeBtn").disabled && document.querySelector("#overview button.item")');
      await evaluate('document.querySelector("#overview button.item").click()');
      await check('!document.querySelector("#panel").hidden && document.querySelector("#panel .evidence")', 'Laptop analysis opens component evidence');
    }
    await evaluate('document.querySelector("#crumbs .back").click()');
    await waitFor('!document.querySelector("#twinView").hidden && !navigationScene.zoomed && navigationScene.tweens.list.length === 0');
    await check('[...navigationScene.slabs.values()].every(s => Math.abs(s.mesh.position.z) < 0.001) && [...navigationScene.racks.values()].every(r => r.labelEl.style.opacity !== "0")', 'Returning restores laptops and group labels');
    await check('!navigationScene.camera.view?.enabled && navigationScene.camera.fov === 35', 'Returning restores the site camera projection');
  }
  await evaluate('location.hash = "#/site/site-a/rack/r06"');
  await waitFor('navigationScene.siteId === "site-a" && navigationScene.selectedRack === "r06" && !document.querySelector("#analyzeBtn").disabled && navigationScene.tweens.list.length === 0');
  await check('navigationScene.slabs.size === 84 && navigationScene.racks.size === 7', 'Site A retains its server racks');
  const serverZ = await evaluate('navigationScene.slabs.get("site-a-609").mesh.position.z');
  await clickDevice('site-a-609');
  await evaluate('document.querySelector("#crumbs .back").click()');
  await waitFor('!document.querySelector("#twinView").hidden && !navigationScene.zoomed && navigationScene.tweens.list.length === 0');
  await check(`Math.abs(navigationScene.slabs.get("site-a-609").mesh.position.z - ${serverZ}) < 0.001`, 'Returning restores the server to its rack');
  assert.deepEqual(errors, [], 'No browser exceptions');
  console.log('PASS: all laptop and server navigation checks');
} finally {
  socket.close();
}
