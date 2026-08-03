import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createPlatformRuntimeMapController,
  PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY,
  resolvePlatformRuntimeMapFallback
} from '../src/command-center/platformRuntimeMapRenderer.js';


test('static runtime map owns one observer/listener and never schedules RAF', () => {
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
  assert.equal(initial.activeRafCount, 0);
  assert.equal(initial.frameCount, 1);

  controller.setScene(scene('two'));
  assert.equal(controller.getSnapshot().frameCount, 2);
  assert.equal(harness.canvas[PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY].activeRafCount, 0);
  controller.dispose();
  assert.equal(harness.documentTarget.listenerCount(), 0);
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
      { zoneKey: 'standard', utilizationPercent: 50, queuedCount: 2 },
      { zoneKey: 'agent', utilizationPercent: 25, queuedCount: 1 }
    ]
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
  return {
    canvas,
    container: { getBoundingClientRect: () => ({ width: 900, height: 500 }) },
    documentTarget,
    environment: {
      documentTarget,
      ResizeObserverCtor: ResizeObserver,
      requestFrame: () => 1,
      cancelFrame: () => {},
      getDevicePixelRatio: () => 1,
      now: () => { now += 0.1; return now; }
    }
  };
}
