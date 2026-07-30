import {
  buildReviewHeroModel,
  visibleReviewJourneyStages
} from './reviewJourneyPresentation.js';

export const REVIEW_WORKSPACE_MODES = Object.freeze([
  'LOADING',
  'IMMERSIVE',
  'RESULT'
]);

const immersiveStatuses = new Set(['QUEUED', 'RUNNING']);
const allowedStatuses = new Set([
  'QUEUED',
  'RUNNING',
  'SUCCESS',
  'FAILED',
  'CANCELLED',
  'SKIPPED',
  'UNKNOWN'
]);

const agentActivityLabels = Object.freeze({
  AGENT_ANALYZING: 'Agent 正在分析变更',
  AGENT_TOOL_ACTIVITY: 'Agent 正在进行受控只读取证',
  AGENT_CONVERGING: 'Agent 正在收敛结论',
  AGENT_SUBMITTING: 'Agent 正在提交结构化结果'
});

const repositoryStatusLabels = Object.freeze({
  PREPARED: '已准备',
  WORKTREE_MISSING: '不可用',
  UNAVAILABLE: '不可用',
  DISABLED: '未启用',
  FAILED: '不可用'
});

const retrieverStatusLabels = Object.freeze({
  COMPLETED: '已完成',
  SUCCESS: '已完成',
  UNAVAILABLE: '不可用',
  FAILED: '不可用',
  SKIPPED: '已跳过',
  DISABLED: '未启用'
});

const preflightStatusLabels = Object.freeze({
  COMPLETED: '已完成',
  FAILED: '不可用（Review 继续）',
  RUNNING: '执行中',
  REUSED: '已复用',
  NOT_APPLICABLE: '不适用'
});

export function normalizeReviewWorkspaceMode(mode) {
  return REVIEW_WORKSPACE_MODES.includes(mode) ? mode : 'RESULT';
}

export function resolveReviewWorkspaceFrame(mode, isTaskDetailRoute) {
  const normalizedMode = normalizeReviewWorkspaceMode(mode);
  return {
    mode: normalizedMode,
    immersive: Boolean(isTaskDetailRoute) && normalizedMode === 'IMMERSIVE'
  };
}

export function deriveReviewWorkspaceMode({
  loaded = false,
  journey = null,
  safeFallback = false
} = {}) {
  if (!loaded) return 'LOADING';
  if (safeFallback || !journey || typeof journey !== 'object') return 'RESULT';
  const status = normalizeStatus(journey.status);
  if (journey.historical || !immersiveStatuses.has(status)) return 'RESULT';
  return 'IMMERSIVE';
}

export function buildReviewImmersivePresentation(input = {}) {
  const loaded = Boolean(input.loaded);
  try {
    const journey = input.journey && typeof input.journey === 'object'
      ? input.journey
      : null;
    const mode = deriveReviewWorkspaceMode({
      loaded,
      journey,
      safeFallback: Boolean(input.safeFallback)
    });
    if (!journey) return emptyPresentation(mode);

    const nowMs = normalizeNow(input.now);
    const stages = visibleReviewJourneyStages(journey);
    const currentStage = stages.find(stage => stage.id === journey.currentStageId) || null;
    const hero = buildReviewHeroModel(journey);
    const status = normalizeStatus(journey.status);
    const startedAt = safeIsoTime(journey.startedAt, nowMs);
    const lastHeartbeatAt = safeIsoTime(journey.agentSummary?.lastHeartbeatAt, nowMs);
    const taskSummary = safeTaskSummary(input.taskSummary, nowMs);

    return {
      mode,
      selectedReviewKey: safeStableKey(journey.selectorKey),
      engineVisual: journey.engineKind === 'STANDARD' || journey.engineKind === 'FALLBACK'
        ? 'STANDARD_FLOW'
        : 'AGENT_PARTICLE',
      engineIdentity: journey.engineKind === 'FALLBACK'
        ? 'FALLBACK'
        : journey.engineKind === 'STANDARD'
          ? 'STANDARD'
          : 'AGENT',
      identityLabel: safeText(journey.engineLabel, '历史任务未记录'),
      providerModelLabel: safeText(journey.providerModelLabel, 'Provider/model 未记录'),
      status,
      statusLabel: safeText(journey.statusLabel, '历史任务未记录'),
      currentStageId: currentStage?.id || null,
      currentStageTitle: currentStage?.title || '等待可靠阶段记录',
      headline: hero.title,
      description: hero.description,
      ariaLabel: hero.ariaLabel,
      heroState: hero.state,
      startedAt,
      elapsedMs: (
        mode === 'IMMERSIVE'
        && startedAt
      ) ? nowMs - Date.parse(startedAt) : null,
      heartbeat: {
        lastHeartbeatAt,
        delayed: Boolean(journey.agentSummary?.progressMayBeDelayed)
      },
      stages,
      contextMetrics: buildContextMetrics(
        stages,
        input.changedFilesSummary
      ),
      activityMetrics: buildActivityMetrics(journey, currentStage),
      fallbackTransfer: journey.engineKind === 'FALLBACK'
        ? {
            title: 'Agent 已转交 Standard Review',
            description: 'Standard Review 正在按既有策略接管本次任务。'
          }
        : null,
      hasTaskInfo: Boolean(taskSummary),
      taskSummary
    };
  } catch {
    return emptyPresentation(loaded ? 'RESULT' : 'LOADING');
  }
}

function buildContextMetrics(stages, changedFilesSummary) {
  const metrics = [];
  const changedFileCount = nonNegativeNumber(changedFilesSummary?.changedFileCount);
  addMetric(metrics, 'changed-files', '变更文件', changedFileCount);

  const context = stages
    .find(stage => stage.id === 'context')
    ?.details?.context;
  if (context?.hasReliableRecord) {
    addMetric(
      metrics,
      'context-pack',
      'Context Pack',
      context.contextPack?.built ? '已记录' : null
    );
    addMetric(
      metrics,
      'repository',
      '本地仓库准备',
      repositoryStatusLabels[context.repository?.status]
    );
    addMetric(
      metrics,
      'planner',
      'Planner Signal',
      nonNegativeNumber(context.planner?.signalCount)
    );
    addMetric(
      metrics,
      'retriever',
      'Retriever',
      retrieverStatusLabels[context.retriever?.status]
    );
    const available = nonNegativeNumber(context.requestedContext?.available);
    const unavailable = nonNegativeNumber(context.requestedContext?.unavailable);
    if (available !== null || unavailable !== null) {
      addMetric(
        metrics,
        'requested-context',
        'Requested Context',
        `${available ?? '-'} 可用 / ${unavailable ?? '-'} 不可用`
      );
    }
    const notInjected = nonNegativeNumber(context.budgetCuts?.notInjectedEvidenceCount);
    addMetric(metrics, 'not-injected', '未注入证据', notInjected);
  }

  const preflight = stages
    .find(stage => stage.id === 'preflight')
    ?.details?.preflight?.auto;
  addMetric(
    metrics,
    'preflight',
    'AUTO_PREFLIGHT',
    preflightStatusLabels[preflight?.status]
  );
  return metrics;
}

function buildActivityMetrics(journey, currentStage) {
  const metrics = [];
  if (journey.engineKind === 'AGENT' && journey.agentSummary) {
    const summary = journey.agentSummary;
    const budgets = summary.effectiveBudgets || {};
    addMetric(
      metrics,
      'agent-activity',
      '当前安全活动',
      agentActivityLabels[summary.phase] || 'Agent 正在执行 Review'
    );
    addMetric(metrics, 'tool-calls', '工具调用', usedLimitText(
      summary.toolCallCount,
      budgets.maxToolCalls
    ));
    addMetric(metrics, 'evidence-calls', '证据调用', usedLimitText(
      summary.evidenceCallsUsed,
      budgets.maxEvidenceCalls
    ));
    addMetric(metrics, 'source-bytes', '源码返回', usedLimitText(
      summary.sourceBytesReturned,
      budgets.maxSourceBytes,
      ' bytes'
    ));
    return metrics;
  }

  if (journey.engineKind === 'FALLBACK') {
    addMetric(metrics, 'fallback-activity', '当前安全活动', 'Standard Review 已接管');
  } else {
    addMetric(
      metrics,
      'provider-activity',
      '当前安全活动',
      currentStage ? `${currentStage.title}正在执行` : '等待 Provider 状态'
    );
  }
  const recordCount = Array.isArray(currentStage?.events)
    ? currentStage.events.length
    : null;
  addMetric(metrics, 'safe-records', '安全阶段记录', recordCount);
  return metrics;
}

function emptyPresentation(mode) {
  return {
    mode: normalizeReviewWorkspaceMode(mode),
    selectedReviewKey: null,
    engineVisual: 'STANDARD_FLOW',
    engineIdentity: 'STANDARD',
    identityLabel: '历史任务未记录',
    providerModelLabel: 'Provider/model 未记录',
    status: 'UNKNOWN',
    statusLabel: '历史任务未记录',
    currentStageId: null,
    currentStageTitle: '等待可靠阶段记录',
    headline: '历史任务未记录完整进度',
    description: '仅展示现有可靠记录，不补造阶段、时间、耗时或执行状态。',
    ariaLabel: '历史任务未记录完整进度',
    heroState: 'HISTORY',
    startedAt: null,
    elapsedMs: null,
    heartbeat: {
      lastHeartbeatAt: null,
      delayed: false
    },
    stages: [],
    contextMetrics: [],
    activityMetrics: [],
    fallbackTransfer: null,
    hasTaskInfo: false,
    taskSummary: null
  };
}

function safeTaskSummary(value, nowMs) {
  if (!value || typeof value !== 'object') return null;
  const id = nonNegativeNumber(value.id);
  const title = safeText(value.title, '');
  if (id === null && !title) return null;
  return {
    id,
    title: title || `Review 任务 #${id}`,
    triggerLabel: safeText(value.triggerLabel, '历史任务未记录'),
    targetLabel: safeText(value.targetLabel, '历史任务未记录'),
    taskStatusLabel: safeText(value.taskStatusLabel, '历史任务未记录'),
    eventAt: safeIsoTime(value.eventAt, nowMs),
    changedFileCount: nonNegativeNumber(value.changedFileCount)
  };
}

function addMetric(target, id, label, value) {
  if (value === null || value === undefined || value === '') return;
  target.push({
    id,
    label,
    value: String(value)
  });
}

function usedLimitText(usedValue, limitValue, suffix = '') {
  const used = nonNegativeNumber(usedValue);
  const limit = nonNegativeNumber(limitValue);
  if (used === null && limit === null) return null;
  return `${used ?? '-'} / ${limit ?? '-'}${suffix}`;
}

function safeIsoTime(value, nowMs) {
  const timestamp = Date.parse(value || '');
  if (!Number.isFinite(timestamp) || timestamp < 0 || timestamp > nowMs) return null;
  return new Date(timestamp).toISOString();
}

function normalizeNow(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : Date.now();
}

function normalizeStatus(value) {
  const status = String(value || '').trim().toUpperCase();
  return allowedStatuses.has(status) ? status : 'UNKNOWN';
}

function nonNegativeNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function safeStableKey(value) {
  const key = String(value || '').trim();
  return key ? key.slice(0, 160) : null;
}

function safeText(value, fallback) {
  const text = String(value || '')
    .replace(/[\u0000-\u001f\u007f]/g, ' ')
    .trim();
  return text ? text.slice(0, 160) : fallback;
}
