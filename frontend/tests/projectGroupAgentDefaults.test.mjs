import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
const appShellSource = await readFile(new URL('../src/appShell.js', import.meta.url), 'utf8');
const styleSource = await readFile(new URL('../src/styles.css', import.meta.url), 'utf8');

test('project group Agent Review fixed defaults stay out of the settings controls', () => {
  assert.equal(appSource.includes("reviewEngine: 'AGENT'"), true);
  assert.equal(appSource.includes('agentSourceExportAllowed: true'), true);
  assert.equal(appSource.includes('aiReviewEnabled: true'), true);
  assert.equal(appSource.includes('triggerOnManual: true'), true);
  assert.equal(appSource.includes('此处决定所选项目组后续 MR、Push 和默认 Manual Review 使用的主引擎'), false);
  assert.equal(appSource.includes('<Text strong>Review 引擎</Text>'), false);
  assert.equal(appSource.includes('<Text strong>手动触发</Text>'), false);
  assert.equal(appSource.includes('<Text strong>允许 Agent 外发源码片段</Text>'), false);
  assert.equal(appSource.includes('<Text strong>启用项目组 AI Review</Text>'), false);
});

test('project group policy cards follow their feature switches', () => {
  assert.match(
    appSource,
    /\{pushPolicyDraft\?\.autoFixPreviewEnabled === true && \(\s*<Col xs=\{24\} lg=\{pushPolicyDraft\?\.triggerOnPush === true \? 8 : 24\}>/
  );
  assert.match(
    appSource,
    /\{pushPolicyDraft\?\.triggerOnPush === true && \(\s*<Col xs=\{24\} lg=\{pushPolicyDraft\?\.autoFixPreviewEnabled === true \? 16 : 24\}>/
  );
  assert.equal(appSource.includes('style={{ opacity: (pushPolicyDraft?.autoFixPreviewEnabled === true) ? 1 : 0.55 }}'), false);
});

test('settings cards expose consistent titles, descriptions, and semantic icons', () => {
  assert.equal(appSource.includes('function SettingsCardHeader({ icon, title, description, tags, extra, compact = false })'), true);
  [
    '项目组管理',
    '项目归属与 Review 配置',
    '端类型自动识别规则',
    '项目组 AI Review 通用策略',
    '普通 Review 初始 Prompt',
    'AI 模型 Provider',
    'Agent Review 接入配置',
    'Agent 执行预算',
    '平台全局能力',
    '钉钉通知',
    '修复预览策略',
    'Push 审核策略'
  ].forEach(title => assert.equal(appSource.includes(title), true, `missing settings card title: ${title}`));
  assert.equal(appSource.includes('className="settings-card-description"'), true);
  assert.equal(appSource.includes('icon={<SafetyCertificateOutlined />}'), true);
  assert.equal(appSource.includes('icon={<ThunderboltOutlined />}'), true);
  assert.equal(appSource.includes('title="Agent Review 运行概况"'), false);
  assert.equal(appSource.includes('title="队列与 Worker Pool"'), false);
});

test('task navigation keeps an explicit icon in the shared sidebar model', () => {
  assert.match(appShellSource, /\{ key: '\/tasks', label: '任务', icon: 'tasks' \}/);
  assert.match(appSource, /tasks: <FileSearchOutlined \/>/);
});

test('Agent settings keep spacious headers and compact budget controls without the raised-budget notice', () => {
  assert.equal(styleSource.includes('.settings-subsection > .settings-card-header {\n  margin-bottom: 24px;'), true);
  assert.equal(styleSource.includes('grid-template-columns: repeat(auto-fill, minmax(190px, 212px));'), true);
  assert.equal(appSource.includes('message="当前配置高于默认预算"'), false);
  assert.equal(appSource.includes('message="运行参数无效"'), true);
});

test('Agent convergence budgets share the main grid and settings selects use content-sized columns', () => {
  assert.equal(appSource.includes('{agentBudgetFields.map(item => ('), true);
  assert.equal(appSource.includes('label: \'高级收敛参数\''), false);
  assert.match(appSource, /<Col xs=\{24\} lg=\{8\}>\s*<Text strong>Profile<\/Text>/);
  assert.match(appSource, /<Col xs=\{24\} md=\{7\}>\s*<Text strong>项目组筛选<\/Text>/);
  assert.match(appSource, /<Col xs=\{24\} md=\{10\}>\s*<Text strong>项目<\/Text>/);
  assert.match(appSource, /<Col xs=\{24\} md=\{4\}>\s*<div className="settings-action-row project-config-save-row">/);
});

test('settings collapse fills the page and all business cards use compact framed surfaces', () => {
  assert.doesNotMatch(
    appSource,
    /<Paper[^>]*>\s*<Spin spinning=\{loading\}>\s*<Collapse className="settings-collapse"/
  );
  assert.match(appSource, /<Spin spinning=\{loading\}>\s*<Collapse className="settings-collapse" items=\{orderedCollapseItems\} \/>/);
  assert.match(appSource, /<div className="settings-subsection">\s*<Space direction="vertical" size="middle" className="global-settings-stack">/);
  assert.equal(styleSource.includes('.settings-collapse .ant-collapse-body,\n.settings-collapse .ant-collapse-content-box {\n  padding: 8px !important;'), true);
  assert.equal(styleSource.includes('.settings-inner-card .ant-card-body {\n  padding: 8px;'), true);
  assert.equal(styleSource.includes('.settings-subsection {\n  padding: 16px;'), true);
});
