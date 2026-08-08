import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
const styleSource = await readFile(new URL('../src/styles.css', import.meta.url), 'utf8');
const mockSource = await readFile(new URL('../../scripts/docs54-settings-mock-server.mjs', import.meta.url), 'utf8');

test('renders one visible unified Review model settings workspace', () => {
  assert.match(appSource, /from ['"]\.\/reviewModelConnections\.js['"]/);
  assert.match(appSource, /key: 'review-model-settings'/);
  assert.match(appSource, /title="Agent Review 运行配置"/);
  assert.match(appSource, /title="Standard Review 运行配置"/);
  assert.match(appSource, /title="模型连接目录"/);
  assert.match(appSource, /aria-label="连接详情"/);
  assert.doesNotMatch(appSource, /key: 'provider-settings'/);
  assert.doesNotMatch(appSource, /key: 'agent-review-settings'/);

  const orderedItems = appSource.slice(
    appSource.indexOf('const orderedCollapseItems = ['),
    appSource.indexOf('return (', appSource.indexOf('const orderedCollapseItems = ['))
  );
  assert.match(orderedItems, /'review-model-settings'/);
  assert.doesNotMatch(orderedItems, /'provider-settings'/);
  assert.doesNotMatch(orderedItems, /'agent-review-settings'/);
});

test('decouples Provider detail save from Standard default selection', () => {
  const providerSave = appSource.slice(
    appSource.indexOf('const saveProviderSettings = async'),
    appSource.indexOf('const clearProviderApiKey = async')
  );
  const defaultSave = appSource.slice(
    appSource.indexOf('const saveStandardDefaultProvider = async'),
    appSource.indexOf('const selectProfile =')
  );

  assert.match(providerSave, /method: 'PUT'/);
  assert.doesNotMatch(providerSave, /set-default/);
  assert.match(defaultSave, /code-quality-review-providers\/\$\{selectedProviderCode\}\/set-default/);
  assert.match(defaultSave, /method: 'POST'/);
});

test('keeps Agent runtime selection details and budgets on separate PUT paths', () => {
  const runtimeSelection = appSource.slice(
    appSource.indexOf('const saveAgentRuntimeSelection = async'),
    appSource.indexOf('const validateAgentRuntimeDetail =')
  );
  const runtimeDetail = appSource.slice(
    appSource.indexOf('const saveAgentRuntimeDetail = async'),
    appSource.indexOf('const clearAgentRuntimeKey =')
  );
  const budgetSave = appSource.slice(
    appSource.indexOf('const saveAgentBudgets = async'),
    appSource.indexOf('const resetAgentBudgets =')
  );

  assert.match(
    runtimeSelection,
    /body: JSON\.stringify\(\{\s*enabled: Boolean\(agentSettingsDraft\.enabled\),\s*selectedRuntime: runtimeType\s*\}\)/
  );
  assert.match(runtimeDetail, /body\.customRuntime/);
  assert.match(runtimeDetail, /body\.apiKey/);
  assert.doesNotMatch(runtimeDetail, /selectedRuntime: runtimeType/);
  assert.match(budgetSave, /JSON\.stringify\(\{ budgets: agentSettingsDraft\.budgets \}\)/);
});

test('protects dirty connection drafts before directory selection changes', () => {
  assert.match(appSource, /if \(!agentSettings \|\| !aiSettings\) return;/);
  assert.match(appSource, /dirtyReviewConnectionId === selectedReviewConnectionId/);
  assert.match(appSource, /title: '放弃未保存的连接修改？'/);
  assert.match(appSource, /restoreReviewConnectionDraft\(selectedReviewConnectionId\)/);
  assert.match(appSource, /okText: '放弃并切换'/);
  assert.match(appSource, /cancelText: '继续编辑'/);
});

test('keeps directory rows keyboard-selectable and the three planned layouts bounded', () => {
  assert.match(appSource, /tabIndex: 0/);
  assert.match(appSource, /event\.key === 'Enter' \|\| event\.key === ' '/);
  assert.match(appSource, /scroll=\{\{ x: 920 \}\}/);
  assert.match(styleSource, /grid-template-columns: minmax\(0, 3fr\) minmax\(360px, 2fr\)/);
  assert.match(styleSource, /@media \(max-width: 1199px\)[\s\S]*\.review-connection-workbench[\s\S]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(styleSource, /@media \(max-width: 760px\)[\s\S]*\.review-runtime-card-grid[\s\S]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(styleSource, /\.review-connection-actions \.ant-btn \{\s*min-height: 44px;/);
});

test('does not invent a Standard switch or a fixed Agent fallback selector', () => {
  assert.match(appSource, /平台全局 \{\(settingsDraft\?\.reviewEnabled/);
  assert.match(appSource, /失败后继承 Standard 动态解析链/);
  assert.doesNotMatch(appSource, /aria-label="启用 Standard Review"/);
  assert.doesNotMatch(appSource, /Agent fallback Provider/);
});

test('browser acceptance mock stays local and never calls a model Provider', () => {
  assert.match(mockSource, /const host = '127\.0\.0\.1'/);
  assert.match(mockSource, /docs54-settings-safe-mock/);
  assert.match(mockSource, /safe-mock\.invalid/);
  assert.doesNotMatch(mockSource, /\bfetch\s*\(/);
  assert.doesNotMatch(mockSource, /https\.request/);
});

test('keeps Agent polling terminal states and cleanup bounded', () => {
  const polling = appSource.slice(
    appSource.indexOf('useEffect(() => {\n    const requestId = agentSettingsTestResult?.requestId'),
    appSource.indexOf('const loadProjectTargetConfigs = async')
  );

  assert.match(polling, /\['QUEUED', 'RUNNING'\]\.includes/);
  assert.match(polling, /status: 'POLL_TIMEOUT'/);
  assert.match(polling, /status: 'POLL_FAILED'/);
  assert.match(polling, /if \(timer\) window\.clearTimeout\(timer\)/);
  assert.match(polling, /nextTest\?\.status === 'SUCCESS'/);
});

test('safe mock exposes only fixed local regression scenarios', () => {
  [
    'AGENT_INCOMPLETE',
    'AGENT_ASYNC_SUCCESS',
    'AGENT_ASYNC_FAILED',
    'PROVIDER_TEST_FAILED',
    'SETTINGS_READ_FAILED',
    'AGENT_READ_FAILED',
    'PROVIDERS_READ_FAILED',
    'MUTATION_FAILED'
  ].forEach(scenario => assert.match(mockSource, new RegExp(`'${scenario}'`)));
  assert.match(mockSource, /Unsupported safe mock scenario/);
  assert.match(mockSource, /advanceAgentTestScenario\(\)/);
});

test('preserves surrounding Settings domains and Provider override controls', () => {
  const orderedItems = appSource.slice(
    appSource.indexOf('const orderedCollapseItems = ['),
    appSource.indexOf('return (', appSource.indexOf('const orderedCollapseItems = ['))
  );

  assert.match(orderedItems, /'project-target-configs'/);
  assert.match(orderedItems, /'profile-settings'/);
  assert.match(orderedItems, /'global-settings'/);
  assert.match(appSource, /<Text strong>Provider 覆盖<\/Text>/);
  assert.match(appSource, /commitSettingsChange\('reviewEnabled'/);
});

test('offers an in-page retry after a Settings read failure', () => {
  assert.match(appSource, /action=\{<Button size="small" loading=\{loading\} onClick=\{load\}>重试<\/Button>\}/);
});
