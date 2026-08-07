export const APP_SHELL_SIDEBAR_PREFERENCE_KEY = 'ai-code-review.app-shell.sidebar-collapsed.v1';

export const APP_SHELL_BREAKPOINTS = Object.freeze({
  mobileMax: 760,
  tabletMax: 1199
});

const GOVERNANCE_ROUTES = Object.freeze([
  { key: '/review-quality', label: '质量看板', icon: 'quality' },
  { key: '/evaluation-cases', label: '评估样本', icon: 'samples' },
  { key: '/rule-gaps', label: '规则缺口', icon: 'gaps' },
  { key: '/acceptance-gates', label: '验收记录', icon: 'acceptance' },
  { key: '/evaluation-runs', label: '回放记录', icon: 'replay' }
]);

function routeMatches(pathname, route, exact = false) {
  if (exact) return pathname === route;
  return pathname === route || pathname.startsWith(`${route}/`);
}

export function buildAppShellNavigation({
  qualityGovernanceVisible = false,
  reviewLearningVisible = false
} = {}) {
  const items = [
    { key: '/', label: '运行总览', icon: 'overview', exact: true },
    { key: '/tasks', label: '任务', icon: 'tasks' }
  ];

  if (qualityGovernanceVisible) {
    const children = reviewLearningVisible
      ? [...GOVERNANCE_ROUTES, { key: '/risk-feedback', label: '反馈池', icon: 'feedback' }]
      : GOVERNANCE_ROUTES;
    items.push({ key: 'quality-governance', label: '质量治理', icon: 'governance', children: [...children] });
  }

  items.push({ key: '/settings', label: '设置', icon: 'settings' });
  return items;
}

export function flattenAppShellNavigation(items) {
  return items.flatMap(item => item.children?.length ? item.children : [item]);
}

export function resolveAppShellSelectedKey(pathname, items) {
  const matches = flattenAppShellNavigation(items)
    .filter(item => routeMatches(pathname, item.key, item.exact))
    .sort((left, right) => right.key.length - left.key.length);
  return matches[0]?.key || '';
}

export function resolveAppShellOpenKeys(selectedKey, items) {
  const parent = items.find(item => item.children?.some(child => child.key === selectedKey));
  return parent ? [parent.key] : [];
}

export function readSidebarCollapsedPreference(storage) {
  try {
    const value = storage?.getItem(APP_SHELL_SIDEBAR_PREFERENCE_KEY);
    if (value === 'true') return true;
    if (value === 'false' || value == null) return false;
  } catch {
    return false;
  }
  return false;
}

export function writeSidebarCollapsedPreference(storage, collapsed) {
  try {
    storage?.setItem(APP_SHELL_SIDEBAR_PREFERENCE_KEY, collapsed ? 'true' : 'false');
    return true;
  } catch {
    return false;
  }
}

export function resolveAppShellViewport(width) {
  if (width <= APP_SHELL_BREAKPOINTS.mobileMax) return 'mobile';
  if (width <= APP_SHELL_BREAKPOINTS.tabletMax) return 'tablet';
  return 'desktop';
}
