export const TARGET_TYPE_OPTIONS = Object.freeze([
  { value: 'BACKEND', label: '后端', color: 'green' },
  { value: 'WEB_PC', label: 'PC Web', color: 'blue' },
  { value: 'APP_IOS', label: 'iOS', color: 'purple' },
  { value: 'APP_ANDROID', label: 'Android', color: 'magenta' },
  { value: 'APP_CROSS_PLATFORM', label: '跨端', color: 'cyan' },
  { value: 'GENERAL', label: '通用', color: 'default' }
]);

export const DEFAULT_TARGET_PATHS = Object.freeze({
  BACKEND: ['src/main/java/**', 'src/main/resources/**', 'backend-python/**', 'backend/**', 'pom.xml'],
  WEB_PC: ['frontend/**', 'web/**', 'src/**/*.tsx', 'src/**/*.jsx', 'src/**/*.vue', 'package.json'],
  APP_IOS: ['ios/**', '**/*.swift', '**/*.m', '**/*.mm', 'Podfile'],
  APP_ANDROID: ['android/**', '**/*.kt', '**/*.kts', '**/*.gradle', 'build.gradle'],
  APP_CROSS_PLATFORM: ['flutter/**', '**/*.dart', 'pubspec.yaml', 'rn/**', 'miniapp/**'],
  GENERAL: ['**/*']
});

export const EMPTY_PROJECT_FILTERS = Object.freeze({
  keyword: '',
  targetType: undefined,
  notificationStatus: undefined,
  reviewStatus: undefined
});

export const EMPTY_WEBHOOK_FILTERS = Object.freeze({
  keyword: '',
  status: undefined,
  lastTestStatus: undefined
});

export function targetTypeMeta(targetType) {
  return TARGET_TYPE_OPTIONS.find(item => item.value === targetType) || {
    value: targetType || 'GENERAL',
    label: targetType || '通用',
    color: 'default'
  };
}

export function projectDisplayName(project) {
  const raw = String(project?.name || '').trim();
  if (!raw) return `项目 ${project?.id || '-'}`;
  const segments = raw.split('/').filter(Boolean);
  return segments.at(-1) || raw;
}

export function projectRepositoryUrl(project) {
  const repositoryUrl = String(project?.repositoryUrl || '').trim();
  if (!repositoryUrl) return null;
  try {
    const url = new URL(repositoryUrl);
    return ['http:', 'https:'].includes(url.protocol) ? repositoryUrl : null;
  } catch {
    return null;
  }
}

export function normalizePage(data, fallbackPageNo = 1, fallbackPageSize = 20) {
  return {
    items: Array.isArray(data?.items) ? data.items : [],
    total: Number(data?.total || 0),
    pageNo: Number(data?.pageNo || fallbackPageNo),
    pageSize: Number(data?.pageSize || fallbackPageSize)
  };
}

export function normalizeProjectConfiguration(configuration) {
  const targetConfig = configuration?.targetConfig || {};
  const reviewSettings = configuration?.reviewSettings || {};
  return {
    targetType: configuration?.targetType || 'GENERAL',
    targetConfig: {
      templateCode: targetConfig.templateCode || 'general-default',
      codeQualityProfileCode: targetConfig.codeQualityProfileCode || null,
      providerCode: targetConfig.providerCode || null,
      pathPatterns: Array.isArray(targetConfig.pathPatterns) && targetConfig.pathPatterns.length
        ? targetConfig.pathPatterns
        : ['**/*'],
      reminderCardEnabled: Boolean(targetConfig.reminderCardEnabled)
    },
    aiReviewModels: Array.isArray(configuration?.aiReviewModels)
      ? configuration.aiReviewModels.map((item, index) => ({
        reviewKey: item.reviewKey || `${String(item.providerCode || 'provider').toLowerCase()}-${index + 1}`,
        providerCode: item.providerCode,
        modelName: item.modelName || null,
        displayName: item.displayName || item.modelName || item.providerCode,
        enabled: item.enabled !== false,
        sortOrder: Number(item.sortOrder ?? ((index + 1) * 10))
      }))
      : [],
    reviewSettings: {
      triggerOnMr: reviewSettings.triggerOnMr !== false,
      triggerOnPush: Boolean(reviewSettings.triggerOnPush),
      triggerOnlyWhenRiskMatched: Boolean(reviewSettings.triggerOnlyWhenRiskMatched),
      autoFixPreviewEnabled: Boolean(reviewSettings.autoFixPreviewEnabled),
      autoFixPreviewSeverities: Array.isArray(reviewSettings.autoFixPreviewSeverities)
        ? reviewSettings.autoFixPreviewSeverities
        : ['CRITICAL'],
      pushBranchPatterns: Array.isArray(reviewSettings.pushBranchPatterns)
        ? reviewSettings.pushBranchPatterns
        : ['develop', 'feature/*', 'bugfix/*', 'hotfix/*'],
      pushMinChangedFiles: Number(reviewSettings.pushMinChangedFiles ?? 10),
      pushMinDiffBytes: Number(reviewSettings.pushMinDiffBytes ?? 30000),
      pushMinCommitCount: Number(reviewSettings.pushMinCommitCount ?? 3),
      pushMaxChangedFiles: Number(reviewSettings.pushMaxChangedFiles ?? -1),
      pushMaxDiffBytes: Number(reviewSettings.pushMaxDiffBytes ?? -1),
      pushDebounceSeconds: Number(reviewSettings.pushDebounceSeconds ?? 300)
    },
    webhookIds: Array.isArray(configuration?.webhookIds) ? configuration.webhookIds.map(Number) : []
  };
}

export function applyProjectEditorDefaults(configuration, defaultsResponse) {
  const normalized = normalizeProjectConfiguration(configuration);
  const defaults = defaultsResponse?.targetConfig || {};
  const defaultPaths = Array.isArray(defaults.pathPatterns) && defaults.pathPatterns.length
    ? defaults.pathPatterns
    : normalized.targetConfig.pathPatterns;
  return {
    ...normalized,
    targetConfig: {
      ...normalized.targetConfig,
      providerCode: null,
      pathPatterns: [...defaultPaths]
    },
    aiReviewModels: []
  };
}

export function configurationFingerprint(value) {
  return JSON.stringify(value || null);
}

export function webhookTestMeta(status) {
  switch (String(status || 'UNTESTED').toUpperCase()) {
    case 'SUCCESS':
      return { label: '测试成功', color: 'success' };
    case 'FAILED':
      return { label: '测试失败', color: 'error' };
    case 'SKIPPED':
      return { label: '已跳过', color: 'warning' };
    default:
      return { label: '未测试', color: 'default' };
  }
}

export function formatDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}
