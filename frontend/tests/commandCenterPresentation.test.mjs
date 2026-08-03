import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildCommandCenterPresentation,
  stageLabel
} from '../src/command-center/commandCenterPresentation.js';


test('presentation builds a shared queue and two stable review bases', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: {
      freshness: 'FRESH',
      generatedAt: '2026-08-03T02:00:00Z',
      reviewLanes: {
        standard: lane('standard', 10, 3, 7, item({ fallback: true })),
        agent: lane('agent', 4, 2, 5, item({ requestedEngine: 'AGENT' }))
      }
    }
  });

  assert.deepEqual(presentation.map.lanes.map(laneItem => laneItem.zoneKey), ['standard', 'agent']);
  assert.equal(presentation.map.queue.zoneKey, 'shared-queue');
  assert.equal(presentation.map.queue.queuedCount, 12);
  assert.equal(presentation.hud.totalRunning, 5);
  assert.equal(presentation.hud.totalCapacity, 14);
  assert.equal(presentation.hud.utilizationPercent, 36);
  assert.equal(presentation.map.lanes[0].nextQueued.engineToken, 'fallback');
  assert.equal(presentation.map.lanes[1].nextQueued.engineToken, 'agent');
  assert.equal(presentation.map.scene.id, 'platform-runtime-map');
});


test('presentation keeps empty map truthful without synthetic reviews', () => {
  const presentation = buildCommandCenterPresentation();

  assert.equal(presentation.hud.totalRunning, 0);
  assert.equal(presentation.map.queue.queuedCount, 0);
  assert.equal(presentation.map.lanes.length, 2);
  assert.deepEqual(presentation.map.lanes.map(laneItem => laneItem.runningItems), [[], []]);
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
