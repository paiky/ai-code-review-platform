import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const appSource = await read('../src/App.jsx');
const pageSource = await read('../src/command-center/CommandCenterPage.jsx');
const apiSource = await read('../src/command-center/commandCenterApi.js');
const hookSource = await read('../src/command-center/useCommandCenterSnapshots.js');
const topologySource = await read('../src/command-center/CommandCenterTopology.jsx');
const canvasSource = await read('../src/command-center/CommandCenterCanvas.jsx');
const rendererSource = await read('../src/command-center/commandCenterCanvasRenderer.js');
const presentationSource = await read('../src/command-center/commandCenterPresentation.js');
const focusSource = await read('../src/command-center/commandCenterFocus.js');
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
  assert.equal(appSource.includes('指挥中心'), true);
});


test('phase 4C home remains one lifecycle workspace without pulse, rail, or governance panels', () => {
  assert.equal(pageSource.includes('data-command-center-phase="PHASE_4C"'), true);
  assert.equal(pageSource.includes('command-center-map-shell'), true);
  assert.equal(pageSource.includes('command-center-map-toolbar'), true);
  assert.equal(pageSource.includes('command-center-flow-dock'), true);
  assert.equal(pageSource.includes('Review 生命周期地图'), true);
  assert.equal(pageSource.includes('SystemPulse'), false);
  assert.equal(pageSource.includes('GovernanceLoop'), false);
  assert.equal(pageSource.includes('LiveOperationsRail'), false);
  assert.equal(pageSource.includes('CommandCenterFocusBar'), false);
  assert.equal(pageSource.includes('运行脉搏'), false);
  assert.equal(pageSource.includes('运行侧栏'), false);
  assert.equal(pageSource.includes('质量治理回路'), false);
  assert.equal(styleSource.includes('.command-center-hero'), false);
  assert.equal(styleSource.includes('.command-center-pulse'), false);
  assert.equal(styleSource.includes('.command-center-live-rail'), false);
  assert.equal(styleSource.includes('.command-center-governance'), false);
});


test('phase 4C Canvas stays draw-only while DOM owns drill-down and focus is independent', () => {
  assert.equal(pageSource.includes('<canvas'), false);
  assert.equal(pageSource.includes('<CommandCenterCanvas'), true);
  assert.equal(pageSource.includes('WebSocket'), false);
  assert.equal(pageSource.includes('EventSource'), false);
  assert.equal(topologySource.includes('<canvas'), false);
  assert.equal(topologySource.includes('requestAnimationFrame'), false);
  assert.equal((canvasSource.match(/<canvas/g) || []).length, 1);
  assert.equal(canvasSource.includes('data-command-center-canvas-phase="PHASE_4C"'), true);
  assert.equal(canvasSource.includes('prefers-reduced-motion: reduce'), true);
  assert.equal(canvasSource.includes('max-width: 700px'), true);
  assert.equal(topologySource.includes('data-command-center-canvas-fallback'), true);
  assert.equal(topologySource.includes('data-command-center-dom-overlay="true"'), true);
  assert.equal(topologySource.includes('command-center-flow-node-overlay'), true);
  assert.equal(topologySource.includes("aria-current={focused ? 'step' : undefined}"), true);
  assert.equal(topologySource.includes("event.key !== 'Enter' && event.key !== ' '"), true);
  assert.equal(topologySource.includes('event.preventDefault()'), true);
  assert.equal(topologySource.includes("onActivateNode?.(column.key)"), true);
  assert.equal(canvasSource.includes('}, [shouldMountCanvas])'), true);
  assert.equal(canvasSource.includes('controllerRef.current?.setFocus'), true);
  assert.equal(canvasSource.includes('}, [focus?.flowId])'), true);
  assert.equal(rendererSource.includes('setFocus(flowId)'), true);
  assert.equal(rendererSource.includes('particleLayoutRevision'), true);
  assert.equal(rendererSource.includes('COMMAND_CENTER_AMBIENT_FRAME_INTERVAL_MS'), true);
  assert.equal(rendererSource.includes('isAnimationEnabled: () => this.shouldAnimate()'), true);
  assert.equal(rendererSource.includes('reconcileCommandCenterScenes'), true);
  assert.equal(rendererSource.includes('COMMAND_CENTER_INDEPENDENT_FLOW_LIMIT = 20'), true);
  assert.equal(rendererSource.includes('COMMAND_CENTER_PARTICLE_LIMIT = 120'), true);
  assert.equal(rendererSource.includes('__commandCenterCanvasDiagnostics'), true);
  assert.equal(rendererSource.includes('setInterval'), false);
  assert.equal(rendererSource.includes('setTimeout'), false);
  assert.equal(presentationSource.includes("freshness === 'FRESH'"), true);
});


test('public snapshot API remains read-only while the home hook requests Runtime only', () => {
  assert.equal(apiSource.includes('/api/command-center/runtime?'), true);
  assert.equal(apiSource.includes('/api/command-center/governance?'), true);
  assert.equal(apiSource.includes("method: 'POST'"), false);
  assert.equal(apiSource.includes("method: 'PUT'"), false);
  assert.equal(apiSource.includes("method: 'DELETE'"), false);
  assert.equal(hookSource.includes('loadRuntimeSnapshot'), true);
  assert.equal(hookSource.includes('loadGovernanceSnapshot'), false);
  assert.equal(hookSource.includes('GOVERNANCE_INTERVAL_MS'), false);
  assert.equal(pageSource.includes('governance'), false);
  assert.equal(pageSource.includes('useCommandCenterRuntimeSnapshot'), true);
});


test('single Runtime poller pauses, aborts, deduplicates, and cleans up', () => {
  assert.equal(hookSource.includes('RUNTIME_INTERVAL_MS = 5_000'), true);
  assert.equal(hookSource.includes("document.visibilityState === 'hidden'"), true);
  assert.equal(hookSource.includes('createVisibilityRefreshLifecycle'), true);
  assert.equal(lifecycleSource.includes("addEventListener?.('visibilitychange'"), true);
  assert.equal(lifecycleSource.includes("addEventListener?.('focus'"), true);
  assert.equal(hookSource.includes('AbortController'), true);
  assert.equal(hookSource.includes('window.clearTimeout'), true);
  assert.equal((hookSource.match(/window\.setTimeout/g) || []).length, 1);
  assert.equal(hookSource.includes('setInterval'), false);
  assert.equal(hookSource.includes('deduplicated'), true);
  assert.equal(hookSource.includes('__commandCenterPollingDiagnostics'), true);
});


test('Task Flow toolbar, focused map stage, Flow Dock, and AppFrame drawers share focus', () => {
  assert.equal(pageSource.includes('aria-label="选择活跃 Task"'), true);
  assert.equal(pageSource.includes('aria-label="选择具体 Review Flow"'), true);
  assert.equal(pageSource.includes('focus={focus}'), true);
  assert.equal(pageSource.includes('selectedFlow.stageLabel'), true);
  assert.equal(pageSource.includes('selectedFlow.providerModelLabel'), true);
  assert.equal(pageSource.includes('openJobQueue'), true);
  assert.equal(pageSource.includes('openFailureNotifications'), true);
  assert.equal((pageSource.match(/aria-haspopup="dialog"/g) || []).length, 2);
  assert.equal((pageSource.match(/aria-expanded=/g) || []).length, 2);
  assert.equal(focusSource.includes('taskId: selectedFlow.taskId'), true);
  assert.equal(topologySource.includes('selectedFlow?.columnKey === column.key'), true);
});


test('phase 4 palette provides WCAG AA body-text contrast on map and node surfaces', () => {
  const colors = {
    background: '#080b1a',
    map: '#101a33',
    node: '#132442',
    primary: '#f7faff',
    secondary: '#b8c7e6'
  };
  for (const [name, value] of Object.entries(colors)) {
    assert.equal(styleSource.includes(value), true, `missing ${name} token ${value}`);
  }
  for (const surface of [colors.background, colors.map, colors.node]) {
    assert.ok(contrastRatio(colors.primary, surface) >= 4.5);
    assert.ok(contrastRatio(colors.secondary, surface) >= 4.5);
  }
  assert.equal(styleSource.includes('@keyframes'), false);
  assert.equal(styleSource.includes('.command-center-page button:focus-visible'), true);
  assert.equal(styleSource.includes('outline: 3px solid var(--cc-cyan)'), true);
});


test('AppFrame owns drawers and disables duplicate background polling on home', () => {
  const frameSource = sourceBetween('function AppFrame()', 'export default function App()');
  assert.equal(frameSource.includes('<AppFrameOperationsContext.Provider'), true);
  assert.equal(frameSource.includes('isCommandCenterRoute'), true);
  assert.equal(frameSource.includes('window.setInterval'), false);
  assert.equal(frameSource.includes('createVisibilityRefreshLifecycle'), true);
  assert.equal(frameSource.includes('{ signal: controller.signal }'), true);
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
