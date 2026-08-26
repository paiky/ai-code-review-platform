import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
const appShellSource = await readFile(new URL('../src/appShell.js', import.meta.url), 'utf8');
const styleSource = await readFile(new URL('../src/styles.css', import.meta.url), 'utf8');
const projectPageSource = await readFile(new URL('../src/project-config/ProjectConfigurationPage.jsx', import.meta.url), 'utf8');
const projectDrawerSource = await readFile(new URL('../src/project-config/ProjectConfigurationDrawer.jsx', import.meta.url), 'utf8');
const projectStyleSource = await readFile(new URL('../src/project-config/projectConfiguration.css', import.meta.url), 'utf8');
const settingsSource = [appSource, projectPageSource, projectDrawerSource].join('\n');

test('legacy project group controls and API dependencies stay removed', () => {
  for (const marker of [
    '/api/project-groups',
    '项目组 AI Review 通用策略',
    '保存项目组 AI Review 策略',
    'Profile / 项目组策略',
    'selectedPushPolicyGroupId',
    'pushPolicyFromGroup'
  ]) {
    assert.equal(settingsSource.includes(marker), false, marker);
  }
});

test('settings workspaces expose consistent titles, descriptions, and semantic icons', () => {
  assert.equal(appSource.includes('function SettingsCardHeader({ icon, title, description, tags, extra, compact = false })'), true);
  [
    '项目通知与 Review 配置',
    '端类型自动识别规则',
    'Review 触发',
    '普通 Review 初始 Prompt',
    'Agent Review 运行配置',
    'Standard Review 运行配置',
    '模型连接目录',
    'Agent 执行预算',
    '平台全局能力',
    '钉钉通知'
  ].forEach(title => assert.equal(settingsSource.includes(title), true, `missing settings title: ${title}`));
  assert.equal(appSource.includes('className="settings-card-description"'), true);
  assert.equal(projectDrawerSource.includes('基础与 Review 配置'), false);
  assert.equal(projectDrawerSource.includes('icon={<ThunderboltOutlined />}'), true);
  assert.equal(appSource.includes('title="项目组管理"'), false);
  assert.equal(appSource.includes('title="项目归属与 Review 配置"'), false);
});
test('task navigation keeps an explicit icon in the shared sidebar model', () => {
  assert.match(appShellSource, /\{ key: '\/tasks', label: '任务', icon: 'tasks' \}/);
  assert.match(appSource, /tasks: <FileSearchOutlined \/>/);
});

test('Agent settings keep spacious headers and responsive recommended budget selects', () => {
  assert.match(styleSource, /\.settings-subsection > \.settings-card-header \{\s*margin-bottom: 24px;/);
  assert.equal(styleSource.includes('grid-template-columns: repeat(4, minmax(0, 1fr));'), true);
  assert.equal(styleSource.includes('.agent-budget-field-select {'), true);
  assert.equal(appSource.includes('message="当前配置高于默认预算"'), false);
  assert.equal(appSource.includes('title="运行参数无效"'), true);
});

test('Agent convergence budgets keep their grid while project filters move into the project center', () => {
  assert.equal(appSource.includes('{agentBudgetFields.map(item => ('), true);
  assert.equal(appSource.includes('label: \'高级收敛参数\''), false);
  assert.match(appSource, /<Col xs=\{24\} lg=\{8\}>\s*<Text strong>Profile<\/Text>/);
  assert.match(projectPageSource, /placeholder="项目名 \/ GitLab 路径 \/ ID"/);
  assert.match(projectPageSource, /placeholder="全部通知状态"/);
  assert.match(projectPageSource, /placeholder="全部 Review 状态"/);
  assert.match(projectStyleSource, /grid-template-columns: minmax\(150px, 0\.8fr\)/);
});
test('settings route panel fills the page and all business cards use compact framed surfaces', () => {
  assert.doesNotMatch(
    appSource,
    /<Paper[^>]*>\s*<Spin spinning=\{loading\}>\s*<Collapse className="settings-collapse"/
  );
  assert.match(appSource, /<Spin spinning=\{loading\}>\s*<section[\s\S]*className="settings-route-panel"/);
  assert.match(appSource, /<div className="settings-subsection">\s*<Space direction="vertical" size="middle" className="global-settings-stack">/);
  assert.match(styleSource, /\.settings-route-panel \{\s*min-width: 0;/);
  assert.match(styleSource, /\.settings-inner-card \.ant-card-body \{\s*padding: 8px;/);
  assert.match(styleSource, /\.settings-subsection \{\s*padding: 16px;/);
  assert.match(projectStyleSource, /\.project-config-page \{\s*width: 100%;\s*min-width: 0;/);
});
