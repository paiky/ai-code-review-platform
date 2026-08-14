const SEVERITY_WEIGHTS = Object.freeze({
  CRITICAL: 4,
  HIGH: 3,
  MAJOR: 3,
  MEDIUM: 2,
  MINOR: 2,
  LOW: 1
});

const TERMINAL_STATUSES = new Set(['SUCCESS', 'FAILED', 'CANCELLED', 'SKIPPED']);

function normalizedSeverity(value) {
  return String(value || '').trim().toUpperCase();
}

function nonNegativeNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function safeErrorCode(value) {
  const code = String(value || '').trim().toUpperCase();
  return /^[A-Z][A-Z0-9_]{0,79}$/.test(code) ? code : null;
}

export function severityWeight(value) {
  return SEVERITY_WEIGHTS[normalizedSeverity(value)] || 0;
}

export function buildFindingRiskCounts(findings) {
  const counts = {
    total: 0,
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    unknown: 0
  };
  for (const finding of Array.isArray(findings) ? findings : []) {
    counts.total += 1;
    switch (normalizedSeverity(finding?.severity)) {
      case 'CRITICAL':
        counts.critical += 1;
        break;
      case 'HIGH':
      case 'MAJOR':
        counts.high += 1;
        break;
      case 'MEDIUM':
      case 'MINOR':
        counts.medium += 1;
        break;
      case 'LOW':
        counts.low += 1;
        break;
      default:
        counts.unknown += 1;
    }
  }
  return counts;
}

export function highestRiskOriginalIndex(findings) {
  const source = Array.isArray(findings) ? findings : [];
  let highestIndex = null;
  let highestWeight = -1;
  source.forEach((finding, index) => {
    const weight = severityWeight(finding?.severity);
    if (weight > highestWeight) {
      highestIndex = index;
      highestWeight = weight;
    }
  });
  return highestIndex;
}

export function cleanFormalReviewSummary(value) {
  return String(value || '')
    .replace(/\[([^\]]+)]\(<?[^)>\n]+>?\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/\r\n?/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function resolveFormalReviewSummary(review, findings) {
  const source = Array.isArray(findings) ? findings : [];
  const summary = cleanFormalReviewSummary(review?.summary);
  if (summary && summary.toLowerCase() !== 'findings') return summary;
  return source.length > 0
    ? `本次 Review 共发现 ${source.length} 个代码质量问题。`
    : '本次 Review 未发现需要报告的代码质量问题。';
}

export function isReviewFallback(review) {
  return String(review?.requestedEngine || '').toUpperCase() === 'AGENT'
    && String(review?.effectiveEngine || '').toUpperCase() === 'STANDARD_FALLBACK';
}

export function isTerminalReviewStatus(status) {
  return TERMINAL_STATUSES.has(String(status || '').toUpperCase());
}

export function resolveReviewPresentationKey(review, journey) {
  return String(
    review?.reviewKey
    || journey?.selectorKey
    || review?.id
    || 'historical-review'
  );
}

export function resolveFindingDeepLink(hash, findingCount) {
  const count = Number(findingCount);
  if (!Number.isInteger(count) || count <= 0) return null;
  const match = /^#(fix-preview|finding)-(\d+)$/.exec(String(hash || ''));
  if (!match) return null;
  const index = Number(match[2]);
  if (!Number.isSafeInteger(index) || index < 0 || index >= count) return null;
  return {
    index,
    kind: match[1] === 'fix-preview' ? 'FIX_PREVIEW' : 'FINDING',
    targetId: `${match[1]}-${index}`
  };
}

export function resolveInitialExpandedFindingIndexes(findings, hash = '') {
  const source = Array.isArray(findings) ? findings : [];
  const deepLink = resolveFindingDeepLink(hash, source.length);
  if (deepLink) return [deepLink.index];
  const index = highestRiskOriginalIndex(source);
  return index === null ? [] : [index];
}

export function initializeFindingExpansionRegistry(registry, reviewKey, findings, hash = '') {
  const current = registry && typeof registry === 'object' ? registry : {};
  const key = String(reviewKey || 'historical-review');
  if (Object.prototype.hasOwnProperty.call(current, key)) return current;
  return {
    ...current,
    [key]: resolveInitialExpandedFindingIndexes(findings, hash)
  };
}

export function setReviewExpandedFindingIndexes(registry, reviewKey, indexes, findingCount) {
  const current = registry && typeof registry === 'object' ? registry : {};
  const count = Number(findingCount);
  const normalized = (Array.isArray(indexes) ? indexes : [])
    .filter(index => Number.isSafeInteger(index) && index >= 0 && index < count)
    .filter((index, position, source) => source.indexOf(index) === position);
  return { ...current, [String(reviewKey || 'historical-review')]: normalized };
}

export function mergeDeepLinkedFinding(currentIndexes, hash, findingCount) {
  const current = Array.isArray(currentIndexes)
    ? currentIndexes.filter(index => Number.isSafeInteger(index) && index >= 0)
    : [];
  const deepLink = resolveFindingDeepLink(hash, findingCount);
  if (!deepLink || current.includes(deepLink.index)) return current;
  return [...current, deepLink.index];
}

export function buildTerminalReviewResultPresentation(review, journey) {
  const findings = Array.isArray(review?.findings) ? review.findings : [];
  const status = String(journey?.status || review?.status || 'UNKNOWN').toUpperCase();
  const fallback = isReviewFallback(review);
  const successfulFallback = fallback && status === 'SUCCESS';
  const titles = {
    SUCCESS: successfulFallback ? 'Review 完成 · 已降级' : 'Review 完成',
    FAILED: 'Review 失败',
    CANCELLED: 'Review 已取消',
    SKIPPED: 'Review 已跳过'
  };
  const errorCode = safeErrorCode(
    review?.agentRunSummary?.errorCode
    || review?.agentRunSummary?.failureCode
    || review?.errorCode
  );
  let reason = null;
  if (successfulFallback) reason = 'Standard Review 已接管并生成正式结果';
  else if (status === 'FAILED') reason = errorCode ? `错误码：${errorCode}` : '本次 Review 未能成功完成。';
  else if (status === 'CANCELLED') reason = '本次 Review 已取消。';
  else if (status === 'SKIPPED') reason = '本次 Review 已跳过。';
  const formalSummary = cleanFormalReviewSummary(review?.summary);
  const hasFormalSummary = formalSummary && formalSummary.toLowerCase() !== 'findings';

  return {
    status,
    title: titles[status] || 'Review 结果',
    fallback,
    successfulFallback,
    reason,
    issueCount: findings.length,
    riskCounts: buildFindingRiskCounts(findings),
    summary: status === 'SUCCESS'
      ? resolveFormalReviewSummary(review, findings)
      : hasFormalSummary
        ? formalSummary
        : reason,
    engineLabel: journey?.engineLabel || '历史任务未记录',
    providerModelLabel: journey?.providerModelLabel || [review?.provider, review?.model].filter(Boolean).join(' / ') || '历史任务未记录',
    durationMs: nonNegativeNumber(journey?.durationMs),
    agentDurationMs: nonNegativeNumber(review?.agentRunSummary?.durationMs),
    agentRunId: review?.agentRunSummary?.runId ?? review?.agentRunId ?? null
  };
}
