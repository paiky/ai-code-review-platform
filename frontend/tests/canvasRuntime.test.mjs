import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createCanvasRuntime,
  normalizeCanvasDpr
} from '../src/canvas/canvasRuntime.js';


test('owns size DPR observer visibility RAF and diagnostics without renderer state', () => {
  const harness = createHarness({ width: 0, height: 0, dpr: 4 });
  const resizeEvents = [];
  const drawEvents = [];
  let animated = true;
  const runtime = harness.create({
    maxDpr: 2,
    onResize: event => resizeEvents.push(event),
    onDraw: event => drawEvents.push(event),
    isAnimationEnabled: () => animated
  });

  assert.ok(runtime);
  assert.equal(normalizeCanvasDpr(4, { maxDpr: 2 }), 2);
  assert.equal(runtime.getSnapshot().running, false);
  assert.equal(runtime.getSnapshot().frameCount, 0);
  assert.equal(resizeEvents.length, 1);
  assert.equal(drawEvents.length, 0);

  harness.resize(640, 320);
  assert.equal(harness.canvas.width, 1280);
  assert.equal(harness.canvas.height, 640);
  assert.equal(runtime.getSnapshot().dpr, 2);
  assert.equal(runtime.getSnapshot().frameCount, 1);
  assert.equal(harness.pendingFrames(), 1);
  assert.deepEqual(
    drawEvents.map(({ width, height, dpr }) => [width, height, dpr]),
    [[640, 320, 2]]
  );

  runtime.refresh();
  assert.equal(runtime.getSnapshot().frameCount, 2);
  assert.equal(harness.pendingFrames(), 1);
  assert.equal(harness.observerInstances.length, 1);
  assert.equal(harness.documentTarget.listenerCount(), 1);

  harness.setHidden(true);
  assert.equal(harness.pendingFrames(), 0);
  harness.setHidden(false);
  assert.equal(runtime.getSnapshot().frameCount, 3);
  assert.equal(harness.pendingFrames(), 1);

  animated = false;
  runtime.refresh();
  assert.equal(runtime.getSnapshot().frameCount, 4);
  assert.equal(harness.pendingFrames(), 0);

  runtime.dispose();
  const disposed = runtime.getSnapshot();
  assert.equal(disposed.disposed, true);
  assert.equal(disposed.observerActive, false);
  assert.equal(disposed.listenerActive, false);
  assert.equal(harness.observerInstances[0].disconnectCount, 1);
  assert.equal(harness.documentTarget.listenerCount(), 0);
});


test('keeps initialization and draw failures local and cleans runtime resources once', () => {
  let initializationFailures = 0;
  const unavailable = createHarness({ context: null }).create({
    onDraw() {},
    onFailure: () => {
      initializationFailures += 1;
    }
  });
  assert.equal(unavailable, null);
  assert.equal(initializationFailures, 1);

  let drawFailures = 0;
  const harness = createHarness();
  const runtime = harness.create({
    onDraw: () => {
      throw new Error('synthetic draw failure');
    },
    isAnimationEnabled: () => true,
    onFailure: () => {
      drawFailures += 1;
    }
  });

  assert.ok(runtime);
  const failed = runtime.getSnapshot();
  assert.equal(failed.failed, true);
  assert.equal(failed.running, false);
  assert.equal(failed.observerActive, false);
  assert.equal(failed.listenerActive, false);
  assert.equal(drawFailures, 1);
  assert.equal(harness.pendingFrames(), 0);
  assert.equal(harness.documentTarget.listenerCount(), 0);

  runtime.refresh();
  runtime.dispose();
  assert.equal(drawFailures, 1);
});


function createHarness({
  width = 640,
  height = 360,
  dpr = 1,
  context = {}
} = {}) {
  let currentWidth = width;
  let currentHeight = height;
  let nextFrameId = 1;
  let clock = 0;
  const frameCallbacks = new Map();
  const observerInstances = [];
  const documentTarget = createDocumentTarget();
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => context
  };
  const container = {
    getBoundingClientRect: () => ({
      width: currentWidth,
      height: currentHeight
    })
  };

  class FakeResizeObserver {
    constructor(callback) {
      this.callback = callback;
      this.target = null;
      this.disconnectCount = 0;
      observerInstances.push(this);
    }

    observe(target) {
      this.target = target;
    }

    disconnect() {
      this.disconnectCount += 1;
      this.target = null;
    }

    emit(nextWidth, nextHeight) {
      this.callback([{
        target: this.target,
        contentRect: {
          width: nextWidth,
          height: nextHeight
        }
      }]);
    }
  }

  const environment = {
    documentTarget,
    ResizeObserverCtor: FakeResizeObserver,
    requestFrame: callback => {
      const id = nextFrameId;
      nextFrameId += 1;
      frameCallbacks.set(id, callback);
      return id;
    },
    cancelFrame: id => {
      frameCallbacks.delete(id);
    },
    getDevicePixelRatio: () => dpr,
    now: () => {
      clock += 0.25;
      return clock;
    }
  };

  return {
    canvas,
    documentTarget,
    observerInstances,
    create: options => createCanvasRuntime({
      canvas,
      container,
      environment,
      ...options
    }),
    pendingFrames: () => frameCallbacks.size,
    resize: (nextWidth, nextHeight) => {
      currentWidth = nextWidth;
      currentHeight = nextHeight;
      observerInstances[0].emit(nextWidth, nextHeight);
    },
    setHidden: hidden => {
      documentTarget.hidden = hidden;
      documentTarget.visibilityState = hidden ? 'hidden' : 'visible';
      documentTarget.emit('visibilitychange');
    }
  };
}


function createDocumentTarget() {
  const listeners = new Map();
  return {
    hidden: false,
    visibilityState: 'visible',
    addEventListener(type, callback) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(callback);
    },
    removeEventListener(type, callback) {
      listeners.get(type)?.delete(callback);
    },
    emit(type) {
      for (const callback of listeners.get(type) || []) callback();
    },
    listenerCount() {
      return [...listeners.values()]
        .reduce((total, callbacks) => total + callbacks.size, 0);
    }
  };
}
