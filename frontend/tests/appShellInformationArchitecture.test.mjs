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

test('shell brand uses the site favicon as its visible logo', () => {
  assert.match(appSource, /<img alt="" className="app-shell-brand-icon" src="\/favicon\.png" \/>/);
  assert.match(styleSource, /\.app-shell-brand-icon\s*\{[^}]*width:\s*28px;[^}]*height:\s*28px;/s);
  assert.match(appSource, /SafetyCertificateOutlined,[\s\S]*} from '@ant-design\/icons';/);
});

test('shell styling fixes the shared dimensions without introducing content scrolling', () => {
  assert.match(styleSource, /--app-shell-header-height:\s*56px/);
  assert.match(styleSource, /--app-shell-sidebar-expanded:\s*224px/);
  assert.match(styleSource, /--app-shell-sidebar-collapsed:\s*72px/);
  assert.match(styleSource, /\.app-main-layout\s*\{[^}]*min-width:\s*0;/s);
  assert.match(styleSource, /\.app-header\s*\{[^}]*position:\s*sticky;[^}]*top:\s*0;/s);
  assert.match(appSource, /<Sider[\s\S]*collapsedWidth=\{72\}[\s\S]*width=\{224\}/s);
  assert.doesNotMatch(styleSource, /\.app-content\s*\{[^}]*overflow-y:/s);
});

test('expanded shell menus expose controlled submenu state changes', () => {
  assert.match(appSource, /openKeys=\{collapsed \? undefined : openKeys\}/);
  assert.match(appSource, /onOpenChange=\{collapsed \? undefined : onOpenChange\}/);
  assert.match(appSource, /onOpenChange=\{setOpenNavigationKeys\}/);
});
