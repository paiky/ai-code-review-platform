import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  applyProjectEditorDefaults,
  normalizePage,
  normalizeProjectConfiguration,
  projectDisplayName,
  projectRepositoryUrl,
  TARGET_TYPE_OPTIONS
} from '../src/project-config/projectConfigurationModel.js';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
const navigationSource = await readFile(new URL('../src/settingsNavigation.js', import.meta.url), 'utf8');
const pageSource = await readFile(new URL('../src/project-config/ProjectConfigurationPage.jsx', import.meta.url), 'utf8');
const tableSource = await readFile(new URL('../src/project-config/ProjectConfigurationTable.jsx', import.meta.url), 'utf8');
const drawerSource = await readFile(new URL('../src/project-config/ProjectConfigurationDrawer.jsx', import.meta.url), 'utf8');
const batchSource = await readFile(new URL('../src/project-config/BatchWebhookDrawer.jsx', import.meta.url), 'utf8');
const librarySource = await readFile(new URL('../src/project-config/WebhookLibrary.jsx', import.meta.url), 'utf8');
const editorSource = await readFile(new URL('../src/project-config/WebhookEditorModal.jsx', import.meta.url), 'utf8');
const apiSource = await readFile(new URL('../src/project-config/projectConfigurationApi.js', import.meta.url), 'utf8');
const cssSource = await readFile(new URL('../src/project-config/projectConfiguration.css', import.meta.url), 'utf8');

test('normalizes project pages and complete configuration drafts without losing saved values', () => {
  assert.equal(TARGET_TYPE_OPTIONS.length, 6);
  assert.deepEqual(TARGET_TYPE_OPTIONS.map(item => item.value), [
    'BACKEND', 'WEB_PC', 'APP_IOS', 'APP_ANDROID', 'APP_CROSS_PLATFORM', 'GENERAL'
  ]);
  assert.deepEqual(normalizePage({ items: [{ id: 1 }], total: 7, pageNo: 2, pageSize: 5 }), {
    items: [{ id: 1 }], total: 7, pageNo: 2, pageSize: 5
  });
  assert.equal(projectDisplayName({ name: 'group/service-api' }), 'service-api');
  assert.equal(projectRepositoryUrl({ repositoryUrl: 'https://gitlab.example.com/group/service-api' }), 'https://gitlab.example.com/group/service-api');
  assert.equal(projectRepositoryUrl({ repositoryUrl: 'javascript:alert(1)' }), null);

  const draft = normalizeProjectConfiguration({
    targetType: 'WEB_PC',
    targetConfig: {
      templateCode: 'frontend-default',
      codeQualityProfileCode: 'web-pc-default-ai-review',
      providerCode: null,
      pathPatterns: ['frontend/**'],
      reminderCardEnabled: false
    },
    aiReviewModels: [{ providerCode: 'DEEPSEEK', modelName: 'deepseek-v4', enabled: true }],
    reviewSettings: { triggerOnMr: true, triggerOnPush: true, pushDebounceSeconds: 60 },
    webhookIds: [3, 8]
  });
  assert.equal(draft.targetType, 'WEB_PC');
  assert.deepEqual(draft.targetConfig.pathPatterns, ['frontend/**']);
  assert.equal(draft.reviewSettings.triggerOnPush, true);
  assert.equal(draft.reviewSettings.pushDebounceSeconds, 60);
  assert.deepEqual(draft.webhookIds, [3, 8]);
});

test('initializes server default paths while preserving profile and clearing model overrides', () => {
  const managed = applyProjectEditorDefaults({
    targetType: 'BACKEND',
    targetConfig: {
      templateCode: 'custom-template',
      codeQualityProfileCode: 'legacy-profile',
      providerCode: 'LEGACY',
      pathPatterns: ['legacy/**'],
      reminderCardEnabled: true
    },
    aiReviewModels: [{ providerCode: 'LEGACY', enabled: true }]
  }, {
    targetConfig: {
      pathPatterns: ['backend-python/**', 'backend/**']
    }
  });
  assert.equal(managed.targetConfig.templateCode, 'custom-template');
  assert.equal(managed.targetConfig.codeQualityProfileCode, 'legacy-profile');
  assert.equal(managed.targetConfig.providerCode, null);
  assert.deepEqual(managed.targetConfig.pathPatterns, ['backend-python/**', 'backend/**']);
  assert.deepEqual(managed.aiReviewModels, []);
});

test('replaces the visible project-group settings workspace with a modular project center', () => {
  assert.match(appSource, /import ProjectConfigurationPage from ['"]\.\/project-config\/ProjectConfigurationPage\.jsx['"]/);
  assert.match(appSource, /children: <ProjectConfigurationPage onDirtyChange=\{handleProjectCenterDirtyChange\} \/>/);
  assert.doesNotMatch(appSource, /title="项目组管理"/);
  assert.doesNotMatch(appSource, /title="项目归属与 Review 配置"/);
  assert.match(navigationSource, /label: '项目 \/ 端类型配置'/);
  assert.match(pageSource, /项目通知与 Review 配置/);
  assert.match(pageSource, /项目配置[\s\S]*钉钉机器人库/);
  assert.match(pageSource, /MIGRATION_NOTICE_KEY/);
});

test('uses server filters and pagination and keeps selection scoped to the current result page', () => {
  ['keyword', 'targetType', 'notificationStatus', 'reviewStatus', 'pageNo', 'pageSize']
    .forEach(field => assert.match(apiSource, new RegExp(`${field}:`)));
  assert.match(tableSource, /pagination=\{\{/);
  assert.match(tableSource, /preserveSelectedRowKeys: false/);
  assert.match(pageSource, /setSelectedRowKeys\(\[\]\);\s*setAppliedFilters/);
  assert.match(pageSource, /const changePage = \(pageNo, pageSize\) => \{\s*setSelectedRowKeys\(\[\]\)/);
  assert.match(pageSource, /批量配置机器人/);
  assert.match(tableSource, /project\.notificationStatus/);
  assert.match(tableSource, /project\.healthWarning/);
  assert.match(tableSource, /project\.reviewStatus/);
});

test('submits the complete project configuration and protects auto-detection evidence', () => {
  assert.match(apiSource, /\/api\/projects\/\$\{projectId\}\/configuration/);
  ['targetConfig', 'aiReviewModels', 'reviewSettings', 'webhookIds', 'triggerOnMr', 'triggerOnPush', 'pushBranchPatterns', 'autoFixPreviewSeverities']
    .forEach(field => assert.match(drawerSource, new RegExp(field)));
  assert.match(drawerSource, /evidenceVersion: detectionPreview\.evidenceVersion/);
  assert.match(drawerSource, /端类型变化将同时调整以下 Review 配置/);
  assert.doesNotMatch(drawerSource, /放弃未保存的项目配置/);
});

test('keeps profile and path overrides editable while removing project review model controls', () => {
  assert.match(drawerSource, /fetchReviewProfiles\(\)/);
  assert.match(drawerSource, /fetchProjectConfigurationDefaults\(configuration\.targetType\)/);
  assert.match(drawerSource, /applyProjectEditorDefaults/);
  assert.match(drawerSource, /AI Review Profile[\s\S]*options=\{profileOptions\}/);
  assert.match(drawerSource, /项目路径规则[\s\S]*mode="tags"/);
  assert.doesNotMatch(drawerSource, /fetchReviewProviders|buildProviderModels/);
  assert.doesNotMatch(drawerSource, /选择一个或多个模型连接/);
  assert.doesNotMatch(drawerSource, /<Text strong>Review 模型<\/Text>/);
  assert.doesNotMatch(cssSource, /project-config-managed-defaults|project-config-managed-field/);
});

test('previews batch webhook changes and keeps saved webhook targets server-owned', () => {
  assert.match(batchSource, /previewBatchNotificationWebhooks\(payload\)/);
  assert.match(batchSource, /saveBatchNotificationWebhooks\(payload\)/);
  assert.match(batchSource, /REPLACE[\s\S]*ADD[\s\S]*REMOVE/);
  assert.match(batchSource, /确认配置 \{projects\.length\} 个项目/);
  assert.match(librarySource, /testNotificationWebhook\(webhook\.id\)/);
  assert.doesNotMatch(librarySource, /testNotificationWebhook\([^)]*webhookUrl/);
  assert.match(editorSource, /if \(!editing \|\| draft\.replaceWebhook\) payload\.webhookUrl = webhookUrl/);
  assert.match(editorSource, /当前 Webhook/);
  assert.doesNotMatch(editorSource, /加签密钥/);
});

test('bounds the project center at desktop, tablet and mobile layouts', () => {
  assert.match(tableSource, /const PROJECT_COLUMN_WIDTH = 190/);
  assert.match(tableSource, /const TABLE_SCROLL_WIDTH = 1090/);
  assert.match(tableSource, /fixed: 'left'/);
  assert.match(tableSource, /fixed: 'right'/);
  assert.match(tableSource, /scroll=\{\{ x: TABLE_SCROLL_WIDTH \}\}/);
  assert.match(cssSource, /@media \(max-width: 1199px\)/);
  assert.match(cssSource, /@media \(max-width: 760px\)/);
  assert.match(cssSource, /@media \(max-width: 480px\)/);
  assert.match(cssSource, /max-width: 100vw/);
  assert.match(cssSource, /\.project-config-table-shell \{[\s\S]*overflow: hidden/);
});

test('links project names to GitLab without repeating repository URLs or a GitLab ID column', () => {
  assert.match(tableSource, /href=\{repositoryUrl\}/);
  assert.match(tableSource, /target="_blank"/);
  assert.match(tableSource, /rel="noopener noreferrer"/);
  assert.doesNotMatch(tableSource, /title: 'GitLab ID'/);
  assert.doesNotMatch(tableSource, /projectRepositoryHint/);
});

test('keeps the target detection summary compact instead of stretching the status tag', () => {
  assert.match(pageSource, /expandIconPosition="end"/);
  assert.match(pageSource, /project-config-rules-copy/);
  assert.match(pageSource, /project-config-rules-status/);
  assert.doesNotMatch(cssSource, /\.project-config-rules-label > span/);
  assert.match(cssSource, /\.project-config-rules-status \{[\s\S]*flex: 0 0 auto/);
});

test('dismisses the project drawer directly while keeping batch draft protection', () => {
  [drawerSource, batchSource].forEach(source => assert.match(source, /mask=\{\{ closable: !saving \}\}/));
  assert.match(drawerSource, /const requestClose = \(\) => \{\s*onDirtyChange\?\.\(false\);\s*onClose\?\.\(\);\s*\}/);
  assert.match(batchSource, /onClose=\{requestClose\}/);
});

test('keeps the project drawer free of redundant informational alerts', () => {
  assert.doesNotMatch(drawerSource, /已应用当前端类型默认路径/);
  assert.doesNotMatch(drawerSource, /任务仍会执行，钉钉通知将记录为跳过/);
  assert.doesNotMatch(drawerSource, /基础与 Review 配置|端类型变化会加载对应的服务端默认配置/);
});

test('keeps webhook status controls aligned and removes duplicate page header actions', () => {
  assert.match(editorSource, /project-config-webhook-status-field/);
  assert.match(cssSource, /\.project-config-webhook-status-field \{[\s\S]*flex-direction: row/);
  assert.match(cssSource, /\.project-config-webhook-status-field > \.ant-switch \{[\s\S]*flex: 0 0 auto/);
  assert.doesNotMatch(pageSource, /刷新当前项目页/);
  assert.doesNotMatch(pageSource, />刷新项目<\/Button>/);
  assert.doesNotMatch(pageSource, />管理机器人<\/Button>/);
});

test('uses current Ant Design drawer and alert properties in the project center', () => {
  const sources = [pageSource, drawerSource, batchSource, librarySource, editorSource];
  sources.forEach(source => assert.doesNotMatch(source, /\bmessage=/));
  [drawerSource, batchSource].forEach(source => {
    assert.match(source, /<Drawer[\s\S]{0,120}\bsize=/);
    assert.doesNotMatch(source, /<Drawer[\s\S]{0,120}\bwidth=/);
  });
});
