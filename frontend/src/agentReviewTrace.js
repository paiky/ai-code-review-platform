export const agentTracePhases = new Set([
  'AGENT_ANALYZING',
  'AGENT_TOOL_ACTIVITY',
  'AGENT_CONVERGING',
  'AGENT_SUBMITTING'
]);

export function isAgentTraceProgressEvent(event) {
  return agentTracePhases.has(event?.phase);
}

export function collectAgentTraceEvents(events) {
  const byKey = new Map();
  (Array.isArray(events) ? events : [])
    .filter(isAgentTraceProgressEvent)
    .forEach(event => {
      const detail = parseDetail(event?.detail);
      const key = `${detail?.runId ?? 'run'}:${detail?.sequence ?? event?.id}`;
      if (!byKey.has(key)) byKey.set(key, event);
    });
  return [...byKey.values()].sort((left, right) => {
    const leftDetail = parseDetail(left?.detail);
    const rightDetail = parseDetail(right?.detail);
    return Number(leftDetail?.sequence || 0) - Number(rightDetail?.sequence || 0);
  });
}

export function formatAgentTraceDetail(detail) {
  const value = parseDetail(detail);
  if (!value) return '';
  const activityLabels = {
    ANALYZING: '分析变更',
    LIST_FILES: '列出安全文件',
    SEARCH_CODE: '搜索代码',
    READ_FILE_RANGE: '读取源码片段',
    READ_DIFF_RANGE: '读取 Diff 片段',
    SUBMIT_REVIEW: '提交 Review Card'
  };
  const lines = [
    `序号：${Number(value.sequence || 0)}`,
    `活动：${activityLabels[value.activity] || value.activity || '-'}`
  ];
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

function parseDetail(detail) {
  if (detail && typeof detail === 'object') return detail;
  try {
    const value = JSON.parse(detail);
    return value && typeof value === 'object' ? value : null;
  } catch {
    return null;
  }
}
