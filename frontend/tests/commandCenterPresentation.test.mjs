import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildCommandCenterPresentation,
  reviewTaskTarget,
  stageLabel
} from '../src/command-center/commandCenterPresentation.js';


test('H1 presentation exposes the frozen homepage contract from a fresh Runtime v2 snapshot', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: runtime({
      agent: {
        workerPool: {
          idleCount: 1,
          busyCount: 1,
          drainingCount: 0,
          offlineCount: 1,
          workers: [
            { workerId: 'worker-1', state: 'BUSY', online: true, capacity: 2, activeJobId: 9 },
            { workerId: 'worker-2', state: 'IDLE', online: true, capacity: 1 },
            { workerId: 'worker-3', state: 'IDLE', online: false, capacity: 1 }
          ]
        },
        queueMetrics: { onlineCapacity: 3, oldestQueuedSeconds: 91 }
      },
      providersObserved: [{
        providerCode: 'DS',
        providerName: 'DeepSeek',
        modelName: 'v4',
        status: 'ACTIVE',
        activeFlowCount: 2
      }],
      alerts: [{ id: 'OFFLINE:w3', type: 'WORKER_OFFLINE', navigationTarget: null }],
      reviewLanes: {
        standard: lane('standard', 10, 3, 7, item({ fallback: true })),
        agent: lane('agent', 3, 2, 5, item({ requestedEngine: 'AGENT' }))
      },
      scheduler: { queuedJobCount: 12, runningJobCount: 5 }
    })
  });

  assert.deepEqual(Object.keys(presentation).filter(key => key !== 'map'), [
    'hud',
    'intake',
    'engineSelection',
    'agentLane',
    'standardLane',
    'fallback',
    'resultPersistence',
    'footer',
    'diagnostics'
  ]);
  assert.deepEqual(presentation.hud, {
    freshness: 'FRESH',
    resourceState: 'FRESH',
    generatedAt: '2026-08-03T02:00:00Z',
    totalQueuedJobs: 12,
    totalRunningJobs: 5,
    coverage: {
      status: 'COMPLETE',
      truncated: false,
      bounded: true,
      sections: { activeFlows: 'BOUNDED' },
      diagnostics: []
    },
    providersObserved: [{
      providerCode: 'DS',
      providerName: 'DeepSeek',
      modelName: 'v4',
      status: 'ACTIVE',
      activeFlowCount: 2,
      label: 'DeepSeek / v4'
    }],
    alerts: [{ id: 'OFFLINE:w3', type: 'WORKER_OFFLINE', navigationTarget: null }],
    error: null
  });
  assert.deepEqual(presentation.intake.items.map(item => item.key), [
    'MANUAL', 'MERGE_REQUEST', 'PUSH', 'RETRY'
  ]);
  assert.equal(Object.hasOwn(presentation.intake, 'queuedCount'), false);
  assert.deepEqual(presentation.engineSelection.routes.map(route => route.key), ['AGENT', 'STANDARD']);
  assert.match(presentation.engineSelection.automaticAgentUnavailableDescription, /直接进入 Standard Review/);
  assert.equal(presentation.agentLane.queued, 5);
  assert.equal(presentation.agentLane.running, 2);
  assert.equal(presentation.agentLane.onlineCapacity, 3);
  assert.deepEqual(presentation.agentLane.workerSummary, {
    idle: 1,
    busy: 1,
    draining: 0,
    offline: 1
  });
  assert.equal(presentation.standardLane.capacity, 10);
  assert.equal(presentation.standardLane.providers[0].label, 'DeepSeek / v4');
  assert.equal(presentation.agentLane.visibleRunningItemCount, 0);
  assert.equal(presentation.agentLane.totalRunningItemCount, 2);
  assert.equal(presentation.agentLane.runningItemsTruncated, true);
  assert.equal(presentation.fallback.mode, 'STRUCTURAL_ONLY');
  assert.equal(presentation.resultPersistence.mode, 'STRUCTURAL_ONLY');
  assert.equal(presentation.resultPersistence.navigationTarget, '/tasks');
  assert.deepEqual(presentation.footer.agentCapacity, { running: 2, onlineCapacity: 3 });
  assert.deepEqual(presentation.footer.standardSlots, { running: 3, capacity: 10 });
  assert.equal(presentation.footer.oldestAgentQueueSeconds, 91);
  assert.equal(presentation.footer.alerts.count, 1);
  assert.deepEqual(presentation.diagnostics, []);
  assert.equal(presentation.map.compatibilityMode, 'H1_LEGACY_RENDERER');
});


test('scheduler and lane mismatches preserve both sources and emit diagnostics', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: runtime({
      scheduler: { queuedJobCount: 20, runningJobCount: 9 },
      reviewLanes: {
        standard: lane('standard', 10, 3, 7),
        agent: lane('agent', 0, 2, 5)
      }
    })
  });

  assert.equal(presentation.hud.totalQueuedJobs, 20);
  assert.equal(presentation.hud.totalRunningJobs, 9);
  assert.equal(presentation.standardLane.queued + presentation.agentLane.queued, 12);
  assert.equal(presentation.standardLane.running + presentation.agentLane.running, 5);
  assert.deepEqual(presentation.diagnostics.map(item => item.code), [
    'SCHEDULER_LANE_QUEUED_MISMATCH',
    'SCHEDULER_LANE_RUNNING_MISMATCH'
  ]);
  assert.equal(presentation.hud.coverage.diagnostics, presentation.diagnostics);
});


test('stale truncated snapshot keeps zero capacity, empty providers and empty next reviews truthful', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: runtime({
      freshness: 'STALE',
      coverage: { truncated: true, sections: { activeFlows: 'BOUNDED' } },
      providersObserved: [],
      scheduler: { queuedJobCount: 0, runningJobCount: 0 },
      agent: {
        workerPool: { workers: [] },
        queueMetrics: { onlineCapacity: 0, oldestQueuedSeconds: null }
      },
      reviewLanes: {
        standard: lane('standard', 0, 0, 0),
        agent: lane('agent', 0, 0, 0)
      }
    })
  });

  assert.equal(presentation.hud.freshness, 'STALE');
  assert.equal(presentation.hud.coverage.status, 'PARTIAL');
  assert.equal(presentation.agentLane.onlineCapacity, 0);
  assert.equal(presentation.standardLane.capacity, 0);
  assert.deepEqual(presentation.hud.providersObserved, []);
  assert.equal(presentation.agentLane.nextQueued, null);
  assert.equal(presentation.standardLane.nextQueued, null);
  assert.equal(presentation.footer.oldestAgentQueueSeconds, null);
});


test('empty and failed resources never synthesize reviews, providers, alerts or metrics', () => {
  const empty = buildCommandCenterPresentation();
  const failed = buildCommandCenterPresentation({ runtimeError: 'Runtime 数据加载失败' });

  for (const presentation of [empty, failed]) {
    assert.equal(presentation.hud.freshness, 'EMPTY');
    assert.equal(presentation.hud.totalQueuedJobs, 0);
    assert.equal(presentation.hud.totalRunningJobs, 0);
    assert.deepEqual(presentation.hud.providersObserved, []);
    assert.deepEqual(presentation.hud.alerts, []);
    assert.deepEqual(presentation.agentLane.runningItems, []);
    assert.deepEqual(presentation.standardLane.runningItems, []);
    assert.equal(presentation.resultPersistence.navigationTarget, '/tasks');
  }
  assert.equal(empty.hud.resourceState, 'EMPTY');
  assert.equal(failed.hud.resourceState, 'ERROR_EMPTY');
  assert.equal(failed.hud.error, 'Runtime 数据加载失败');
});


test('request failure can retain the last successful snapshot without replacing its fields', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: runtime({
      scheduler: { queuedJobCount: 4, runningJobCount: 1 },
      reviewLanes: {
        standard: lane('standard', 10, 1, 4),
        agent: lane('agent', 0, 0, 0)
      }
    }),
    runtimeError: 'HTTP 503'
  });

  assert.equal(presentation.hud.resourceState, 'ERROR_RETAINED');
  assert.equal(presentation.hud.error, 'HTTP 503');
  assert.equal(presentation.hud.generatedAt, '2026-08-03T02:00:00Z');
  assert.equal(presentation.hud.totalQueuedJobs, 4);
  assert.equal(presentation.standardLane.running, 1);
});


test('primary H1 contract omits unsupported KPI and blended utilization fields', () => {
  const presentation = buildCommandCenterPresentation({ runtime: runtime() });
  const primary = Object.fromEntries(
    Object.entries(presentation).filter(([key]) => key !== 'map')
  );
  const serialized = JSON.stringify(primary);

  for (const forbidden of [
    'passRate',
    'hitRate',
    'fallbackRate',
    'platformHealth',
    'historicalTrend',
    'utilizationPercent'
  ]) {
    assert.equal(serialized.includes(forbidden), false, forbidden);
  }
});


test('review labels use project first and stable stage vocabulary', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: runtime({
      scheduler: { queuedJobCount: 0, runningJobCount: 1 },
      reviewLanes: {
        standard: { ...lane('standard', 10, 1, 0), runningItems: [item()] },
        agent: lane('agent', 0, 0, 0)
      }
    })
  });
  const review = presentation.standardLane.runningItems[0];

  assert.equal(review.projectName, 'paycenter');
  assert.equal(review.motionIdentity, '1:41:standard-main');
  assert.equal(review.navigationTarget, '/tasks/41?reviewKey=standard-main');
  assert.equal(review.providerModelLabel, 'deepseek · v4');
  assert.equal(stageLabel('AGENT_CONVERGING'), 'Agent 收敛');
  assert.equal(stageLabel('FUTURE_STAGE'), '执行中');
});


test('review task targets are internal, encoded and unavailable without a positive task id', () => {
  assert.equal(
    reviewTaskTarget({ taskId: 42, reviewKey: 'agent/a b' }),
    '/tasks/42?reviewKey=agent%2Fa%20b'
  );
  assert.equal(reviewTaskTarget({ taskId: 7, reviewKey: '' }), '/tasks/7?reviewKey=default');
  assert.equal(reviewTaskTarget({ taskId: 0, reviewKey: 'standard' }), null);
  assert.equal(reviewTaskTarget({ taskId: 'not-a-task', reviewKey: 'standard' }), null);
});


function runtime(overrides = {}) {
  return {
    freshness: 'FRESH',
    generatedAt: '2026-08-03T02:00:00Z',
    scheduler: { queuedJobCount: 0, runningJobCount: 0 },
    agent: {
      workerPool: { workers: [] },
      queueMetrics: { onlineCapacity: 0, oldestQueuedSeconds: null }
    },
    providersObserved: [],
    alerts: [],
    coverage: { truncated: false, sections: { activeFlows: 'BOUNDED' } },
    reviewLanes: {
      standard: lane('standard', 10, 0, 0),
      agent: lane('agent', 0, 0, 0)
    },
    ...overrides
  };
}


function lane(zoneKey, capacity, runningCount, queuedCount, nextQueued = null) {
  return {
    zoneKey,
    capacity,
    runningCount,
    queuedCount,
    utilizationPercent: capacity ? Math.round(runningCount / capacity * 100) : 0,
    runningItems: [],
    nextQueued,
    runningItemsTruncated: false,
    queueOrder: zoneKey === 'agent' ? 'AGENT_PRIORITY_FIFO' : 'PROVIDER_PRIORITY_FIFO'
  };
}


function item(overrides = {}) {
  return {
    jobId: 1,
    taskId: 41,
    reviewKey: 'standard-main',
    projectName: 'paycenter',
    displayName: '主审查',
    requestedEngine: 'STANDARD',
    effectiveEngine: 'STANDARD',
    fallback: false,
    status: 'RUNNING',
    stage: 'MODEL_CALLING',
    provider: 'deepseek',
    model: 'v4',
    ...overrides
  };
}
