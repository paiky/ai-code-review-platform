import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const appSource = await read('../src/App.jsx');
const pageSource = await read('../src/command-center/CommandCenterPage.jsx');
const apiSource = await read('../src/command-center/commandCenterApi.js');
const hookSource = await read('../src/command-center/useCommandCenterSnapshots.js');
const canvasSource = await read('../src/command-center/CommandCenterCanvas.jsx');
const rendererSource = await read('../src/command-center/platformRuntimeMapRenderer.js');
const presentationSource = await read('../src/command-center/commandCenterPresentation.js');
const lifecycleSource = await read('../src/visibilityRefreshLifecycle.js');
const styleSource = await read('../src/command-center/commandCenter.css');


function read(relativePath) {
  return readFile(new URL(relativePath, import.meta.url), 'utf8');
}


function sourceBetween(start, end) {
  const startIndex = appSource.indexOf(start);
  const endIndex = appSource.indexOf(end, startIndex + start.length);
  assert.notEqual(startIndex, -1, `missing source marker: ${start}`);
  assert.notEqual(endIndex, -1, `missing source marker: ${end}`);
  return appSource.slice(startIndex, endIndex);
}


test('root route renders Command Center while preserving legacy taskId redirect', () => {
  const source = sourceBetween('function HomePage()', 'function AppFrame()');
  assert.equal(source.includes("new URLSearchParams(location.search).get('taskId')"), true);
  assert.equal(source.includes('to={`/tasks/${legacyTaskId}`}'), true);
  assert.equal(source.includes('<CommandCenterPage />'), true);
});


test('phase 5A home is a compact platform-level dual-lane runtime map', () => {
  assert.equal(pageSource.includes('data-command-center-phase="PHASE_5A"'), true);
  assert.equal(pageSource.includes('平台 Review 运行地图'), true);
  assert.equal(pageSource.includes('<CommandCenterCanvas'), true);
  assert.equal(presentationSource.includes("zoneKey: 'shared-queue'"), true);
  assert.equal(presentationSource.includes("zoneKey: 'platform-runtime-map'"), true);
  assert.equal(presentationSource.includes("'standard'"), true);
  assert.equal(presentationSource.includes("'agent'"), true);
});


test('removed lifecycle modules and duplicate global controls do not appear on home', () => {
  const forbidden = [
    '选择活跃 Task',
    '选择具体 Review Flow',
    'GitLab / Manual',
    'Rule Analysis',
    'Finding / Notification',
    'command-center-flow-dock',
    'openJobQueue',
    'openFailureNotifications',
    '<Select'
  ];
  for (const text of forbidden) assert.equal(pageSource.includes(text), false, text);
  assert.equal(pageSource.includes('WebSocket'), false);
  assert.equal(pageSource.includes('EventSource'), false);
});


test('DOM owns review navigation and overflow modal while bases and next reviews stay noninteractive', () => {
  assert.equal(pageSource.includes('`/tasks/${item.taskId}?reviewKey=${reviewKey}`'), true);
  assert.equal(pageSource.includes('<Modal'), true);
  assert.equal(canvasSource.includes('command-center-overflow-tower'), true);
  assert.equal(canvasSource.includes('onOpenOverflow(lane)'), true);
  assert.equal(canvasSource.includes('function NextReview'), true);
  assert.equal(canvasSource.includes('data-zone-key={lane.zoneKey}'), true);
  assert.equal((canvasSource.match(/<canvas/g) || []).length, 1);
  assert.equal(canvasSource.includes('data-command-center-dom-overlay="true"'), true);
  assert.equal(canvasSource.includes('data-command-center-canvas-phase="PHASE_5A"'), true);
});


test('single static Canvas controller preserves fallback and resource ownership', () => {
  assert.equal(canvasSource.includes('prefers-reduced-motion: reduce'), true);
  assert.equal(canvasSource.includes('max-width: 700px'), true);
  assert.equal(rendererSource.includes('createCanvasRuntime'), true);
  assert.equal(rendererSource.includes('isAnimationEnabled: () => false'), true);
  assert.equal(rendererSource.includes('setInterval'), false);
  assert.equal(rendererSource.includes('setTimeout'), false);
  assert.equal(rendererSource.includes('requestAnimationFrame'), false);
  assert.equal(rendererSource.includes('data-command-center-active-raf'), true);
});


test('public snapshot API remains read-only and runtime polling stays deduplicated', () => {
  assert.equal(apiSource.includes('/api/command-center/runtime?'), true);
  assert.equal(apiSource.includes("method: 'POST'"), false);
  assert.equal(hookSource.includes('RUNTIME_INTERVAL_MS = 5_000'), true);
  assert.equal(hookSource.includes('createVisibilityRefreshLifecycle'), true);
  assert.equal(hookSource.includes('AbortController'), true);
  assert.equal((hookSource.match(/window\.setTimeout/g) || []).length, 1);
  assert.equal(hookSource.includes('setInterval'), false);
  assert.equal(hookSource.includes('deduplicated'), true);
  assert.equal(lifecycleSource.includes("addEventListener?.('visibilitychange'"), true);
  assert.equal(lifecycleSource.includes("addEventListener?.('focus'"), true);
});


test('daylight palette maintains WCAG AA text contrast', () => {
  const surfaces = ['#eaf2f7', '#ffffff', '#dff6f5', '#eee9ff', '#fff3cc'];
  const text = '#17324d';
  for (const color of [text, ...surfaces]) assert.equal(styleSource.includes(color), true, color);
  for (const surface of surfaces) assert.ok(contrastRatio(text, surface) >= 4.5, surface);
  assert.equal(styleSource.includes('.command-center-page button:focus-visible'), true);
});


function contrastRatio(foreground, background) {
  const lighter = Math.max(relativeLuminance(foreground), relativeLuminance(background));
  const darker = Math.min(relativeLuminance(foreground), relativeLuminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}


function relativeLuminance(hex) {
  const channels = hex.slice(1).match(/.{2}/g).map(value => Number.parseInt(value, 16) / 255);
  const [red, green, blue] = channels.map(value => (
    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  ));
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}
