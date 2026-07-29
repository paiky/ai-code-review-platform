import assert from 'node:assert/strict';
import test from 'node:test';

import {
  collectAgentTraceEvents,
  formatAgentTraceDetail,
  groupAgentTraceEvents,
  summarizeAgentTrace
} from '../src/agentReviewTrace.js';


test('keeps Standard and old Agent tasks compatible when no safe trace exists', () => {
  const standard = [
    { id: 1, phase: 'STARTED', detail: '{}' },
    { id: 2, phase: 'DEEPSEEK_RESPONSE', detail: '{}' }
  ];
  const oldAgent = [
    { id: 3, phase: 'AGENT_QUEUED', detail: '{}' },
    { id: 4, phase: 'AGENT_FINISHED', detail: '{}' }
  ];

  assert.deepEqual(collectAgentTraceEvents(standard), []);
  assert.deepEqual(collectAgentTraceEvents(oldAgent), []);
});


test('deduplicates and orders Agent trace events by runId and sequence', () => {
  const events = [
    { id: 3, phase: 'AGENT_SUBMITTING', detail: '{"runId":7,"sequence":2}' },
    { id: 1, phase: 'AGENT_ANALYZING', detail: '{"runId":7,"sequence":0}' },
    { id: 2, phase: 'AGENT_TOOL_ACTIVITY', detail: '{"runId":7,"sequence":1}' },
    { id: 4, phase: 'AGENT_TOOL_ACTIVITY', detail: '{"runId":7,"sequence":1}' }
  ];

  assert.deepEqual(
    collectAgentTraceEvents(events).map(event => event.id),
    [1, 2, 3]
  );
});


test('formats only the visible safe whitelist and hides hashes and raw fields', () => {
  const visible = formatAgentTraceDetail(JSON.stringify({
    runId: 7,
    sequence: 1,
    activity: 'SEARCH_CODE',
    status: 'SUCCESS',
    durationMs: 2,
    itemCount: 1,
    sourceBytes: 20,
    queryHash: '0123456789abcdef',
    query: 'SECRET_QUERY',
    source: 'SECRET_SOURCE',
    path: 'D:/private/source.py',
    pathSummary: [
      { pathHash: 'fedcba9876543210', suffix: '.py', depth: 3 }
    ],
    reviewBudget: {
      phase: 'DISCOVERY',
      evidenceCallsUsed: 1,
      evidenceCallsRemaining: 9,
      sourceBytesRemaining: 199980,
      mustSubmit: false
    }
  }));

  assert.match(visible, /活动：搜索代码/);
  assert.match(visible, /文件类型：\.py（目录深度 3）/);
  assert.doesNotMatch(visible, /0123456789abcdef|fedcba9876543210/);
  assert.doesNotMatch(visible, /SECRET_|D:\/private/);
});


test('summarizes safe heartbeat budgets and reports delayed progress after 45 seconds', () => {
  const heartbeatAt = '2026-07-29T12:00:00+08:00';
  const summary = summarizeAgentTrace([
    {
      id: 1,
      phase: 'AGENT_ANALYZING',
      createdAt: heartbeatAt,
      detail: '{"runId":7,"sequence":0,"activity":"ANALYZING"}'
    },
    {
      id: 2,
      phase: 'AGENT_HEARTBEAT',
      createdAt: heartbeatAt,
      detail: JSON.stringify({
        runId: 7,
        heartbeatSequence: 3,
        toolCallCount: 4,
        evidenceCallsUsed: 2,
        sourceBytesReturned: 12000,
        reviewBudget: {
          phase: 'DISCOVERY',
          evidenceCallsUsed: 2,
          evidenceCallsRemaining: 8
        },
        effectiveBudgets: {
          maxTurns: 12,
          maxToolCalls: 40,
          maxSourceBytes: 200000,
          timeoutSeconds: 600,
          inlineDiffBytes: 200000,
          maxEvidenceCalls: 10,
          convergeAtCalls: 8,
          submitByTurn: 9
        },
        query: 'SECRET_QUERY',
        source: 'SECRET_SOURCE'
      })
    }
  ], Date.parse(heartbeatAt) + 46_000);

  assert.equal(summary.phase, 'AGENT_ANALYZING');
  assert.equal(summary.progressMayBeDelayed, true);
  assert.equal(summary.toolCallCount, 4);
  assert.equal(summary.evidenceCallsUsed, 2);
  assert.equal(summary.turnCount, null);
  assert.equal(summary.effectiveBudgets.maxTurns, 12);
  assert.equal(JSON.stringify(summary).includes('SECRET_'), false);
});


test('orders Agent terminal status after tools and exposes final turns', () => {
  const events = [
    {
      id: 4,
      phase: 'AGENT_HEARTBEAT',
      createdAt: '2026-07-29T11:00:00+08:00',
      detail: JSON.stringify({
        runId: 8,
        heartbeatSequence: 2,
        toolCallCount: 4
      })
    },
    {
      id: 3,
      phase: 'AGENT_FINISHED',
      detail: JSON.stringify({
        runId: 8,
        status: 'SUCCEEDED',
        turnCount: 5,
        toolCallCount: 6,
        effectiveBudgets: {
          maxTurns: 14,
          maxToolCalls: 40,
          maxSourceBytes: 200000,
          timeoutSeconds: 600,
          inlineDiffBytes: 200000,
          maxEvidenceCalls: 10,
          convergeAtCalls: 8,
          submitByTurn: 9
        }
      })
    },
    {
      id: 1,
      phase: 'AGENT_ANALYZING',
      detail: '{"runId":8,"sequence":0,"activity":"ANALYZING"}'
    },
    {
      id: 2,
      phase: 'AGENT_TOOL_ACTIVITY',
      detail: '{"runId":8,"sequence":1,"activity":"SEARCH_CODE","status":"SUCCESS"}'
    }
  ];

  assert.deepEqual(
    collectAgentTraceEvents(events).map(event => event.phase),
    ['AGENT_ANALYZING', 'AGENT_TOOL_ACTIVITY', 'AGENT_FINISHED']
  );
  const summary = summarizeAgentTrace(events);
  assert.equal(summary.terminal, true);
  assert.equal(summary.turnCount, 5);
  assert.equal(summary.toolCallCount, 6);
  assert.equal(summary.progressMayBeDelayed, false);
});


test('groups consecutive duplicate tool activities without exposing raw detail', () => {
  const grouped = groupAgentTraceEvents([
    {
      id: 1,
      phase: 'AGENT_TOOL_ACTIVITY',
      detail: JSON.stringify({
        runId: 9,
        sequence: 1,
        activity: 'READ_FILE_RANGE',
        status: 'SUCCESS',
        durationMs: 2,
        itemCount: 3,
        sourceBytes: 20,
        pathSummary: [{ suffix: '.py', depth: 2, pathHash: 'secret-hash' }]
      })
    },
    {
      id: 2,
      phase: 'AGENT_TOOL_ACTIVITY',
      detail: JSON.stringify({
        runId: 9,
        sequence: 2,
        activity: 'READ_FILE_RANGE',
        status: 'SUCCESS',
        durationMs: 4,
        itemCount: 5,
        sourceBytes: 30,
        query: 'SECRET_QUERY'
      })
    }
  ]);

  assert.equal(grouped.length, 1);
  const visible = formatAgentTraceDetail(grouped[0].detail);
  assert.match(visible, /序号：1～2/);
  assert.match(visible, /合并活动：2 次/);
  assert.match(visible, /耗时：6 ms/);
  assert.doesNotMatch(visible, /secret-hash|SECRET_QUERY/);
});


test('shows only the latest claim attempt and safely formats lease recovery', () => {
  const events = [
    {
      id: 1,
      phase: 'AGENT_ANALYZING',
      detail: '{"runId":10,"claimAttempt":1,"sequence":0,"activity":"ANALYZING"}'
    },
    {
      id: 2,
      phase: 'AGENT_TOOL_ACTIVITY',
      detail: '{"runId":10,"claimAttempt":1,"sequence":1,"activity":"SEARCH_CODE"}'
    },
    {
      id: 3,
      phase: 'AGENT_RECLAIMED',
      detail: JSON.stringify({
        runId: 10,
        claimAttempt: 2,
        reasonCode: 'LEASE_EXPIRED',
        workerId: 'SECRET_WORKER'
      })
    },
    {
      id: 4,
      phase: 'AGENT_ANALYZING',
      detail: '{"runId":10,"claimAttempt":2,"sequence":0,"activity":"ANALYZING"}'
    },
    {
      id: 5,
      phase: 'AGENT_HEARTBEAT',
      createdAt: '2026-07-29T12:00:00+08:00',
      detail: '{"runId":10,"claimAttempt":2,"heartbeatSequence":0}'
    }
  ];

  const collected = collectAgentTraceEvents(events);
  assert.deepEqual(
    collected.map(event => event.phase),
    ['AGENT_RECLAIMED', 'AGENT_ANALYZING']
  );
  const summary = summarizeAgentTrace(events);
  assert.equal(summary.runId, 10);
  assert.equal(summary.claimAttempt, 2);
  const visible = formatAgentTraceDetail(
    collected[0].detail,
    collected[0].phase
  );
  assert.match(visible, /第 2 次/);
  assert.match(visible, /上一租约已过期/);
  assert.doesNotMatch(visible, /SECRET_WORKER/);
});
