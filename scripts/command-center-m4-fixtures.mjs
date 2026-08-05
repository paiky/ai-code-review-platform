export const COMMAND_CENTER_M4_SCENARIOS = Object.freeze([
  'idle',
  'agent-queued',
  'standard-queued',
  'agent-running',
  'standard-running',
  'dual-running',
  'fallback-running',
  'stale',
  'runtime-error',
  'governance-error'
]);


export function commandCenterRuntimeFixture(scenario = 'idle', now = Date.now()) {
  assertScenario(scenario);
  const activity = activityFor(scenario);
  const generatedAt = new Date(scenario === 'stale' ? now - 60_000 : now).toISOString();
  const from = new Date(now - 24 * 60 * 60 * 1_000).toISOString();
  const agentRunningItems = activity.agentRunning > 0
    ? [laneItem({ jobId: 201, taskId: 901, reviewKey: 'agent-live', engine: 'AGENT', workerId: 'agent-m4-a' })]
    : [];
  const standardRunningItems = activity.standardRunning > 0
    ? [laneItem({
        jobId: 301,
        taskId: 902,
        reviewKey: activity.fallback ? 'agent-fallback-live' : 'standard-live',
        engine: activity.fallback ? 'AGENT' : 'STANDARD',
        effectiveEngine: activity.fallback ? 'STANDARD_FALLBACK' : 'STANDARD',
        fallback: activity.fallback,
        stage: activity.fallback ? 'FALLBACK' : 'MODEL_CALLING',
        provider: 'OpenAI',
        model: 'gpt-5.5'
      })]
    : [];
  const agentNextQueued = activity.agentQueued > 0
    ? laneItem({
        jobId: 211,
        taskId: 903,
        reviewKey: 'agent-next',
        engine: 'AGENT',
        status: 'QUEUED',
        stage: 'AGENT_QUEUED',
        workerId: null,
        startedAt: null
      })
    : null;
  const standardNextQueued = activity.standardQueued > 0
    ? laneItem({
        jobId: 311,
        taskId: 904,
        reviewKey: 'standard-next',
        engine: 'STANDARD',
        status: 'QUEUED',
        stage: 'QUEUED',
        provider: null,
        model: null,
        startedAt: null
      })
    : null;
  const runningItems = [...agentRunningItems, ...standardRunningItems];
  const queuedCount = activity.agentQueued + activity.standardQueued;
  const runningCount = activity.agentRunning + activity.standardRunning;

  return {
    schemaVersion: 'command-center-runtime-v2',
    generatedAt,
    window: { from, to: new Date(now).toISOString(), hours: 24 },
    intake: { taskCount: 38, activeTaskCount: 4 },
    activeTasks: activeTasks(now),
    activeFlows: runningItems.map(item => ({
      id: `${item.taskId}:${item.reviewKey}`,
      taskId: item.taskId,
      reviewKey: item.reviewKey,
      displayName: item.displayName,
      requestedEngine: item.requestedEngine,
      effectiveEngine: item.effectiveEngine,
      fallback: item.fallback,
      status: 'RUNNING',
      stage: item.stage,
      stageSource: 'JOB',
      providerCode: item.provider,
      model: item.model,
      queuedAt: item.queuedAt,
      startedAt: item.startedAt,
      updatedAt: generatedAt,
      durationSeconds: 42
    })),
    reviewLanes: {
      standard: {
        zoneKey: 'standard',
        capacity: 10,
        runningCount: activity.standardRunning,
        queuedCount: activity.standardQueued,
        utilizationPercent: activity.standardRunning * 10,
        runningItems: standardRunningItems,
        nextQueued: standardNextQueued,
        runningItemsTruncated: false,
        queueOrder: 'PROVIDER_PRIORITY_FIFO'
      },
      agent: {
        zoneKey: 'agent',
        capacity: 2,
        runningCount: activity.agentRunning,
        queuedCount: activity.agentQueued,
        utilizationPercent: activity.agentRunning * 50,
        runningItems: agentRunningItems,
        nextQueued: agentNextQueued,
        runningItemsTruncated: false,
        queueOrder: 'AGENT_PRIORITY_FIFO'
      }
    },
    scheduler: {
      activeJobCount: queuedCount + runningCount,
      queuedJobCount: queuedCount,
      runningJobCount: runningCount
    },
    standard: {
      activeFlowCount: activity.standardRunning,
      findingCount: 5,
      statusCounts: { RUNNING: activity.standardRunning, SUCCESS: 17, FAILED: 1 }
    },
    agent: {
      activeFlowCount: activity.agentRunning,
      findingCount: 3,
      statusCounts: { RUNNING: activity.agentRunning, SUCCESS: 9, FAILED: 0 },
      workerPool: {
        enabled: true,
        onlineCount: 2,
        offlineCount: 1,
        idleCount: Math.max(0, 2 - activity.agentRunning),
        busyCount: activity.agentRunning,
        drainingCount: 0,
        workers: [
          worker('agent-m4-a', activity.agentRunning ? 'BUSY' : 'IDLE', true, generatedAt),
          worker('agent-m4-b', 'IDLE', true, generatedAt),
          worker('agent-m4-offline', 'IDLE', false, generatedAt)
        ]
      },
      queueMetrics: {
        queued: activity.agentQueued,
        running: activity.agentRunning,
        expiredLease: 0,
        oldestQueuedSeconds: activity.agentQueued ? 38 : null,
        onlineCapacity: 2,
        busyCapacity: activity.agentRunning,
        utilizationPercent: activity.agentRunning * 50,
        drainingWorkers: 0
      }
    },
    providersObserved: [
      provider('OPENAI', 'OpenAI', 'gpt-5.5', activity.standardRunning > 0, generatedAt),
      provider('DEEPSEEK', 'DeepSeek', 'deepseek-v4-pro', activity.agentRunning > 0, generatedAt)
    ],
    alerts: [],
    todayResults: {
      status: 'LIVE',
      scope: 'TODAY',
      date: new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date(now)),
      timezone: 'UTC+08:00',
      from,
      to: new Date(now).toISOString(),
      totalCount: 31,
      completedCount: 27,
      successCount: 24,
      failureCount: 2,
      skippedCount: 1,
      runningCount: 4,
      otherCount: 0,
      statusCounts: { SUCCESS: 24, FAILED: 2, SKIPPED: 1, RUNNING: 4 }
    },
    coverage: {
      phase: 'M4_ACCEPTANCE',
      truncated: false,
      sections: { activeTasks: 'COMPLETE', reviewLanes: 'COMPLETE', todayResults: 'COMPLETE' },
      limits: { activeTasks: 50, runningItems: 100 },
      filters: {},
      scanned: { activeTasks: 4 }
    }
  };
}


export function commandCenterGovernanceFixture(now = Date.now()) {
  const to = new Date(now).toISOString();
  const from = new Date(now - 24 * 60 * 60 * 1_000).toISOString();
  return {
    schemaVersion: 'command-center-governance-v1',
    generatedAt: to,
    window: { from, to, hours: 24 },
    ruleAnalysis: { status: 'LIVE', scope: 'WINDOW', resultCount: 30, riskItemCount: 11, riskDistribution: { CRITICAL: 2, HIGH: 9 } },
    preflight: { status: 'LIVE', scope: 'WINDOW', runCount: 30, findingCount: 4, statusCounts: { COMPLETED: 30 } },
    contextQuality: { status: 'LIVE', scope: 'WINDOW', findingCount: 27, statusCounts: { SUFFICIENT: 21, PARTIAL: 6 } },
    findingRisk: { status: 'LIVE', scope: 'WINDOW', findingCount: 27, affectedTaskCount: 11, highestRisk: 'CRITICAL', severityCounts: { CRITICAL: 6, HIGH: 5, MEDIUM: 7, LOW: 9 } },
    notifications: { status: 'LIVE', scope: 'WINDOW', recordCount: 18, statusCounts: { SUCCESS: 17, FAILED: 1 } },
    feedback: { status: 'LIVE', scope: 'ALL_TIME', totalCount: 12, pendingCount: 3, statusCounts: { PENDING: 3, COMPLETED: 9 }, typeCounts: {}, contextMissingCount: 2, policyCandidateCount: 1 },
    evaluation: { status: 'LIVE', scope: 'ALL_TIME', caseCount: 8, verdictCounts: {}, ruleGapCounts: {}, runCount: 4, runStatusCounts: {}, acceptance: { totalCount: 4, statusCounts: { PASSED: 4 }, latestStatus: 'PASSED' }, agentSampleGate: { annotatedSampleCount: 30, requiredSampleCount: 30, ready: true } },
    policies: { status: 'LIVE', scope: 'ALL_TIME', totalCount: 5, enabledCount: 4, candidateCount: 1 },
    coverage: { phase: 'M4_ACCEPTANCE', truncated: false, sections: { findingRisk: 'COMPLETE' }, limits: {}, filters: {}, scanned: {} }
  };
}


function activityFor(scenario) {
  return {
    idle: { agentQueued: 0, agentRunning: 0, standardQueued: 0, standardRunning: 0, fallback: false },
    'agent-queued': { agentQueued: 2, agentRunning: 0, standardQueued: 0, standardRunning: 0, fallback: false },
    'standard-queued': { agentQueued: 0, agentRunning: 0, standardQueued: 2, standardRunning: 0, fallback: false },
    'agent-running': { agentQueued: 0, agentRunning: 1, standardQueued: 0, standardRunning: 0, fallback: false },
    'standard-running': { agentQueued: 0, agentRunning: 0, standardQueued: 0, standardRunning: 1, fallback: false },
    'dual-running': { agentQueued: 0, agentRunning: 1, standardQueued: 0, standardRunning: 1, fallback: false },
    'fallback-running': { agentQueued: 0, agentRunning: 0, standardQueued: 0, standardRunning: 1, fallback: true },
    stale: { agentQueued: 0, agentRunning: 0, standardQueued: 0, standardRunning: 0, fallback: false },
    'runtime-error': { agentQueued: 0, agentRunning: 0, standardQueued: 0, standardRunning: 0, fallback: false },
    'governance-error': { agentQueued: 0, agentRunning: 0, standardQueued: 0, standardRunning: 0, fallback: false }
  }[scenario];
}


function laneItem({
  jobId,
  taskId,
  reviewKey,
  engine,
  effectiveEngine = engine,
  fallback = false,
  status = 'RUNNING',
  stage = engine === 'AGENT' ? 'AGENT_ANALYZING' : 'MODEL_CALLING',
  provider = engine === 'AGENT' ? 'DeepSeek' : 'OpenAI',
  model = engine === 'AGENT' ? 'deepseek-v4-pro' : 'gpt-5.5',
  workerId = engine === 'AGENT' ? 'agent-m4-a' : null,
  startedAt = '2026-08-05T01:00:20.000Z'
}) {
  return {
    jobId,
    taskId,
    reviewKey,
    projectName: taskId === 901 ? '支付服务' : '订单服务',
    displayName: fallback ? 'Agent fallback Review' : engine === 'AGENT' ? 'Agent 实时审查' : 'Standard 实时审查',
    requestedEngine: engine,
    effectiveEngine,
    fallback,
    status,
    stage,
    provider,
    model,
    workerId,
    queuedAt: '2026-08-05T01:00:00.000Z',
    startedAt,
    durationSeconds: status === 'RUNNING' ? 42 : null
  };
}


function activeTasks(now) {
  return [
    task(901, '支付服务', '李明', 'GITLAB_MR_WEBHOOK', 'feature/payment-check', 'main', null, now - 15_000),
    task(902, '订单服务', '王芳', 'GITLAB_PUSH_WEBHOOK', null, null, '7f4c8d1a9b20', now - 34_000),
    task(903, '库存服务', null, 'MANUAL', 'release/2026.08', 'main', null, now - 57_000),
    task(904, '结算服务', '赵磊', 'RETRY', 'fix/settlement-lock', 'main', null, now - 92_000)
  ];
}


function task(taskId, projectName, authorName, triggerType, sourceBranch, targetBranch, commitSha, updatedAt) {
  return {
    taskId,
    projectId: taskId - 800,
    projectName,
    triggerType,
    authorName,
    authorUsername: authorName ? `m4-user-${taskId}` : null,
    externalUrl: `https://gitlab.example.local/m4/project-${taskId}/-/merge_requests/1`,
    repositoryUrl: `https://gitlab.example.local/m4/project-${taskId}`,
    sourceBranch,
    targetBranch,
    commitSha,
    technicalStatus: 'RUNNING',
    reviewStatus: 'RUNNING',
    riskLevel: taskId === 902 ? 'HIGH' : 'MEDIUM',
    ruleRiskItemCount: taskId === 902 ? 3 : 1,
    flowCount: 1,
    stage: 'REVIEW_RUNNING',
    stageSource: 'M4_FIXTURE',
    createdAt: new Date(updatedAt - 60_000).toISOString(),
    updatedAt: new Date(updatedAt).toISOString()
  };
}


function worker(workerId, state, online, lastHeartbeatAt) {
  return { workerId, state, online, capacity: 1, activeJobId: state === 'BUSY' ? 201 : null, activeRunId: state === 'BUSY' ? 501 : null, lastHeartbeatAt, source: 'REGISTERED' };
}


function provider(providerCode, providerName, modelName, active, lastObservedAt) {
  return { providerCode, providerName, providerType: 'OPENAI_COMPATIBLE', modelName, enabled: true, defaultProvider: providerCode === 'OPENAI', status: active ? 'ACTIVE' : 'RECENT_SUCCESS', activeFlowCount: active ? 1 : 0, recentSuccessCount: providerCode === 'OPENAI' ? 17 : 9, recentFailureCount: providerCode === 'OPENAI' ? 1 : 0, lastObservedAt };
}


function assertScenario(scenario) {
  if (!COMMAND_CENTER_M4_SCENARIOS.includes(scenario)) {
    throw new Error(`Unknown Command Center M4 scenario: ${scenario}`);
  }
}
