import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdir, rm } from 'node:fs/promises';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const launcherSource = await readFile(
  new URL('../../scripts/run-docs50-acceptance.ps1', import.meta.url),
  'utf8'
);
const frontendSource = await readFile(
  new URL('../../scripts/run-frontend.ps1', import.meta.url),
  'utf8'
);
const mockSource = await readFile(
  new URL('../../scripts/docs50-mock-server.mjs', import.meta.url),
  'utf8'
);
const detachedLauncherUrl = new URL(
  '../../scripts/start-detached.mjs',
  import.meta.url
);
const repoRoot = fileURLToPath(new URL('../..', import.meta.url));

test('docs50 launcher detaches services and verifies PID port and HTTP identity', () => {
  for (const marker of [
    'start-detached.mjs',
    'Get-ListeningProcessId',
    'Test-ProcessAlive',
    'Test-MockReady',
    'Test-FrontendRootReady',
    'Test-FrontendProxyReady',
    'ReadyTimeoutSeconds',
    'launcherPid',
    'DOCS50_ACCEPTANCE_READY',
    'Stop-RecordedService'
  ]) {
    assert.equal(launcherSource.includes(marker), true, marker);
  }
  assert.equal(launcherSource.includes('WaitForExit'), false);
  assert.equal(launcherSource.includes('Start-Process'), false);
  assert.equal(launcherSource.includes('ProcessStartInfo'), false);
  assert.match(launcherSource, /FrontendPort = 5173/);
  assert.match(launcherSource, /MockPort = 8080/);
});

test('detached launcher returns before its child exits and releases stdio handles', async t => {
  const localDir = new URL(
    '../../.local/docs50-detached-launcher-test/',
    import.meta.url
  );
  const localPath = fileURLToPath(localDir);
  await mkdir(localPath, { recursive: true });
  t.after(async () => {
    await rm(localPath, { recursive: true, force: true });
  });

  const stdoutPath = fileURLToPath(new URL('stdout.log', localDir));
  const stderrPath = fileURLToPath(new URL('stderr.log', localDir));
  const startedAt = Date.now();
  const result = spawnSync(process.execPath, [
    fileURLToPath(detachedLauncherUrl),
    '--cwd', repoRoot,
    '--stdout', stdoutPath,
    '--stderr', stderrPath,
    '--',
    process.execPath,
    '-e',
    'setTimeout(() => {}, 10000)'
  ], {
    encoding: 'utf8',
    timeout: 3000,
    windowsHide: true
  });
  const elapsedMs = Date.now() - startedAt;

  assert.equal(result.status, 0, result.stderr);
  assert.ok(elapsedMs < 2500, `launcher took ${elapsedMs}ms`);
  const { pid } = JSON.parse(result.stdout.trim());
  assert.ok(Number.isInteger(pid) && pid > 0);
  process.kill(pid);
});

test('frontend accepts an explicit proxy override after local dotenv loading', () => {
  const importIndex = frontendSource.indexOf('Import-DotEnvIfPresent $localGitLabEnv');
  const overrideIndex = frontendSource.indexOf(
    '$env:VITE_API_PROXY_TARGET = $ApiProxyTarget'
  );

  assert.ok(importIndex >= 0);
  assert.ok(overrideIndex > importIndex);
  assert.match(frontendSource, /\[string\] \$HostAddress/);
  assert.match(frontendSource, /\[Nullable\[int\]\] \$Port/);
  assert.match(frontendSource, /\[switch\] \$StrictPort/);
});

test('tracked docs50 mock exposes only a local synthetic health identity', () => {
  assert.match(mockSource, /docs50-safe-mock/);
  assert.match(mockSource, /\/api\/__docs50__\/health/);
  assert.match(mockSource, /--port/);
  assert.match(mockSource, /127\.0\.0\.1/);
  assert.match(mockSource, /diffText: '@@ -12,1 \+12,2 @@/);
  assert.equal(mockSource.includes('0.0.0.0'), false);
  assert.equal(mockSource.includes('https://'), false);
});
