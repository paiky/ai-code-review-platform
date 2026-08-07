import assert from 'node:assert/strict';
import test from 'node:test';

import {
  APP_SHELL_SIDEBAR_PREFERENCE_KEY,
  buildAppShellNavigation,
  readSidebarCollapsedPreference,
  resolveAppShellOpenKeys,
  resolveAppShellSelectedKey,
  resolveAppShellViewport,
  writeSidebarCollapsedPreference
} from '../src/appShell.js';

test('navigation keeps the public routes and maps detail routes to their parent', () => {
  const items = buildAppShellNavigation();
  assert.deepEqual(items.map(item => item.key), ['/', '/tasks', '/settings']);
  assert.equal(resolveAppShellSelectedKey('/', items), '/');
  assert.equal(resolveAppShellSelectedKey('/tasks', items), '/tasks');
  assert.equal(resolveAppShellSelectedKey('/tasks/42', items), '/tasks');
  assert.equal(resolveAppShellSelectedKey('/settings', items), '/settings');
  assert.equal(resolveAppShellSelectedKey('/releases', items), '');
  assert.equal(resolveAppShellSelectedKey('/unknown', items), '');
});

test('governance navigation remains behind its existing feature flags', () => {
  const hidden = buildAppShellNavigation({ reviewLearningVisible: true });
  assert.equal(hidden.some(item => item.key === 'quality-governance'), false);

  const visible = buildAppShellNavigation({ qualityGovernanceVisible: true });
  const governance = visible.find(item => item.key === 'quality-governance');
  assert.equal(governance.children.some(item => item.key === '/risk-feedback'), false);
  assert.equal(resolveAppShellSelectedKey('/acceptance-gates/8', visible), '/acceptance-gates');
  assert.deepEqual(resolveAppShellOpenKeys('/acceptance-gates', visible), ['quality-governance']);

  const learning = buildAppShellNavigation({
    qualityGovernanceVisible: true,
    reviewLearningVisible: true
  });
  assert.equal(
    learning.find(item => item.key === 'quality-governance').children.at(-1).key,
    '/risk-feedback'
  );
});

test('sidebar preference defaults to expanded and tolerates invalid or unavailable storage', () => {
  const values = new Map();
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value)
  };

  assert.equal(readSidebarCollapsedPreference(storage), false);
  assert.equal(writeSidebarCollapsedPreference(storage, true), true);
  assert.equal(values.get(APP_SHELL_SIDEBAR_PREFERENCE_KEY), 'true');
  assert.equal(readSidebarCollapsedPreference(storage), true);
  assert.equal(writeSidebarCollapsedPreference(storage, false), true);
  assert.equal(readSidebarCollapsedPreference(storage), false);

  values.set(APP_SHELL_SIDEBAR_PREFERENCE_KEY, 'invalid');
  assert.equal(readSidebarCollapsedPreference(storage), false);
  assert.equal(readSidebarCollapsedPreference({ getItem: () => { throw new Error('denied'); } }), false);
  assert.equal(writeSidebarCollapsedPreference({ setItem: () => { throw new Error('denied'); } }, true), false);
});

test('viewport boundaries follow the shell contract', () => {
  assert.equal(resolveAppShellViewport(390), 'mobile');
  assert.equal(resolveAppShellViewport(760), 'mobile');
  assert.equal(resolveAppShellViewport(761), 'tablet');
  assert.equal(resolveAppShellViewport(1199), 'tablet');
  assert.equal(resolveAppShellViewport(1200), 'desktop');
  assert.equal(resolveAppShellViewport(1440), 'desktop');
});
