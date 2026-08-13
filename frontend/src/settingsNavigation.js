export const AI_REVIEW_MODELS_ROUTE = '/settings/ai-review/models';
export const AI_REVIEW_POLICIES_ROUTE = '/settings/ai-review/policies';
export const DEFAULT_SETTINGS_ROUTE = AI_REVIEW_MODELS_ROUTE;

export const AI_REVIEW_SETTINGS_TABS = Object.freeze([
  {
    key: 'models',
    route: AI_REVIEW_MODELS_ROUTE,
    label: '模型与运行',
    contentKey: 'review-model-settings'
  },
  {
    key: 'policies',
    route: AI_REVIEW_POLICIES_ROUTE,
    label: '策略与 Prompt',
    contentKey: 'profile-settings'
  }
]);

const SETTINGS_ROUTE_REDIRECTS = Object.freeze({
  '/settings': DEFAULT_SETTINGS_ROUTE,
  '/settings/ai-review': DEFAULT_SETTINGS_ROUTE,
  '/settings/model-connections': AI_REVIEW_MODELS_ROUTE,
  '/settings/review-profiles': AI_REVIEW_POLICIES_ROUTE
});

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
    key: 'ai-review-settings',
    route: DEFAULT_SETTINGS_ROUTE,
    label: 'AI Review 配置'
  },
  {
    key: 'global-settings',
    route: '/settings/global',
    label: '全局设置'
  }
]);

export function resolveSettingsSection(pathname) {
  const normalizedPathname = normalizeSettingsPathname(pathname);
  const aiReviewTab = AI_REVIEW_SETTINGS_TABS.find(tab => normalizedPathname === tab.route);
  if (aiReviewTab) {
    const section = SETTINGS_SECTIONS.find(item => item.key === 'ai-review-settings');
    return { ...section, tabKey: aiReviewTab.key, contentKey: aiReviewTab.contentKey };
  }
  return SETTINGS_SECTIONS.find(section => normalizedPathname === section.route) || null;
}

export function resolveSettingsRedirect(pathname) {
  return SETTINGS_ROUTE_REDIRECTS[normalizeSettingsPathname(pathname)] || null;
}

function normalizeSettingsPathname(pathname) {
  return pathname?.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
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
