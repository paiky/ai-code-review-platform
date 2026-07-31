import assert from 'node:assert/strict';
import test from 'node:test';

import {
  GOVERNANCE_SCHEMA_VERSION,
  normalizeGovernanceSnapshot,
  normalizeRuntimeSnapshot,
  RUNTIME_SCHEMA_VERSION,
  snapshotFreshness
} from '../src/command-center/commandCenterModel.js';


const NOW = Date.parse('2026-07-31T02:00:10Z');


test('runtime v1 model normalizes stable flow ids and bounded collections', () => {
  const runtime = normalizeRuntimeSnapshot({
    schemaVersion: RUNTIME_SCHEMA_VERSION,
    generatedAt: '2026-07-31T02:00:00Z',
    intake: { taskCount: 12, activeTaskCount: 2 },
    scheduler: { activeJobCount: 2, queuedJobCount: 1, runningJobCount: 1 },
    activeTasks: [{ taskId: 41, projectId: 7, projectName: 'Core', stage: 'MODEL_CALLING' }],
    activeFlows: [{
      id: 'damaged-id',
      taskId: 41,
      reviewKey: 'agent-main',
      requestedEngine: 'AGENT',
      effectiveEngine: 'STANDARD_FALLBACK',
      fallback: true,
      status: 'FALLBACK',
      stage: 'FALLBACK',
      stageSource: 'AI_RESULT',
      contextStatusCounts: { INSUFFICIENT: 2 }
    }],
    agent: {
      activeFlowCount: 1,
      workerPool: {
        enabled: true,
        onlineCount: 1,
        workers: [{ workerId: 'w1', state: 'BUSY', online: true, capacity: 1 }]
      },
      queueMetrics: { queued: 1, utilizationPercent: 100 }
    },
    providersObserved: [{ providerCode: 'DS', providerName: 'DeepSeek', status: 'ACTIVE' }],
    alerts: [{ id: 'FALLBACK:1', type: 'FALLBACK', taskId: 41, navigationTarget: '/tasks/41' }],
    coverage: { phase: 'PHASE_1', truncated: false }
  }, { now: NOW });

  assert.equal(runtime.schemaCompatible, true);
  assert.equal(runtime.freshness, 'FRESH');
  assert.equal(runtime.activeFlows[0].id, '41:agent-main');
  assert.equal(runtime.activeFlows[0].fallback, true);
  assert.deepEqual(runtime.activeFlows[0].contextStatusCounts, { INSUFFICIENT: 2 });
  assert.equal(runtime.agent.workerPool.workers[0].state, 'BUSY');
  assert.equal(runtime.providersObserved[0].status, 'ACTIVE');
  assert.equal(runtime.alerts[0].navigationTarget, '/tasks/41');
});


test('runtime model safely handles damaged payload and unknown enums', () => {
  const runtime = normalizeRuntimeSnapshot({
    schemaVersion: 'command-center-runtime-v2',
    generatedAt: 'broken',
    activeFlows: [{
      taskId: 9,
      reviewKey: 'future',
      status: 'THINKING',
      requestedEngine: 'FUTURE',
      stage: 'FUTURE_STAGE'
    }],
    providersObserved: [{ providerCode: 'P', status: 'HEALTHY' }],
    alerts: [{ navigationTarget: 'https://unsafe.invalid' }]
  }, { now: NOW });

  assert.equal(runtime.schemaCompatible, false);
  assert.equal(runtime.freshness, 'EMPTY');
  assert.equal(runtime.activeFlows[0].status, 'RUNNING');
  assert.equal(runtime.activeFlows[0].id, '9:future');
  assert.equal(runtime.providersObserved[0].status, 'NO_RECENT_DATA');
  assert.equal(runtime.alerts[0].navigationTarget, null);
});


test('freshness thresholds distinguish runtime and governance age', () => {
  assert.equal(snapshotFreshness('2026-07-31T02:00:00Z', 15_000, NOW), 'FRESH');
  assert.equal(snapshotFreshness('2026-07-31T01:59:54Z', 15_000, NOW), 'STALE');
  assert.equal(snapshotFreshness('2026-07-31T01:58:00Z', 180_000, NOW), 'FRESH');
  assert.equal(snapshotFreshness(null, 15_000, NOW), 'EMPTY');
});


test('governance model preserves explicit scopes, coverage and sample gate', () => {
  const governance = normalizeGovernanceSnapshot({
    schemaVersion: GOVERNANCE_SCHEMA_VERSION,
    generatedAt: '2026-07-31T02:00:00Z',
    ruleAnalysis: { scope: 'WINDOW', riskItemCount: 4 },
    findingRisk: { scope: 'WINDOW', severityCounts: { CRITICAL: 2 } },
    feedback: { scope: 'ALL_TIME', pendingCount: 3 },
    evaluation: {
      scope: 'ALL_TIME',
      caseCount: 28,
      acceptance: { totalCount: 2, latestStatus: 'PASSED' },
      agentSampleGate: { annotatedSampleCount: 28, requiredSampleCount: 30, ready: false }
    },
    policies: { scope: 'ALL_TIME', candidateCount: 5 },
    coverage: { phase: 'PHASE_1', truncated: true, scanned: { findingResults: 2000 } }
  }, { now: NOW });

  assert.equal(governance.schemaCompatible, true);
  assert.equal(governance.ruleAnalysis.scope, 'WINDOW');
  assert.equal(governance.feedback.scope, 'ALL_TIME');
  assert.equal(governance.evaluation.acceptance.latestStatus, 'PASSED');
  assert.equal(governance.evaluation.agentSampleGate.ready, false);
  assert.equal(governance.coverage.truncated, true);
  assert.equal(governance.coverage.scanned.findingResults, 2000);
});
