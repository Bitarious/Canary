/** Verify that the device summary and selected-component details do not cover the mobile canvas. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const base = process.argv[2];
const browser = await chromium.launch({executablePath:process.env.CHROME_PATH, args:['--enable-unsafe-swiftshader']});
try {
  for (const {width, touch} of [{width:390,touch:true}, {width:980,touch:false}, {width:1100,touch:false}, {width:1440,touch:true}]) {
    const page = await browser.newPage({viewport:{width,height:844},hasTouch:touch,reducedMotion:'reduce'});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`${base}/#/device/site-a-609`);
    await page.waitForFunction(()=>window.driftops?.state.current?.id==='site-a-609');
    const stage=await page.locator('#stage').boundingBox();
    const overview=await page.locator('#overview').boundingBox();
    assert.ok(stage.height>=220);
    assert.ok(stage.y+stage.height<=overview.y, 'Summary must stay below the 3D canvas');
    await page.locator('#analyzeBtn').click();
    await page.waitForFunction(()=>window.driftops.state.analysis&&!window.driftops.state.scanning);
    await page.locator('#overview button.item').filter({hasText:'Disk 3'}).click();
    const panel=await page.locator('#panel').boundingBox();
    assert.ok(stage.y+stage.height<=panel.y,'Details must stay below the 3D canvas');
    assert.equal(await page.locator('#stage').evaluate(el=>el.inert),false);
    await page.locator('#panel').evaluate(el=>el.scrollTop=200);
    assert.ok(await page.locator('#panel').evaluate(el=>el.scrollTop>0));
    await page.locator('#panel .close').click();
    assert.ok(await page.locator('#overview').isVisible());
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.deepEqual(errors,[]);
    await page.close();
    console.log(`PASS: Server 609 summary, Disk 3, scrolling, and close at ${width}px, touch=${touch}`);
  }
} finally {await browser.close();}
