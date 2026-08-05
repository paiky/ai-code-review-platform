const SEVERITY_ORDER = Object.freeze(['CRITICAL', 'HIGH', 'MEDIUM']);
const RISK_LEVELS = Object.freeze({ LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 });


export function providerQualityVisual(providerExecution) {
  const available = Boolean(providerExecution?.available);
  const successCount = available ? safeCount(providerExecution?.successCount) : 0;
  const failureCount = available ? safeCount(providerExecution?.failureCount) : 0;
  const totalCount = successCount + failureCount;
  return {
    available,
    empty: totalCount === 0,
    successCount,
    failureCount,
    successPercent: totalCount > 0 ? roundPercent(successCount / totalCount) : 0,
    failurePercent: totalCount > 0 ? roundPercent(failureCount / totalCount) : 0,
    label: available
      ? totalCount > 0
        ? `成功 ${successCount}，失败 ${failureCount}`
        : '暂无 Provider 执行记录'
      : 'Provider 执行结果暂不可用'
  };
}


export function findingSeverityVisual(findingRisk) {
  const available = Boolean(findingRisk?.available);
  const counts = available && findingRisk?.severityCounts && typeof findingRisk.severityCounts === 'object'
    ? findingRisk.severityCounts
    : {};
  const normalized = Object.entries(counts).reduce((result, [key, value]) => {
    const token = String(key || '').trim().toUpperCase();
    if (!token) return result;
    result[token] = (result[token] || 0) + safeCount(value);
    return result;
  }, {});
  const known = new Set([...SEVERITY_ORDER, 'LOW']);
  const otherCount = Object.entries(normalized)
    .filter(([token]) => !known.has(token))
    .reduce((total, [, count]) => total + count, 0);
  const bars = [
    ...SEVERITY_ORDER.map(token => ({ token: token.toLowerCase(), label: severityLabel(token), count: normalized[token] || 0 })),
    { token: 'low-other', label: '低/其他', count: (normalized.LOW || 0) + otherCount }
  ];
  const maximum = Math.max(...bars.map(item => item.count), 0);
  const totalCount = bars.reduce((total, item) => total + item.count, 0);
  return {
    available,
    empty: totalCount === 0,
    bars: bars.map(item => ({
      ...item,
      percent: maximum > 0 ? Math.max(roundPercent(item.count / maximum), item.count > 0 ? 12 : 0) : 0
    })),
    label: available
      ? totalCount > 0
        ? bars.map(item => `${item.label} ${item.count}`).join('，')
        : '暂无 Finding 严重级别记录'
      : 'Finding 严重级别暂不可用'
  };
}


export function affectedRiskVisual(findingRisk) {
  const available = Boolean(findingRisk?.available);
  const token = String(findingRisk?.highestRisk || '').trim().toUpperCase();
  const level = available ? RISK_LEVELS[token] || 0 : 0;
  return {
    available,
    empty: level === 0,
    level,
    token: token.toLowerCase() || 'none',
    label: available
      ? level > 0
        ? `最高风险 ${severityLabel(token)}`
        : '暂无风险级别记录'
      : '风险级别暂不可用'
  };
}


function safeCount(value) {
  const count = Number(value);
  return Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
}


function roundPercent(value) {
  return Math.round(value * 1_000) / 10;
}


function severityLabel(token) {
  return {
    CRITICAL: '严重',
    HIGH: '高',
    MEDIUM: '中',
    LOW: '低'
  }[token] || '其他';
}
