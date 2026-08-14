import { collectAgentTraceEvents } from './agentReviewTrace.js';

export const SAFE_TRACE_ACTIVITY_TYPES = Object.freeze([
  'ANALYZING',
  'LIST_FILES',
  'SEARCH_CODE',
  'READ_FILE_RANGE',
  'READ_DIFF_RANGE',
  'SUBMIT_REVIEW',
  'RECLAIMED',
  'FINISHED',
  'FALLBACK',
  'CANCELLED'
]);

export const SAFE_TRACE_STATUSES = Object.freeze([
  'STARTED',
  'RUNNING',
  'SUCCESS',
  'FAILED',
  'WARNING',
  'CANCELLED',
  'UNKNOWN'
]);

const safeActivityTypes = new Set(SAFE_TRACE_ACTIVITY_TYPES);
const safeStatuses = new Set(SAFE_TRACE_STATUSES);
const MAX_SAFE_TRACE_INTEGER = 2_147_483_647;

const phaseActivityTypes = Object.freeze({
  AGENT_RECLAIMED: 'RECLAIMED',
  AGENT_ANALYZING: 'ANALYZING',
  AGENT_SUBMITTING: 'SUBMIT_REVIEW',
  AGENT_SUBMIT_VALIDATION_FAILED: 'SUBMIT_REVIEW',
  AGENT_REVIEW_SUBMITTED: 'SUBMIT_REVIEW',
  AGENT_OUTPUT_CONVERGENCE_FAILED: 'SUBMIT_REVIEW',
  AGENT_FINISHED: 'FINISHED',
  AGENT_FALLBACK: 'FALLBACK',
  AGENT_CANCELLED: 'CANCELLED'
});

const phaseStatuses = Object.freeze({
  AGENT_RECLAIMED: 'WARNING',
  AGENT_ANALYZING: 'STARTED',
  AGENT_SUBMITTING: 'STARTED',
  AGENT_SUBMIT_VALIDATION_FAILED: 'FAILED',
  AGENT_REVIEW_SUBMITTED: 'SUCCESS',
  AGENT_OUTPUT_CONVERGENCE_FAILED: 'FAILED',
  AGENT_FINISHED: 'SUCCESS',
  AGENT_FALLBACK: 'WARNING',
  AGENT_CANCELLED: 'CANCELLED'
});

export function buildSafeTraceViewModel({
  reviewKey,
  engineKind,
  events,
  agentSummary,
  agentDurationMs
} = {}) {
  if (!['AGENT', 'FALLBACK'].includes(String(engineKind || '').toUpperCase())) {
    return null;
  }

  const rawTraceEvents = collectAgentTraceEvents(events);
  const mappedEvents = rawTraceEvents.map(buildSafeTraceEvent).filter(Boolean);
  const safeEvents = groupSafeTraceEvents(mappedEvents);
  const discardedEventCount = rawTraceEvents.length - mappedEvents.length;
  const summary = buildSafeTraceSummary(agentSummary, agentDurationMs);
  const state = safeEvents.length === 0
    ? 'UNAVAILABLE'
    : discardedEventCount > 0
      ? 'PARTIAL'
      : 'AVAILABLE';

  return {
    reviewKey: safeReviewKey(reviewKey),
    state,
    events: safeEvents,
    summary
  };
}

export function buildSafeTraceEvent(event) {
  const detail = parseDetail(event?.detail);
  if (!detail) return null;
  const sequence = boundedInteger(detail.sequence);
  if (sequence === null) return null;

  const phase = String(event?.phase || '').toUpperCase();
  const rawActivityType = phaseActivityTypes[phase] || String(detail.activity || '').toUpperCase();
  if (!safeActivityTypes.has(rawActivityType)) return null;

  const rawStatus = phaseStatuses[phase] || String(detail.status || '').toUpperCase();
  const result = {
    sequence,
    activityType: rawActivityType,
    status: safeStatuses.has(rawStatus) ? rawStatus : 'UNKNOWN'
  };
  const durationMs = boundedInteger(detail.durationMs);
  const itemCount = boundedInteger(detail.itemCount);
  const sourceBytes = boundedInteger(detail.sourceBytes);
  const errorCode = safeErrorCode(detail.errorCode);
  if (durationMs !== null) result.durationMs = durationMs;
  if (itemCount !== null) result.itemCount = itemCount;
  if (sourceBytes !== null) result.sourceBytes = sourceBytes;
  if (errorCode) result.errorCode = errorCode;
  return result;
}

export function groupSafeTraceEvents(events) {
  const grouped = [];
  for (const sourceEvent of Array.isArray(events) ? events : []) {
    const event = cloneSafeTraceEvent(sourceEvent);
    if (!event) continue;
    const previous = grouped.at(-1);
    if (
      !previous
      || previous.activityType !== event.activityType
      || previous.status !== event.status
      || event.sequence !== (previous.sequenceEnd ?? previous.sequence) + 1
    ) {
      grouped.push(event);
      continue;
    }
    previous.sequenceEnd = event.sequenceEnd ?? event.sequence;
    previous.groupCount = (previous.groupCount || 1) + (event.groupCount || 1);
    mergeOptionalCount(previous, event, 'durationMs');
    mergeOptionalCount(previous, event, 'itemCount');
    mergeOptionalCount(previous, event, 'sourceBytes');
    if (!previous.errorCode && event.errorCode) previous.errorCode = event.errorCode;
  }
  return grouped;
}

export function buildSafeTraceSummary(agentSummary, agentDurationMs) {
  const source = agentSummary && typeof agentSummary === 'object' ? agentSummary : {};
  const budgets = source.effectiveBudgets && typeof source.effectiveBudgets === 'object'
    ? source.effectiveBudgets
    : {};
  const result = {};
  addOptionalInteger(result, 'runId', source.runId);
  addOptionalInteger(result, 'claimAttempt', source.claimAttempt);
  addOptionalInteger(result, 'agentDurationMs', agentDurationMs, { includeZero: true });
  addOptionalInteger(result, 'toolCallsUsed', source.toolCallCount);
  addOptionalInteger(result, 'toolCallsLimit', budgets.maxToolCalls);
  addOptionalInteger(result, 'evidenceCallsUsed', source.evidenceCallsUsed);
  addOptionalInteger(result, 'evidenceCallsLimit', budgets.maxEvidenceCalls);
  addOptionalInteger(result, 'sourceBytesUsed', source.sourceBytesReturned);
  addOptionalInteger(result, 'sourceBytesLimit', budgets.maxSourceBytes);
  if (source.terminal) {
    addOptionalInteger(result, 'modelTurnsUsed', source.turnCount);
  }
  addOptionalInteger(result, 'modelTurnsLimit', budgets.maxTurns);
  addOptionalInteger(result, 'submitAttempts', source.submitAttemptCount);
  addOptionalInteger(result, 'submitAttemptLimit', source.maxSubmitAttempts);
  return result;
}

function cloneSafeTraceEvent(value) {
  if (!value || typeof value !== 'object') return null;
  const sequence = boundedInteger(value.sequence);
  const activityType = String(value.activityType || '').toUpperCase();
  const status = String(value.status || '').toUpperCase();
  if (sequence === null || !safeActivityTypes.has(activityType) || !safeStatuses.has(status)) {
    return null;
  }
  const result = { sequence, activityType, status };
  const sequenceEnd = boundedInteger(value.sequenceEnd);
  const groupCount = boundedInteger(value.groupCount);
  const durationMs = boundedInteger(value.durationMs);
  const itemCount = boundedInteger(value.itemCount);
  const sourceBytes = boundedInteger(value.sourceBytes);
  const errorCode = safeErrorCode(value.errorCode);
  if (sequenceEnd !== null && sequenceEnd >= sequence) result.sequenceEnd = sequenceEnd;
  if (groupCount !== null && groupCount > 1) result.groupCount = groupCount;
  if (durationMs !== null) result.durationMs = durationMs;
  if (itemCount !== null) result.itemCount = itemCount;
  if (sourceBytes !== null) result.sourceBytes = sourceBytes;
  if (errorCode) result.errorCode = errorCode;
  return result;
}

function mergeOptionalCount(target, source, key) {
  if (source[key] === undefined) return;
  target[key] = Math.min(
    MAX_SAFE_TRACE_INTEGER,
    Number(target[key] || 0) + Number(source[key])
  );
}

function addOptionalInteger(target, key, value, options = {}) {
  const number = boundedInteger(value);
  if (number === null || (!options.includeZero && number === 0)) return;
  target[key] = number;
}

function boundedInteger(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0 || number > MAX_SAFE_TRACE_INTEGER) return null;
  return Math.floor(number);
}

function safeErrorCode(value) {
  const code = String(value || '').trim().toUpperCase();
  return /^[A-Z][A-Z0-9_]{0,79}$/.test(code) ? code : null;
}

function safeReviewKey(value) {
  const key = String(value || 'legacy').trim();
  return key.slice(0, 200) || 'legacy';
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
