import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildCommandCenterPresentation,
  stageLabel
} from '../src/command-center/commandCenterPresentation.js';


test('presentation builds the five-node operation map and stable review lanes', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: {
      freshness: 'FRESH',
      generatedAt: '2026-08-03T02:00:00Z',
      agent: {
        workerPool: {
          workers: [{ workerId: 'worker-1', state: 'BUSY', online: true, capacity: 1, activeJobId: 9 }]
        }
      },
      reviewLanes: {
        standard: lane('standard', 10, 3, 7, item({ fallback: true })),
        agent: lane('agent', 4, 2, 5, item({ requestedEngine: 'AGENT' }))
      }
    }
  });

  assert.deepEqual(presentation.map.lanes.map(laneItem => laneItem.zoneKey), ['standard', 'agent']);
  assert.equal(presentation.map.zoneKey, 'ai-review-operation-map');
  assert.equal(presentation.map.queueGate.zoneKey, 'queue-gate');
  assert.equal(presentation.map.queueGate.queuedCount, 12);
  assert.equal(presentation.map.core.zoneKey, 'ai-review-core');
  assert.equal(presentation.map.core.runningCount, 5);
  assert.equal(presentation.map.resultBeacon.zoneKey, 'result-beacon');
  assert.equal(presentation.map.resultBeacon.mode, 'STRUCTURAL_ONLY');
  assert.equal(presentation.map.resultBeacon.description, '结果回流至任务详情与既有通知链路');
  assert.deepEqual(presentation.map.connections.map(({ from, to }) => `${from}->${to}`), [
    'queue-gate->ai-review-core',
    'ai-review-core->standard',
    'ai-review-core->agent',
    'standard->result-beacon',
    'agent->result-beacon'
  ]);
  assert.equal(presentation.hud.totalRunning, 5);
  assert.equal(presentation.hud.totalCapacity, 14);
  assert.equal(presentation.hud.utilizationPercent, 36);
  assert.equal(presentation.map.lanes[0].nextQueued.engineToken, 'fallback');
  assert.equal(presentation.map.lanes[1].nextQueued.engineToken, 'agent');
  assert.equal(presentation.map.scene.id, 'ai-review-operation-map');
  assert.equal(presentation.map.lanes[1].workers[0].workerId, 'worker-1');
});


test('presentation keeps empty map truthful without synthetic reviews', () => {
  const presentation = buildCommandCenterPresentation();

  assert.equal(presentation.hud.totalRunning, 0);
  assert.equal(presentation.map.queueGate.queuedCount, 0);
  assert.equal(presentation.map.lanes.length, 2);
  assert.deepEqual(presentation.map.lanes.map(laneItem => laneItem.runningItems), [[], []]);
  assert.equal(Object.hasOwn(presentation.map.resultBeacon, 'completedCount'), false);
  assert.equal(Object.hasOwn(presentation.map.resultBeacon, 'failureCount'), false);
});


test('review labels use project first and static stage vocabulary', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: {
      reviewLanes: {
        standard: { ...lane('standard', 10, 1, 0), runningItems: [item()] },
        agent: lane('agent', 0, 0, 0)
      }
    }
  });
  const review = presentation.map.lanes[0].runningItems[0];

  assert.equal(review.projectName, 'paycenter');
  assert.equal(review.providerModelLabel, 'deepseek · v4');
  assert.equal(stageLabel('AGENT_CONVERGING'), 'Agent 收敛');
  assert.equal(stageLabel('FUTURE_STAGE'), '执行中');
});


function lane(zoneKey, capacity, runningCount, queuedCount, nextQueued = null) {
  return {
    zoneKey,
    capacity,
    runningCount,
    queuedCount,
    utilizationPercent: capacity ? Math.round(runningCount / capacity * 100) : 0,
    runningItems: [],
    nextQueued,
    runningItemsTruncated: false
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
