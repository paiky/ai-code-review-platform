import { presentSnapshotResource } from './commandCenterResourceState.js';


const ENGINE_ROUTES = Object.freeze([
  Object.freeze({ key: 'AGENT', target: 'agent-review', label: 'Agent → Agent Review', token: 'agent' }),
  Object.freeze({ key: 'STANDARD', target: 'standard-review', label: 'Standard → Standard Review', token: 'standard' }),
  Object.freeze({ key: 'AGENT_STANDARD', target: 'agent-standard-fallback', label: 'Agent Review → Standard Review', token: 'fallback' })
]);

const LANE_META = Object.freeze({
  standard: {
    title: 'Standard Review',
    eyebrow: 'Standard Review',
    description: '由 Provider 调度器执行的标准代码质量审查',
    colorToken: 'standard'
  },
  agent: {
    title: 'Agent Review',
    eyebrow: 'Agent Review',
    description: '由在线 Agent 执行器完成的证据驱动审查',
    colorToken: 'agent'
  }
});

export function buildCommandCenterPresentation({
  runtime,
  runtimeLoading = false,
  runtimeError = '',
  governance,
  governanceLoading = false,
  governanceError = ''
} = {}) {
  const resources = {
    runtime: presentSnapshotResource({
      data: runtime,
      loading: runtimeLoading,
      error: runtimeError
    }),
    governance: presentSnapshotResource({
      data: governance,
      loading: governanceLoading,
      error: governanceError
    })
  };
  const freshness = resources.runtime.freshness;
  const safeRuntime = resources.runtime.available ? runtime : null;
  const safeGovernance = resources.governance.available ? governance : null;
  const providersObserved = presentProviders(safeRuntime?.providersObserved);
  const workers = presentSceneWorkers(safeRuntime?.agent?.workerPool?.workers);
  const standardLane = presentLane(safeRuntime?.reviewLanes?.standard, 'standard', {
    providers: providersObserved
  });
  const agentLane = presentLane(safeRuntime?.reviewLanes?.agent, 'agent', {
    onlineCapacity: safeRuntime?.agent?.queueMetrics?.onlineCapacity,
    workers,
    workerSummary: presentWorkerSummary(safeRuntime?.agent?.workerPool)
  });
  const schedulerQueued = number(safeRuntime?.scheduler?.queuedJobCount);
  const schedulerRunning = number(safeRuntime?.scheduler?.runningJobCount);
  const laneQueued = standardLane.queued + agentLane.queued;
  const laneRunning = standardLane.running + agentLane.running;
  const diagnostics = buildDiagnostics({
    schedulerQueued,
    schedulerRunning,
    laneQueued,
    laneRunning
  });
  const generatedAt = safeRuntime?.generatedAt || null;
  const coverage = presentCoverage(safeRuntime?.coverage, {
    freshness,
    diagnostics
  });
  const resourceState = resources.runtime.state;
  const taskQueue = presentTaskQueue(safeRuntime, resources.runtime);
  const todayResults = presentTodayResults(safeRuntime, resources.runtime);

  return {
    resources,
    currentStatus: presentCurrentStatus(safeRuntime, providersObserved, resources.runtime),
    qualityOutput: presentQualityOutput({
      runtime: safeRuntime,
      governance: safeGovernance,
      resources
    }),
    hud: {
      freshness,
      resourceState,
      generatedAt,
      totalQueuedJobs: schedulerQueued,
      totalRunningJobs: schedulerRunning,
      coverage,
      providersObserved,
      error: text(runtimeError) || null
    },
    taskQueue,
    engineSelection: {
      zoneKey: 'engine-selection',
      title: '引擎选择',
      routes: ENGINE_ROUTES.map(route => ({ ...route }))
    },
    agentLane,
    standardLane,
    fallback: {
      zoneKey: 'agent-standard-fallback',
      mode: 'STRUCTURAL_ONLY',
      from: 'agent-review',
      to: 'standard-review',
      description: 'Agent 运行失败、超时或租约耗尽时可能创建新的 Standard 任务；当前不表达任务级父子转移。'
    },
    todayResults,
    diagnostics,
    // H1 does not change JSX/Canvas. This adapter keeps the existing renderer safe
    // until H2 switches the DOM to the frozen homepage contract above.
    map: buildH1CompatibilityMap({
      agentLane,
      standardLane,
      freshness,
      generatedAt
    })
  };
}


function presentTaskQueue(runtime, resource) {
  const tasks = resource.available && Array.isArray(runtime?.activeTasks)
    ? runtime.activeTasks
    : [];
  const activeCount = resource.available
    ? number(runtime?.intake?.activeTaskCount)
    : null;
  const items = tasks.slice(0, 3).map(task => {
    const taskId = Math.trunc(Number(task?.taskId));
    const sourceBranch = text(task?.sourceBranch);
    const targetBranch = text(task?.targetBranch);
    const commitSha = text(task?.commitSha);
    return {
      taskId: Number.isFinite(taskId) && taskId > 0 ? taskId : null,
      projectName: text(task?.projectName) || '未知项目',
      authorLabel: taskAuthorLabel(task),
      triggerLabel: taskTriggerLabel(task?.triggerType),
      branchCommitLabel: sourceBranch && targetBranch
        ? `${sourceBranch} → ${targetBranch}`
        : sourceBranch || (commitSha ? `Commit ${commitSha.slice(0, 8)}` : '未记录分支或 Commit'),
      stage: text(task?.stage) || 'UNKNOWN',
      stageLabel: stageLabel(task?.stage),
      updatedAt: task?.updatedAt || null,
      navigationTarget: Number.isFinite(taskId) && taskId > 0 ? `/tasks/${taskId}` : null,
      externalUrl: safeExternalReviewUrl(task?.externalUrl)
        || safeExternalReviewUrl(task?.repositoryUrl)
    };
  });
  return {
    zoneKey: 'review-task-queue',
    eyebrow: '实时任务',
    title: '任务队列',
    subtitle: '最近活动 · 非跨引擎执行顺序',
    resourceState: resource.state,
    available: resource.available,
    visibleCount: items.length,
    activeCount,
    overflowCount: activeCount === null ? 0 : Math.max(activeCount - items.length, 0),
    items
  };
}


function presentTodayResults(runtime, resource) {
  const value = resource.available ? runtime?.todayResults : null;
  const available = Boolean(value);
  return {
    zoneKey: 'today-review-results',
    eyebrow: '北京时间自然日',
    title: '今日 Review 结果',
    subtitle: '00:00—当前',
    resourceState: resource.state,
    available,
    date: available ? value.date || null : null,
    timezone: available ? value.timezone || 'UTC+08:00' : null,
    totalCount: available ? number(value.totalCount) : null,
    completedCount: available ? number(value.completedCount) : null,
    successCount: available ? number(value.successCount) : null,
    failureCount: available ? number(value.failureCount) : null,
    skippedCount: available ? number(value.skippedCount) : null,
    runningCount: available ? number(value.runningCount) : null,
    otherCount: available ? number(value.otherCount) : null,
    navigationTarget: '/tasks'
  };
}


function taskAuthorLabel(task) {
  const name = text(task?.authorName);
  if (name) return name;
  const username = text(task?.authorUsername);
  return username ? `@${username.replace(/^@+/, '')}` : '未记录作者';
}


function taskTriggerLabel(value) {
  return {
    MANUAL: '手动审查',
    MANUAL_REVIEW: '手动审查',
    MERGE_REQUEST: 'Merge Request',
    GITLAB_MR: 'Merge Request',
    GITLAB_MR_WEBHOOK: 'Merge Request',
    PUSH: 'Push',
    GITLAB_PUSH: 'Push',
    GITLAB_PUSH_WEBHOOK: 'Push',
    RETRY: '重试'
  }[String(value || '').trim().toUpperCase()] || '其他触发';
}


export function safeExternalReviewUrl(value) {
  const candidate = text(value);
  if (!candidate) return null;
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
      ? parsed.href
      : null;
  } catch {
    return null;
  }
}


function presentCurrentStatus(runtime, providersObserved, resource) {
  const available = resource.available;
  return {
    resourceState: resource.state,
    available,
    generatedAt: available ? runtime.generatedAt || null : null,
    queuedExecutionCount: available ? number(runtime.scheduler?.queuedJobCount) : null,
    runningExecutionCount: available ? number(runtime.scheduler?.runningJobCount) : null,
    activeReviewTaskCount: available ? number(runtime.intake?.activeTaskCount) : null,
    oldestAgentQueueSeconds: available
      ? nullableNumber(runtime.agent?.queueMetrics?.oldestQueuedSeconds)
      : null,
    provider: available
      ? selectCurrentProvider(runtime.providersObserved, providersObserved)
      : null
  };
}


function presentQualityOutput({ runtime, governance, resources }) {
  const runtimeAvailable = resources.runtime.available;
  const governanceAvailable = resources.governance.available;
  const runtimeHours = positiveNumber(runtime?.window?.hours);
  const governanceHours = positiveNumber(governance?.window?.hours);
  const windowHours = runtimeHours || governanceHours || 24;
  const providerExecution = presentProviderExecution(
    runtimeAvailable ? runtime?.providersObserved : null,
    resources.runtime.state
  );
  const findingRisk = governanceAvailable ? governance.findingRisk || {} : {};

  return {
    window: {
      hours: windowHours,
      label: `近 ${windowHours} 小时`,
      runtimeHours,
      governanceHours,
      aligned: !runtimeHours || !governanceHours || runtimeHours === governanceHours
    },
    reviewTasks: {
      source: 'runtime',
      resourceState: resources.runtime.state,
      available: runtimeAvailable,
      count: runtimeAvailable ? number(runtime.intake?.taskCount) : null
    },
    providerExecution,
    findingRisk: {
      source: 'governance',
      resourceState: resources.governance.state,
      available: governanceAvailable,
      findingCount: governanceAvailable ? number(findingRisk.findingCount) : null,
      affectedTaskCount: governanceAvailable ? number(findingRisk.affectedTaskCount) : null,
      highestRisk: governanceAvailable ? findingRisk.highestRisk || null : null,
      severityCounts: governanceAvailable ? { ...(findingRisk.severityCounts || {}) } : null
    }
  };
}


function presentProviderExecution(value, resourceState) {
  if (!Array.isArray(value)) {
    return {
      source: 'runtime',
      resourceState,
      available: false,
      successCount: null,
      failureCount: null,
      totalCount: null,
      successRate: null,
      hasRecords: false
    };
  }
  const successCount = value.reduce(
    (total, provider) => total + number(provider?.recentSuccessCount),
    0
  );
  const failureCount = value.reduce(
    (total, provider) => total + number(provider?.recentFailureCount),
    0
  );
  const totalCount = successCount + failureCount;
  return {
    source: 'runtime',
    resourceState,
    available: true,
    successCount,
    failureCount,
    totalCount,
    successRate: totalCount > 0
      ? Math.round(successCount / totalCount * 1_000) / 10
      : null,
    hasRecords: totalCount > 0
  };
}


function presentLane(value, zoneKey, options = {}) {
  const lane = value || {};
  const meta = LANE_META[zoneKey];
  const runningItems = (Array.isArray(lane.runningItems) ? lane.runningItems : [])
    .map(presentItem);
  const running = number(lane.runningCount);
  const queued = number(lane.queuedCount);
  const capacity = zoneKey === 'agent'
    ? number(options.onlineCapacity)
    : number(lane.capacity);
  const visibleRunningItemCount = runningItems.length;
  const totalRunningItemCount = running;

  return {
    ...meta,
    zoneKey: `${zoneKey}-review`,
    colorToken: zoneKey,
    engine: zoneKey === 'agent' ? 'AGENT' : 'STANDARD',
    queued,
    running,
    capacity,
    onlineCapacity: zoneKey === 'agent' ? capacity : null,
    workerSummary: zoneKey === 'agent' ? options.workerSummary : null,
    providers: zoneKey === 'standard' ? options.providers || [] : [],
    nextQueued: lane.nextQueued ? presentItem(lane.nextQueued) : null,
    runningItems,
    visibleRunningItemCount,
    totalRunningItemCount,
    runningItemsTruncated: Boolean(lane.runningItemsTruncated)
      || visibleRunningItemCount < totalRunningItemCount,
    queueOrder: lane.queueOrder || null,
    workers: zoneKey === 'agent' ? options.workers || [] : []
  };
}


function presentWorkerSummary(value) {
  const pool = value || {};
  const workers = Array.isArray(pool.workers) ? pool.workers : [];
  return {
    idle: countOrDerived(pool, 'idleCount', workers, worker => worker?.online && worker?.state === 'IDLE'),
    busy: countOrDerived(pool, 'busyCount', workers, worker => worker?.online && worker?.state === 'BUSY'),
    draining: countOrDerived(
      pool,
      'drainingCount',
      workers,
      worker => worker?.online && worker?.state === 'DRAINING'
    ),
    offline: countOrDerived(pool, 'offlineCount', workers, worker => !worker?.online)
  };
}


function presentProviders(value) {
  return (Array.isArray(value) ? value : []).map(provider => ({
    providerCode: provider.providerCode,
    providerName: provider.providerName,
    modelName: provider.modelName || null,
    status: provider.status,
    activeFlowCount: number(provider.activeFlowCount),
    label: [provider.providerName || provider.providerCode, provider.modelName]
      .filter(Boolean)
      .join(' / ')
  }));
}


function selectCurrentProvider(rawProviders, presentedProviders) {
  const source = Array.isArray(rawProviders) ? rawProviders : [];
  if (!source.length) return null;

  const ranked = source.map((provider, index) => ({
    index,
    rank: providerRank(provider),
    observedAt: observedAtTimestamp(provider.lastObservedAt)
  }));
  ranked.sort((left, right) => {
    const rankDifference = left.rank - right.rank;
    if (rankDifference) return rankDifference;
    if (left.rank === 1) {
      const observedDifference = right.observedAt - left.observedAt;
      if (observedDifference) return observedDifference;
    }
    return left.index - right.index;
  });
  return presentedProviders[ranked[0].index] || null;
}


function providerRank(provider) {
  if (number(provider?.activeFlowCount) > 0) return 0;
  if (observedAtTimestamp(provider?.lastObservedAt) !== null) return 1;
  if (provider?.defaultProvider && provider?.enabled !== false) return 2;
  if (provider?.enabled !== false) return 3;
  return 4;
}


function observedAtTimestamp(value) {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : null;
}


function presentCoverage(value, { freshness, diagnostics }) {
  const coverage = value || {};
  return {
    status: freshness === 'EMPTY'
      ? 'EMPTY'
      : coverage.truncated ? 'PARTIAL' : 'COMPLETE',
    truncated: Boolean(coverage.truncated),
    bounded: true,
    sections: coverage.sections || {},
    diagnostics
  };
}


function buildDiagnostics({ schedulerQueued, schedulerRunning, laneQueued, laneRunning }) {
  const diagnostics = [];
  if (schedulerQueued !== laneQueued) {
    diagnostics.push({
      code: 'SCHEDULER_LANE_QUEUED_MISMATCH',
      schedulerValue: schedulerQueued,
      laneValue: laneQueued
    });
  }
  if (schedulerRunning !== laneRunning) {
    diagnostics.push({
      code: 'SCHEDULER_LANE_RUNNING_MISMATCH',
      schedulerValue: schedulerRunning,
      laneValue: laneRunning
    });
  }
  return diagnostics;
}


function buildH1CompatibilityMap({ agentLane, standardLane, freshness, generatedAt }) {
  const lanes = [standardLane, agentLane].map(presentCompatibilityLane);
  const runningCount = lanes.reduce((total, lane) => total + lane.running, 0);
  const queuedCount = lanes.reduce((total, lane) => total + lane.queued, 0);
  return {
    compatibilityMode: 'H1_LEGACY_RENDERER',
    zoneKey: 'ai-review-operation-map',
    queueGate: {
      zoneKey: 'queue-gate',
      queuedCount,
      standardQueuedCount: standardLane.queued,
      agentQueuedCount: agentLane.queued,
      nextQueued: {
        standard: standardLane.nextQueued,
        agent: agentLane.nextQueued
      }
    },
    core: {
      zoneKey: 'ai-review-core',
      runningCount,
      capacity: 0,
      utilizationPercent: 0,
      freshness,
      generatedAt
    },
    lanes,
    resultBeacon: {
      zoneKey: 'result-beacon',
      mode: 'STRUCTURAL_ONLY',
      title: '结果持久化',
      description: '结果落库后进入审查任务详情与既有通知链路'
    },
    connections: [
      { from: 'queue-gate', to: 'ai-review-core', token: 'queue' },
      { from: 'ai-review-core', to: 'standard', token: 'standard' },
      { from: 'ai-review-core', to: 'agent', token: 'agent' },
      { from: 'standard', to: 'result-beacon', token: 'standard' },
      { from: 'agent', to: 'result-beacon', token: 'agent' }
    ],
    scene: {
      id: 'ai-review-operation-map',
      snapshotKey: generatedAt || 'EMPTY',
      freshness,
      runningCount,
      queuedCount,
      capacity: 0,
      utilizationPercent: 0,
      lanes: lanes.map(presentMotionLane),
      connections: [
        { from: 'queue-gate', to: 'ai-review-core', token: 'queue' },
        { from: 'ai-review-core', to: 'standard', token: 'standard' },
        { from: 'ai-review-core', to: 'agent', token: 'agent' },
        { from: 'standard', to: 'result-beacon', token: 'standard' },
        { from: 'agent', to: 'result-beacon', token: 'agent' }
      ]
    }
  };
}


function presentCompatibilityLane(lane) {
  return {
    ...lane,
    zoneKey: lane.engine === 'AGENT' ? 'agent' : 'standard',
    queuedCount: lane.queued,
    runningCount: lane.running,
    utilizationPercent: lane.capacity > 0
      ? Math.min(100, Math.round(lane.running / lane.capacity * 100))
      : 0
  };
}


function presentItem(item) {
  return {
    ...item,
    motionIdentity: reviewMotionIdentity(item),
    navigationTarget: reviewTaskTarget(item),
    providerModelLabel: [item.provider, item.model].filter(Boolean).join(' · ') || 'Provider 待分配',
    stageLabel: stageLabel(item.stage),
    engineToken: item.fallback ? 'fallback' : item.requestedEngine === 'AGENT' ? 'agent' : 'standard'
  };
}


export function reviewTaskTarget(item) {
  const taskId = Math.trunc(Number(item?.taskId));
  if (!Number.isFinite(taskId) || taskId <= 0) return null;
  const reviewKey = typeof item?.reviewKey === 'string' && item.reviewKey.trim()
    ? item.reviewKey.trim()
    : 'default';
  return `/tasks/${taskId}?reviewKey=${encodeURIComponent(reviewKey)}`;
}


function presentMotionLane(lane) {
  return {
    zoneKey: lane.engine === 'AGENT' ? 'agent' : 'standard',
    capacity: lane.capacity,
    runningCount: lane.running,
    queuedCount: lane.queued,
    utilizationPercent: lane.capacity > 0
      ? Math.min(100, Math.round(lane.running / lane.capacity * 100))
      : 0,
    nextQueuedIdentity: lane.nextQueued?.motionIdentity || null,
    runningItems: lane.runningItems.map(item => ({
      identity: item.motionIdentity,
      stage: item.stage || 'RUNNING'
    })),
    workers: lane.workers.map(worker => ({
      identity: String(worker.workerId || ''),
      state: workerMotionState(worker)
    }))
  };
}


function reviewMotionIdentity(item) {
  return [item?.jobId, item?.taskId, item?.reviewKey]
    .map(value => String(value ?? ''))
    .join(':');
}


function workerMotionState(worker) {
  if (!worker?.online) return 'OFFLINE';
  return String(worker.state || 'IDLE').toUpperCase();
}


function presentSceneWorkers(value) {
  return (Array.isArray(value) ? value : []).map(worker => ({
    workerId: worker.workerId,
    state: worker.state,
    online: Boolean(worker.online),
    capacity: number(worker.capacity),
    activeJobId: worker.activeJobId
  }));
}


export function stageLabel(value) {
  return {
    PREFLIGHT: '预检',
    QUEUED: '排队中',
    CONTEXT_BUILDING: '构建上下文',
    MODEL_CALLING: '模型调用',
    AGENT_ANALYZING: 'Agent 分析',
    AGENT_TOOL_ACTIVITY: 'Agent 工具活动',
    AGENT_CONVERGING: 'Agent 收敛',
    AGENT_SUBMITTING: 'Agent 提交',
    FALLBACK: 'Standard 降级'
  }[String(value || '').toUpperCase()] || '执行中';
}


function countOrDerived(source, key, items, predicate) {
  return Object.hasOwn(source, key)
    ? number(source[key])
    : items.filter(predicate).length;
}


function nullableNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  return number(value);
}


function positiveNumber(value) {
  const parsed = number(value);
  return parsed > 0 ? parsed : null;
}


function text(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : '';
}


function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}
