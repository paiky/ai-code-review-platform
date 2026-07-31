const STAGE_COLUMNS = {
  RULE_ANALYSIS: 'rule',
  RULE_COMPLETED: 'rule',
  PREFLIGHT: 'orchestration',
  QUEUED: 'orchestration',
  CONTEXT_BUILDING: 'execution',
  MODEL_CALLING: 'execution',
  AGENT_ANALYZING: 'execution',
  AGENT_TOOL_ACTIVITY: 'execution',
  AGENT_CONVERGING: 'execution',
  AGENT_SUBMITTING: 'execution',
  FINDING_READY: 'delivery',
  NOTIFYING: 'delivery',
  COMPLETED: 'delivery',
  FAILED: 'delivery',
  SKIPPED: 'delivery',
  FALLBACK: 'execution'
};

const STATE_TOKENS = {
  FAILED: 'danger',
  TIMED_OUT: 'danger',
  CRITICAL: 'danger',
  FALLBACK: 'warning',
  RECENT_FAILURE: 'warning',
  QUEUED: 'queued',
  RUNNING: 'active',
  PENDING: 'active',
  CLAIMED: 'active',
  ACTIVE: 'active',
  SUCCESS: 'success',
  RECENT_SUCCESS: 'success',
  COMPLETED: 'success',
  DISABLED: 'muted',
  NO_RECENT_DATA: 'muted',
  STALE: 'warning'
};

const TOPOLOGY_COLUMNS = [
  {
    key: 'intake',
    eyebrow: 'INTAKE',
    title: 'GitLab / Manual',
    description: '事件进入平台并创建 ReviewTask。',
    position: { x: 0.1, y: 0.5 }
  },
  {
    key: 'rule',
    eyebrow: 'RULE & DECISION',
    title: 'Rule Analysis',
    description: '规则识别与 Risk Card 聚合。',
    position: { x: 0.3, y: 0.5 }
  },
  {
    key: 'orchestration',
    eyebrow: 'ORCHESTRATION',
    title: 'Review Execution Core',
    description: 'Task、Preflight 与 Scheduler 编排。',
    position: { x: 0.5, y: 0.5 }
  },
  {
    key: 'execution',
    eyebrow: 'EVIDENCE & EXECUTION',
    title: 'Standard / Agent',
    description: 'Context、Provider、Agent Worker 双引擎执行。',
    position: { x: 0.7, y: 0.5 }
  },
  {
    key: 'delivery',
    eyebrow: 'RESULT & DELIVERY',
    title: 'Finding / Notification',
    description: 'Finding 风险判断与通知交付。',
    position: { x: 0.9, y: 0.5 }
  }
];


export function buildCommandCenterPresentation({ runtime, governance } = {}) {
  const safeRuntime = runtime || null;
  const safeGovernance = governance || null;
  const flows = (safeRuntime?.activeFlows || []).map(flow => ({
    ...flow,
    engineKind: flow.fallback
      ? 'FALLBACK'
      : flow.requestedEngine === 'AGENT'
        ? 'AGENT'
        : 'STANDARD',
    stateToken: stateToken(flow.fallback ? 'FALLBACK' : flow.status),
    columnKey: STAGE_COLUMNS[flow.stage] || 'execution',
    providerModelLabel: [flow.providerCode, flow.model].filter(Boolean).join(' · ') || 'Provider 未记录',
    stageLabel: stageLabel(flow.stage)
  }));
  const flowCountByColumn = flows.reduce((counts, flow) => ({
    ...counts,
    [flow.columnKey]: (counts[flow.columnKey] || 0) + 1
  }), {});
  const topologyColumns = TOPOLOGY_COLUMNS.map(column => ({
    key: column.key,
    eyebrow: column.eyebrow,
    title: column.title,
    description: column.description
  }));
  const topologyScene = buildTopologyScene(flowCountByColumn);

  return {
    allowAnimation: false,
    pulse: {
      activeTasks: safeRuntime?.intake?.activeTaskCount ?? 0,
      activeJobs: safeRuntime?.scheduler?.activeJobCount ?? 0,
      queueDepth: safeRuntime?.agent?.queueMetrics?.queued ?? 0,
      onlineWorkers: safeRuntime?.agent?.workerPool?.onlineCount ?? 0,
      activeProviders: (safeRuntime?.providersObserved || []).filter(provider => provider.status === 'ACTIVE').length,
      criticalFindings: safeGovernance?.findingRisk?.severityCounts?.CRITICAL ?? 0,
      runtimeFreshness: safeRuntime?.freshness || 'EMPTY',
      governanceFreshness: safeGovernance?.freshness || 'EMPTY',
      generatedAt: safeRuntime?.generatedAt || null
    },
    topology: {
      activeTasks: safeRuntime?.activeTasks || [],
      flows,
      flowCountByColumn,
      columns: topologyColumns,
      scene: topologyScene,
      standardFlowCount: flows.filter(flow => flow.engineKind === 'STANDARD').length,
      agentFlowCount: flows.filter(flow => flow.engineKind === 'AGENT').length,
      fallbackFlowCount: flows.filter(flow => flow.engineKind === 'FALLBACK').length
    },
    operations: {
      scheduler: safeRuntime?.scheduler || {},
      queue: safeRuntime?.agent?.queueMetrics || {},
      workers: safeRuntime?.agent?.workerPool || {},
      providers: (safeRuntime?.providersObserved || []).map(provider => ({
        ...provider,
        stateToken: stateToken(provider.status),
        statusLabel: providerStatusLabel(provider.status)
      })),
      flows,
      alerts: (safeRuntime?.alerts || []).map(alert => ({
        ...alert,
        stateToken: stateToken(alert.type === 'CRITICAL_FINDING' ? 'CRITICAL' : alert.status),
        typeLabel: alertTypeLabel(alert.type)
      }))
    },
    governance: buildGovernancePresentation(safeGovernance)
  };
}


function buildTopologyScene(flowCountByColumn) {
  const nodes = TOPOLOGY_COLUMNS.map(column => ({
    id: `lifecycle:${column.key}`,
    columnKey: column.key,
    x: column.position.x,
    y: column.position.y,
    flowCount: flowCountByColumn[column.key] || 0
  }));
  return {
    id: 'review-lifecycle',
    allowAnimation: false,
    nodes,
    edges: nodes.slice(0, -1).map((node, index) => ({
      id: `${node.id}->${nodes[index + 1].id}`,
      from: node.id,
      to: nodes[index + 1].id
    }))
  };
}


export function stateToken(value) {
  return STATE_TOKENS[String(value || '').toUpperCase()] || 'neutral';
}


export function stageLabel(value) {
  return {
    RULE_ANALYSIS: '规则分析',
    RULE_COMPLETED: '规则已完成',
    PREFLIGHT: 'Preflight',
    QUEUED: '排队中',
    CONTEXT_BUILDING: '构建上下文',
    MODEL_CALLING: '模型调用',
    AGENT_ANALYZING: 'Agent 分析',
    AGENT_TOOL_ACTIVITY: 'Agent 工具活动',
    AGENT_CONVERGING: 'Agent 收敛',
    AGENT_SUBMITTING: 'Agent 提交',
    FINDING_READY: 'Finding 已生成',
    NOTIFYING: '通知处理中',
    COMPLETED: '已完成',
    FAILED: '失败',
    SKIPPED: '已跳过',
    FALLBACK: 'Standard Fallback'
  }[value] || '运行中';
}


function buildGovernancePresentation(governance) {
  if (!governance) return { metrics: [], coverage: null };
  return {
    metrics: [
      metric('Rule Analysis', governance.ruleAnalysis?.riskItemCount, governance.ruleAnalysis?.scope, '/tasks'),
      metric('Preflight Finding', governance.preflight?.findingCount, governance.preflight?.scope, '/review-quality'),
      metric('Context Insufficient', governance.contextQuality?.statusCounts?.INSUFFICIENT, governance.contextQuality?.scope, '/review-quality'),
      metric('Critical Finding', governance.findingRisk?.severityCounts?.CRITICAL, governance.findingRisk?.scope, '/review-quality'),
      metric('Notification Failed', governance.notifications?.statusCounts?.FAILED, governance.notifications?.scope, '/tasks'),
      metric('Pending Feedback', governance.feedback?.pendingCount, governance.feedback?.scope, '/risk-feedback'),
      metric('Evaluation Case', governance.evaluation?.caseCount, governance.evaluation?.scope, '/evaluation-cases'),
      metric('Policy Candidate', governance.policies?.candidateCount, governance.policies?.scope, '/risk-feedback'),
      metric('Acceptance Gate', governance.evaluation?.acceptance?.totalCount, governance.evaluation?.scope, '/acceptance-gates'),
      metric(
        'Agent Sample Gate',
        `${governance.evaluation?.agentSampleGate?.annotatedSampleCount ?? 0}/${governance.evaluation?.agentSampleGate?.requiredSampleCount ?? 30}`,
        governance.evaluation?.scope,
        '/review-quality'
      )
    ],
    coverage: governance.coverage
  };
}


function metric(label, value, scope, href) {
  return {
    label,
    value: value ?? 0,
    scope: scope || 'UNKNOWN',
    href
  };
}


function providerStatusLabel(value) {
  return {
    DISABLED: '已禁用',
    ACTIVE: '当前活跃',
    RECENT_SUCCESS: '最近成功',
    RECENT_FAILURE: '最近失败',
    NO_RECENT_DATA: '暂无近期数据'
  }[value] || '状态未知';
}


function alertTypeLabel(value) {
  return {
    JOB_FAILED: 'Review Job 失败',
    AGENT_RUN_FAILED: 'Agent 执行失败',
    FALLBACK: 'Agent 已降级',
    WORKER_OFFLINE: 'Worker 离线',
    WORKER_DRAINING: 'Worker 排空',
    LEASE_EXPIRED: '任务租约过期',
    NOTIFICATION_FAILED: '通知失败',
    CRITICAL_FINDING: 'Critical Finding'
  }[value] || value || '未知告警';
}
