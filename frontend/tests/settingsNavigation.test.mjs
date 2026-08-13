import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  AI_REVIEW_MODELS_ROUTE,
  AI_REVIEW_POLICIES_ROUTE,
  AI_REVIEW_SETTINGS_TABS,
  DEFAULT_SETTINGS_ROUTE,
  SETTINGS_SECTIONS,
  resolveSettingsRedirect,
  resolveSettingsSection,
  settingsSectionHasDirtyDraft
} from '../src/settingsNavigation.js';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');

test('maps the three settings menu entries and both AI Review tabs to stable child routes', () => {
  assert.equal(DEFAULT_SETTINGS_ROUTE, AI_REVIEW_MODELS_ROUTE);
  assert.equal(AI_REVIEW_MODELS_ROUTE, '/settings/ai-review/models');
  assert.equal(AI_REVIEW_POLICIES_ROUTE, '/settings/ai-review/policies');
  assert.deepEqual(SETTINGS_SECTIONS.map(item => item.key), [
    'project-target-configs',
    'ai-review-settings',
    'global-settings'
  ]);
  assert.deepEqual(AI_REVIEW_SETTINGS_TABS.map(item => item.key), ['models', 'policies']);
  assert.equal(resolveSettingsSection('/settings/project-targets')?.key, 'project-target-configs');
  assert.deepEqual(
    {
      key: resolveSettingsSection(AI_REVIEW_MODELS_ROUTE)?.key,
      tabKey: resolveSettingsSection(AI_REVIEW_MODELS_ROUTE)?.tabKey,
      contentKey: resolveSettingsSection(AI_REVIEW_MODELS_ROUTE)?.contentKey
    },
    { key: 'ai-review-settings', tabKey: 'models', contentKey: 'review-model-settings' }
  );
  assert.deepEqual(
    {
      key: resolveSettingsSection(`${AI_REVIEW_POLICIES_ROUTE}/`)?.key,
      tabKey: resolveSettingsSection(`${AI_REVIEW_POLICIES_ROUTE}/`)?.tabKey,
      contentKey: resolveSettingsSection(`${AI_REVIEW_POLICIES_ROUTE}/`)?.contentKey
    },
    { key: 'ai-review-settings', tabKey: 'policies', contentKey: 'profile-settings' }
  );
  assert.equal(resolveSettingsSection('/settings'), null);
  assert.equal(resolveSettingsSection('/settings/unknown'), null);
  assert.equal(resolveSettingsSection('/settings/global/')?.key, 'global-settings');
});

test('redirects settings roots and legacy AI Review routes to canonical tabs', () => {
  assert.equal(resolveSettingsRedirect('/settings'), AI_REVIEW_MODELS_ROUTE);
  assert.equal(resolveSettingsRedirect('/settings/'), AI_REVIEW_MODELS_ROUTE);
  assert.equal(resolveSettingsRedirect('/settings/ai-review'), AI_REVIEW_MODELS_ROUTE);
  assert.equal(resolveSettingsRedirect('/settings/model-connections'), AI_REVIEW_MODELS_ROUTE);
  assert.equal(resolveSettingsRedirect('/settings/review-profiles/'), AI_REVIEW_POLICIES_ROUTE);
  assert.equal(resolveSettingsRedirect(AI_REVIEW_MODELS_ROUTE), null);
  assert.equal(resolveSettingsRedirect('/settings/unknown'), null);
});

test('scopes dirty drafts to the visible settings module', () => {
  const dirty = new Set(['profile-settings:profile', 'project-target-configs:path-mappings']);
  assert.equal(settingsSectionHasDirtyDraft(dirty, 'profile-settings'), true);
  assert.equal(settingsSectionHasDirtyDraft(dirty, 'project-target-configs'), true);
  assert.equal(settingsSectionHasDirtyDraft(dirty, 'global-settings'), false);
  assert.equal(settingsSectionHasDirtyDraft(new Set(), 'review-model-settings', 'STANDARD:DEEPSEEK'), true);
});

test('redirects legacy settings and protects shell, history and page-close navigation', () => {
  assert.match(appSource, /const redirectRoute = resolveSettingsRedirect\(location\.pathname\)/);
  assert.match(appSource, /<Navigate to=\{redirectRoute\} replace \/>/);
  assert.match(appSource, /path=\{`\$\{SETTINGS_ROUTE\}\/\*`\}/);
  assert.match(appSource, /title: '放弃当前设置模块的未保存修改？'/);
  assert.match(appSource, /window\.addEventListener\('beforeunload', onBeforeUnload\)/);
  assert.match(appSource, /registerSettingsNavigationGuard\(\{/);
  assert.match(appSource, /requestSettingsNavigation\(performNavigation\)/);
  assert.match(appSource, /requestSettingsNavigation\(\(\) => navigate\(nextTab\.route\)\)/);
});
