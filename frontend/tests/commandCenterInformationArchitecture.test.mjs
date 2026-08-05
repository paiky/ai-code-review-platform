import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const appSource = await read('../src/App.jsx');
const pageSource = await read('../src/command-center/CommandCenterPage.jsx');
const apiSource = await read('../src/command-center/commandCenterApi.js');
const hookSource = await read('../src/command-center/useCommandCenterSnapshots.js');
const canvasSource = await read('../src/command-center/CommandCenterCanvas.jsx');
const presentationSource = await read('../src/command-center/commandCenterPresentation.js');
const topologySource = await read('../src/command-center/commandCenterTopology.js');
const visualSource = await read('../src/command-center/commandCenterVisual.js');
const lifecycleSource = await read('../src/visibilityRefreshLifecycle.js');
const styleSource = await read('../src/command-center/commandCenter.css');
const globalStyleSource = await read('../src/styles.css');


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


test('M3 page preserves five current Runtime metrics and four 24-hour quality metrics', () => {
  assert.equal(pageSource.includes('data-command-center-phase="LIVE_TOPOLOGY_M3"'), true);
  assert.equal(pageSource.includes('AI Review 指挥中心'), true);
  assert.equal((pageSource.match(/<HudMetric/g) || []).length, 5);
  assert.equal((pageSource.match(/<QualityMetric/g) || []).length, 4);
  for (const label of [
    'Runtime 更新时间',
    '排队执行数',
    '运行执行数',
    '进行中审查任务',
    '当前 Provider / Model',
    '审查任务',
    'Provider 执行结果',
    '发现问题数',
    '受影响任务'
  ]) assert.equal(pageSource.includes(label), true, label);
  for (const removed of [
    'label="快照覆盖范围"',
    'label="Runtime 告警"',
    'label="Agent 容量"',
    'label="Standard Provider 槽位"',
    'label="Agent 最长排队等待"'
  ]) assert.equal(pageSource.includes(removed), false, removed);
});


test('M2-1 page exposes live side nodes, dual review tracks and one structural fallback', () => {
  for (const token of [
    'ReviewTaskQueue',
    'EngineSelection',
    'lane={agentLane}',
    'lane={standardLane}',
    'FallbackRelation',
    'TodayReviewResults'
  ]) assert.equal(canvasSource.includes(token), true, token);
  assert.equal((canvasSource.match(/<FallbackRelation/g) || []).length, 1);
  assert.equal(canvasSource.includes('Agent Review → Standard Review'), true);
  assert.equal(canvasSource.includes('任务队列'), true);
  assert.equal(canvasSource.includes('今日 Review 结果'), false);
  assert.equal(presentationSource.includes("title: '今日 Review 结果'"), true);
  assert.equal(canvasSource.includes('todayResults.navigationTarget'), true);
  assert.equal(canvasSource.includes('Agent 到 Standard 的结构性降级关系'), true);
  assert.equal(canvasSource.includes('target="_blank"'), true);
  assert.equal(canvasSource.includes('rel="noopener noreferrer"'), true);
});


test('M3 semantic DOM owns content while one measured SVG owns CSS-only route motion', () => {
  assert.equal(canvasSource.includes('data-command-center-renderer="DOM_SVG_LIVE_TOPOLOGY"'), true);
  assert.equal(canvasSource.includes('data-command-center-canvas-mounted="false"'), true);
  assert.equal(canvasSource.includes('data-command-center-dom-fallback="always"'), true);
  assert.equal(canvasSource.includes('data-command-center-animation-owner="CSS_STATE_M3"'), true);
  assert.equal((canvasSource.match(/<svg/g) || []).length, 1);
  assert.equal(canvasSource.includes('aria-hidden="true"'), true);
  assert.equal(canvasSource.includes('focusable="false"'), true);
  assert.equal(canvasSource.includes('<canvas'), false);
  assert.equal(canvasSource.includes('platformRuntimeMapRenderer'), false);
  assert.equal(styleSource.includes('pointer-events: none'), true);
  assert.equal(canvasSource.includes('useLayoutEffect'), true);
  assert.equal(canvasSource.includes('observeCommandCenterTopology'), true);
  assert.equal(topologySource.includes('new ResizeObserverClass(publish)'), true);
  assert.equal(`${pageSource}\n${canvasSource}\n${topologySource}\n${visualSource}`.includes('requestAnimationFrame'), false);
  assert.equal(canvasSource.includes('command-center-flow'), true);
  assert.equal(canvasSource.includes('command-center-pulse'), true);
  assert.equal(canvasSource.includes('pathLength="100"'), true);
  for (const id of [
    'queue-engine',
    'engine-agent',
    'engine-standard',
    'agent-result',
    'standard-result',
    'agent-standard'
  ]) assert.equal(topologySource.includes(`id: '${id}'`), true, id);
});


test('I2 page exposes truthful independent resource, retained, retry and truncated copy', () => {
  for (const copy of [
    'Runtime 实时',
    'Runtime 已过期',
    '等待 Runtime 快照',
    'Runtime 刷新失败，已保留最后一次成功快照。',
    'Runtime 快照暂不可用。',
    'Runtime 快照部分截断。',
    '调度器总数与执行轨分布存在差异',
    '不会生成模拟任务、执行器或 Provider。',
    '指挥中心数据暂时无法获取。',
    '质量统计刷新失败，已保留上次数据',
    '质量统计暂时无法获取。',
    '部分质量统计已截断，当前指标可能不完整。',
    '重试 Runtime',
    '重试质量统计',
    '当前无等待任务',
    '暂无可观测 Provider'
  ]) assert.equal(`${pageSource}\n${canvasSource}`.includes(copy), true, copy);
});


test('I2 page preserves review navigation and adds only resource retry controls', () => {
  for (const token of [
    'useNavigate',
    '<Modal',
    'data-command-center-action="open-review-from-modal"',
    'afterClose={restoreOverflowFocus}',
    'restoreCommandCenterFocus(trigger, pageRef.current)',
    'className="command-center-notice-action"',
    'reloadRuntime',
    'reloadGovernance'
  ]) assert.equal(pageSource.includes(token), true, token);
  for (const token of [
    'data-command-center-action="open-running-review"',
    'data-command-center-action="open-review-tasks"',
    'onOpenOverflow',
    '查看审查任务',
    '查看运行项'
  ]) assert.equal(canvasSource.includes(token), true, token);
  assert.equal(pageSource.includes('onKeyDown'), false);
  assert.equal(canvasSource.includes('onKeyDown'), false);
  assert.equal(`${pageSource}\n${canvasSource}`.includes('type="button"'), true);
  assert.equal(pageSource.includes('当前列表来自 Runtime 有界快照'), true);
  assert.equal(pageSource.includes('接口已标记为部分截断'), true);
  assert.equal(pageSource.includes('data-command-center-action="open-alert"'), false);
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


test('visible operational copy is Chinese while approved product terms remain unchanged', () => {
  const visibleSources = `${pageSource}\n${canvasSource}\n${presentationSource}`;
  for (const copy of [
    'Agent Review',
    'Standard Review',
    'Runtime',
    'Provider',
    'Model',
    'Merge Request',
    'Push'
  ]) assert.equal(visibleSources.includes(copy), true, copy);
  for (const forbidden of [
    'Manual Review',
    'Review Intake',
    'Engine Selection',
    'TRIGGER INPUT',
    'POLICY ROUTER',
    'Queued Jobs',
    'Running Jobs',
    'Online Capacity',
    'Worker Summary',
    'Running Items',
    'STRUCTURAL ONLY',
    'Result Persistence',
    'Task Detail / Notification',
    'Bounded Snapshot',
    'Runtime Alerts'
  ]) assert.equal(visibleSources.includes(forbidden), false, forbidden);
  assert.equal(visibleSources.includes('label="Retry"'), false);
});


test('deployment polish fills wide viewports and removes the redundant heading row', () => {
  assert.equal(pageSource.includes('className="command-center-heading"'), false);
  assert.equal(pageSource.includes('data-command-center-action="refresh-runtime"'), false);
  assert.equal(pageSource.includes('当前调度快照 · 双 Review 执行轨 · 结构性结果回流'), false);
  assert.equal(pageSource.includes('aria-label="AI Review 指挥中心"'), true);
  assert.match(styleSource, /\.command-center-page\s*\{[^}]*display:\s*flex;[^}]*min-height:\s*calc\(100dvh - 56px\);/s);
  assert.match(styleSource, /\.command-center-shell\s*\{[^}]*width:\s*100%;/s);
  assert.match(styleSource, /\.command-center-runtime-map\s*\{[^}]*flex:\s*1 1 438px;/s);
  assert.doesNotMatch(styleSource, /\.command-center-shell\s*\{[^}]*width:\s*min\(1580px,\s*100%\);/s);
});


test('desktop tablet and mobile layouts preserve the planned information hierarchy', () => {
  assert.equal(styleSource.includes('grid-template-areas:'), true);
  assert.equal(styleSource.includes('"intake . engine . agent . result"'), true);
  assert.equal(styleSource.includes('"intake . engine . standard . result"'), true);
  assert.equal(styleSource.includes('@media (min-width: 1200px)'), true);
  assert.equal(styleSource.includes('@media (min-width: 1440px)'), true);
  assert.equal(styleSource.includes('@media (min-width: 1200px) and (max-height: 1100px)'), true);
  assert.equal(styleSource.includes('@media (max-width: 1199px)'), true);
  assert.equal(styleSource.includes('@media (max-width: 900px)'), true);
  assert.equal(styleSource.includes('@media (max-width: 700px)'), true);
  assert.equal(styleSource.includes('.command-center-intake,'), true);
  assert.equal(styleSource.includes('.command-center-engine,'), true);
  assert.equal(styleSource.includes('.command-center-fallback,'), true);
  assert.equal(styleSource.includes('.command-center-result { display: none; }'), true);
  assert.equal(styleSource.includes('flex-direction: column'), true);
  assert.equal(styleSource.includes('.command-center-task-queue { order: 1; width: min(100%, 520px);'), true);
  assert.equal(styleSource.includes('.command-center-result { order: 6; width: min(100%, 520px);'), true);
  assert.equal(globalStyleSource.includes('@media (min-width: 761px) and (max-width: 1000px)'), true);
  assert.equal(styleSource.includes('grid-template-columns: repeat(5, minmax(0, 1fr))'), true);
  assert.equal(styleSource.includes('grid-template-rows: clamp(168px, 21vh, 200px) 58px clamp(168px, 21vh, 200px)'), true);
  assert.equal(styleSource.includes('.command-center-hud-card.is-running { order: 1; }'), true);
  assert.equal(styleSource.includes('.command-center-quality-card.is-provider-result { order: 4; }'), true);
  assert.equal(canvasSource.includes('command-center-mobile-route-summary'), true);
  assert.equal(styleSource.includes('.command-center-mobile-route-summary'), true);
});


test('M3 drives measured routes from truthful state and preserves reduced-motion and small-screen fallbacks', () => {
  assert.equal(pageSource.includes('data-command-center-resource-state'), true);
  assert.equal(pageSource.includes('data-command-center-activity={motionScene.activity}'), true);
  assert.equal(canvasSource.includes("data-queued={lane.queued > 0 ? 'true' : 'false'}"), true);
  assert.equal(canvasSource.includes("data-running={lane.running > 0 ? 'true' : 'false'}"), true);
  assert.equal(canvasSource.includes("data-active={state.active ? 'true' : 'false'}"), true);
  assert.equal(canvasSource.includes('data-fallback-active'), true);
  assert.equal(styleSource.includes('[data-flow-state="queued"]'), true);
  assert.equal(styleSource.includes('[data-flow-state="running"]'), true);
  assert.equal(styleSource.includes('cc-engine-orbit-clockwise'), true);
  assert.equal(styleSource.includes('cc-engine-orbit-counterclockwise'), true);
  assert.equal(styleSource.includes('cc-review-neon'), true);
  assert.equal(canvasSource.includes('command-center-review-neon'), true);
  assert.equal(styleSource.includes('@property --cc-neon-angle'), false);
  assert.equal(styleSource.includes('.command-center-static-connections,'), true);
  assert.equal(styleSource.includes('.command-center-port { display: none; }'), true);
  assert.equal(styleSource.includes('@media (prefers-reduced-motion: reduce)'), true);
  assert.equal(styleSource.includes('animation: none !important'), true);
});


test('M2-1 exposes rounded glass surfaces, circular engine and truthful quality micro visuals', () => {
  assert.equal(canvasSource.includes('command-center-engine-orbit is-outer'), true);
  assert.equal(canvasSource.includes('command-center-engine-panel'), true);
  assert.equal(canvasSource.includes('command-center-result-badge'), true);
  assert.equal((canvasSource.match(/command-center-connection is-/g) || []).length >= 3, true);
  assert.equal(pageSource.includes('providerQualityVisual'), true);
  assert.equal(pageSource.includes('findingSeverityVisual'), true);
  assert.equal(pageSource.includes('affectedRiskVisual'), true);
  assert.equal(pageSource.includes('data-command-center-quality-visual="review-signal"'), true);
  assert.equal(styleSource.includes('--cc-radius-card: 20px'), true);
  assert.equal(styleSource.includes('border-radius: 13px 3px 13px 3px'), false);
  assert.equal(styleSource.includes('border-radius: 14px 4px 14px 4px'), false);
  assert.equal(styleSource.includes('@supports not (backdrop-filter: blur(1px))'), true);
  assert.equal(styleSource.includes('@media (forced-colors: active)'), true);
});


test('M4 desktop polish keeps topology overlays translucent and removes duplicate lane eyebrow labels', () => {
  assert.equal(canvasSource.includes('<small>{lane.eyebrow}</small>'), false);
  assert.equal(styleSource.includes('background: rgba(255, 255, 255, 0.08);'), true);
  assert.equal(styleSource.includes('background: rgba(247, 252, 255, 0.06);'), true);
  assert.equal((styleSource.match(/backdrop-filter: none;/g) || []).length >= 2, true);
});


test('daylight surfaces maintain WCAG AA body text contrast and visible focus styling', () => {
  const surfaces = ['#ffffff', '#f7fbff', '#f1ebff', '#fff2e6', '#e8faf6', '#fff0ee'];
  const text = '#17324d';
  for (const color of [text, ...surfaces]) assert.equal(styleSource.includes(color), true, color);
  for (const surface of surfaces) assert.ok(contrastRatio(text, surface) >= 4.5, surface);
  assert.equal(styleSource.includes('.command-center-page :focus-visible'), true);
});


test('public snapshot APIs remain read-only and both polling resources stay independent and deduplicated', () => {
  assert.equal(apiSource.includes('/api/command-center/runtime?'), true);
  assert.equal(apiSource.includes('/api/command-center/governance?'), true);
  assert.equal(apiSource.includes("method: 'POST'"), false);
  assert.equal(hookSource.includes('RUNTIME_INTERVAL_MS = 5_000'), true);
  assert.equal(hookSource.includes('GOVERNANCE_INTERVAL_MS = 60_000'), true);
  assert.equal(hookSource.includes("runtime: {"), true);
  assert.equal(hookSource.includes("governance: {"), true);
  assert.equal(hookSource.includes("loadResource('runtime')"), true);
  assert.equal(hookSource.includes("loadResource('governance')"), true);
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
