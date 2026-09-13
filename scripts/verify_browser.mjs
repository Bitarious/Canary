/** Start an isolated demo and run the evidence and 3D navigation regressions. */
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const root = fileURLToPath(new URL('../', import.meta.url));
const temporary = await mkdtemp(join(tmpdir(), 'canary-browser-'));
const children = new Set();
let profile;
function child(command, args, options = {}) {
  const process = spawn(command, args, { cwd: root, stdio: ['ignore', 'pipe', 'pipe'], ...options });
  children.add(process);
  process.once('exit', () => children.delete(process));
  process.once('error', () => children.delete(process));
  return process;
}
function run(args, timeout = 240000) {
  return new Promise((resolve, reject) => {
    const process = child('node', args, { stdio: 'inherit' });
    const timer = setTimeout(() => { process.kill('SIGKILL'); reject(new Error('Browser check timed out')); }, timeout);
    process.once('error', error => { clearTimeout(timer); reject(error); });
    process.once('exit', code => { clearTimeout(timer); code === 0 ? resolve() : reject(new Error(`Browser check exited ${code}`)); });
  });
}
try {
  // Port zero lets the OS allocate an unused local port. The harness owns this server.
  const server = child(process.env.PYTHON || 'python3', ['-u', '-c',
    `import os,sys\nfrom pathlib import Path\nsys.path.insert(0, 'driftops3d')\nimport server\nserver.DATA=Path(os.environ['CANARY_TEST_DATA'])\nOriginal=server.ThreadingHTTPServer\nclass Ephemeral(Original):\n def __init__(self,*a,**kw):\n  super().__init__(*a,**kw)\n  print('CANARY_PORT='+str(self.server_port),flush=True)\nserver.ThreadingHTTPServer=Ephemeral\nsys.argv=['server.py','--host','127.0.0.1','--port','0']\nserver.main()`], { env: { ...process.env, CANARY_TEST_DATA: join(temporary, 'machines') } });
  let output = '';
  server.stderr.on('data', data => process.stderr.write(data));
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Demo server did not start')), 60000);
    server.stdout.on('data', data => {
      output += data;
      const match = output.match(/CANARY_PORT=(\d+)/);
      if (match) { clearTimeout(timer); resolve(Number(match[1])); }
    });
    server.once('error', error => { clearTimeout(timer); reject(error); });
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Demo server exited ${code}`)); });
  });
  const base = `http://127.0.0.1:${port}`;
  await run(['driftops3d/tests/evidence-ui.mjs', base]);
  const userData = join(temporary, 'chromium');
  profile = await chromium.launchPersistentContext(userData, {
    executablePath: process.env.CHROME_PATH || undefined,
    headless: true,
    args: ['--remote-debugging-port=0', '--enable-unsafe-swiftshader'],
  });
  const debugPort = (await readFile(join(userData, 'DevToolsActivePort'), 'utf8')).split('\n')[0];
  await run(['driftops3d/tests/site-navigation.mjs', base, `http://127.0.0.1:${debugPort}`]);
} finally {
  if (profile) await profile.close();
  await Promise.all([...children].map(process => new Promise(resolve => {
    const timer = setTimeout(() => process.kill('SIGKILL'), 5000);
    process.once('exit', () => { clearTimeout(timer); resolve(); });
    process.kill('SIGTERM');
  })));
  await rm(temporary, { recursive: true, force: true });
}
