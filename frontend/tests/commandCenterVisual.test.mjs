import assert from 'node:assert/strict';
import test from 'node:test';

import {
  commandCenterMotionScene,
  commandCenterMotionState
} from '../src/command-center/commandCenterVisual.js';


test('fresh Runtime derives idle queued and running activity from the two lanes', () => {
  assert.equal(commandCenterMotionState(presentation(), false), 'idle');
  assert.equal(commandCenterMotionState(presentation({ agentQueued: 2 }), false), 'queued');
  assert.equal(commandCenterMotionState(presentation({ standardRunning: 1 }), false), 'running');
});


test('loading stale empty and failed Runtime resources pause every motion owner', () => {
  assert.equal(commandCenterMotionState(presentation({ preparation: 'preparing' }), true), 'paused');
  for (const state of ['STALE', 'EMPTY', 'ERROR_RETAINED', 'ERROR_EMPTY']) {
    const scene = commandCenterMotionScene(presentation({ state, preparation: 'preparing' }), false);
    assert.equal(scene.activity, 'paused', state);
    assert.equal(Object.values(scene.connections).some(connection => connection.active), false, state);
    assert.equal(scene.fallbackActive, false, state);
  }
  assert.equal(commandCenterMotionState(null, false), 'paused');
});


test('queued Agent activates intake and Agent branch without pretending execution reached results', () => {
  const scene = commandCenterMotionScene(presentation({ agentQueued: 3 }));

  assert.deepEqual(scene.lanes.agent, { activity: 'queued', queued: true, running: false });
  assert.deepEqual(scene.lanes.standard, { activity: 'idle', queued: false, running: false });
  assert.deepEqual(scene.connections['queue-engine'], { activity: 'queued', active: true });
  assert.deepEqual(scene.connections['engine-agent'], { activity: 'queued', active: true });
  assert.equal(scene.connections['agent-result'].active, false);
  assert.equal(scene.connections['engine-standard'].active, false);
});


test('fresh preparation activates only intake and Agent handoff with weaker preparing state', () => {
  const scene = commandCenterMotionScene(presentation({ preparation: 'preparing' }));

  assert.equal(scene.activity, 'preparing');
  assert.deepEqual(scene.lanes.agent, { activity: 'idle', queued: false, running: false });
  assert.deepEqual(scene.lanes.standard, { activity: 'idle', queued: false, running: false });
  assert.deepEqual(scene.connections['queue-engine'], { activity: 'preparing', active: true });
  assert.deepEqual(scene.connections['engine-agent'], { activity: 'preparing', active: true });
  assert.equal(scene.connections['agent-result'].active, false);
  assert.equal(scene.connections['standard-result'].active, false);
  assert.equal(scene.connections['agent-standard'].active, false);
});


test('real queued or running lanes outrank preparation and delayed preparation remains idle', () => {
  const queued = commandCenterMotionScene(presentation({
    preparation: 'preparing',
    agentQueued: 1
  }));
  assert.equal(queued.activity, 'queued');
  assert.equal(queued.connections['queue-engine'].activity, 'queued');
  assert.equal(queued.connections['engine-agent'].activity, 'queued');

  const running = commandCenterMotionScene(presentation({
    preparation: 'preparing',
    standardRunning: 1
  }));
  assert.equal(running.activity, 'running');
  assert.equal(running.connections['engine-agent'].active, false);
  assert.equal(running.connections['engine-standard'].activity, 'running');

  const delayed = commandCenterMotionScene(presentation({ preparation: 'delayed' }));
  assert.equal(delayed.activity, 'idle');
  assert.equal(Object.values(delayed.connections).some(connection => connection.active), false);
});


test('Agent and Standard branches remain independently queued or running', () => {
  const scene = commandCenterMotionScene(presentation({
    agentQueued: 2,
    standardRunning: 1
  }));

  assert.equal(scene.activity, 'running');
  assert.equal(scene.connections['queue-engine'].activity, 'running');
  assert.equal(scene.connections['engine-agent'].activity, 'queued');
  assert.equal(scene.connections['engine-standard'].activity, 'running');
  assert.equal(scene.connections['agent-result'].active, false);
  assert.equal(scene.connections['standard-result'].activity, 'running');
});


test('fallback path activates only for a truthful fallback running item or next queued item', () => {
  const inconsistentItemOnly = commandCenterMotionScene(presentation({
    standardRunningItems: [{ fallback: true }],
    standardNextQueued: { fallback: true }
  }));
  assert.equal(inconsistentItemOnly.fallbackActive, false);

  const ordinaryRunning = commandCenterMotionScene(presentation({
    standardRunning: 1,
    standardRunningItems: [{ fallback: false }]
  }));
  assert.equal(ordinaryRunning.fallbackActive, false);
  assert.equal(ordinaryRunning.connections['agent-standard'].active, false);

  const fallbackRunning = commandCenterMotionScene(presentation({
    standardRunning: 1,
    standardRunningItems: [{ fallback: true }]
  }));
  assert.equal(fallbackRunning.fallbackActive, true);
  assert.deepEqual(fallbackRunning.connections['agent-standard'], { activity: 'running', active: true });
  assert.deepEqual(fallbackRunning.connections['engine-agent'], { activity: 'running', active: true });
  assert.deepEqual(fallbackRunning.connections['engine-standard'], { activity: 'idle', active: false });
  assert.deepEqual(fallbackRunning.connections['standard-result'], { activity: 'running', active: true });

  const fallbackQueued = commandCenterMotionScene(presentation({
    standardQueued: 1,
    standardNextQueued: { fallback: true }
  }));
  assert.equal(fallbackQueued.fallbackActive, true);
  assert.deepEqual(fallbackQueued.connections['agent-standard'], { activity: 'queued', active: true });
  assert.deepEqual(fallbackQueued.connections['engine-agent'], { activity: 'queued', active: true });
  assert.deepEqual(fallbackQueued.connections['engine-standard'], { activity: 'idle', active: false });
  assert.equal(fallbackQueued.connections['standard-result'].active, false);
});


function presentation({
  state = 'FRESH',
  agentQueued = 0,
  agentRunning = 0,
  standardQueued = 0,
  standardRunning = 0,
  standardRunningItems = [],
  standardNextQueued = null,
  preparation = 'idle'
} = {}) {
  return {
    resources: { runtime: { state } },
    dispatchPreparation: { activity: preparation },
    agentLane: {
      queued: agentQueued,
      running: agentRunning,
      runningItems: [],
      nextQueued: null
    },
    standardLane: {
      queued: standardQueued,
      running: standardRunning,
      runningItems: standardRunningItems,
      nextQueued: standardNextQueued
    }
  };
}
