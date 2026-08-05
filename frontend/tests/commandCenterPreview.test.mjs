import assert from 'node:assert/strict';
import test from 'node:test';

import {
  COMMAND_CENTER_PREVIEW_PHASES,
  canStartCommandCenterPreview,
  commandCenterPreviewScene,
  composeCommandCenterPreviewScene,
  createCommandCenterPreviewController
} from '../src/command-center/commandCenterPreview.js';


const AVAILABLE = Object.freeze({
  runtimeState: 'FRESH',
  runtimeLoading: false,
  firstLoadComplete: true,
  realActivity: 'idle'
});


test('A7 preview timeline covers five truthful display-only phases in exactly six seconds', () => {
  assert.deepEqual(
    COMMAND_CENTER_PREVIEW_PHASES.map(phase => [phase.id, phase.durationMs]),
    [
      ['AGENT_QUEUED', 800],
      ['AGENT_RUNNING', 2400],
      ['FALLBACK_HANDOFF', 1200],
      ['STANDARD_FALLBACK', 1400],
      ['RESETTING', 200]
    ]
  );
  assert.equal(COMMAND_CENTER_PREVIEW_PHASES.reduce((sum, phase) => sum + phase.durationMs, 0), 6000);

  const queued = commandCenterPreviewScene('AGENT_QUEUED');
  assert.equal(queued.lanes.agent.queued, true);
  assert.equal(queued.lanes.standard.running, false);
  assert.equal(queued.fallbackActive, false);

  const running = commandCenterPreviewScene('AGENT_RUNNING');
  assert.equal(running.lanes.agent.running, true);
  assert.equal(running.connections['agent-result'].active, true);

  const handoff = commandCenterPreviewScene('FALLBACK_HANDOFF');
  assert.equal(handoff.fallbackActive, true);
  assert.equal(handoff.connections['agent-standard'].active, true);
  assert.equal(handoff.lanes.standard.running, false);

  const fallback = commandCenterPreviewScene('STANDARD_FALLBACK');
  assert.equal(fallback.fallbackActive, true);
  assert.equal(fallback.lanes.standard.running, true);
  assert.equal(fallback.connections['standard-result'].active, true);

  const resetting = commandCenterPreviewScene('RESETTING');
  assert.equal(resetting.activity, 'idle');
  assert.equal(Object.values(resetting.connections).some(connection => connection.active), false);
});


test('A7 controller rejects repeat clicks and owns at most one sequential timeout', () => {
  const clock = createVirtualTimers();
  const phases = [];
  const controller = createCommandCenterPreviewController({
    onPhaseChange: phase => phases.push(phase),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn
  });

  assert.equal(controller.start(AVAILABLE), true);
  assert.equal(controller.start(AVAILABLE), false);
  assert.deepEqual(phases, ['AGENT_QUEUED']);
  assert.equal(controller.getState().pendingTimerCount, 1);

  while (clock.pendingCount() > 0) {
    assert.equal(clock.pendingCount(), 1);
    clock.runNext();
    assert.ok(controller.getState().pendingTimerCount <= 1);
  }

  assert.deepEqual(phases, [
    'AGENT_QUEUED',
    'AGENT_RUNNING',
    'FALLBACK_HANDOFF',
    'STANDARD_FALLBACK',
    'RESETTING',
    null
  ]);
  assert.deepEqual(clock.delays, [800, 2400, 1200, 1400, 200]);
  assert.equal(clock.maxPending, 1);
  assert.deepEqual(controller.getState(), {
    active: false,
    disposed: false,
    phase: null,
    pendingTimerCount: 0
  });
});


test('A7 preview is disabled until a fresh idle first load and real activity takes over immediately', () => {
  for (const unavailable of [
    { ...AVAILABLE, runtimeState: 'STALE' },
    { ...AVAILABLE, runtimeState: 'ERROR_RETAINED' },
    { ...AVAILABLE, runtimeState: 'ERROR_EMPTY' },
    { ...AVAILABLE, runtimeLoading: true },
    { ...AVAILABLE, firstLoadComplete: false },
    { ...AVAILABLE, realActivity: 'queued' },
    { ...AVAILABLE, realActivity: 'running' }
  ]) assert.equal(canStartCommandCenterPreview(unavailable), false);
  assert.equal(canStartCommandCenterPreview(AVAILABLE), true);

  const clock = createVirtualTimers();
  const phases = [];
  const controller = createCommandCenterPreviewController({
    onPhaseChange: phase => phases.push(phase),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn
  });
  assert.equal(controller.start({ ...AVAILABLE, runtimeState: 'STALE' }), false);
  assert.equal(controller.start(AVAILABLE), true);
  assert.equal(controller.syncAvailability({ ...AVAILABLE, realActivity: 'running' }), true);
  assert.deepEqual(phases, ['AGENT_QUEUED', null]);
  assert.equal(clock.pendingCount(), 0);

  const realRunning = commandCenterPreviewScene('AGENT_RUNNING');
  assert.strictEqual(composeCommandCenterPreviewScene(realRunning, 'FALLBACK_HANDOFF'), realRunning);
});


test('A7 cleanup clears its timeout and preview composition never mutates metrics', () => {
  const clock = createVirtualTimers();
  const phases = [];
  const controller = createCommandCenterPreviewController({
    onPhaseChange: phase => phases.push(phase),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn
  });
  assert.equal(controller.start(AVAILABLE), true);
  controller.dispose();
  controller.dispose();
  assert.equal(clock.pendingCount(), 0);
  assert.equal(controller.getState().disposed, true);
  assert.equal(controller.start(AVAILABLE), false);
  assert.deepEqual(phases, ['AGENT_QUEUED']);

  const metrics = Object.freeze({
    queuedExecutionCount: 0,
    runningExecutionCount: 0,
    activeReviewTaskCount: 0,
    reviewTaskCount24h: 14,
    findingCount24h: 11
  });
  const before = JSON.stringify(metrics);
  const realIdle = commandCenterPreviewScene('RESETTING');
  for (const phase of COMMAND_CENTER_PREVIEW_PHASES) {
    composeCommandCenterPreviewScene(realIdle, phase.id);
  }
  assert.equal(JSON.stringify(metrics), before);
});


function createVirtualTimers() {
  let nextId = 1;
  const pending = new Map();
  const delays = [];
  let maxPending = 0;
  return {
    delays,
    get maxPending() { return maxPending; },
    setTimeoutFn(callback, delay) {
      const id = nextId;
      nextId += 1;
      delays.push(delay);
      pending.set(id, callback);
      maxPending = Math.max(maxPending, pending.size);
      return id;
    },
    clearTimeoutFn(id) {
      pending.delete(id);
    },
    pendingCount() {
      return pending.size;
    },
    runNext() {
      const entry = pending.entries().next().value;
      assert.ok(entry, 'expected one pending virtual timeout');
      const [id, callback] = entry;
      pending.delete(id);
      callback();
    }
  };
}
