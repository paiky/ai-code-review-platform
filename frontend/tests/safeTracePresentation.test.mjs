import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildSafeTraceEvent,
  buildSafeTraceSummary,
  buildSafeTraceViewModel,
  groupSafeTraceEvents
} from '../src/safeTracePresentation.js';

function traceEvent(id, phase, detail) {
  return { id, phase, detail: JSON.stringify(detail) };
}

test('builds a serializable SafeTraceViewModel without prohibited fields or values', () => {
  const sensitiveValues = [
    'SECRET_PROMPT',
    'SECRET_QUERY',
    'SECRET_PATH',
    'SECRET_ARGUMENTS',
    'SECRET_INPUT',
    'SECRET_OUTPUT',
    'SECRET_REASONING',
    'SECRET_RESPONSE',
    'SECRET_FAILURE',
    'SECRET_WORKER'
  ];
  const events = [traceEvent(1, 'AGENT_TOOL_ACTIVITY', {
    runId: 12,
    claimAttempt: 1,
    sequence: 3,
    activity: 'READ_FILE_RANGE',
    status: 'SUCCESS',
    durationMs: 8,
    itemCount: 2,
    sourceBytes: 512,
    errorCode: 'SAFE_ERROR',
    prompt: sensitiveValues[0],
    query: sensitiveValues[1],
    queryHash: 'SECRET_HASH',
    path: sensitiveValues[2],
    pathSummary: [{ suffix: '.py', pathHash: 'SECRET_PATH_HASH' }],
    arguments: sensitiveValues[3],
    input: sensitiveValues[4],
    output: sensitiveValues[5],
    reasoning: sensitiveValues[6],
    rawResponse: sensitiveValues[7],
    failureMessage: sensitiveValues[8],
    workerId: sensitiveValues[9],
    displayLabel: 'SECRET_LABEL',
    message: 'SECRET_MESSAGE'
  })];

  const viewModel = buildSafeTraceViewModel({
    reviewKey: 'agent-review',
    engineKind: 'AGENT',
    events,
    agentSummary: {
      runId: 12,
      claimAttempt: 1,
      terminal: false,
      toolCallCount: 4,
      evidenceCallsUsed: 2,
      sourceBytesReturned: 512,
      effectiveBudgets: { maxToolCalls: 40, maxEvidenceCalls: 10, maxSourceBytes: 200000 }
    },
    agentDurationMs: 181000
  });

  assert.deepEqual(viewModel.events, [{
    sequence: 3,
    activityType: 'READ_FILE_RANGE',
    status: 'SUCCESS',
    durationMs: 8,
    itemCount: 2,
    sourceBytes: 512,
    errorCode: 'SAFE_ERROR'
  }]);
  assert.equal(viewModel.state, 'AVAILABLE');
  assert.equal(viewModel.summary.agentDurationMs, 181000);
  const serialized = JSON.stringify(viewModel);
  for (const value of [...sensitiveValues, 'SECRET_HASH', 'SECRET_PATH_HASH', 'SECRET_LABEL', 'SECRET_MESSAGE']) {
    assert.equal(serialized.includes(value), false, value);
  }
  for (const field of [
    'detail', 'message', 'displayLabel', 'query', 'queryHash', 'path', 'pathSummary',
    'arguments', 'input', 'output', 'reasoning', 'prompt', 'rawResponse',
    'failureMessage', 'workerId'
  ]) {
    assert.equal(Object.hasOwn(viewModel.events[0], field), false, field);
  }
});

test('normalizes unknown status and drops missing sequence unknown activity and unsafe numbers', () => {
  const unknownStatus = buildSafeTraceEvent(traceEvent(1, 'AGENT_TOOL_ACTIVITY', {
    runId: 1,
    sequence: 1,
    activity: 'SEARCH_CODE',
    status: 'BACKEND_SECRET_STATUS',
    durationMs: -1,
    itemCount: Number.MAX_SAFE_INTEGER,
    sourceBytes: 'not-a-number',
    errorCode: 'unsafe code'
  }));
  assert.deepEqual(unknownStatus, {
    sequence: 1,
    activityType: 'SEARCH_CODE',
    status: 'UNKNOWN'
  });
  assert.equal(buildSafeTraceEvent(traceEvent(2, 'AGENT_TOOL_ACTIVITY', {
    runId: 1,
    activity: 'SEARCH_CODE',
    status: 'SUCCESS'
  })), null);
  assert.equal(buildSafeTraceEvent(traceEvent(3, 'AGENT_TOOL_ACTIVITY', {
    runId: 1,
    sequence: 2,
    activity: 'SECRET_ACTIVITY',
    status: 'SUCCESS'
  })), null);
});

test('marks mixed valid and invalid scoped records partial and never invents an order', () => {
  const viewModel = buildSafeTraceViewModel({
    reviewKey: 'partial-review',
    engineKind: 'AGENT',
    events: [
      traceEvent(1, 'AGENT_ANALYZING', { runId: 2, claimAttempt: 1, sequence: 0 }),
      traceEvent(2, 'AGENT_TOOL_ACTIVITY', {
        runId: 2,
        claimAttempt: 1,
        activity: 'SEARCH_CODE',
        status: 'SUCCESS'
      })
    ],
    agentSummary: { runId: 2, claimAttempt: 1 }
  });
  assert.equal(viewModel.state, 'PARTIAL');
  assert.deepEqual(viewModel.events, [{
    sequence: 0,
    activityType: 'ANALYZING',
    status: 'STARTED'
  }]);

  const unavailable = buildSafeTraceViewModel({
    reviewKey: 'history',
    engineKind: 'AGENT',
    events: [traceEvent(3, 'AGENT_FINISHED', { runId: 3 })],
    agentSummary: { runId: 3, claimAttempt: 0, terminal: true }
  });
  assert.equal(unavailable.state, 'UNAVAILABLE');
  assert.deepEqual(unavailable.events, []);
});

test('keeps only the latest run and claim attempt and separates submit from finished', () => {
  const viewModel = buildSafeTraceViewModel({
    reviewKey: 'reclaimed-review',
    engineKind: 'FALLBACK',
    events: [
      traceEvent(1, 'AGENT_TOOL_ACTIVITY', {
        runId: 8, claimAttempt: 1, sequence: 1, activity: 'SEARCH_CODE', status: 'SUCCESS'
      }),
      traceEvent(2, 'AGENT_RECLAIMED', {
        runId: 8, claimAttempt: 2, sequence: 0, workerId: 'SECRET_OLD_WORKER'
      }),
      traceEvent(3, 'AGENT_SUBMITTING', {
        runId: 8, claimAttempt: 2, sequence: 1, attempt: 1
      }),
      traceEvent(4, 'AGENT_REVIEW_SUBMITTED', {
        runId: 8, claimAttempt: 2, sequence: 2, attempt: 1
      }),
      traceEvent(5, 'AGENT_FINISHED', {
        runId: 8, claimAttempt: 2, sequence: 3
      })
    ],
    agentSummary: { runId: 8, claimAttempt: 2, terminal: true, turnCount: 5 }
  });

  assert.deepEqual(viewModel.events.map(item => [item.sequence, item.activityType, item.status]), [
    [0, 'RECLAIMED', 'WARNING'],
    [1, 'SUBMIT_REVIEW', 'STARTED'],
    [2, 'SUBMIT_REVIEW', 'SUCCESS'],
    [3, 'FINISHED', 'SUCCESS']
  ]);
  assert.equal(JSON.stringify(viewModel).includes('SECRET_OLD_WORKER'), false);
});

test('groups only adjacent matching activity and status while aggregating bounded counters', () => {
  const grouped = groupSafeTraceEvents([
    { sequence: 1, activityType: 'READ_FILE_RANGE', status: 'SUCCESS', durationMs: 2, itemCount: 3 },
    { sequence: 2, activityType: 'READ_FILE_RANGE', status: 'SUCCESS', durationMs: 4, itemCount: 5 },
    { sequence: 3, activityType: 'SEARCH_CODE', status: 'SUCCESS' },
    { sequence: 4, activityType: 'READ_FILE_RANGE', status: 'SUCCESS', durationMs: 1 },
    { sequence: 6, activityType: 'READ_FILE_RANGE', status: 'SUCCESS', durationMs: 2 }
  ]);
  assert.deepEqual(grouped, [
    {
      sequence: 1,
      sequenceEnd: 2,
      groupCount: 2,
      activityType: 'READ_FILE_RANGE',
      status: 'SUCCESS',
      durationMs: 6,
      itemCount: 8
    },
    { sequence: 3, activityType: 'SEARCH_CODE', status: 'SUCCESS' },
    { sequence: 4, activityType: 'READ_FILE_RANGE', status: 'SUCCESS', durationMs: 1 },
    { sequence: 6, activityType: 'READ_FILE_RANGE', status: 'SUCCESS', durationMs: 2 }
  ]);
});

test('keeps quotas optional and hides running model turns instead of manufacturing zero', () => {
  assert.deepEqual(buildSafeTraceSummary({
    runId: 5,
    claimAttempt: 1,
    terminal: false,
    toolCallCount: 0,
    turnCount: 0,
    effectiveBudgets: { maxTurns: 18, maxToolCalls: 40 }
  }), {
    runId: 5,
    claimAttempt: 1,
    toolCallsLimit: 40,
    modelTurnsLimit: 18
  });
  assert.deepEqual(buildSafeTraceSummary({ runId: 0, claimAttempt: 0 }), {});
  assert.equal(buildSafeTraceViewModel({ engineKind: 'STANDARD', events: [] }), null);
});
