import {
  getLatestAgentTraceScope,
  isAgentHeartbeatProgressEvent,
  isAgentTraceProgressEvent,
  isEventInAgentTraceScope,
  summarizeAgentTrace
} from './agentReviewTrace.js';

export const REVIEW_JOURNEY_STAGE_STATUSES = Object.freeze([
  'WAITING',
  'ACTIVE',
  'SUCCESS',
  'WARNING',
  'FAILED',
  'SKIPPED',
  'CANCELLED'
]);

export const REVIEW_JOURNEY_STAGE_DEFINITIONS = Object.freeze([
  Object.freeze({
    id: 'scheduling',
    title: '排队与调度',
    detailKind: 'SCHEDULING',
    phases: Object.freeze([
      'QUEUED',
      'AGENT_QUEUED',
      'STARTED',
      'REQUEST_BUILT',
      'PROVIDER_SELECTED',
      'REQUEST_VALIDATED'
    ])
  }),
  Object.freeze({
    id: 'preflight',
    title: '确定性预检',
    detailKind: 'PREFLIGHT',
    phases: Object.freeze([
      'DETERMINISTIC_PRECHECK_STARTED',
      'DETERMINISTIC_PRECHECK_COMPLETED',
      'DETERMINISTIC_PRECHECK_FAILED',
      'DETERMINISTIC_PRECHECK_REUSED'
    ])
  }),
  Object.freeze({
    id: 'context',
    title: '上下文准备',
    detailKind: 'CONTEXT',
    phases: Object.freeze([
      'CONTEXT_PACK_BUILT',
      'LOCAL_REPO_PREPARED',
      'LOCAL_REPO_PREPARE_FAILED',
      'LOCAL_CONTEXT_RETRIEVED',
      'LOCAL_CONTEXT_RETRIEVE_FAILED'
    ])
  }),
  Object.freeze({
    id: 'model-review',
    title: '模型 Review',
    detailKind: 'MODEL_REVIEW',
    phases: Object.freeze([
      'AGENT_RECLAIMED',
      'AGENT_ANALYZING',
      'AGENT_TOOL_ACTIVITY',
      'AGENT_CONVERGING',
      'AGENT_SUBMITTING',
      'AGENT_HEARTBEAT',
      'PROVIDER_START',
      'HTTP_REQUEST_START'
    ])
  }),
  Object.freeze({
    id: 'parse-save',
    title: '解析与保存',
    detailKind: 'PARSE_SAVE',
    phases: Object.freeze([
      'OUTPUT_EXTRACTED',
      'JSON_PARSE_START',
      'JSON_PARSE_FAILED',
      'SAVE_RESULT',
      'RESULT_SAVED',
      'SAVE_FAILED'
    ])
  }),
  Object.freeze({
    id: 'terminal',
    title: '成功、失败、取消或 fallback 终态',
    detailKind: 'TERMINAL',
    phases: Object.freeze([
      'AGENT_FINISHED',
      'AGENT_FALLBACK',
      'AGENT_FALLBACK_QUEUED',
      'AGENT_CANCELLED',
      'FINISHED',
      'FAILED',
      'JOB_INTERRUPTED'
    ])
  })
]);

export const TASK_SHARED_PREFLIGHT_PHASES = Object.freeze([
  'DETERMINISTIC_PRECHECK_STARTED',
  'DETERMINISTIC_PRECHECK_COMPLETED',
  'DETERMINISTIC_PRECHECK_FAILED'
]);

const taskSharedPreflightPhases = new Set(TASK_SHARED_PREFLIGHT_PHASES);
const stageByFixedPhase = new Map(
  REVIEW_JOURNEY_STAGE_DEFINITIONS.flatMap(stage => (
    stage.phases.map(phase => [phase, stage.id])
  ))
);
const providerPhasePattern = /^(OPENAI|ANTHROPIC|DEEPSEEK|XIAOMIMO|GLM|CUSTOM)_(REQUEST|RESPONSE|FAILED)$/;
const providerParsedPattern = /^(OPENAI|ANTHROPIC|DEEPSEEK|XIAOMIMO|GLM|CUSTOM)_PARSED$/;
const cancellationPhases = new Set(['AGENT_CANCELLED', 'JOB_INTERRUPTED']);
const warningPhases = new Set([
  'DETERMINISTIC_PRECHECK_FAILED',
  'LOCAL_REPO_PREPARE_FAILED',
  'LOCAL_CONTEXT_RETRIEVE_FAILED',
  'AGENT_FALLBACK',
  'AGENT_FALLBACK_QUEUED'
]);
const terminalSuccessPhases = new Set(['AGENT_FINISHED', 'FINISHED']);
const runtimeQueuePhases = new Set(['QUEUED', 'AGENT_QUEUED']);
const stageStatusPriority = Object.freeze({
  WAITING: 0,
  SKIPPED: 1,
  SUCCESS: 2,
  WARNING: 3,
  ACTIVE: 4,
  FAILED: 5,
  CANCELLED: 5
});

const reviewStatusLabels = Object.freeze({
  QUEUED: '排队中',
  RUNNING: '运行中',
  SUCCESS: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
  SKIPPED: '已跳过',
  UNKNOWN: '历史任务未记录'
});

const stageWarningSummaries = Object.freeze({
  preflight: '确定性预检存在 fail-open 警告，Review 主结果不由该警告决定。',
  context: '部分上下文能力不可用，本次 Review 继续使用已有证据。',
  'model-review': '模型 Review 存在降级或部分失败，请以最终 Review 状态为准。',
  'parse-save': '解析或保存阶段存在警告，请以最终 Review 状态为准。',
  terminal: 'Agent 已转交 Standard fallback，请以最终保存结果为准。'
});
const stageFailureSummaries = Object.freeze({
  scheduling: 'Review 未能完成调度或请求准备。',
  preflight: '确定性预检未能完成；该检查失败不会改写 Review 主状态。',
  context: '上下文准备未能完成，请以本次实际可用证据为准。',
  'model-review': '模型 Review 未能成功完成。',
  'parse-save': '结构化解析或结果保存未能成功完成。',
  terminal: '本次 Review 没有成功进入完成终态。'
});
const stageSuggestedActions = Object.freeze({
  scheduling: '等待页面轮询更新；若任务已终止，可使用现有重试入口。',
  preflight: '继续以最终 Review 状态为准；需要时使用现有确定性检查入口复核。',
  context: '继续以正式 Review 结果为准；需要时使用现有高准确模式入口复核。',
  'model-review': '查看本阶段安全执行记录，并按现有操作决定是否重试。',
  'parse-save': '查看本阶段安全执行记录，并按现有操作决定是否重试。',
  terminal: '以正式结果和 Review 身份为准；需要时使用现有重试入口。'
});
const safePhaseLabels = Object.freeze({
  QUEUED: '已进入 Review 队列',
  AGENT_QUEUED: 'Agent Review 已进入队列',
  STARTED: 'Review 已启动',
  REQUEST_BUILT: 'Review 请求已准备',
  PROVIDER_SELECTED: 'Provider 已选择',
  REQUEST_VALIDATED: '请求已校验',
  DETERMINISTIC_PRECHECK_STARTED: '确定性预检已启动',
  DETERMINISTIC_PRECHECK_COMPLETED: '确定性预检已完成',
  DETERMINISTIC_PRECHECK_FAILED: '确定性预检不可用',
  DETERMINISTIC_PRECHECK_REUSED: '已复用本次调度的确定性预检',
  CONTEXT_PACK_BUILT: 'Context Pack 已构建',
  LOCAL_REPO_PREPARED: '本地上下文已准备',
  LOCAL_REPO_PREPARE_FAILED: '本地上下文准备不可用',
  LOCAL_CONTEXT_RETRIEVED: '受控上下文检索已完成',
  LOCAL_CONTEXT_RETRIEVE_FAILED: '受控上下文检索不可用',
  AGENT_RECLAIMED: '租约过期后重新领取',
  AGENT_ANALYZING: 'Agent 正在分析变更',
  AGENT_TOOL_ACTIVITY: 'Agent 正在受控只读取证',
  AGENT_CONVERGING: 'Agent 正在收敛结论',
  AGENT_SUBMITTING: 'Agent 正在提交 Review Card',
  AGENT_HEARTBEAT: 'Agent 最新安全心跳',
  PROVIDER_START: 'Provider 调用已启动',
  HTTP_REQUEST_START: 'Provider 请求已发起',
  OUTPUT_EXTRACTED: 'Provider 输出已提取',
  JSON_PARSE_START: '结构化解析已启动',
  JSON_PARSE_FAILED: '结构化解析失败',
  SAVE_RESULT: 'Review 结果正在保存',
  RESULT_SAVED: 'Review 结果已保存',
  SAVE_FAILED: 'Review 结果保存失败',
  AGENT_FINISHED: 'Agent Review 已完成',
  AGENT_FALLBACK: 'Agent 已转交 Standard fallback',
  AGENT_FALLBACK_QUEUED: 'Standard fallback 已排队',
  AGENT_CANCELLED: 'Agent Review 已取消',
  FINISHED: 'Review 已完成',
  FAILED: 'Review 执行失败',
  JOB_INTERRUPTED: 'Review 已中断'
});
const agentSubStageDefinitions = Object.freeze([
  Object.freeze({ id: 'analyzing', title: '分析变更', phase: 'AGENT_ANALYZING' }),
  Object.freeze({ id: 'evidence', title: '受控只读取证', phase: 'AGENT_TOOL_ACTIVITY' }),
  Object.freeze({ id: 'converging', title: '收敛结论', phase: 'AGENT_CONVERGING' }),
  Object.freeze({ id: 'submitting', title: '提交 Review Card', phase: 'AGENT_SUBMITTING' })
]);
const agentEffectiveBudgetKeys = Object.freeze([
  'maxTurns',
  'maxToolCalls',
  'maxSourceBytes',
  'timeoutSeconds',
  'inlineDiffBytes',
  'maxEvidenceCalls',
  'convergeAtCalls',
  'submitByTurn'
]);

export function buildReviewJourneys(reviews, events, options = {}) {
  const source = Array.isArray(reviews) ? reviews : [];
  const allowUnscopedCompatibility = source.length <= 1;
  return source.map((review, index) => buildReviewJourney(review, events, {
    ...options,
    index,
    multiReview: source.length > 1,
    allowUnscopedCompatibility
  }));
}

export function buildReviewJourney(review, events, options = {}) {
  const sourceReview = review && typeof review === 'object' ? review : {};
  const nowMs = normalizeNow(options.now);
  const scopedEvents = selectReviewJourneyEvents(sourceReview, events, {
    allowUnscopedCompatibility: options.allowUnscopedCompatibility !== false
  });
  const attemptScopedEvents = selectLatestAgentAttempt(scopedEvents);
  const identity = deriveReviewIdentity(sourceReview);
  const status = deriveReviewStatus(sourceReview, attemptScopedEvents);
  const agentSummary = ['AGENT', 'FALLBACK'].includes(identity.engineKind)
    ? safeAgentSummary(summarizeAgentTrace(attemptScopedEvents, nowMs), nowMs)
    : null;
  const mappedEvents = attemptScopedEvents
    .map(event => {
      const stageId = stageIdForPhase(event?.phase);
      return stageId ? {
        event,
        stageId,
        timestamp: parseJourneyTimestamp(event?.createdAt, nowMs)
      } : null;
    })
    .filter(Boolean);
  const currentStageId = deriveCurrentStageId(status, mappedEvents, identity.historical);
  const stages = REVIEW_JOURNEY_STAGE_DEFINITIONS.map(definition => {
    const stageEvents = mappedEvents.filter(item => item.stageId === definition.id);
    const statusCandidates = stageEvents.map(item => stageStatusForEvent(item.event));
    if (
      definition.id === 'scheduling'
      && status === 'QUEUED'
      && !identity.historical
    ) {
      statusCandidates.push('ACTIVE');
    }
    if (
      definition.id === currentStageId
      && ['QUEUED', 'RUNNING'].includes(status)
    ) {
      statusCandidates.push('ACTIVE');
    }
    if (
      definition.id === 'terminal'
      && isTerminalReviewStatus(status)
      && !identity.historical
    ) {
      statusCandidates.push(terminalStageStatus(status, identity.effectiveEngine));
    }
    const stageStatus = pickStageStatus(statusCandidates);
    const statusDerivedVisible = !identity.historical && (
      (definition.id === 'scheduling' && status === 'QUEUED')
      || (definition.id === 'terminal' && isTerminalReviewStatus(status))
    );
    return buildStage(
      definition,
      stageEvents,
      stageStatus,
      stageEvents.length > 0 || statusDerivedVisible,
      {
        agentSummary,
        identity,
        review: sourceReview,
        reviewStatus: status,
        allEvents: attemptScopedEvents
      }
    );
  });
  const reviewTimes = deriveReviewTimes(
    sourceReview,
    mappedEvents,
    status,
    nowMs
  );

  return {
    reviewKey: normalizeReviewKey(sourceReview.reviewKey),
    selectorKey: reviewSelectionKey(sourceReview, options.index || 0),
    requestedEngine: identity.requestedEngine,
    effectiveEngine: identity.effectiveEngine,
    engineLabel: identity.engineLabel,
    engineKind: identity.engineKind,
    historical: identity.historical,
    multiReview: Boolean(options.multiReview),
    groupLabel: options.multiReview ? '多模型 Review' : identity.engineLabel,
    providerLabel: providerLabel(sourceReview),
    modelLabel: cleanLabel(sourceReview.model),
    providerModelLabel: providerModelLabel(sourceReview),
    status,
    statusLabel: reviewJourneyStatusLabel(status),
    running: status === 'QUEUED' || status === 'RUNNING',
    terminal: isTerminalReviewStatus(status),
    currentStageId,
    startedAt: reviewTimes.startedAt,
    finishedAt: reviewTimes.finishedAt,
    durationMs: reviewTimes.durationMs,
    agentSummary,
    stages
  };
}

export function selectReviewJourneyEvents(review, events, options = {}) {
  const source = Array.isArray(events) ? events : [];
  const reviewKey = normalizeReviewKey(review?.reviewKey);
  const allowUnscopedCompatibility = options.allowUnscopedCompatibility !== false;
  return source.flatMap(event => {
    if (!event || typeof event !== 'object') return [];
    const eventReviewKey = normalizeReviewKey(event.reviewKey);
    const phase = normalizeEnum(event.phase);
    if (reviewKey) {
      if (eventReviewKey === reviewKey) {
        return [{ ...event, journeyShared: false }];
      }
      if (!eventReviewKey && taskSharedPreflightPhases.has(phase)) {
        return [{ ...event, journeyShared: true }];
      }
      return [];
    }
    if (!allowUnscopedCompatibility || eventReviewKey) return [];
    return [{
      ...event,
      journeyShared: taskSharedPreflightPhases.has(phase)
    }];
  });
}

export function reviewSelectionKey(review, index = 0) {
  const reviewKey = normalizeReviewKey(review?.reviewKey);
  if (reviewKey) return reviewKey;
  const id = cleanLabel(review?.id);
  return `legacy:${id || index}`;
}

export function resolveReviewSelectionKey(journeys, options = {}) {
  const source = Array.isArray(journeys) ? journeys : [];
  const availableKeys = new Set(source.map(item => item?.selectorKey).filter(Boolean));
  const requestedReviewKey = normalizeReviewKey(options.requestedReviewKey);
  if (options.preferRequested !== false && requestedReviewKey) {
    const requested = source.find(item => item?.reviewKey === requestedReviewKey);
    if (requested?.selectorKey) return requested.selectorKey;
  }
  if (options.currentSelectionKey && availableKeys.has(options.currentSelectionKey)) {
    return options.currentSelectionKey;
  }
  return source[0]?.selectorKey || null;
}

export function reviewJourneyStatusLabel(status) {
  return reviewStatusLabels[status] || reviewStatusLabels.UNKNOWN;
}

function deriveReviewIdentity(review) {
  const requestedEngine = normalizeEnum(review?.requestedEngine);
  const effectiveEngine = normalizeEnum(review?.effectiveEngine);
  if (requestedEngine === 'AGENT' && effectiveEngine === 'AGENT') {
    return {
      requestedEngine,
      effectiveEngine,
      engineLabel: 'Agent Review',
      engineKind: 'AGENT',
      historical: false
    };
  }
  if (requestedEngine === 'AGENT' && effectiveEngine === 'STANDARD_FALLBACK') {
    return {
      requestedEngine,
      effectiveEngine,
      engineLabel: 'Agent -> Standard fallback',
      engineKind: 'FALLBACK',
      historical: false
    };
  }
  if (requestedEngine === 'STANDARD' && effectiveEngine === 'STANDARD') {
    return {
      requestedEngine,
      effectiveEngine,
      engineLabel: 'Standard Review',
      engineKind: 'STANDARD',
      historical: false
    };
  }
  return {
    requestedEngine: requestedEngine || null,
    effectiveEngine: effectiveEngine || null,
    engineLabel: '历史任务未记录',
    engineKind: 'HISTORICAL',
    historical: true
  };
}

function deriveReviewStatus(review, events) {
  const phases = new Set(events.map(event => normalizeEnum(event?.phase)));
  if (
    phases.has('AGENT_CANCELLED')
    || phases.has('JOB_INTERRUPTED')
    || ['CANCELLED', 'CANCELED'].includes(normalizeEnum(review?.status))
  ) {
    return 'CANCELLED';
  }
  const rawStatus = normalizeEnum(review?.status);
  if (rawStatus === 'QUEUED') return 'QUEUED';
  if (rawStatus === 'RUNNING' || rawStatus === 'PENDING') {
    const runtimeEvents = events.filter(event => {
      const phase = normalizeEnum(event?.phase);
      return stageIdForPhase(phase) && !taskSharedPreflightPhases.has(phase);
    });
    if (
      runtimeEvents.length > 0
      && runtimeEvents.every(event => runtimeQueuePhases.has(normalizeEnum(event?.phase)))
    ) {
      return 'QUEUED';
    }
    return 'RUNNING';
  }
  if (rawStatus === 'SUCCESS' || rawStatus === 'COMPLETED') return 'SUCCESS';
  if (rawStatus === 'FAILED') return 'FAILED';
  if (rawStatus === 'SKIPPED') return 'SKIPPED';
  if ([...phases].some(phase => cancellationPhases.has(phase))) return 'CANCELLED';
  if ([...phases].some(phase => terminalSuccessPhases.has(phase))) return 'SUCCESS';
  if (phases.has('FAILED')) return 'FAILED';
  return 'UNKNOWN';
}

function selectLatestAgentAttempt(events) {
  const scope = getLatestAgentTraceScope(events);
  if (!scope) return events;
  return events.filter(event => (
    (!isAgentTraceProgressEvent(event) && !isAgentHeartbeatProgressEvent(event))
    || isEventInAgentTraceScope(event, scope)
  ));
}

function stageIdForPhase(value) {
  const phase = normalizeEnum(value);
  if (stageByFixedPhase.has(phase)) return stageByFixedPhase.get(phase);
  if (providerPhasePattern.test(phase)) return 'model-review';
  if (providerParsedPattern.test(phase)) return 'parse-save';
  return null;
}

function deriveCurrentStageId(status, mappedEvents, historical) {
  if (status === 'QUEUED' && !historical) return 'scheduling';
  if (status !== 'RUNNING') return null;
  const latest = [...mappedEvents].sort(compareMappedEventRecency).at(-1);
  return latest?.stageId || null;
}

function compareMappedEventRecency(left, right) {
  const leftHasTime = Number.isFinite(left?.timestamp);
  const rightHasTime = Number.isFinite(right?.timestamp);
  if (leftHasTime !== rightHasTime) return leftHasTime ? 1 : -1;
  if (leftHasTime && left.timestamp !== right.timestamp) {
    return left.timestamp - right.timestamp;
  }
  return stableEventId(left?.event) - stableEventId(right?.event);
}

function stableEventId(event) {
  const id = Number(event?.id);
  return Number.isFinite(id) ? id : 0;
}

function stageStatusForEvent(event) {
  const phase = normalizeEnum(event?.phase);
  const level = normalizeEnum(event?.level);
  if (cancellationPhases.has(phase)) return 'CANCELLED';
  if (warningPhases.has(phase)) return 'WARNING';
  if (
    phase === 'FAILED'
    || phase === 'SAVE_FAILED'
    || phase === 'JSON_PARSE_FAILED'
    || phase === 'PROVIDER_FAILED'
    || providerPhasePattern.test(phase) && phase.endsWith('_FAILED')
    || level === 'ERROR'
  ) {
    return 'FAILED';
  }
  if (level === 'WARN' || level === 'WARNING') return 'WARNING';
  return 'SUCCESS';
}

function pickStageStatus(statuses) {
  if (!Array.isArray(statuses) || statuses.length === 0) return 'WAITING';
  return statuses.reduce((selected, status) => (
    (stageStatusPriority[status] ?? -1) >= (stageStatusPriority[selected] ?? -1)
      ? status
      : selected
  ), 'WAITING');
}

function terminalStageStatus(status, effectiveEngine) {
  if (status === 'CANCELLED') return 'CANCELLED';
  if (status === 'FAILED') return 'FAILED';
  if (status === 'SKIPPED') return 'SKIPPED';
  if (effectiveEngine === 'STANDARD_FALLBACK') return 'WARNING';
  return 'SUCCESS';
}

function buildStage(definition, mappedEvents, status, visible, context) {
  const timestamps = mappedEvents
    .map(item => item.timestamp)
    .filter(Number.isFinite)
    .sort((left, right) => left - right);
  const startedTimestamp = timestamps[0] ?? null;
  const canFinish = status !== 'ACTIVE' && timestamps.length >= 2;
  const finishedTimestamp = canFinish ? timestamps[timestamps.length - 1] : null;
  const durationMs = (
    Number.isFinite(startedTimestamp)
    && Number.isFinite(finishedTimestamp)
    && finishedTimestamp >= startedTimestamp
  ) ? finishedTimestamp - startedTimestamp : null;
  const safeEvents = [...mappedEvents]
    .sort(compareMappedEventRecency)
    .map(item => safeJourneyEvent(item.event, item.timestamp));
  return {
    id: definition.id,
    title: definition.title,
    status,
    visible,
    startedAt: toIsoString(startedTimestamp),
    finishedAt: toIsoString(finishedTimestamp),
    durationMs,
    summary: stageSummary(definition.title, status),
    warningSummary: status === 'WARNING'
      ? stageWarningSummaries[definition.id] || '该阶段存在警告。'
      : status === 'FAILED'
        ? stageFailureSummaries[definition.id] || '该阶段没有成功完成。'
        : null,
    suggestedAction: ['WARNING', 'FAILED'].includes(status)
      ? stageSuggestedActions[definition.id] || '请以最终 Review 状态为准。'
      : null,
    safeMetrics: buildStageSafeMetrics(definition.id, safeEvents, context),
    events: safeEvents,
    detailKind: definition.detailKind,
    subStages: definition.id === 'model-review'
      ? buildAgentSubStages(context?.allEvents, context?.agentSummary, context?.reviewStatus)
      : []
  };
}

function stageSummary(title, status) {
  const labels = {
    WAITING: '尚无可靠记录',
    ACTIVE: '正在执行',
    SUCCESS: '已完成',
    WARNING: '已完成但存在警告',
    FAILED: '执行失败',
    SKIPPED: '已跳过',
    CANCELLED: '已取消'
  };
  return `${title}：${labels[status] || labels.WAITING}`;
}

function safeJourneyEvent(event, timestamp) {
  const phase = normalizeEnum(event?.phase) || null;
  const hasDetail = event?.detail !== null
    && event?.detail !== undefined
    && String(event.detail).trim() !== '';
  const detailAvailable = !hasDetail || parseDetailObject(event.detail) !== null;
  return {
    id: nonNegativeNumber(event?.id),
    reviewKey: normalizeReviewKey(event?.reviewKey),
    phase,
    level: safeJourneyLevel(event?.level),
    createdAt: toIsoString(timestamp),
    shared: Boolean(event?.journeyShared),
    auxiliary: isAgentHeartbeatProgressEvent(event),
    safeLabel: safePhaseLabel(phase),
    safeSummary: safeEventSummary(phase, Boolean(event?.journeyShared)),
    detailAvailable
  };
}

function buildStageSafeMetrics(stageId, events, context = {}) {
  if (stageId === 'scheduling') {
    return [
      safeMetric('Review 引擎', context.identity?.engineLabel),
      safeMetric('Provider/model', providerModelLabel(context.review))
    ].filter(Boolean);
  }
  if (stageId === 'preflight') {
    const sharedCount = events.filter(event => event.shared).length;
    return [
      safeMetric('安全阶段记录', events.length),
      sharedCount > 0 ? safeMetric('本次调度共享', sharedCount) : null
    ].filter(Boolean);
  }
  if (stageId === 'model-review' && context.agentSummary) {
    const summary = context.agentSummary;
    const budgets = summary.effectiveBudgets || {};
    return [
      safeMetric('Agent Run', summary.runId == null ? null : `#${summary.runId}`),
      safeMetric('领取尝试', summary.claimAttempt == null ? null : `第 ${summary.claimAttempt} 次`),
      safeMetric('最近心跳', summary.lastHeartbeatAt),
      safeMetric('工具调用', usedLimitText(summary.toolCallCount, budgets.maxToolCalls)),
      safeMetric('证据调用', usedLimitText(summary.evidenceCallsUsed, budgets.maxEvidenceCalls)),
      safeMetric('源码返回', usedLimitText(summary.sourceBytesReturned, budgets.maxSourceBytes, ' bytes')),
      safeMetric(
        '模型回合',
        summary.terminal
          ? usedLimitText(summary.turnCount, budgets.maxTurns)
          : budgets.maxTurns == null
            ? '完成后可见'
            : `完成后可见 / ${budgets.maxTurns}`
      )
    ].filter(Boolean);
  }
  if (stageId === 'parse-save') {
    const findingCount = nonNegativeNumber(context.review?.findingCount);
    return [
      safeMetric('安全阶段记录', events.length),
      findingCount === null ? null : safeMetric('结构化问题', findingCount)
    ].filter(Boolean);
  }
  if (stageId === 'terminal') {
    return [
      safeMetric('Review 状态', reviewJourneyStatusLabel(context.reviewStatus)),
      safeMetric('实际引擎', context.identity?.engineLabel)
    ].filter(Boolean);
  }
  return events.length > 0 ? [safeMetric('安全阶段记录', events.length)] : [];
}

function buildAgentSubStages(events, agentSummary, reviewStatus) {
  if (!agentSummary) return [];
  const phases = new Set(
    (Array.isArray(events) ? events : []).map(event => normalizeEnum(event?.phase))
  );
  const activePhase = reviewStatus === 'RUNNING' ? agentSummary.phase : null;
  const hasOperationalPhase = agentSubStageDefinitions.some(item => phases.has(item.phase));
  if (!hasOperationalPhase) return [];
  return agentSubStageDefinitions.map(item => ({
    id: item.id,
    title: item.title,
    status: activePhase === item.phase
      ? 'ACTIVE'
      : phases.has(item.phase)
        ? 'SUCCESS'
        : 'WAITING'
  }));
}

function safeAgentSummary(summary, nowMs) {
  if (!summary || typeof summary !== 'object') return null;
  const heartbeatTimestamp = parseJourneyTimestamp(summary.lastHeartbeatAt, nowMs);
  return {
    runId: nonNegativeNumber(summary.runId),
    claimAttempt: nonNegativeNumber(summary.claimAttempt),
    phase: normalizeEnum(summary.phase) || 'AGENT_ANALYZING',
    terminal: Boolean(summary.terminal),
    hasHeartbeat: Boolean(summary.hasHeartbeat) && Number.isFinite(heartbeatTimestamp),
    lastHeartbeatAt: toIsoString(heartbeatTimestamp),
    heartbeatSequence: nonNegativeNumber(summary.heartbeatSequence),
    progressMayBeDelayed: Boolean(summary.progressMayBeDelayed),
    toolCallCount: nonNegativeNumber(summary.toolCallCount) ?? 0,
    evidenceCallsUsed: nonNegativeNumber(summary.evidenceCallsUsed) ?? 0,
    sourceBytesReturned: nonNegativeNumber(summary.sourceBytesReturned) ?? 0,
    diffBytesReturned: nonNegativeNumber(summary.diffBytesReturned) ?? 0,
    turnCount: summary.terminal ? nonNegativeNumber(summary.turnCount) : null,
    effectiveBudgets: safeNumberMap(summary.effectiveBudgets, agentEffectiveBudgetKeys),
    reviewBudget: {
      phase: ['DISCOVERY', 'CONVERGE', 'SUBMIT'].includes(normalizeEnum(summary.reviewBudget?.phase))
        ? normalizeEnum(summary.reviewBudget.phase)
        : '',
      evidenceCallsUsed: nonNegativeNumber(summary.reviewBudget?.evidenceCallsUsed) ?? 0,
      evidenceCallsRemaining: nonNegativeNumber(summary.reviewBudget?.evidenceCallsRemaining) ?? 0,
      sourceBytesRemaining: nonNegativeNumber(summary.reviewBudget?.sourceBytesRemaining) ?? 0,
      mustSubmit: Boolean(summary.reviewBudget?.mustSubmit)
    }
  };
}

function safeNumberMap(value, allowedKeys) {
  const source = value && typeof value === 'object' ? value : {};
  const allowed = new Set(allowedKeys);
  return Object.fromEntries(
    Object.entries(source)
      .filter(([key]) => allowed.has(key))
      .map(([key, item]) => [key, nonNegativeNumber(item)])
      .filter(([, item]) => item !== null)
  );
}

function safeMetric(label, value) {
  if (value === null || value === undefined || value === '') return null;
  return { label, value: String(value) };
}

function usedLimitText(usedValue, limitValue, suffix = '') {
  const used = nonNegativeNumber(usedValue);
  const limit = nonNegativeNumber(limitValue);
  if (used === null && limit === null) return null;
  return `${used ?? '-'} / ${limit ?? '-'}${suffix}`;
}

function nonNegativeNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function safePhaseLabel(phase) {
  if (safePhaseLabels[phase]) return safePhaseLabels[phase];
  const providerMatch = providerPhasePattern.exec(phase || '');
  if (providerMatch) {
    const [, provider, action] = providerMatch;
    const actionLabel = {
      REQUEST: '请求已发起',
      RESPONSE: '响应已返回',
      FAILED: '调用失败'
    }[action];
    return `${provider} ${actionLabel}`;
  }
  const parsedMatch = providerParsedPattern.exec(phase || '');
  if (parsedMatch) return `${parsedMatch[1]} 输出已解析`;
  return '高级执行记录';
}

function safeJourneyLevel(value) {
  const level = normalizeEnum(value);
  return ['INFO', 'DEBUG', 'WARN', 'WARNING', 'ERROR'].includes(level) ? level : null;
}

function safeEventSummary(phase, shared) {
  if (shared) return '本次调度共享的确定性预检记录。';
  if (phase === 'AGENT_HEARTBEAT') {
    return '用于刷新最新心跳和预算摘要，不作为独立时间轴节点。';
  }
  if (phase === 'DETERMINISTIC_PRECHECK_FAILED') {
    return '预检不可用，Review 主状态不会由该记录改写。';
  }
  if (phase === 'LOCAL_REPO_PREPARE_FAILED' || phase === 'LOCAL_CONTEXT_RETRIEVE_FAILED') {
    return '部分上下文能力不可用，本次 Review 继续使用已有证据。';
  }
  if (phase === 'AGENT_FALLBACK' || phase === 'AGENT_FALLBACK_QUEUED') {
    return 'Agent 已按既有策略显式转交 Standard Review。';
  }
  return `${safePhaseLabel(phase)}。`;
}

function parseDetailObject(detail) {
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) return detail;
  try {
    const value = JSON.parse(detail);
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  } catch {
    return null;
  }
}

function deriveReviewTimes(review, mappedEvents, status, nowMs) {
  const eventTimestamps = mappedEvents
    .map(item => item.timestamp)
    .filter(Number.isFinite)
    .sort((left, right) => left - right);
  const reviewStarted = parseJourneyTimestamp(review?.startedAt, nowMs);
  const reviewFinished = parseJourneyTimestamp(review?.finishedAt, nowMs);
  const startedTimestamp = Number.isFinite(reviewStarted)
    ? reviewStarted
    : eventTimestamps[0] ?? null;
  const terminal = isTerminalReviewStatus(status);
  const finishedCandidate = Number.isFinite(reviewFinished)
    ? reviewFinished
    : terminal
      ? eventTimestamps[eventTimestamps.length - 1] ?? null
      : null;
  const finishedTimestamp = (
    terminal
    && Number.isFinite(finishedCandidate)
    && (!Number.isFinite(startedTimestamp) || finishedCandidate >= startedTimestamp)
  ) ? finishedCandidate : null;
  const durationMs = (
    Number.isFinite(startedTimestamp)
    && Number.isFinite(finishedTimestamp)
    && finishedTimestamp > startedTimestamp
  ) ? finishedTimestamp - startedTimestamp : null;
  return {
    startedAt: toIsoString(startedTimestamp),
    finishedAt: toIsoString(finishedTimestamp),
    durationMs
  };
}

function isTerminalReviewStatus(status) {
  return ['SUCCESS', 'FAILED', 'CANCELLED', 'SKIPPED'].includes(status);
}

function providerLabel(review) {
  return cleanLabel(review?.provider) || cleanLabel(review?.displayName);
}

function providerModelLabel(review) {
  const provider = providerLabel(review);
  const model = cleanLabel(review?.model);
  if (provider && model && provider !== model) return `${provider} / ${model}`;
  return provider || model || 'Provider/model 未记录';
}

function parseJourneyTimestamp(value, nowMs) {
  if (!value) return null;
  const normalized = String(value).includes('T')
    ? String(value)
    : String(value).replace(' ', 'T');
  const hasExplicitTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(normalized);
  const timestamp = Date.parse(hasExplicitTimezone ? normalized : `${normalized}Z`);
  if (!Number.isFinite(timestamp) || timestamp > nowMs) return null;
  return timestamp;
}

function normalizeNow(value) {
  if (value instanceof Date) return value.getTime();
  const number = Number(value);
  return Number.isFinite(number) ? number : Date.now();
}

function toIsoString(timestamp) {
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : null;
}

function normalizeReviewKey(value) {
  return cleanLabel(value);
}

function normalizeEnum(value) {
  return cleanLabel(value)?.toUpperCase() || '';
}

function cleanLabel(value) {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}
