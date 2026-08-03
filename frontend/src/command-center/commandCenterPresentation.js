const LANE_META = Object.freeze({
  standard: {
    title: 'Standard Review 工坊',
    eyebrow: 'STANDARD REVIEW',
    description: '普通 Review 通过共享 Provider 容量执行',
    colorToken: 'standard'
  },
  agent: {
    title: 'Agent Review 基地',
    eyebrow: 'AGENT REVIEW',
    description: 'Agent Review 由在线 Worker 塔接管',
    colorToken: 'agent'
  }
});


export function buildCommandCenterPresentation({ runtime } = {}) {
  const safeRuntime = runtime || null;
  const workers = presentSceneWorkers(safeRuntime?.agent?.workerPool?.workers);
  const standard = presentLane(safeRuntime?.reviewLanes?.standard, 'standard');
  const agent = presentLane(safeRuntime?.reviewLanes?.agent, 'agent', workers);
  const totalRunning = standard.runningCount + agent.runningCount;
  const totalQueued = standard.queuedCount + agent.queuedCount;
  const totalCapacity = standard.capacity + agent.capacity;
  const freshness = safeRuntime?.freshness || 'EMPTY';
  const generatedAt = safeRuntime?.generatedAt || null;

  return {
    hud: {
      totalRunning,
      totalQueued,
      totalCapacity,
      utilizationPercent: totalCapacity > 0
        ? Math.min(100, Math.round(totalRunning / totalCapacity * 100))
        : 0,
      freshness,
      generatedAt
    },
    map: {
      zoneKey: 'ai-review-operation-map',
      queueGate: {
        zoneKey: 'queue-gate',
        queuedCount: totalQueued,
        standardQueuedCount: standard.queuedCount,
        agentQueuedCount: agent.queuedCount,
        nextQueued: {
          standard: standard.nextQueued,
          agent: agent.nextQueued
        }
      },
      core: {
        zoneKey: 'ai-review-core',
        runningCount: totalRunning,
        capacity: totalCapacity,
        utilizationPercent: totalCapacity > 0
          ? Math.min(100, Math.round(totalRunning / totalCapacity * 100))
          : 0,
        freshness,
        generatedAt
      },
      lanes: [standard, agent],
      resultBeacon: {
        zoneKey: 'result-beacon',
        mode: 'STRUCTURAL_ONLY',
        title: 'Result Beacon',
        description: '结果回流至任务详情与既有通知链路'
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
        snapshotKey: safeRuntime?.generatedAt || 'EMPTY',
        freshness,
        runningCount: totalRunning,
        queuedCount: totalQueued,
        capacity: totalCapacity,
        utilizationPercent: totalCapacity > 0
          ? Math.min(100, Math.round(totalRunning / totalCapacity * 100))
          : 0,
        lanes: [standard, agent].map(presentMotionLane),
        connections: [
          { from: 'queue-gate', to: 'ai-review-core', token: 'queue' },
          { from: 'ai-review-core', to: 'standard', token: 'standard' },
          { from: 'ai-review-core', to: 'agent', token: 'agent' },
          { from: 'standard', to: 'result-beacon', token: 'standard' },
          { from: 'agent', to: 'result-beacon', token: 'agent' }
        ]
      }
    }
  };
}


function presentLane(value, zoneKey, workers = []) {
  const lane = value || {};
  const meta = LANE_META[zoneKey];
  return {
    ...lane,
    ...meta,
    zoneKey,
    engine: zoneKey === 'agent' ? 'AGENT' : 'STANDARD',
    capacity: number(lane.capacity),
    runningCount: number(lane.runningCount),
    queuedCount: number(lane.queuedCount),
    utilizationPercent: number(lane.utilizationPercent),
    runningItems: (lane.runningItems || []).map(presentItem),
    nextQueued: lane.nextQueued ? presentItem(lane.nextQueued) : null,
    runningItemsTruncated: Boolean(lane.runningItemsTruncated),
    workers: zoneKey === 'agent' ? workers : []
  };
}


function presentItem(item) {
  return {
    ...item,
    motionIdentity: reviewMotionIdentity(item),
    providerModelLabel: [item.provider, item.model].filter(Boolean).join(' · ') || 'Provider 待分配',
    stageLabel: stageLabel(item.stage),
    engineToken: item.fallback ? 'fallback' : item.requestedEngine === 'AGENT' ? 'agent' : 'standard'
  };
}


function presentMotionLane(lane) {
  return {
    zoneKey: lane.zoneKey,
    capacity: lane.capacity,
    runningCount: lane.runningCount,
    queuedCount: lane.queuedCount,
    utilizationPercent: lane.utilizationPercent,
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


function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}
