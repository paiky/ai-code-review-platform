import { buildFindingRiskCounts, isTerminalReviewStatus } from './reviewResultPresentation.js';

const inputPhases = new Set([
  'AGENT_INPUT_BUILD_STARTED',
  'AGENT_INPUT_BUILD_COMPLETED',
  'AGENT_INPUT_BUILD_FAILED',
  'REQUEST_BUILT',
  'CONTEXT_PACK_BUILT'
]);

const transferPhases = new Set([
  'AGENT_PREFLIGHT_FAILED',
  'AGENT_FALLBACK',
  'AGENT_FALLBACK_QUEUED'
]);

const standardContextPhases = new Set([
  'CONTEXT_PACK_BUILT',
  'LOCAL_REPO_PREPARE_STARTED',
  'LOCAL_REPO_PREPARED',
  'LOCAL_REPO_PREPARE_FAILED',
  'LOCAL_CONTEXT_RETRIEVED',
  'LOCAL_CONTEXT_RETRIEVE_FAILED'
]);

function boundedCount(value) {
  return Number.isSafeInteger(value) && value >= 0 && value <= 2_147_483_647 ? value : null;
}

function byRecordedOrder(left, right) {
  if (left.id !== null && right.id !== null) return left.id - right.id;
  return (left.createdAt || '').localeCompare(right.createdAt || '');
}

function afterTransfer(event, transfer) {
  if (event.id !== null && transfer.id !== null) return event.id > transfer.id;
  return Boolean(event.createdAt && transfer.createdAt && event.createdAt > transfer.createdAt);
}

export function buildReviewExecutionPresentation(journey, result) {
  const kind = journey?.engineKind;
  const isAgent = kind === 'AGENT' || kind === 'FALLBACK';
  const isFallback = kind === 'FALLBACK';
  const stages = Array.isArray(journey?.stages) ? journey.stages : [];
  const events = [
    ...stages.flatMap(stage => stage.events
      .filter(event => event.phase && !event.auxiliary)
      .map(event => ({ ...event, stageId: stage.id }))),
    ...(journey?.otherEvents || []).map(event => {
      const isProvider = event.phase.startsWith('HTTP_RESPONSE_') || event.phase === 'PROVIDER_FAILED';
      return { ...event, stageId: isProvider ? 'model-review' : null };
    })
  ].sort(byRecordedOrder);
  const seen = new Set();
  const recordedEvents = events.filter(event => {
    const key = event.id ?? [event.phase, event.createdAt, event.level].join(':');
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const transfer = isFallback
    ? recordedEvents.find(event => transferPhases.has(event.phase)) || null
    : null;
  const standardEvents = recordedEvents.filter(event => {
    if (event.phase.startsWith('AGENT_')) return false;
    if (transfer) return afterTransfer(event, transfer);
    return !isFallback || !event.phase.startsWith('LOCAL_REPO_');
  });
  const standard = kind === 'STANDARD' || isFallback
    ? [
      { id: 'context', title: '上下文准备', events: standardEvents.filter(event => standardContextPhases.has(event.phase)) },
      { id: 'provider', title: 'Provider 请求与响应', events: standardEvents.filter(event => event.stageId === 'model-review') },
      { id: 'parse-save', title: '解析与保存', events: standardEvents.filter(event => event.stageId === 'parse-save') }
    ].filter(section => section.events.length > 0)
    : [];
  const context = stages.find(stage => stage.id === 'context')?.details?.context;
  const builtStandardContext = standard.some(section => (
    section.id === 'context' && section.events.some(event => event.phase === 'CONTEXT_PACK_BUILT')
  ));
  const input = recordedEvents.filter(event => (
    inputPhases.has(event.phase)
    && (isAgent || !event.phase.startsWith('AGENT_'))
    && (!transfer || event.phase.startsWith('AGENT_') || afterTransfer(event, transfer))
  ));
  const safeTrace = isAgent
    ? stages.find(stage => stage.id === 'model-review')?.details?.safeTrace
    : null;
  const agentConversation = isAgent ? journey?.agentConversation : null;
  return {
    input,
    agentInput: isAgent ? journey?.agentInput : null,
    agentInstructions: isAgent ? journey?.agentInstructions : null,
    standardInput: builtStandardContext && context ? {
      changedFileCount: context.contextPack.changedFileCount,
      signalCount: context.planner.signalCount,
      includedSnippetCount: context.retriever.includedSnippetCount,
      unavailableContextCount: context.requestedContext.unavailable,
      notInjectedEvidenceCount: context.budgetCuts.notInjectedEvidenceCount,
      truncated: context.budgetCuts.truncated || context.contextPack.truncated
    } : null,
    standardInstructions: journey?.standardInstructions,
    standard,
    agentConversation,
    agentOtherActivities: agentConversation?.otherActivities.filter(event => (
      event.activityType !== 'FALLBACK' || !transfer
    )) || [],
    agentEvents: safeTrace?.events.filter(event => event.activityType !== 'FALLBACK' || !transfer) || [],
    agentTracePartial: safeTrace?.state === 'PARTIAL',
    transfer: isFallback ? {
      event: transfer,
      errorCode: [journey?.agentSummary?.failureCode, result?.agentRunSummary?.failureCode]
        .find(code => typeof code === 'string' && /^[A-Z][A-Z0-9_]{0,79}$/.test(code)) || null
    } : null,
    final: buildFinalResponse(result, journey)
  };
}

function buildFinalResponse(result, journey) {
  const resultStatus = String(result?.status || '').toUpperCase();
  const status = ['COMPLETED', 'SUCCESS'].includes(resultStatus)
    ? 'SUCCESS'
    : resultStatus === 'CANCELED' ? 'CANCELLED' : resultStatus;
  const hasSavedResult = Number.isSafeInteger(result?.id)
    && result.id > 0
    && isTerminalReviewStatus(status);
  const findings = result?.findings;
  return {
    status: hasSavedResult ? status : journey?.status,
    hasSavedResult,
    issueCount: hasSavedResult && status === 'SUCCESS'
      ? boundedCount(result.findingCount) ?? (Array.isArray(findings) ? findings.length : null)
      : null,
    riskCounts: hasSavedResult && status === 'SUCCESS' && Array.isArray(findings)
      ? buildFindingRiskCounts(findings)
      : null,
    missingContextCount: hasSavedResult && status === 'SUCCESS' && Array.isArray(findings)
      ? findings.filter(item => (
        (Array.isArray(item?.missingContext) && item.missingContext.length > 0)
        || ['PARTIAL', 'INSUFFICIENT'].includes(item?.contextStatus)
      )).length
      : null
  };
}
