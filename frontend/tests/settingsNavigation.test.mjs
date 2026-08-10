import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  DEFAULT_SETTINGS_ROUTE,
  SETTINGS_SECTIONS,
  resolveSettingsSection,
  settingsSectionHasDirtyDraft
} from '../src/settingsNavigation.js';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');

test('maps the four existing settings modules to stable child routes', () => {
  assert.equal(DEFAULT_SETTINGS_ROUTE, '/settings/model-connections');
  assert.deepEqual(SETTINGS_SECTIONS.map(item => item.key), [
    'project-target-configs',
    'profile-settings',
    'review-model-settings',
    'global-settings'
  ]);
  for (const section of SETTINGS_SECTIONS) {
    assert.equal(resolveSettingsSection(section.route)?.key, section.key);
  }
  assert.equal(resolveSettingsSection('/settings'), null);
  assert.equal(resolveSettingsSection('/settings/unknown'), null);
  assert.equal(resolveSettingsSection('/settings/global/')?.key, 'global-settings');
});

test('scopes dirty drafts to the visible settings module', () => {
  const dirty = new Set(['profile-settings:profile', 'project-target-configs:path-mappings']);
  assert.equal(settingsSectionHasDirtyDraft(dirty, 'profile-settings'), true);
  assert.equal(settingsSectionHasDirtyDraft(dirty, 'project-target-configs'), true);
  assert.equal(settingsSectionHasDirtyDraft(dirty, 'global-settings'), false);
  assert.equal(settingsSectionHasDirtyDraft(new Set(), 'review-model-settings', 'STANDARD:DEEPSEEK'), true);
});

test('redirects legacy settings and protects shell, history and page-close navigation', () => {
  assert.match(appSource, /location\.pathname === SETTINGS_ROUTE[\s\S]*<Navigate to=\{DEFAULT_SETTINGS_ROUTE\} replace \/>/);
  assert.match(appSource, /path=\{`\$\{SETTINGS_ROUTE\}\/\*`\}/);
  assert.match(appSource, /title: '放弃当前设置模块的未保存修改？'/);
  assert.match(appSource, /window\.addEventListener\('beforeunload', onBeforeUnload\)/);
  assert.match(appSource, /registerSettingsNavigationGuard\(\{/);
  assert.match(appSource, /requestSettingsNavigation\(performNavigation\)/);
});
