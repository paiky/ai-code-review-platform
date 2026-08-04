import assert from 'node:assert/strict';
import test from 'node:test';

import {
  normalizeRuntimeSnapshot,
  RUNTIME_SCHEMA_VERSION
} from '../src/command-center/commandCenterModel.js';
import { buildCommandCenterPresentation } from '../src/command-center/commandCenterPresentation.js';


const NOW = Date.parse('2026-08-04T02:00:10Z');
const FRESH_AT = '2026-08-04T02:00:00Z';


test('I2 data matrix keeps empty lanes, zero capacity and absent observations truthful', () => {
  const presentation = present({
    reviewLanes: {
      standard: lane('standard', 0, 0, 0),
      agent: lane('agent', 0, 0, 0)
    },
    agent: {
      workerPool: workerPool(),
      queueMetrics: { onlineCapacity: 0, oldestQueuedSeconds: null }
    }
  });

  assert.equal(presentation.hud.resourceState, 'FRESH');
  assert.equal(presentation.agentLane.queued, 0);
  assert.equal(presentation.agentLane.running, 0);
  assert.equal(presentation.agentLane.onlineCapacity, 0);
  assert.equal(presentation.agentLane.nextQueued, null);
  assert.equal(presentation.standardLane.queued, 0);
  assert.equal(presentation.standardLane.running, 0);
  assert.equal(presentation.standardLane.capacity, 0);
  assert.equal(presentation.standardLane.nextQueued, null);
  assert.deepEqual(presentation.hud.providersObserved, []);
  assert.equal(Object.hasOwn(presentation.hud, 'alerts'), false);
  assert.equal(presentation.qualityOutput.providerExecution.hasRecords, false);
});


test('I2 data matrix preserves a Standard-only workload, multiple providers and bounded running items', () => {
  const presentation = present({
    scheduler: { activeJobCount: 7, queuedJobCount: 4, runningJobCount: 3 },
    reviewLanes: {
      standard: {
        ...lane('standard', 8, 3, 4),
        runningItems: [
          runningItem({ jobId: 11, taskId: 101, reviewKey: 'standard/main' }),
          runningItem({ jobId: 12, taskId: 102, reviewKey: 'standard second' })
        ],
        nextQueued: runningItem({
          jobId: 13,
          taskId: 103,
          reviewKey: 'next-standard',
          status: 'QUEUED',
          stage: 'QUEUED'
        }),
        runningItemsTruncated: true
      },
      agent: lane('agent', 0, 0, 0)
    },
    providersObserved: [
      provider('OPENAI', 'OpenAI', 'gpt-5.4'),
      provider('DEEPSEEK', 'DeepSeek', 'v4')
    ],
    coverage: {
      phase: 'PHASE_1',
      truncated: true,
      sections: { reviewLanes: 'BOUNDED', providersObserved: 'FULL' }
    }
  });

  assert.equal(presentation.agentLane.running, 0);
  assert.equal(presentation.standardLane.running, 3);
  assert.equal(presentation.standardLane.queued, 4);
  assert.equal(presentation.standardLane.visibleRunningItemCount, 2);
  assert.equal(presentation.standardLane.totalRunningItemCount, 3);
  assert.equal(presentation.standardLane.runningItemsTruncated, true);
  assert.equal(presentation.standardLane.nextQueued.navigationTarget, '/tasks/103?reviewKey=next-standard');
  assert.deepEqual(
    presentation.hud.providersObserved.map(item => item.label),
    ['OpenAI / gpt-5.4', 'DeepSeek / v4']
  );
  assert.equal(presentation.hud.coverage.status, 'PARTIAL');
  assert.equal(presentation.hud.coverage.truncated, true);
  assert.deepEqual(presentation.diagnostics, []);
});


test('I2 data matrix preserves online, busy, draining and offline Agent worker states', () => {
  const runtime = normalize({
    reviewLanes: {
      standard: lane('standard', 10, 0, 0),
      agent: lane('agent', 3, 2, 1)
    },
    scheduler: { activeJobCount: 3, queuedJobCount: 1, runningJobCount: 2 },
    agent: {
      workerPool: workerPool({
        onlineCount: 3,
        offlineCount: 1,
        idleCount: 1,
        busyCount: 1,
        drainingCount: 1,
        workers: [
          worker('agent-idle', 'IDLE', true),
          worker('agent-busy', 'BUSY', true),
          worker('agent-draining', 'DRAINING', true),
          worker('agent-offline', 'IDLE', false)
        ]
      }),
      queueMetrics: {
        queued: 1,
        running: 2,
        onlineCapacity: 3,
        busyCapacity: 1,
        drainingWorkers: 1
      }
    }
  });
  const presentation = buildCommandCenterPresentation({ runtime });

  assert.deepEqual(
    runtime.agent.workerPool.workers.map(item => [item.workerId, item.state, item.online]),
    [
      ['agent-idle', 'IDLE', true],
      ['agent-busy', 'BUSY', true],
      ['agent-draining', 'DRAINING', true],
      ['agent-offline', 'IDLE', false]
    ]
  );
  assert.deepEqual(presentation.agentLane.workerSummary, {
    idle: 1,
    busy: 1,
    draining: 1,
    offline: 1
  });
  assert.equal(presentation.agentLane.onlineCapacity, 3);
});


test('I2 resource matrix distinguishes fresh, stale, empty and both error modes', () => {
  const fresh = present();
  const staleRuntime = normalize({ generatedAt: '2026-08-04T01:59:00Z' });
  const stale = buildCommandCenterPresentation({ runtime: staleRuntime });
  const emptyRuntime = normalize({
    generatedAt: null,
    scheduler: { activeJobCount: 1, queuedJobCount: 0, runningJobCount: 1 },
    reviewLanes: {
      standard: {
        ...lane('standard', 10, 1, 0),
        runningItems: [runningItem()]
      },
      agent: lane('agent', 0, 0, 0)
    },
    providersObserved: [provider('OPENAI', 'OpenAI', 'gpt-5.4')]
  });
  const empty = buildCommandCenterPresentation({ runtime: emptyRuntime });
  const errorEmpty = buildCommandCenterPresentation({ runtimeError: 'HTTP 503' });
  const errorRetained = buildCommandCenterPresentation({
    runtime: freshRuntime(),
    runtimeError: 'HTTP 503'
  });

  assert.equal(fresh.resources.runtime.state, 'FRESH');
  assert.equal(stale.resources.runtime.state, 'STALE');
  assert.equal(empty.resources.runtime.state, 'EMPTY');
  assert.equal(errorEmpty.resources.runtime.state, 'ERROR_EMPTY');
  assert.equal(errorRetained.resources.runtime.state, 'ERROR_RETAINED');
  assert.equal(errorRetained.hud.generatedAt, new Date(FRESH_AT).toISOString());
  assert.equal(empty.hud.totalRunningJobs, 0);
  assert.deepEqual(empty.hud.providersObserved, []);
  assert.deepEqual(empty.standardLane.runningItems, []);
});


function present(overrides = {}) {
  return buildCommandCenterPresentation({ runtime: normalize(overrides) });
}


function normalize(overrides = {}) {
  return normalizeRuntimeSnapshot({
    schemaVersion: RUNTIME_SCHEMA_VERSION,
    generatedAt: FRESH_AT,
    scheduler: { activeJobCount: 0, queuedJobCount: 0, runningJobCount: 0 },
    reviewLanes: {
      standard: lane('standard', 10, 0, 0),
      agent: lane('agent', 0, 0, 0)
    },
    agent: {
      workerPool: workerPool(),
      queueMetrics: { onlineCapacity: 0, oldestQueuedSeconds: null }
    },
    providersObserved: [],
    alerts: [],
    coverage: { phase: 'PHASE_1', truncated: false, sections: {} },
    ...overrides
  }, { now: NOW });
}


function freshRuntime() {
  return normalize();
}


function lane(zoneKey, capacity, runningCount, queuedCount) {
  return {
    zoneKey,
    capacity,
    runningCount,
    queuedCount,
    runningItems: [],
    nextQueued: null,
    runningItemsTruncated: false,
    queueOrder: null
  };
}


function workerPool(overrides = {}) {
  return {
    enabled: true,
    onlineCount: 0,
    offlineCount: 0,
    idleCount: 0,
    busyCount: 0,
    drainingCount: 0,
    workers: [],
    ...overrides
  };
}


function worker(workerId, state, online) {
  return {
    workerId,
    state,
    online,
    capacity: 1,
    activeJobId: state === 'BUSY' ? 12 : null,
    activeRunId: state === 'BUSY' ? 22 : null
  };
}


function runningItem(overrides = {}) {
  return {
    jobId: 1,
    taskId: 100,
    reviewKey: 'standard-main',
    projectName: 'Command Center',
    displayName: 'Standard Review',
    requestedEngine: 'STANDARD',
    effectiveEngine: 'STANDARD',
    fallback: false,
    status: 'RUNNING',
    stage: 'MODEL_CALLING',
    provider: 'OpenAI',
    model: 'gpt-5.4',
    ...overrides
  };
}


function provider(providerCode, providerName, modelName) {
  return {
    providerCode,
    providerName,
    providerType: 'OPENAI_COMPATIBLE',
    modelName,
    enabled: true,
    defaultProvider: false,
    status: 'ACTIVE',
    activeFlowCount: 1
  };
}
