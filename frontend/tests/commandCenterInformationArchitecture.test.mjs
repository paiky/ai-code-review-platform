import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
const pageSource = await readFile(
  new URL('../src/command-center/CommandCenterPage.jsx', import.meta.url),
  'utf8'
);
const apiSource = await readFile(
  new URL('../src/command-center/commandCenterApi.js', import.meta.url),
  'utf8'
);
const hookSource = await readFile(
  new URL('../src/command-center/useCommandCenterSnapshots.js', import.meta.url),
  'utf8'
);
const topologySource = await readFile(
  new URL('../src/command-center/CommandCenterTopology.jsx', import.meta.url),
  'utf8'
);
const canvasSource = await readFile(
  new URL('../src/command-center/CommandCenterCanvas.jsx', import.meta.url),
  'utf8'
);
const rendererSource = await readFile(
  new URL('../src/command-center/commandCenterCanvasRenderer.js', import.meta.url),
  'utf8'
);
const presentationSource = await readFile(
  new URL('../src/command-center/commandCenterPresentation.js', import.meta.url),
  'utf8'
);


function sourceBetween(start, end) {
  const startIndex = appSource.indexOf(start);
  const endIndex = appSource.indexOf(end, startIndex + start.length);
  assert.notEqual(startIndex, -1, `missing source marker: ${start}`);
  assert.notEqual(endIndex, -1, `missing source marker: ${end}`);
  return appSource.slice(startIndex, endIndex);
}


test('root route renders Command Center while preserving the legacy taskId redirect', () => {
  const homePageSource = sourceBetween('function HomePage()', 'function AppFrame()');

  assert.equal(homePageSource.includes("new URLSearchParams(location.search).get('taskId')"), true);
  assert.equal(homePageSource.includes('to={`/tasks/${legacyTaskId}`}'), true);
  assert.equal(homePageSource.includes('<CommandCenterPage />'), true);
  assert.equal(homePageSource.includes('<TaskListPage />'), false);
});


test('task list and task detail routes remain explicit and separate from home', () => {
  assert.equal(appSource.includes('<Route path={HOME_ROUTE} element={<HomePage />} />'), true);
  assert.equal(appSource.includes('<Route path={TASK_LIST_ROUTE} element={<TaskListPage />} />'), true);
  assert.equal(
    appSource.includes('<Route path={`${TASK_LIST_ROUTE}/:taskId`} element={<TaskDetailPage />} />'),
    true
  );
  assert.equal(appSource.includes('const isCommandCenterRoute = location.pathname === HOME_ROUTE'), true);
  assert.equal(
    appSource.includes('const isTaskRoute = location.pathname.startsWith(TASK_LIST_ROUTE)'),
    true
  );
  assert.equal(appSource.includes('指挥中心'), true);
});


test('phase two D Canvas stays read-only and uses only snapshot-driven animation', () => {
  assert.equal(pageSource.includes('data-command-center-phase="PHASE_2D"'), true);
  assert.equal(pageSource.includes('READ-ONLY CONTROL PLANE'), true);
  assert.equal(pageSource.includes('<canvas'), false);
  assert.equal(pageSource.includes('<CommandCenterCanvas'), true);
  assert.equal(pageSource.includes('WebSocket'), false);
  assert.equal(pageSource.includes('EventSource'), false);
  assert.equal(topologySource.includes('<canvas'), false);
  assert.equal(topologySource.includes('requestAnimationFrame'), false);
  assert.equal((canvasSource.match(/<canvas/g) || []).length, 1);
  assert.equal(canvasSource.includes('data-command-center-canvas-phase="PHASE_2D"'), true);
  assert.equal(canvasSource.includes('prefers-reduced-motion: reduce'), true);
  assert.equal(canvasSource.includes('max-width: 700px'), true);
  assert.equal(canvasSource.includes('data-command-center-canvas-fallback'), false);
  assert.equal(topologySource.includes('data-command-center-canvas-fallback'), true);
  assert.equal(topologySource.includes('PHASE 2D · LIVE CANVAS'), true);
  assert.equal(topologySource.includes('PHASE 2D · DOM FALLBACK'), true);
  assert.equal(rendererSource.includes('isAnimationEnabled: () => this.shouldAnimate()'), true);
  assert.equal(rendererSource.includes('reconcileCommandCenterScenes'), true);
  assert.equal(rendererSource.includes('COMMAND_CENTER_INDEPENDENT_FLOW_LIMIT = 20'), true);
  assert.equal(rendererSource.includes('COMMAND_CENTER_PARTICLE_LIMIT = 120'), true);
  assert.equal(rendererSource.includes('__commandCenterCanvasDiagnostics'), true);
  assert.equal(rendererSource.includes('setInterval'), false);
  assert.equal(rendererSource.includes('setTimeout'), false);
  assert.equal(presentationSource.includes("freshness === 'FRESH'"), true);
});


test('phase one data layer calls only the two read snapshot endpoints', () => {
  assert.equal(apiSource.includes('/api/command-center/runtime?'), true);
  assert.equal(apiSource.includes('/api/command-center/governance?'), true);
  assert.equal(apiSource.includes("method: 'POST'"), false);
  assert.equal(apiSource.includes("method: 'PUT'"), false);
  assert.equal(apiSource.includes("method: 'DELETE'"), false);
});


test('runtime and governance polling are independent, pausable, and cleaned up', () => {
  assert.equal(hookSource.includes('RUNTIME_INTERVAL_MS = 5_000'), true);
  assert.equal(hookSource.includes('GOVERNANCE_INTERVAL_MS = 60_000'), true);
  assert.equal(hookSource.includes("document.visibilityState === 'hidden'"), true);
  assert.equal(hookSource.includes("document.addEventListener('visibilitychange'"), true);
  assert.equal(hookSource.includes("window.addEventListener('focus'"), true);
  assert.equal(hookSource.includes('AbortController'), true);
  assert.equal(hookSource.includes('window.clearTimeout'), true);
  assert.equal(hookSource.includes('window.setTimeout'), true);
  assert.equal(hookSource.includes('setInterval'), false);
});
