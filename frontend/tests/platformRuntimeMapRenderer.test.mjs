import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createPlatformRuntimeMapController,
  PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY,
  resolvePlatformRuntimeMapFallback
} from '../src/command-center/platformRuntimeMapRenderer.js';


test('dynamic runtime map owns one observer/listener and one bounded RAF', () => {
  const harness = createHarness();
  const controller = createPlatformRuntimeMapController({
    canvas: harness.canvas,
    container: harness.container,
    environment: harness.environment,
    scene: scene('one')
  });

  assert.ok(controller);
  const initial = controller.getSnapshot();
  assert.equal(initial.observerRegistrationCount, 1);
  assert.equal(initial.listenerRegistrationCount, 1);
  assert.equal(initial.activeRafCount, 1);
  assert.equal(initial.frameCount, 1);

  harness.runFrame(40);
  assert.equal(controller.getSnapshot().frameCount, 2);
  assert.equal(controller.getSnapshot().activeRafCount, 1);
  controller.setScene(scene('two'));
  assert.equal(controller.getSnapshot().frameCount, 3);
  assert.equal(harness.canvas[PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY].activeRafCount, 1);
  assert.equal(harness.canvas.attributes.get('data-command-center-animated-reviews'), '2');
  assert.equal(harness.canvas.attributes.get('data-command-center-online-workers'), '1');
  assert.equal(harness.canvas.attributes.get('data-command-center-scene-updates'), '2');
  controller.dispose();
  assert.equal(harness.documentTarget.listenerCount(), 0);
  assert.equal(harness.pendingFrameCount(), 0);
});


test('empty or stale snapshots remain static and never invent animation', () => {
  const harness = createHarness();
  const controller = createPlatformRuntimeMapController({
    canvas: harness.canvas,
    container: harness.container,
    environment: harness.environment,
    scene: { ...scene('stale'), freshness: 'STALE', workers: [] }
  });
  assert.equal(controller.getSnapshot().activeRafCount, 0);
  assert.equal(harness.canvas.attributes.get('data-command-center-animated-reviews'), '0');
  controller.setScene({ snapshotKey: 'empty', freshness: 'FRESH', lanes: [], workers: [] });
  assert.equal(controller.getSnapshot().activeRafCount, 0);
  controller.dispose();
});


test('fallback resolver prefers complete static DOM conditions', () => {
  assert.equal(resolvePlatformRuntimeMapFallback({ smallScreen: true }), 'SMALL_SCREEN');
  assert.equal(resolvePlatformRuntimeMapFallback({ reducedMotion: true }), 'REDUCED_MOTION');
  assert.equal(resolvePlatformRuntimeMapFallback({ canvasFailed: true }), 'CANVAS_FAILED');
  assert.equal(resolvePlatformRuntimeMapFallback({ canvasReady: false }), 'CANVAS_LOADING');
  assert.equal(resolvePlatformRuntimeMapFallback({ canvasReady: true }), null);
});


function scene(snapshotKey) {
  return {
    snapshotKey,
    freshness: 'FRESH',
    lanes: [
      {
        zoneKey: 'standard', utilizationPercent: 50, queuedCount: 2,
        runningItems: [{ jobId: 11, taskId: 21, reviewKey: 'standard', fallback: false }]
      },
      {
        zoneKey: 'agent', utilizationPercent: 25, queuedCount: 1,
        runningItems: [{ jobId: 12, taskId: 22, reviewKey: 'agent', workerId: 'worker-1' }]
      }
    ],
    workers: [{ workerId: 'worker-1', state: 'BUSY', online: true, capacity: 1, activeJobId: 12 }]
  };
}


function createHarness() {
  const listeners = new Set();
  const documentTarget = {
    hidden: false,
    visibilityState: 'visible',
    addEventListener(name, listener) { if (name === 'visibilitychange') listeners.add(listener); },
    removeEventListener(name, listener) { if (name === 'visibilitychange') listeners.delete(listener); },
    listenerCount() { return listeners.size; }
  };
  class ResizeObserver {
    constructor(callback) { this.callback = callback; }
    observe() {}
    disconnect() {}
  }
  let now = 0;
  let nextFrameId = 0;
  const frames = new Map();
  const context = new Proxy({}, {
    get(target, property) {
      if (!(property in target)) target[property] = () => {};
      return target[property];
    },
    set(target, property, value) { target[property] = value; return true; }
  });
  const canvas = {
    width: 0,
    height: 0,
    attributes: new Map(),
    getContext: () => context,
    setAttribute(name, value) { this.attributes.set(name, value); }
  };
  const harness = {
    canvas,
    container: { getBoundingClientRect: () => ({ width: 900, height: 500 }) },
    documentTarget,
    environment: {
      documentTarget,
      ResizeObserverCtor: ResizeObserver,
      requestFrame: callback => {
        nextFrameId += 1;
        frames.set(nextFrameId, callback);
        return nextFrameId;
      },
      cancelFrame: frameId => frames.delete(frameId),
      getDevicePixelRatio: () => 1,
      now: () => { now += 0.1; return now; }
    },
    runFrame(timestamp) {
      const [entry] = frames.entries();
      if (!entry) return;
      frames.delete(entry[0]);
      entry[1](timestamp);
    },
    pendingFrameCount: () => frames.size
  };
  return harness;
}
