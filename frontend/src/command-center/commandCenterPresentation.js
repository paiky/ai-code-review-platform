const INTAKE_ITEMS = Object.freeze([
  Object.freeze({ key: 'MANUAL', label: 'Manual Review', description: '手动发起 Review' }),
  Object.freeze({ key: 'MERGE_REQUEST', label: 'Merge Request', description: 'GitLab MR 自动或手动触发' }),
  Object.freeze({ key: 'PUSH', label: 'Push', description: '通过 Push 审核策略门禁触发' }),
  Object.freeze({ key: 'RETRY', label: 'Retry', description: '从既有 Review 任务重新发起' })
]);

const ENGINE_ROUTES = Object.freeze([
  Object.freeze({ key: 'AGENT', target: 'agent-review', label: 'AGENT → Agent Review' }),
  Object.freeze({ key: 'STANDARD', target: 'standard-review', label: 'STANDARD → Standard Review' })
]);

const LANE_META = Object.freeze({
  standard: {
    title: 'Standard Review',
    eyebrow: 'STANDARD REVIEW',
    description: 'Provider Scheduler 调度的标准代码质量 Review',
    colorToken: 'standard'
  },
  agent: {
    title: 'Agent Review',
    eyebrow: 'AGENT REVIEW',
    description: '由在线 Agent Worker 执行的证据驱动 Review',
    colorToken: 'agent'
  }
});

const UNAVAILABLE_DESCRIPTION = '自动触发选择 Agent 但 Agent 不可用时，可按策略直接进入 Standard Review。';


export function buildCommandCenterPresentation({ runtime, runtimeError = '' } = {}) {
  const safeRuntime = runtime || null;
  const providersObserved = presentProviders(safeRuntime?.providersObserved);
  const alerts = Array.isArray(safeRuntime?.alerts) ? safeRuntime.alerts : [];
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
  const freshness = safeRuntime?.freshness || 'EMPTY';
  const generatedAt = safeRuntime?.generatedAt || null;
  const coverage = presentCoverage(safeRuntime?.coverage, {
    freshness,
    diagnostics
  });
  const resourceState = runtimeError
    ? safeRuntime ? 'ERROR_RETAINED' : 'ERROR_EMPTY'
    : freshness;

  return {
    hud: {
      freshness,
      resourceState,
      generatedAt,
      totalQueuedJobs: schedulerQueued,
      totalRunningJobs: schedulerRunning,
      coverage,
      providersObserved,
      alerts,
      error: text(runtimeError) || null
    },
    intake: {
      zoneKey: 'review-intake',
      title: 'Review Intake',
      items: INTAKE_ITEMS.map(item => ({ ...item }))
    },
    engineSelection: {
      zoneKey: 'engine-selection',
      title: 'Engine Selection',
      routes: ENGINE_ROUTES.map(route => ({ ...route })),
      automaticAgentUnavailableDescription: UNAVAILABLE_DESCRIPTION
    },
    agentLane,
    standardLane,
    fallback: {
      zoneKey: 'agent-standard-fallback',
      mode: 'STRUCTURAL_ONLY',
      from: 'agent-review',
      to: 'standard-review',
      description: 'Agent 运行失败、超时或租约耗尽时可能创建新的 Standard Job；当前不表达任务级父子转移。'
    },
    resultPersistence: {
      zoneKey: 'result-persistence',
      mode: 'STRUCTURAL_ONLY',
      title: 'Result Persistence',
      description: '结果落库后进入 Review 任务详情与既有通知链路',
      navigationTarget: '/tasks'
    },
    footer: {
      agentCapacity: {
        running: agentLane.running,
        onlineCapacity: agentLane.onlineCapacity
      },
      standardSlots: {
        running: standardLane.running,
        capacity: standardLane.capacity
      },
      oldestAgentQueueSeconds: nullableNumber(
        safeRuntime?.agent?.queueMetrics?.oldestQueuedSeconds
      ),
      alerts: {
        count: alerts.length,
        items: alerts
      }
    },
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
      title: 'Result Persistence',
      description: '结果落库后进入 Review 任务详情与既有通知链路'
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
    PREFLIGHT: 'Preflight',
    QUEUED: '排队中',
    CONTEXT_BUILDING: '构建上下文',
    MODEL_CALLING: '模型调用',
    AGENT_ANALYZING: 'Agent 分析',
    AGENT_TOOL_ACTIVITY: 'Agent 工具活动',
    AGENT_CONVERGING: 'Agent 收敛',
    AGENT_SUBMITTING: 'Agent 提交',
    FALLBACK: 'Standard Fallback'
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


function text(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : '';
}


function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}
