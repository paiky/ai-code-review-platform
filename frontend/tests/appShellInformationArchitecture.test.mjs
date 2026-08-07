import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
const styleSource = await readFile(new URL('../src/styles.css', import.meta.url), 'utf8');

test('AppFrame owns one responsive admin shell and removes it entirely in immersive mode', () => {
  assert.match(appSource, /viewportMode !== 'mobile'[\s\S]*<Sider/s);
  assert.match(appSource, /viewportMode === 'tablet'[\s\S]*app-sidebar-tablet-drawer/s);
  assert.match(appSource, /viewportMode === 'mobile'[\s\S]*app-sidebar-mobile-drawer/s);
  assert.equal((appSource.match(/!reviewWorkspaceFrame\.immersive &&/g) || []).length >= 4, true);
  assert.match(appSource, /setTemporaryNavigationOpen\(false\);\s*\}, \[reviewWorkspaceFrame\.immersive, viewportMode\]\)/);
});

test('global header exposes only real operations in the planned order', () => {
  const start = appSource.indexOf('<div className="header-actions">');
  const end = appSource.indexOf('</div>', start);
  const headerActions = appSource.slice(start, end);
  const markers = ['帮助', '版本', 'AI Review 失败通知', 'AI Review 调度队列'];
  let previous = -1;
  for (const marker of markers) {
    const position = headerActions.indexOf(marker);
    assert.equal(position > previous, true, marker);
    previous = position;
  }
  assert.doesNotMatch(headerActions, /管理员|头像|退出/);
});

test('shell styling fixes the shared dimensions without introducing content scrolling', () => {
  assert.match(styleSource, /--app-shell-header-height:\s*56px/);
  assert.match(styleSource, /--app-shell-sidebar-expanded:\s*224px/);
  assert.match(styleSource, /--app-shell-sidebar-collapsed:\s*72px/);
  assert.match(styleSource, /\.app-main-layout\s*\{[^}]*min-width:\s*0;/s);
  assert.match(styleSource, /\.app-header\s*\{[^}]*position:\s*sticky;[^}]*top:\s*0;/s);
  assert.doesNotMatch(styleSource, /\.app-content\s*\{[^}]*overflow-y:/s);
});
