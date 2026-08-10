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

  assert.match(appSource, /const activeSettingsItem = collapseItems\.find\(item => item\.key === activeSettingsSection\?\.key\)/);
  assert.match(appSource, /data-settings-section=\{activeSettingsSection\?\.key \|\| ''\}/);
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

test('keeps dynamic Agent selection, details and budgets on separate mutation paths', () => {
  const runtimeSelection = appSource.slice(
    appSource.indexOf('const saveDynamicAgentRuntimeSelection = async'),
    appSource.indexOf('const requestDeleteAgentRuntime =')
  );
  const runtimeDetail = appSource.slice(
    appSource.indexOf('const saveDynamicAgentRuntimeDetail = async'),
    appSource.indexOf('const clearDynamicAgentRuntimeKey =')
  );
  const budgetSave = appSource.slice(
    appSource.indexOf('const saveAgentBudgets = async'),
    appSource.indexOf('const resetAgentBudgets =')
  );

  assert.match(runtimeSelection, /code-quality-agent-runtimes\/\$\{runtime\.runtimeCode\}\/set-current/);
  assert.match(runtimeSelection, /JSON\.stringify\(\{ enabled: Boolean\(agentSettingsDraft\.enabled\) \}\)/);
  assert.doesNotMatch(runtimeSelection, /selectedRuntime:/);
  assert.match(runtimeDetail, /code-quality-agent-runtimes\/\$\{runtime\.runtimeCode\}/);
  assert.match(runtimeDetail, /buildUpdateAgentRuntimeRequest/);
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
  const directoryColumns = appSource.slice(
    appSource.indexOf('const reviewConnectionColumns = ['),
    appSource.indexOf('const activeRuntimeType =', appSource.indexOf('const reviewConnectionColumns = ['))
  );
  assert.match(directoryColumns, /title: '操作'/);
  assert.match(directoryColumns, /providerDeleteAvailability\(provider\)/);
  assert.match(directoryColumns, /agentRuntimeDeleteAvailability\(runtime\)/);
  assert.match(directoryColumns, /className: 'review-connection-directory-actions'/);
  assert.match(directoryColumns, /icon=\{<DeleteOutlined \/>\}/);
  assert.doesNotMatch(directoryColumns, />\s*详情\s*<\/Button>/);
  assert.match(styleSource, /grid-template-columns: minmax\(0, 3fr\) minmax\(360px, 2fr\)/);
  assert.match(styleSource, /@media \(max-width: 1199px\)[\s\S]*\.review-connection-workbench[\s\S]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(styleSource, /@media \(max-width: 760px\)[\s\S]*\.review-runtime-card-grid[\s\S]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(styleSource, /\.review-connection-actions \.ant-btn \{\s*min-height: 44px;/);
  assert.match(styleSource, /@media \(max-width: 760px\)[\s\S]*\.review-provider-danger-zone[\s\S]*display: flex/);
  assert.match(styleSource, /@media \(max-width: 760px\)[\s\S]*\.review-connection-directory-actions[\s\S]*display: none/);
});

test('creates Agent or Standard connections without selecting defaults or testing connectivity', () => {
  const createFlow = appSource.slice(
    appSource.indexOf('const createReviewConnection = async'),
    appSource.indexOf('const closeDeleteProviderModal =')
  );
  assert.match(appSource, /title="新增模型连接"/);
  assert.match(appSource, />\s*新增模型连接\s*<\/Button>/);
  assert.match(createFlow, /code-quality-agent-runtimes', \{\s*method: 'POST'/);
  assert.match(createFlow, /code-quality-review-providers', \{\s*method: 'POST'/);
  assert.match(createFlow, /setSelectedReviewConnectionId\(connectionId\)/);
  assert.match(createFlow, /setSelectedReviewConnectionId\(`AGENT:\$\{created\.runtimeCode\}`\)/);
  assert.match(appSource, /title: '切换 Review 类型并丢弃当前输入？'/);
  assert.match(appSource, /Agent Review'[\s\S]*Standard Review'/);
  assert.match(appSource, /agentProtocolOptionsForWorkerPool\(agentSettings\?\.workerPool\)\.map/);
  assert.doesNotMatch(createFlow, /set-default/);
  assert.doesNotMatch(createFlow, /\/test/);
});

test('deletes only confirmed custom Providers and preserves selection on failures', () => {
  const deleteFlow = appSource.slice(
    appSource.indexOf('const deleteCustomProvider = async'),
    appSource.indexOf('const updateAgentDefaultKeyDraft =')
  );
  assert.match(appSource, /title="永久删除自定义 Provider"/);
  assert.match(appSource, /matchesProviderDeleteConfirmation/);
  assert.match(deleteFlow, /method: 'DELETE'/);
  assert.match(deleteFlow, /resolveReviewModelConnectionSelection\(nextRows, previousSelection\)/);
  assert.match(deleteFlow, /setProviderDeleteError\(err\.message\)/);
  assert.match(appSource, /className="review-provider-danger-zone"/);
  assert.match(appSource, /runAfterDiscardingConnectionDraft/);
});

test('supports native Runtime edit, test and protected delete without exposing key state', () => {
  assert.match(appSource, /const saveDynamicAgentRuntimeDetail = async/);
  assert.match(appSource, /const testDynamicAgentRuntime = async/);
  assert.match(appSource, /code-quality-agent-runtimes\/\$\{runtime\.runtimeCode\}\/test/);
  assert.match(appSource, /title="永久删除自定义 Agent Runtime"/);
  assert.match(appSource, /matchesAgentRuntimeDeleteConfirmation/);
  assert.match(appSource, /className="review-provider-danger-zone"/);
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
    'PROVIDER_DELETE_IN_USE',
    'MUTATION_FAILED'
  ].forEach(scenario => assert.match(mockSource, new RegExp(`'${scenario}'`)));
  assert.match(mockSource, /Unsupported safe mock scenario/);
  assert.match(mockSource, /advanceAgentTestScenario\(\)/);
  assert.match(mockSource, /request\.method === 'POST' && url\.pathname === '\/api\/code-quality-review-providers'/);
  assert.match(mockSource, /request\.method === 'POST' && url\.pathname === '\/api\/code-quality-agent-runtimes'/);
  assert.match(mockSource, /runtimeTestMatch/);
  assert.match(mockSource, /request\.method === 'DELETE' && providerMatch/);
});

test('preserves surrounding Settings domains and Provider override controls', () => {
  assert.match(appSource, /key: 'project-target-configs'/);
  assert.match(appSource, /key: 'profile-settings'/);
  assert.match(appSource, /key: 'global-settings'/);
  assert.match(appSource, /<Text strong>Provider 覆盖<\/Text>/);
  assert.match(appSource, /commitSettingsChange\('reviewEnabled'/);
});

test('offers an in-page retry after a Settings read failure', () => {
  assert.match(appSource, /action=\{<Button size="small" loading=\{loading\} onClick=\{load\}>重试<\/Button>\}/);
});
