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


test('runtime v2 model normalizes stable flow ids and bounded collections', () => {
  const runtime = normalizeRuntimeSnapshot({
    schemaVersion: RUNTIME_SCHEMA_VERSION,
    generatedAt: '2026-07-31T02:00:00Z',
    intake: { taskCount: 12, activeTaskCount: 2 },
    scheduler: { activeJobCount: 2, queuedJobCount: 1, runningJobCount: 1 },
    activeTasks: [{
      taskId: 41,
      projectId: 7,
      projectName: 'Core',
      stage: 'MODEL_CALLING',
      authorName: 'Mayn',
      authorUsername: 'mayn',
      externalUrl: 'https://gitlab.example.com/core/-/merge_requests/41',
      repositoryUrl: 'https://gitlab.example.com/core',
      sourceBranch: 'feature/live-topology',
      targetBranch: 'main',
      commitSha: 'abcdef123456'
    }],
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
    providersObserved: [{
      providerCode: 'DS',
      providerName: 'DeepSeek',
      status: 'ACTIVE',
      recentSuccessCount: 8,
      recentFailureCount: 2,
      lastObservedAt: '2026-07-31T01:59:58Z'
    }],
    alerts: [{ id: 'FALLBACK:1', type: 'FALLBACK', taskId: 41, navigationTarget: '/tasks/41' }],
    todayResults: {
      status: 'LIVE',
      scope: 'TODAY',
      date: '2026-07-31',
      timezone: 'UTC+08:00',
      from: '2026-07-30T16:00:00Z',
      to: '2026-07-31T02:00:00Z',
      totalCount: 7,
      completedCount: 5,
      successCount: 4,
      failureCount: 1,
      skippedCount: 0,
      runningCount: 2,
      otherCount: 0,
      statusCounts: { SUCCESS: 4, FAILED: 1, RUNNING: 2 }
    },
    coverage: { phase: 'PHASE_1', truncated: false }
  }, { now: NOW });

  assert.equal(runtime.schemaCompatible, true);
  assert.equal(runtime.freshness, 'FRESH');
  assert.equal(runtime.activeFlows[0].id, '41:agent-main');
  assert.equal(runtime.activeFlows[0].fallback, true);
  assert.equal(runtime.activeFlows[0].statusRecognized, true);
  assert.equal(runtime.activeFlows[0].stageRecognized, true);
  assert.deepEqual(runtime.activeFlows[0].contextStatusCounts, { INSUFFICIENT: 2 });
  assert.equal(runtime.activeTasks[0].authorName, 'Mayn');
  assert.equal(runtime.activeTasks[0].sourceBranch, 'feature/live-topology');
  assert.equal(runtime.activeTasks[0].commitSha, 'abcdef123456');
  assert.equal(runtime.todayResults.date, '2026-07-31');
  assert.equal(runtime.todayResults.from, '2026-07-30T16:00:00.000Z');
  assert.equal(runtime.todayResults.completedCount, 5);
  assert.deepEqual(runtime.todayResults.statusCounts, { SUCCESS: 4, FAILED: 1, RUNNING: 2 });
  assert.equal(runtime.agent.workerPool.workers[0].state, 'BUSY');
  assert.equal(runtime.providersObserved[0].status, 'ACTIVE');
  assert.equal(runtime.providersObserved[0].recentSuccessCount, 8);
  assert.equal(runtime.providersObserved[0].recentFailureCount, 2);
  assert.equal(runtime.providersObserved[0].lastObservedAt, '2026-07-31T01:59:58.000Z');
  assert.equal(runtime.alerts[0].navigationTarget, '/tasks/41');
});


test('runtime model safely handles damaged payload and unknown enums', () => {
  const runtime = normalizeRuntimeSnapshot({
    schemaVersion: 'command-center-runtime-v3',
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
  assert.equal(runtime.activeFlows[0].statusRecognized, false);
  assert.equal(runtime.activeFlows[0].stage, 'UNKNOWN');
  assert.equal(runtime.activeFlows[0].stageRecognized, false);
  assert.equal(runtime.activeFlows[0].id, '9:future');
  assert.equal(runtime.providersObserved[0].status, 'NO_RECENT_DATA');
  assert.equal(runtime.alerts[0].navigationTarget, null);
  assert.equal(runtime.todayResults, null);
});


test('runtime v2 preserves truthful lane items and engine-specific next review', () => {
  const runtime = normalizeRuntimeSnapshot({
    schemaVersion: RUNTIME_SCHEMA_VERSION,
    generatedAt: '2026-07-31T02:00:00Z',
    reviewLanes: {
      standard: {
        zoneKey: 'standard',
        capacity: 10,
        runningCount: 2,
        queuedCount: 4,
        utilizationPercent: 20,
        runningItems: [{
          jobId: 1,
          taskId: 41,
          reviewKey: 'fallback-main',
          projectName: 'paycenter',
          displayName: 'Fallback Review',
          requestedEngine: 'AGENT',
          effectiveEngine: 'STANDARD_FALLBACK',
          fallback: true,
          status: 'RUNNING',
          stage: 'FALLBACK'
        }],
        nextQueued: { jobId: 2, taskId: 42, reviewKey: 'next-standard' },
        runningItemsTruncated: false,
        queueOrder: 'priority ASC, queuedAt ASC, id ASC'
      },
      agent: {
        zoneKey: 'agent',
        capacity: 3,
        runningCount: 1,
        queuedCount: 2,
        utilizationPercent: 33,
        runningItems: [],
        nextQueued: { jobId: 3, taskId: 43, reviewKey: 'next-agent', workerId: null },
        queueOrder: 'priority DESC, queuedAt ASC, id ASC'
      }
    }
  }, { now: NOW });

  assert.equal(runtime.reviewLanes.standard.capacity, 10);
  assert.equal(runtime.reviewLanes.standard.runningItems[0].fallback, true);
  assert.equal(runtime.reviewLanes.standard.nextQueued.reviewKey, 'next-standard');
  assert.equal(runtime.reviewLanes.agent.nextQueued.reviewKey, 'next-agent');
  assert.equal(runtime.reviewLanes.agent.capacity, 3);
});


test('runtime v1 fallback never invents a next review from active flow order', () => {
  const runtime = normalizeRuntimeSnapshot({
    schemaVersion: 'command-center-runtime-v1',
    generatedAt: '2026-07-31T02:00:00Z',
    scheduler: { runningJobCount: 3, queuedJobCount: 5 },
    activeFlows: [{
      taskId: 9,
      reviewKey: 'latest-updated',
      requestedEngine: 'STANDARD',
      status: 'RUNNING',
      stage: 'MODEL_CALLING'
    }],
    agent: { queueMetrics: { running: 1, queued: 2, onlineCapacity: 2 } }
  }, { now: NOW });

  assert.equal(runtime.schemaCompatible, true);
  assert.equal(runtime.reviewLanes.standard.runningCount, 2);
  assert.equal(runtime.reviewLanes.standard.queuedCount, 3);
  assert.equal(runtime.reviewLanes.standard.nextQueued, null);
  assert.equal(runtime.reviewLanes.agent.nextQueued, null);
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
    findingRisk: {
      scope: 'WINDOW',
      findingCount: 9,
      affectedTaskCount: 4,
      highestRisk: 'CRITICAL',
      severityCounts: { CRITICAL: 2 }
    },
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
  assert.equal(governance.findingRisk.findingCount, 9);
  assert.equal(governance.findingRisk.affectedTaskCount, 4);
  assert.equal(governance.findingRisk.highestRisk, 'CRITICAL');
  assert.equal(governance.evaluation.acceptance.latestStatus, 'PASSED');
  assert.equal(governance.evaluation.agentSampleGate.ready, false);
  assert.equal(governance.coverage.truncated, true);
  assert.equal(governance.coverage.scanned.findingResults, 2000);
});
