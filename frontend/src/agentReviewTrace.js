export const agentTracePhases = new Set([
  'AGENT_RECLAIMED',
  'AGENT_ANALYZING',
  'AGENT_TOOL_ACTIVITY',
  'AGENT_CONVERGING',
  'AGENT_SUBMITTING',
  'AGENT_FINISHED',
  'AGENT_FALLBACK',
  'AGENT_CANCELLED'
]);

const agentToolTracePhases = new Set([
  'AGENT_TOOL_ACTIVITY',
  'AGENT_CONVERGING',
  'AGENT_SUBMITTING'
]);

const agentTerminalPhases = new Set([
  'AGENT_FINISHED',
  'AGENT_FALLBACK',
  'AGENT_CANCELLED'
]);

export function isAgentTraceProgressEvent(event) {
  return agentTracePhases.has(event?.phase);
}

export function isAgentHeartbeatProgressEvent(event) {
  return event?.phase === 'AGENT_HEARTBEAT';
}

export function collectAgentTraceEvents(events) {
  const source = Array.isArray(events) ? events : [];
  const latestScope = getLatestAgentTraceScope(source);
  if (!latestScope) return [];
  const byKey = new Map();
  source
    .filter(isAgentTraceProgressEvent)
    .forEach(event => {
      const detail = parseDetail(event?.detail);
      if (!matchesScope(detail, latestScope)) return;
      const terminalKey = agentTerminalPhases.has(event?.phase) ? event.phase : null;
      const reclaimedKey = event?.phase === 'AGENT_RECLAIMED' ? event.phase : null;
      const key = `${detail?.runId ?? 'run'}:${scopeAttempt(detail)}:${terminalKey ?? reclaimedKey ?? detail?.sequence ?? event?.id}`;
      if (!byKey.has(key)) byKey.set(key, event);
    });
  return [...byKey.values()].sort((left, right) => {
    const leftDetail = parseDetail(left?.detail);
    const rightDetail = parseDetail(right?.detail);
    return traceSortValue(left, leftDetail) - traceSortValue(right, rightDetail);
  });
}

export function groupAgentTraceEvents(events) {
  const grouped = [];
  for (const event of collectAgentTraceEvents(events)) {
    const detail = parseDetail(event?.detail) || {};
    const previous = grouped[grouped.length - 1];
    const previousDetail = parseDetail(previous?.detail) || {};
    const canMerge = previous
      && agentToolTracePhases.has(event?.phase)
      && event.phase === previous.phase
      && detail.activity === previousDetail.activity
      && detail.status === previousDetail.status;
    if (!canMerge) {
      grouped.push(event);
      continue;
    }
    const pathSummary = [
      ...(Array.isArray(previousDetail.pathSummary) ? previousDetail.pathSummary : []),
      ...(Array.isArray(detail.pathSummary) ? detail.pathSummary : [])
    ].map(item => ({
      suffix: String(item?.suffix || ''),
      depth: Number(item?.depth || 0)
    }));
    const uniquePaths = [...new Map(
      pathSummary.map(item => [`${item.suffix}:${item.depth}`, item])
    ).values()];
    grouped[grouped.length - 1] = {
      ...previous,
      id: `${previous.id}-${event.id}`,
      createdAt: event.createdAt || previous.createdAt,
      detail: {
        runId: detail.runId ?? previousDetail.runId,
        claimAttempt: scopeAttempt(detail),
        sequence: previousDetail.sequence,
        sequenceEnd: detail.sequence,
        groupCount: Number(previousDetail.groupCount || 1) + 1,
        activity: detail.activity,
        status: detail.status,
        durationMs: Number(previousDetail.durationMs || 0) + Number(detail.durationMs || 0),
        itemCount: Number(previousDetail.itemCount || 0) + Number(detail.itemCount || 0),
        sourceBytes: Number(previousDetail.sourceBytes || 0) + Number(detail.sourceBytes || 0),
        errorCode: detail.errorCode || previousDetail.errorCode,
        pathSummary: uniquePaths,
        reviewBudget: detail.reviewBudget || previousDetail.reviewBudget
      }
    };
  }
  return grouped;
}

export function summarizeAgentTrace(events, now = Date.now()) {
  const source = Array.isArray(events) ? events : [];
  const latestScope = getLatestAgentTraceScope(source);
  if (!latestScope) return null;
  const scoped = source.filter(event => {
    if (!isAgentTraceProgressEvent(event) && !isAgentHeartbeatProgressEvent(event)) {
      return false;
    }
    return matchesScope(parseDetail(event?.detail), latestScope);
  });
  const heartbeats = scoped
    .filter(isAgentHeartbeatProgressEvent)
    .sort((left, right) => {
      const leftValue = Number(parseDetail(left?.detail)?.heartbeatSequence || 0);
      const rightValue = Number(parseDetail(right?.detail)?.heartbeatSequence || 0);
      return leftValue - rightValue;
    });
  const trace = collectAgentTraceEvents(scoped);
  const terminal = [...trace].reverse().find(event => agentTerminalPhases.has(event.phase));
  const latestTrace = trace[trace.length - 1];
  const latestHeartbeat = heartbeats[heartbeats.length - 1];
  const heartbeatDetail = parseDetail(latestHeartbeat?.detail) || {};
  const traceDetail = parseDetail((terminal || latestTrace)?.detail) || {};
  const operationalTrace = [...trace].reverse().find(
    event => !agentTerminalPhases.has(event.phase)
  );
  const operationalDetail = parseDetail(operationalTrace?.detail) || {};
  const metrics = terminal
    ? traceDetail
    : latestHeartbeat
      ? heartbeatDetail
      : traceDetail;
  const effectiveBudgets = validNumberMap(
    traceDetail.effectiveBudgets || heartbeatDetail.effectiveBudgets,
    [
      'maxTurns',
      'maxToolCalls',
      'maxSourceBytes',
      'timeoutSeconds',
      'inlineDiffBytes',
      'maxEvidenceCalls',
      'convergeAtCalls',
      'submitByTurn'
    ]
  );
  const reviewBudget = safeReviewBudget(
    heartbeatDetail.reviewBudget
      || operationalDetail.reviewBudget
      || traceDetail.reviewBudget
  );
  const lastHeartbeatAt = latestHeartbeat?.createdAt || null;
  const heartbeatTime = Date.parse(lastHeartbeatAt || '');
  return {
    runId: latestScope.runId,
    claimAttempt: latestScope.claimAttempt,
    phase: terminal?.phase || latestTrace?.phase || 'AGENT_ANALYZING',
    terminal: Boolean(terminal),
    hasHeartbeat: Boolean(latestHeartbeat),
    lastHeartbeatAt,
    heartbeatSequence: latestHeartbeat
      ? Number(heartbeatDetail.heartbeatSequence || 0)
      : null,
    progressMayBeDelayed: !terminal
      && Number.isFinite(heartbeatTime)
      && Number(now) - heartbeatTime > 45_000,
    toolCallCount: safeNumber(metrics.toolCallCount),
    evidenceCallsUsed: safeNumber(
      metrics.evidenceCallsUsed ?? reviewBudget.evidenceCallsUsed
    ),
    sourceBytesReturned: safeNumber(metrics.sourceBytesReturned),
    diffBytesReturned: safeNumber(metrics.diffBytesReturned),
    turnCount: terminal ? safeNumber(traceDetail.turnCount) : null,
    effectiveBudgets,
    reviewBudget
  };
}

export function formatAgentTraceDetail(detail, eventPhase = '') {
  const value = parseDetail(detail);
  if (!value) return '';
  const activityLabels = {
    ANALYZING: '分析变更',
    LIST_FILES: '列出安全文件',
    SEARCH_CODE: '搜索代码',
    READ_FILE_RANGE: '读取源码片段',
    READ_DIFF_RANGE: '读取 Diff 片段',
    SUBMIT_REVIEW: '提交 Review Card',
    RECLAIMED: '租约过期后重新领取',
    FINISHED: 'Agent Review 完成',
    FALLBACK: 'Agent Review 降级',
    CANCELLED: 'Agent Review 取消'
  };
  const terminalActivity = {
    AGENT_FINISHED: 'FINISHED',
    AGENT_FALLBACK: 'FALLBACK',
    AGENT_CANCELLED: 'CANCELLED'
  }[eventPhase || value.phase];
  if (eventPhase === 'AGENT_RECLAIMED') {
    const attempt = safeNumber(value.claimAttempt);
    return [
      '活动：租约过期后重新领取',
      `领取尝试：第 ${attempt} 次`,
      `原因：${value.reasonCode === 'LEASE_EXPIRED' ? '上一租约已过期' : '任务重新领取'}`
    ].join('\n');
  }
  const activity = value.activity || terminalActivity;
  const sequenceText = Number(value.groupCount || 0) > 1
    ? `${Number(value.sequence || 0)}～${Number(value.sequenceEnd || value.sequence || 0)}`
    : `${Number(value.sequence || 0)}`;
  const lines = [];
  if (!terminalActivity) lines.push(`序号：${sequenceText}`);
  lines.push(`活动：${activityLabels[activity] || activity || '-'}`);
  if (Number(value.groupCount || 0) > 1) {
    lines.push(`合并活动：${Number(value.groupCount)} 次`);
  }
  if (value.status) lines.push(`状态：${value.status}`);
  if (Number.isFinite(Number(value.durationMs))) lines.push(`耗时：${Number(value.durationMs)} ms`);
  if (Number.isFinite(Number(value.itemCount))) lines.push(`条目数：${Number(value.itemCount)}`);
  if (Number.isFinite(Number(value.sourceBytes))) lines.push(`返回字节：${Number(value.sourceBytes)}`);
  if (value.errorCode) lines.push(`错误码：${value.errorCode}`);
  const pathSummary = Array.isArray(value.pathSummary) ? value.pathSummary : [];
  const fileTypes = [...new Set(pathSummary.map(item => {
    const suffix = String(item?.suffix || '无后缀');
    const depth = Number(item?.depth || 0);
    return `${suffix}（目录深度 ${depth}）`;
  }))];
  if (fileTypes.length > 0) lines.push(`文件类型：${fileTypes.join('、')}`);
  const budget = value.reviewBudget;
  if (budget && typeof budget === 'object') {
    lines.push(
      `取证预算：${budget.phase || '-'}，已用 ${Number(budget.evidenceCallsUsed || 0)}，` +
      `剩余 ${Number(budget.evidenceCallsRemaining || 0)} 次 / ${Number(budget.sourceBytesRemaining || 0)} bytes`
    );
    if (budget.mustSubmit) lines.push('提交要求：必须立即提交 Review Card');
  }
  return lines.join('\n');
}

export function getLatestAgentTraceScope(events) {
  const details = (Array.isArray(events) ? events : [])
    .filter(event => isAgentTraceProgressEvent(event) || isAgentHeartbeatProgressEvent(event))
    .map(event => parseDetail(event?.detail))
    .filter(detail => Number.isFinite(Number(detail?.runId)));
  if (details.length === 0) return null;
  const runId = Math.max(...details.map(detail => Number(detail.runId)));
  const claimAttempt = Math.max(
    ...details
      .filter(detail => Number(detail.runId) === runId)
      .map(scopeAttempt)
  );
  return { runId, claimAttempt };
}

export function isEventInAgentTraceScope(event, scope) {
  if (!scope || (!isAgentTraceProgressEvent(event) && !isAgentHeartbeatProgressEvent(event))) {
    return false;
  }
  return matchesScope(parseDetail(event?.detail), scope);
}

function scopeAttempt(detail) {
  const value = Number(detail?.claimAttempt ?? 0);
  return Number.isFinite(value) && value >= 0 ? value : 0;
}

function matchesScope(detail, scope) {
  return Number(detail?.runId) === scope.runId
    && scopeAttempt(detail) === scope.claimAttempt;
}

function traceSortValue(event, detail) {
  if (event?.phase === 'AGENT_RECLAIMED') return -1;
  if (event?.phase === 'AGENT_FINISHED') return 10_001;
  if (event?.phase === 'AGENT_FALLBACK') return 10_002;
  if (event?.phase === 'AGENT_CANCELLED') return 10_003;
  return Number(detail?.sequence || 0);
}

function validNumberMap(value, allowedKeys) {
  if (!value || typeof value !== 'object') return {};
  const allowed = new Set(allowedKeys);
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key, item]) => allowed.has(key) && Number.isFinite(Number(item)))
      .map(([key, item]) => [key, Number(item)])
  );
}

function safeReviewBudget(value) {
  const source = value && typeof value === 'object' ? value : {};
  const phase = String(source.phase || '').toUpperCase();
  return {
    ...validNumberMap(source, [
      'evidenceCallsUsed',
      'evidenceCallsRemaining',
      'sourceBytesRemaining'
    ]),
    phase: ['DISCOVERY', 'CONVERGE', 'SUBMIT'].includes(phase) ? phase : '',
    mustSubmit: Boolean(source.mustSubmit)
  };
}

function safeNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : 0;
}

function parseDetail(detail) {
  if (detail && typeof detail === 'object') return detail;
  try {
    const value = JSON.parse(detail);
    return value && typeof value === 'object' ? value : null;
  } catch {
    return null;
  }
}
