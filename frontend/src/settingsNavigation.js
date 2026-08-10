export const DEFAULT_SETTINGS_ROUTE = '/settings/model-connections';

let activeSettingsNavigationGuard = null;
let previousHistoryIndex = typeof window === 'undefined' ? null : window.history.state?.idx;
let restoringCancelledHistoryNavigation = false;
let cancelledHistoryFocusTarget = null;

export const SETTINGS_SECTIONS = Object.freeze([
  {
    key: 'project-target-configs',
    route: '/settings/project-targets',
    label: '项目组 / 端类型配置'
  },
  {
    key: 'profile-settings',
    route: '/settings/review-profiles',
    label: 'AI Review 配置'
  },
  {
    key: 'review-model-settings',
    route: DEFAULT_SETTINGS_ROUTE,
    label: '模型连接与 Review 配置'
  },
  {
    key: 'global-settings',
    route: '/settings/global',
    label: '全局设置'
  }
]);

export function resolveSettingsSection(pathname) {
  const normalizedPathname = pathname?.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
  return SETTINGS_SECTIONS.find(section => normalizedPathname === section.route) || null;
}

export function settingsSectionHasDirtyDraft(dirtyDraftTokens, sectionKey, dirtyConnectionId = null) {
  if (!sectionKey) return false;
  if (sectionKey === 'review-model-settings' && dirtyConnectionId) return true;
  return [...(dirtyDraftTokens || [])].some(token => token.startsWith(`${sectionKey}:`));
}

export function registerSettingsNavigationGuard(guard) {
  activeSettingsNavigationGuard = guard;
  previousHistoryIndex = typeof window === 'undefined' ? null : window.history.state?.idx;
  return () => {
    if (activeSettingsNavigationGuard === guard) activeSettingsNavigationGuard = null;
  };
}

export function requestSettingsNavigation(next) {
  if (activeSettingsNavigationGuard?.isDirty?.()) {
    activeSettingsNavigationGuard.requestNavigation(next);
    return true;
  }
  next();
  return false;
}

function handleSettingsHistoryNavigation(event) {
  const nextHistoryIndex = event.state?.idx;
  if (restoringCancelledHistoryNavigation) {
    restoringCancelledHistoryNavigation = false;
    previousHistoryIndex = nextHistoryIndex;
    window.setTimeout(() => cancelledHistoryFocusTarget?.focus?.(), 0);
    return;
  }
  if (!activeSettingsNavigationGuard?.isDirty?.()) {
    previousHistoryIndex = nextHistoryIndex;
    return;
  }
  if (window.confirm('当前设置模块有未保存修改，确定放弃并离开吗？')) {
    previousHistoryIndex = nextHistoryIndex;
    Promise.resolve(activeSettingsNavigationGuard.discard?.()).catch(() => {});
    return;
  }

  event.stopImmediatePropagation();
  const delta = Number(previousHistoryIndex) - Number(nextHistoryIndex);
  if (Number.isFinite(delta) && delta !== 0) {
    cancelledHistoryFocusTarget = document.activeElement;
    restoringCancelledHistoryNavigation = true;
    window.history.go(delta);
    return;
  }
  window.history.pushState(
    window.history.state,
    '',
    activeSettingsNavigationGuard.currentUrl?.() || window.location.href
  );
}

if (typeof window !== 'undefined') {
  window.addEventListener('popstate', handleSettingsHistoryNavigation, true);
}
