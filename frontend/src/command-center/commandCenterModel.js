export const RUNTIME_SCHEMA_VERSION = 'command-center-runtime-v2';
export const LEGACY_RUNTIME_SCHEMA_VERSION = 'command-center-runtime-v1';
export const GOVERNANCE_SCHEMA_VERSION = 'command-center-governance-v1';
export const RUNTIME_STALE_MS = 15_000;
export const GOVERNANCE_STALE_MS = 180_000;
export const COMMAND_CENTER_LIMITS = {
  activeTasks: 50,
  activeFlows: 50,
  workers: 100,
  providers: 100,
  alerts: 50
};

const KNOWN_FLOW_STATUSES = new Set([
  'QUEUED',
  'RUNNING',
  'PENDING',
  'CLAIMED',
  'SUCCESS',
  'FAILED',
  'SKIPPED',
  'CANCELLED',
  'TIMED_OUT',
  'FALLBACK',
  'COMPLETED'
]);
const KNOWN_FLOW_STAGES = new Set([
  'RULE_ANALYSIS',
  'RULE_COMPLETED',
  'PREFLIGHT',
  'QUEUED',
  'CONTEXT_BUILDING',
  'MODEL_CALLING',
  'AGENT_ANALYZING',
  'AGENT_TOOL_ACTIVITY',
  'AGENT_CONVERGING',
  'AGENT_SUBMITTING',
  'FINDING_READY',
  'NOTIFYING',
  'COMPLETED',
  'FAILED',
  'SKIPPED',
  'FALLBACK'
]);
const KNOWN_PROVIDER_STATUSES = new Set([
  'DISABLED',
  'ACTIVE',
  'RECENT_SUCCESS',
  'RECENT_FAILURE',
  'NO_RECENT_DATA'
]);


export function normalizeRuntimeSnapshot(input, { now = Date.now() } = {}) {
  const raw = isRecord(input) ? input : {};
  const generatedAt = safeIso(raw.generatedAt);
  const activeTasks = safeArray(raw.activeTasks)
    .slice(0, COMMAND_CENTER_LIMITS.activeTasks)
    .map(normalizeTask);
  const activeFlows = safeArray(raw.activeFlows)
    .slice(0, COMMAND_CENTER_LIMITS.activeFlows)
    .map(normalizeFlow);
  const reviewLanes = normalizeReviewLanes(raw.reviewLanes, {
    activeFlows,
    scheduler: raw.scheduler,
    agent: raw.agent
  });

  return {
    schemaVersion: safeText(raw.schemaVersion, RUNTIME_SCHEMA_VERSION),
    schemaCompatible: [RUNTIME_SCHEMA_VERSION, LEGACY_RUNTIME_SCHEMA_VERSION]
      .includes(raw.schemaVersion),
    generatedAt,
    freshness: snapshotFreshness(generatedAt, RUNTIME_STALE_MS, now),
    window: normalizeWindow(raw.window),
    intake: {
      taskCount: safeCount(raw.intake?.taskCount),
      activeTaskCount: safeCount(raw.intake?.activeTaskCount)
    },
    activeTasks,
    activeFlows,
    reviewLanes,
    scheduler: {
      activeJobCount: safeCount(raw.scheduler?.activeJobCount),
      queuedJobCount: safeCount(raw.scheduler?.queuedJobCount),
      runningJobCount: safeCount(raw.scheduler?.runningJobCount)
    },
    standard: normalizeEngine(raw.standard),
    agent: {
      ...normalizeEngine(raw.agent),
      workerPool: normalizeWorkerPool(raw.agent?.workerPool),
      queueMetrics: normalizeQueueMetrics(raw.agent?.queueMetrics)
    },
    providersObserved: safeArray(raw.providersObserved)
      .slice(0, COMMAND_CENTER_LIMITS.providers)
      .map(normalizeProvider),
    alerts: safeArray(raw.alerts)
      .slice(0, COMMAND_CENTER_LIMITS.alerts)
      .map(normalizeAlert),
    todayResults: normalizeTodayResults(raw.todayResults),
    coverage: normalizeCoverage(raw.coverage)
  };
}


function normalizeReviewLanes(value, context) {
  const raw = isRecord(value) ? value : {};
  if (isRecord(raw.standard) || isRecord(raw.agent)) {
    return {
      standard: normalizeReviewLane(raw.standard, 'standard', 'STANDARD'),
      agent: normalizeReviewLane(raw.agent, 'agent', 'AGENT')
    };
  }

  const activeFlows = context.activeFlows || [];
  const standardFlowCount = activeFlows.filter(
    flow => flow.status === 'RUNNING' && (flow.requestedEngine !== 'AGENT' || flow.fallback)
  ).length;
  const agentFlowCount = activeFlows.filter(
    flow => flow.status === 'RUNNING' && flow.requestedEngine === 'AGENT' && !flow.fallback
  ).length;
  const schedulerRunning = safeCount(context.scheduler?.runningJobCount);
  const schedulerQueued = safeCount(context.scheduler?.queuedJobCount);
  const agentRunning = safeCount(context.agent?.queueMetrics?.running);
  const agentQueued = safeCount(context.agent?.queueMetrics?.queued);
  return {
    standard: normalizeReviewLane({
      zoneKey: 'standard',
      capacity: 0,
      runningCount: Math.max(standardFlowCount, schedulerRunning - agentRunning),
      queuedCount: Math.max(0, schedulerQueued - agentQueued),
      runningItems: [],
      queueOrder: null
    }, 'standard', 'STANDARD'),
    agent: normalizeReviewLane({
      zoneKey: 'agent',
      capacity: context.agent?.queueMetrics?.onlineCapacity,
      runningCount: Math.max(agentFlowCount, agentRunning),
      queuedCount: agentQueued,
      runningItems: [],
      queueOrder: null
    }, 'agent', 'AGENT')
  };
}


function normalizeReviewLane(value, zoneKey, engine) {
  const raw = isRecord(value) ? value : {};
  const capacity = safeCount(raw.capacity);
  const runningCount = safeCount(raw.runningCount);
  return {
    zoneKey: safeText(raw.zoneKey, zoneKey),
    engine,
    capacity,
    runningCount,
    queuedCount: safeCount(raw.queuedCount),
    utilizationPercent: capacity > 0
      ? Math.min(safeCount(raw.utilizationPercent), 100)
      : 0,
    runningItems: safeArray(raw.runningItems)
      .slice(0, 100)
      .map(normalizeReviewLaneItem),
    nextQueued: isRecord(raw.nextQueued) ? normalizeReviewLaneItem(raw.nextQueued) : null,
    runningItemsTruncated: Boolean(raw.runningItemsTruncated),
    queueOrder: safeNullableText(raw.queueOrder)
  };
}


function normalizeReviewLaneItem(value) {
  const raw = isRecord(value) ? value : {};
  return {
    jobId: safeCount(raw.jobId),
    taskId: safeCount(raw.taskId),
    reviewKey: safeText(raw.reviewKey, 'default'),
    projectName: safeText(raw.projectName, '未知项目'),
    displayName: safeText(raw.displayName, safeText(raw.reviewKey, 'default')),
    requestedEngine: safeEnum(raw.requestedEngine, 'STANDARD'),
    effectiveEngine: safeEnum(raw.effectiveEngine, 'STANDARD'),
    fallback: Boolean(raw.fallback),
    status: safeEnum(raw.status, 'QUEUED'),
    stage: safeEnum(raw.stage, 'QUEUED'),
    provider: safeNullableText(raw.provider),
    model: safeNullableText(raw.model),
    workerId: safeNullableText(raw.workerId),
    queuedAt: safeIso(raw.queuedAt),
    startedAt: safeIso(raw.startedAt),
    durationSeconds: safeNullableCount(raw.durationSeconds)
  };
}


export function normalizeGovernanceSnapshot(input, { now = Date.now() } = {}) {
  const raw = isRecord(input) ? input : {};
  const generatedAt = safeIso(raw.generatedAt);
  return {
    schemaVersion: safeText(raw.schemaVersion, GOVERNANCE_SCHEMA_VERSION),
    schemaCompatible: raw.schemaVersion === GOVERNANCE_SCHEMA_VERSION,
    generatedAt,
    freshness: snapshotFreshness(generatedAt, GOVERNANCE_STALE_MS, now),
    window: normalizeWindow(raw.window),
    ruleAnalysis: normalizeWindowMetric(raw.ruleAnalysis, {
      resultCount: 0,
      riskItemCount: 0,
      riskDistribution: {}
    }),
    preflight: normalizeWindowMetric(raw.preflight, {
      runCount: 0,
      findingCount: 0,
      statusCounts: {}
    }),
    contextQuality: normalizeWindowMetric(raw.contextQuality, {
      findingCount: 0,
      statusCounts: {}
    }),
    findingRisk: normalizeWindowMetric(raw.findingRisk, {
      findingCount: 0,
      affectedTaskCount: 0,
      highestRisk: null,
      severityCounts: {}
    }),
    notifications: normalizeWindowMetric(raw.notifications, {
      recordCount: 0,
      statusCounts: {}
    }),
    feedback: normalizeWindowMetric(raw.feedback, {
      totalCount: 0,
      pendingCount: 0,
      statusCounts: {},
      typeCounts: {},
      contextMissingCount: 0,
      policyCandidateCount: 0
    }, 'ALL_TIME'),
    evaluation: {
      ...normalizeWindowMetric(raw.evaluation, {
        caseCount: 0,
        verdictCounts: {},
        ruleGapCounts: {},
        runCount: 0,
        runStatusCounts: {}
      }, 'ALL_TIME'),
      acceptance: {
        totalCount: safeCount(raw.evaluation?.acceptance?.totalCount),
        statusCounts: safeCounts(raw.evaluation?.acceptance?.statusCounts),
        latestStatus: safeNullableText(raw.evaluation?.acceptance?.latestStatus)
      },
      agentSampleGate: {
        annotatedSampleCount: safeCount(raw.evaluation?.agentSampleGate?.annotatedSampleCount),
        requiredSampleCount: safePositiveCount(raw.evaluation?.agentSampleGate?.requiredSampleCount, 30),
        ready: Boolean(raw.evaluation?.agentSampleGate?.ready)
      }
    },
    policies: normalizeWindowMetric(raw.policies, {
      totalCount: 0,
      enabledCount: 0,
      candidateCount: 0
    }, 'ALL_TIME'),
    coverage: normalizeCoverage(raw.coverage)
  };
}


export function snapshotFreshness(generatedAt, staleAfterMs, now = Date.now()) {
  if (!generatedAt) return 'EMPTY';
  const generatedMs = Date.parse(generatedAt);
  if (!Number.isFinite(generatedMs)) return 'EMPTY';
  return now - generatedMs > staleAfterMs ? 'STALE' : 'FRESH';
}


function normalizeTask(value) {
  const raw = isRecord(value) ? value : {};
  return {
    taskId: safeCount(raw.taskId),
    projectId: safeCount(raw.projectId),
    projectName: safeText(raw.projectName, `Project ${safeCount(raw.projectId)}`),
    groupId: safeNullableCount(raw.groupId),
    triggerType: safeEnum(raw.triggerType),
    authorName: safeNullableText(raw.authorName),
    authorUsername: safeNullableText(raw.authorUsername),
    externalUrl: safeNullableText(raw.externalUrl),
    repositoryUrl: safeNullableText(raw.repositoryUrl),
    sourceBranch: safeNullableText(raw.sourceBranch),
    targetBranch: safeNullableText(raw.targetBranch),
    commitSha: safeNullableText(raw.commitSha),
    technicalStatus: safeEnum(raw.technicalStatus),
    reviewStatus: safeEnum(raw.reviewStatus),
    riskLevel: safeNullableEnum(raw.riskLevel),
    ruleRiskItemCount: safeCount(raw.ruleRiskItemCount),
    flowCount: safeCount(raw.flowCount),
    stage: safeEnum(raw.stage),
    stageSource: safeEnum(raw.stageSource),
    createdAt: safeIso(raw.createdAt),
    updatedAt: safeIso(raw.updatedAt)
  };
}


function normalizeTodayResults(value) {
  if (!isRecord(value)) return null;
  return {
    status: safeEnum(value.status, 'LIVE'),
    scope: safeEnum(value.scope, 'TODAY'),
    date: safeNullableText(value.date),
    timezone: safeText(value.timezone, 'UTC+08:00'),
    from: safeIso(value.from),
    to: safeIso(value.to),
    totalCount: safeCount(value.totalCount),
    completedCount: safeCount(value.completedCount),
    successCount: safeCount(value.successCount),
    failureCount: safeCount(value.failureCount),
    skippedCount: safeCount(value.skippedCount),
    runningCount: safeCount(value.runningCount),
    otherCount: safeCount(value.otherCount),
    statusCounts: safeCounts(value.statusCounts)
  };
}


function normalizeFlow(value) {
  const raw = isRecord(value) ? value : {};
  const taskId = safeCount(raw.taskId);
  const reviewKey = safeText(raw.reviewKey, 'default');
  const stableId = `${taskId}:${reviewKey}`;
  const status = safeEnum(raw.status);
  const stage = safeEnum(raw.stage);
  const statusRecognized = KNOWN_FLOW_STATUSES.has(status);
  const stageRecognized = KNOWN_FLOW_STAGES.has(stage);
  return {
    id: raw.id === stableId ? stableId : stableId,
    taskId,
    reviewKey,
    displayName: safeText(raw.displayName, reviewKey),
    jobType: safeNullableEnum(raw.jobType),
    requestedEngine: safeEnum(raw.requestedEngine, 'STANDARD'),
    effectiveEngine: safeEnum(raw.effectiveEngine, 'STANDARD'),
    fallback: Boolean(raw.fallback),
    status: statusRecognized ? status : 'RUNNING',
    statusRecognized,
    stage: stageRecognized ? stage : 'UNKNOWN',
    stageRecognized,
    stageSource: safeEnum(raw.stageSource, 'INFERRED'),
    providerCode: safeNullableText(raw.providerCode),
    model: safeNullableText(raw.model),
    findingCount: safeCount(raw.findingCount),
    highestRisk: safeNullableEnum(raw.highestRisk),
    contextStatusCounts: safeCounts(raw.contextStatusCounts),
    queuedAt: safeIso(raw.queuedAt),
    startedAt: safeIso(raw.startedAt),
    updatedAt: safeIso(raw.updatedAt),
    durationSeconds: safeNullableCount(raw.durationSeconds)
  };
}


function normalizeEngine(value) {
  const raw = isRecord(value) ? value : {};
  return {
    activeFlowCount: safeCount(raw.activeFlowCount),
    findingCount: safeCount(raw.findingCount),
    statusCounts: safeCounts(raw.statusCounts)
  };
}


function normalizeWorkerPool(value) {
  const raw = isRecord(value) ? value : {};
  return {
    enabled: Boolean(raw.enabled),
    onlineCount: safeCount(raw.onlineCount),
    offlineCount: safeCount(raw.offlineCount),
    idleCount: safeCount(raw.idleCount),
    busyCount: safeCount(raw.busyCount),
    drainingCount: safeCount(raw.drainingCount),
    workers: safeArray(raw.workers)
      .slice(0, COMMAND_CENTER_LIMITS.workers)
      .map(worker => ({
        workerId: safeText(worker?.workerId, 'unknown-worker'),
        state: ['IDLE', 'BUSY', 'DRAINING'].includes(safeEnum(worker?.state))
          ? safeEnum(worker?.state)
          : 'IDLE',
        online: Boolean(worker?.online),
        capacity: safePositiveCount(worker?.capacity, 1),
        activeJobId: safeNullableCount(worker?.activeJobId),
        activeRunId: safeNullableCount(worker?.activeRunId),
        lastHeartbeatAt: safeIso(worker?.lastHeartbeatAt),
        source: safeEnum(worker?.source, 'REGISTERED')
      }))
  };
}


function normalizeQueueMetrics(value) {
  const raw = isRecord(value) ? value : {};
  return {
    queued: safeCount(raw.queued),
    running: safeCount(raw.running),
    expiredLease: safeCount(raw.expiredLease),
    oldestQueuedSeconds: safeNullableCount(raw.oldestQueuedSeconds),
    onlineCapacity: safeCount(raw.onlineCapacity),
    busyCapacity: safeCount(raw.busyCapacity),
    utilizationPercent: Math.min(safeCount(raw.utilizationPercent), 100),
    drainingWorkers: safeCount(raw.drainingWorkers)
  };
}


function normalizeProvider(value) {
  const raw = isRecord(value) ? value : {};
  const status = safeEnum(raw.status, 'NO_RECENT_DATA');
  return {
    providerCode: safeText(raw.providerCode, 'UNKNOWN'),
    providerName: safeText(raw.providerName, safeText(raw.providerCode, 'Unknown Provider')),
    providerType: safeText(raw.providerType, 'UNKNOWN'),
    modelName: safeNullableText(raw.modelName),
    enabled: Boolean(raw.enabled),
    defaultProvider: Boolean(raw.defaultProvider),
    status: KNOWN_PROVIDER_STATUSES.has(status) ? status : 'NO_RECENT_DATA',
    activeFlowCount: safeCount(raw.activeFlowCount),
    recentSuccessCount: safeCount(raw.recentSuccessCount),
    recentFailureCount: safeCount(raw.recentFailureCount),
    lastObservedAt: safeIso(raw.lastObservedAt)
  };
}


function normalizeAlert(value) {
  const raw = isRecord(value) ? value : {};
  return {
    id: safeText(raw.id, `UNKNOWN:${safeCount(raw.taskId)}`),
    type: safeEnum(raw.type),
    status: safeEnum(raw.status),
    taskId: safeNullableCount(raw.taskId),
    reviewKey: safeNullableText(raw.reviewKey),
    projectId: safeNullableCount(raw.projectId),
    projectName: safeNullableText(raw.projectName),
    occurredAt: safeIso(raw.occurredAt),
    navigationTarget: safeInternalPath(raw.navigationTarget)
  };
}


function normalizeWindowMetric(value, defaults, defaultScope = 'WINDOW') {
  const raw = isRecord(value) ? value : {};
  const result = {
    status: safeEnum(raw.status, 'LIVE'),
    scope: safeEnum(raw.scope, defaultScope)
  };
  for (const [key, fallback] of Object.entries(defaults)) {
    if (key.endsWith('Counts') || key.endsWith('Distribution')) {
      result[key] = safeCounts(raw[key]);
    } else if (typeof fallback === 'number') {
      result[key] = safeCount(raw[key]);
    } else {
      result[key] = raw[key] ?? fallback;
    }
  }
  return result;
}


function normalizeCoverage(value) {
  const raw = isRecord(value) ? value : {};
  return {
    phase: safeEnum(raw.phase, 'PHASE_1'),
    truncated: Boolean(raw.truncated),
    sections: safeRecord(raw.sections),
    limits: safeCounts(raw.limits),
    filters: safeRecord(raw.filters),
    scanned: safeCounts(raw.scanned)
  };
}


function normalizeWindow(value) {
  const raw = isRecord(value) ? value : {};
  return {
    from: safeIso(raw.from),
    to: safeIso(raw.to),
    hours: safeCount(raw.hours)
  };
}


function safeCounts(value) {
  const raw = safeRecord(value);
  return Object.fromEntries(
    Object.entries(raw).map(([key, count]) => [key, safeCount(count)])
  );
}


function safeRecord(value) {
  return isRecord(value) ? { ...value } : {};
}


function safeArray(value) {
  return Array.isArray(value) ? value : [];
}


function safeCount(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? Math.trunc(number) : 0;
}


function safePositiveCount(value, fallback) {
  const count = safeCount(value);
  return count > 0 ? count : fallback;
}


function safeNullableCount(value) {
  if (value === null || value === undefined || value === '') return null;
  return safeCount(value);
}


function safeText(value, fallback) {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}


function safeNullableText(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}


function safeEnum(value, fallback = 'UNKNOWN') {
  return safeText(value, fallback).toUpperCase();
}


function safeNullableEnum(value) {
  const text = safeNullableText(value);
  return text ? text.toUpperCase() : null;
}


function safeIso(value) {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Date(time).toISOString() : null;
}


function safeInternalPath(value) {
  const path = safeNullableText(value);
  return path?.startsWith('/') && !path.startsWith('//') ? path : null;
}


function isRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}
