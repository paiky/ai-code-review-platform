import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createPlatformRuntimeMapController,
  measureOperationMapAnchors,
  PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY,
  PLATFORM_RUNTIME_MAP_VISUAL_TOKENS,
  resolvePlatformRuntimeMapFallback
} from '../src/command-center/platformRuntimeMapRenderer.js';


test('static operation map owns one observer and listener with zero RAF', () => {
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
  assert.equal(harness.pendingFrameCount(), 0);
  assert.equal(harness.canvas.attributes.get('data-command-center-anchor-count'), '5');

  controller.setScene(scene('two'));
  assert.equal(controller.getSnapshot().frameCount, 2);
  assert.equal(harness.canvas[PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY].activeRafCount, 0);
  assert.equal(harness.canvas.attributes.get('data-command-center-animated-reviews'), '0');
  assert.equal(harness.canvas.attributes.get('data-command-center-animated-workers'), '0');
  assert.equal(harness.canvas.attributes.get('data-command-center-environment-particles'), '0');
  assert.equal(harness.canvas.attributes.get('data-command-center-scene-updates'), '2');
  assert.equal(PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.standard, '#c88a16');
  assert.equal(PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.agent, '#7056d8');
  controller.dispose();
  assert.equal(harness.documentTarget.listenerCount(), 0);
  assert.equal(harness.pendingFrameCount(), 0);
});


test('route anchors are measured from real DOM zone rectangles', () => {
  const harness = createHarness();
  const anchors = measureOperationMapAnchors(harness.container, scene('anchors').connections);

  assert.equal(anchors.length, 5);
  assert.deepEqual(anchors[0].fromPoint, { x: 200, y: 250 });
  assert.deepEqual(anchors[0].toPoint, { x: 260, y: 250 });
  assert.deepEqual(anchors[1].fromPoint, { x: 420, y: 250 });
  assert.deepEqual(anchors[1].toPoint, { x: 500, y: 140 });
  assert.deepEqual(anchors[4].fromPoint, { x: 760, y: 360 });
  assert.deepEqual(anchors[4].toPoint, { x: 810, y: 250 });
});


test('fallback resolver keeps small-screen and Canvas failure DOM complete', () => {
  assert.equal(resolvePlatformRuntimeMapFallback({ smallScreen: true }), 'SMALL_SCREEN');
  assert.equal(resolvePlatformRuntimeMapFallback({ canvasFailed: true }), 'CANVAS_FAILED');
  assert.equal(resolvePlatformRuntimeMapFallback({ canvasReady: false }), 'CANVAS_LOADING');
  assert.equal(resolvePlatformRuntimeMapFallback({ canvasReady: true }), null);
});


function scene(snapshotKey) {
  return {
    snapshotKey,
    freshness: 'FRESH',
    connections: [
      { from: 'queue-gate', to: 'ai-review-core', token: 'queue' },
      { from: 'ai-review-core', to: 'standard', token: 'standard' },
      { from: 'ai-review-core', to: 'agent', token: 'agent' },
      { from: 'standard', to: 'result-beacon', token: 'standard' },
      { from: 'agent', to: 'result-beacon', token: 'agent' }
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
  const rects = {
    'queue-gate': rect(20, 100, 180, 300),
    'ai-review-core': rect(260, 160, 160, 180),
    standard: rect(500, 60, 260, 160),
    agent: rect(500, 280, 260, 160),
    'result-beacon': rect(810, 160, 140, 180)
  };
  const container = {
    getBoundingClientRect: () => rect(0, 0, 980, 500),
    querySelector(selector) {
      const match = selector.match(/data-zone-key="([^"]+)"/);
      const value = match ? rects[match[1]] : null;
      return value ? { getBoundingClientRect: () => value } : null;
    }
  };
  return {
    canvas,
    container,
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
    pendingFrameCount: () => frames.size
  };
}


function rect(left, top, width, height) {
  return { left, top, right: left + width, bottom: top + height, width, height };
}
