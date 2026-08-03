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
  const standard = presentLane(safeRuntime?.reviewLanes?.standard, 'standard');
  const agent = presentLane(safeRuntime?.reviewLanes?.agent, 'agent');
  const totalRunning = standard.runningCount + agent.runningCount;
  const totalQueued = standard.queuedCount + agent.queuedCount;
  const totalCapacity = standard.capacity + agent.capacity;

  return {
    hud: {
      totalRunning,
      totalQueued,
      totalCapacity,
      utilizationPercent: totalCapacity > 0
        ? Math.min(100, Math.round(totalRunning / totalCapacity * 100))
        : 0,
      freshness: safeRuntime?.freshness || 'EMPTY',
      generatedAt: safeRuntime?.generatedAt || null
    },
    map: {
      zoneKey: 'platform-runtime-map',
      queue: {
        zoneKey: 'shared-queue',
        queuedCount: totalQueued,
        standardQueuedCount: standard.queuedCount,
        agentQueuedCount: agent.queuedCount
      },
      lanes: [standard, agent],
      scene: {
        id: 'platform-runtime-map',
        snapshotKey: safeRuntime?.generatedAt || 'EMPTY',
        freshness: safeRuntime?.freshness || 'EMPTY',
        lanes: [
          sceneLane(standard),
          sceneLane(agent)
        ]
      }
    }
  };
}


function presentLane(value, zoneKey) {
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
    runningItemsTruncated: Boolean(lane.runningItemsTruncated)
  };
}


function presentItem(item) {
  return {
    ...item,
    providerModelLabel: [item.provider, item.model].filter(Boolean).join(' · ') || 'Provider 待分配',
    stageLabel: stageLabel(item.stage),
    engineToken: item.fallback ? 'fallback' : item.requestedEngine === 'AGENT' ? 'agent' : 'standard'
  };
}


function sceneLane(lane) {
  return {
    zoneKey: lane.zoneKey,
    capacity: lane.capacity,
    runningCount: lane.runningCount,
    queuedCount: lane.queuedCount,
    utilizationPercent: lane.utilizationPercent
  };
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
