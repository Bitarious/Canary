/** Verify rejected WebGL attributes and complete graphics unavailability. */
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const base = process.argv[2];
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, args: ['--enable-unsafe-swiftshader'] });
try {
  for (const mobile of [true, false]) {
    const page = await browser.newPage({ viewport: { width: mobile ? 390 : 1440, height: 844 }, hasTouch: mobile });
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function(type, options) {
        if (type.includes('webgl') && options?.antialias) return null;
        return original.call(this, type, options);
      };
    });
    await page.goto(`${base}/#/site/site-a`);
    await page.waitForFunction(() => window.driftops?.state.site && !window.driftops.state.twinScanning);
    await page.evaluate(() => window.driftops.openDevice('site-a-609'));
    await page.waitForFunction(() => window.driftops.state.current?.id === 'site-a-609');
    assert.equal(await page.locator('#stage canvas').count(), 1);
    const options = await page.evaluate(() => ({
      antialias: window.driftops.deviceScene.renderer.getContext().getContextAttributes().antialias,
      ratio: window.driftops.deviceScene.renderer.getPixelRatio(),
      shadows: window.driftops.deviceScene.renderer.shadowMap.enabled,
    }));
    assert.equal(options.antialias, false);
    if (mobile) { assert.equal(options.ratio, 1); assert.equal(options.shadows, false); }
    await page.locator('#analyzeBtn').click();
    await page.waitForFunction(() => window.driftops.state.analysis && !window.driftops.state.scanning);
    await page.locator('#overview button.item').filter({hasText:'Disk 3'}).click();
    assert.ok(await page.locator('#panel').isVisible());
    await page.close();
    console.log(`PASS: ${mobile ? 'mobile' : 'desktop fallback'} renders and selects a disk when anti-aliasing is refused`);
  }
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true });
  await page.addInitScript(() => {
    if (new URLSearchParams(location.search).get('graphics') === 'basic') return;
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, options) {
      return type.includes('webgl') ? null : original.call(this, type, options);
    };
  });
  await page.goto(`${base}/#/device/site-a-609`);
  await page.getByRole('button', {name:'Retry 3D'}).waitFor();
  assert.ok(await page.locator('#toast').isVisible());
  await page.getByRole('link', {name:'View device list'}).click();
  await page.waitForFunction(() => window.driftops.state.fleetRows.length > 0);
  await page.goto(`${base}/#/device/site-a-609`);
  await page.getByRole('button', {name:'Retry 3D'}).click();
  await page.waitForFunction(() => window.driftops?.state.current?.id === 'site-a-609');
  assert.match(page.url(), /graphics=basic/);
  assert.equal(await page.locator('#stage canvas').count(), 1);
  console.log('PASS: total WebGL failure preserves list navigation and supports a basic-graphics retry');
} finally { await browser.close(); }
