import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const appSource = await read('../src/App.jsx');
const pageSource = await read('../src/command-center/CommandCenterPage.jsx');
const apiSource = await read('../src/command-center/commandCenterApi.js');
const hookSource = await read('../src/command-center/useCommandCenterSnapshots.js');
const canvasSource = await read('../src/command-center/CommandCenterCanvas.jsx');
const visualSource = await read('../src/command-center/commandCenterVisual.js');
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


test('H4 page preserves six Runtime HUD metrics and four current-state footer metrics', () => {
  assert.equal(pageSource.includes('data-command-center-phase="HOMEPAGE_VNEXT_H4"'), true);
  assert.equal(pageSource.includes('AI Review 指挥中心'), true);
  assert.equal((pageSource.match(/<HudMetric/g) || []).length, 6);
  assert.equal((pageSource.match(/<FooterMetric/g) || []).length, 4);
  for (const label of [
    'Runtime 更新时间',
    'Total Queued Jobs',
    'Total Running Jobs',
    'Snapshot Coverage',
    'Observed Provider / Model',
    'Runtime Alerts',
    'Agent Capacity',
    'Standard Provider Slots',
    'Oldest Agent Queue Wait'
  ]) assert.equal(pageSource.includes(label), true, label);
});


test('H4 preserves the frozen five-subject dual-review topology with one structural fallback', () => {
  for (const token of [
    'ReviewIntake',
    'EngineSelection',
    'lane={agentLane}',
    'lane={standardLane}',
    'FallbackRelation',
    'ResultPersistence'
  ]) assert.equal(canvasSource.includes(token), true, token);
  assert.equal((canvasSource.match(/<FallbackRelation/g) || []).length, 1);
  assert.equal(canvasSource.includes('Fallback · 结构性关系'), true);
  assert.equal(canvasSource.includes('STRUCTURAL ONLY'), true);
  assert.equal(canvasSource.includes('resultPersistence.navigationTarget'), true);
  assert.equal(canvasSource.includes('Agent 到 Standard 的结构性降级关系'), true);
});


test('all semantic content is DOM-owned while enhanced SVG remains decorative and Canvas stays disabled', () => {
  assert.equal(canvasSource.includes('data-command-center-renderer="DOM_SVG_ENHANCED"'), true);
  assert.equal(canvasSource.includes('data-command-center-canvas-mounted="false"'), true);
  assert.equal(canvasSource.includes('data-command-center-dom-fallback="always"'), true);
  assert.equal(canvasSource.includes('data-command-center-animation-owner="CSS_COMPOSITOR_ONLY"'), true);
  assert.equal((canvasSource.match(/<svg/g) || []).length, 1);
  assert.equal(canvasSource.includes('aria-hidden="true"'), true);
  assert.equal(canvasSource.includes('focusable="false"'), true);
  assert.equal(canvasSource.includes('<canvas'), false);
  assert.equal(canvasSource.includes('platformRuntimeMapRenderer'), false);
  assert.equal(styleSource.includes('pointer-events: none'), true);
  assert.equal(styleSource.includes('@keyframes cc-track-flow'), true);
  assert.equal(styleSource.includes('@keyframes cc-module-breathe'), true);
  assert.equal(styleSource.includes('@keyframes cc-alert-accent'), true);
  assert.equal(`${pageSource}\n${canvasSource}\n${visualSource}`.includes('requestAnimationFrame'), false);
  assert.equal((canvasSource.match(/className="command-center-flow/g) || []).length, 3);
  assert.equal(canvasSource.includes('command-center-flow is-fallback'), false);
});


test('H4 exposes truthful FRESH, STALE, EMPTY, ERROR and truncated copy', () => {
  for (const copy of [
    'Runtime 实时',
    'Runtime 已过期',
    '等待 Runtime 快照',
    'Runtime 刷新失败，已保留最后一次成功快照。',
    'Runtime 快照暂不可用。',
    'Runtime 快照部分截断。',
    'Scheduler 总数与 Lane 分布存在差异',
    '不会生成模拟 Job、Worker 或 Provider。',
    '当前无等待 Review',
    '暂无活跃 Provider'
  ]) assert.equal(`${pageSource}\n${canvasSource}`.includes(copy), true, copy);
});


test('H4 preserves the H3 read-only interactions with native keyboard controls', () => {
  for (const token of [
    'useNavigate',
    '<Modal',
    'reload',
    'data-command-center-action="refresh-runtime"',
    'data-command-center-action="open-alert"',
    'data-command-center-action="open-review-from-modal"',
    'afterClose={restoreOverflowFocus}',
    'restoreCommandCenterFocus(trigger, refreshButtonRef.current)'
  ]) assert.equal(pageSource.includes(token), true, token);
  for (const token of [
    'data-command-center-action="open-running-review"',
    'data-command-center-action="open-review-tasks"',
    'onOpenOverflow',
    '查看 Review 任务',
    '查看运行项'
  ]) assert.equal(canvasSource.includes(token), true, token);
  assert.equal(pageSource.includes('onKeyDown'), false);
  assert.equal(canvasSource.includes('onKeyDown'), false);
  assert.equal(`${pageSource}\n${canvasSource}`.includes('type="button"'), true);
  assert.equal(pageSource.includes('当前列表来自 Runtime 有界快照'), true);
  assert.equal(pageSource.includes('接口已标记为部分截断'), true);
  for (const forbidden of [
    '统一 Task Queue',
    'AI Review Core',
    '负载均衡',
    '平台负载',
    'Overall Pass Rate',
    'Agent Hit Rate',
    'Fallback Rate',
    '查看全部结果',
    '悬浮查看流程',
    '点击查看详情',
    'Drawer',
    'cancelJob',
    'retryJob'
  ]) assert.equal(`${pageSource}\n${canvasSource}`.includes(forbidden), false, forbidden);
});


test('desktop tablet and mobile layouts preserve the planned information hierarchy', () => {
  assert.equal(styleSource.includes('grid-template-areas:'), true);
  assert.equal(styleSource.includes('"intake engine agent result"'), true);
  assert.equal(styleSource.includes('"intake engine standard result"'), true);
  assert.equal(styleSource.includes('@media (min-width: 1200px)'), true);
  assert.equal(styleSource.includes('@media (max-width: 1199px)'), true);
  assert.equal(styleSource.includes('@media (max-width: 700px)'), true);
  assert.equal(styleSource.includes('.command-center-intake,'), true);
  assert.equal(styleSource.includes('.command-center-engine,'), true);
  assert.equal(styleSource.includes('.command-center-fallback,'), true);
  assert.equal(styleSource.includes('.command-center-result { display: none; }'), true);
  assert.equal(styleSource.includes('flex-direction: column'), true);
  assert.equal(canvasSource.includes('command-center-mobile-route-summary'), true);
  assert.equal(styleSource.includes('.command-center-mobile-route-summary'), true);
});


test('motion is presentational, state-gated and disabled for reduced motion and small screens', () => {
  assert.equal(pageSource.includes('data-command-center-resource-state'), true);
  assert.equal(pageSource.includes('data-command-center-motion={motionState}'), true);
  assert.equal(canvasSource.includes("data-running={lane.running > 0 ? 'true' : 'false'}"), true);
  assert.equal(styleSource.includes('[data-command-center-motion="enabled"] .command-center-flow'), true);
  assert.equal(styleSource.includes('[data-command-center-motion="enabled"] .command-center-review-module[data-running="true"]'), true);
  assert.equal(styleSource.includes('@media (prefers-reduced-motion: reduce)'), true);
  assert.equal(styleSource.includes('animation: none !important'), true);
});


test('daylight surfaces maintain WCAG AA body text contrast and visible focus styling', () => {
  const surfaces = ['#ffffff', '#f7fbff', '#f1ebff', '#fff2e6', '#e8faf6', '#fff0ee'];
  const text = '#17324d';
  for (const color of [text, ...surfaces]) assert.equal(styleSource.includes(color), true, color);
  for (const surface of surfaces) assert.ok(contrastRatio(text, surface) >= 4.5, surface);
  assert.equal(styleSource.includes('.command-center-page :focus-visible'), true);
});


test('public snapshot API remains read-only and Runtime polling stays deduplicated', () => {
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
