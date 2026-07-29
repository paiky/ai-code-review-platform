import assert from 'node:assert/strict';
import test from 'node:test';

import {
  collectAgentTraceEvents,
  formatAgentTraceDetail
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
