import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  REVIEW_CANVAS_MAX_DPR,
  REVIEW_CANVAS_PARTICLE_LIMITS,
  REVIEW_CANVAS_SEED,
  createDeterministicParticleLayout,
  createReviewCanvasController,
  normalizeReviewCanvasDpr,
  resolveReviewCanvasParticleLimit,
  resolveReviewCanvasRenderParameters
} from '../src/reviewCanvasRenderer.js';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
const componentSource = await readFile(
  new URL('../src/ReviewImmersiveCanvas.jsx', import.meta.url),
  'utf8'
);

test('uses a fixed seed, deterministic particles and hard particle caps', () => {
  const first = createDeterministicParticleLayout({
    seed: REVIEW_CANVAS_SEED,
    count: 24
  });
  const second = createDeterministicParticleLayout({
    seed: REVIEW_CANVAS_SEED,
    count: 24
  });
  const otherSeed = createDeterministicParticleLayout({
    seed: REVIEW_CANVAS_SEED + 1,
    count: 24
  });
  const capped = createDeterministicParticleLayout({ count: 999 });

  assert.deepEqual(first, second);
  assert.notDeepEqual(first, otherSeed);
  assert.equal(capped.length, REVIEW_CANVAS_PARTICLE_LIMITS.DESKTOP);
  assert.equal(resolveReviewCanvasParticleLimit(390), 48);
  assert.equal(resolveReviewCanvasParticleLimit(1024), 80);
  assert.equal(resolveReviewCanvasParticleLimit(1440), 120);
});

test('maps all running states deterministically for Agent Standard and fallback', () => {
  const expected = {
    QUEUED: [0.08, 0.42, 0.96],
    ANALYZING: [0.32, 0.72, 1.04],
    EVIDENCE: [0.52, 0.86, 1.08],
    CONVERGING: [0.24, 0.78, 0.84],
    SUBMITTING: [0.4, 0.9, 0.72],
    FALLBACK: [0.18, 0.64, 0.9]
  };
  for (const [state, values] of Object.entries(expected)) {
    const params = resolveReviewCanvasRenderParameters({
      engineVisual: 'AGENT_PARTICLE',
      engineIdentity: 'AGENT',
      state,
      currentStageId: 'context'
    });
    assert.deepEqual(
      [params.speed, params.intensity, params.radialScale],
      values,
      state
    );
    assert.equal(params.animated, true);
    assert.equal(params.currentStageId, 'context');
  }

  const standard = resolveReviewCanvasRenderParameters({
    engineVisual: 'STANDARD_FLOW',
    engineIdentity: 'STANDARD',
    state: 'ANALYZING'
  });
  const fallback = resolveReviewCanvasRenderParameters({
    engineVisual: 'STANDARD_FLOW',
    engineIdentity: 'FALLBACK',
    state: 'FALLBACK'
  });
  const reduced = resolveReviewCanvasRenderParameters({
    engineVisual: 'AGENT_PARTICLE',
    engineIdentity: 'AGENT',
    state: 'EVIDENCE',
    reducedMotion: true
  });

  assert.equal(standard.engineVisual, 'STANDARD_FLOW');
  assert.equal(standard.engineIdentity, 'STANDARD');
  assert.equal(fallback.engineVisual, 'STANDARD_FLOW');
  assert.equal(fallback.engineIdentity, 'FALLBACK');
  assert.equal(reduced.animated, false);
  assert.equal(reduced.speed, 0);
});

test('caps DPR and waits at zero size until ResizeObserver supplies a legal size', () => {
  const harness = createHarness({ width: 0, height: 0, dpr: 4 });
  const controller = harness.create();

  assert.ok(controller);
  assert.equal(controller.getSnapshot().running, false);
  assert.equal(controller.getSnapshot().frameCount, 0);
  assert.equal(harness.pendingFrames(), 0);

  harness.resize(600, 320);
  const resized = controller.getSnapshot();
  assert.equal(normalizeReviewCanvasDpr(4), REVIEW_CANVAS_MAX_DPR);
  assert.equal(resized.dpr, 2);
  assert.equal(harness.canvas.width, 1200);
  assert.equal(harness.canvas.height, 640);
  assert.equal(resized.particleCount, 80);
  assert.equal(harness.pendingFrames(), 1);

  harness.resize(0, 0);
  assert.equal(controller.getSnapshot().running, false);
  assert.equal(harness.pendingFrames(), 0);

  harness.resize(390, 220);
  assert.equal(controller.getSnapshot().particleCount, 48);
  assert.equal(harness.pendingFrames(), 1);
  controller.dispose();
});

test('keeps one observer, one visibility listener and one RAF across polling updates', () => {
  const harness = createHarness({ width: 900, height: 420, dpr: 1.5 });
  const controller = harness.create();
  const canvasIdentity = harness.canvas;

  for (const state of [
    'QUEUED',
    'ANALYZING',
    'EVIDENCE',
    'CONVERGING',
    'SUBMITTING',
    'ANALYZING'
  ]) {
    controller.setRenderParameters({
      engineVisual: 'AGENT_PARTICLE',
      engineIdentity: 'AGENT',
      state,
      currentStageId: 'review'
    });
    assert.equal(harness.pendingFrames(), 1, state);
  }

  assert.equal(harness.canvas, canvasIdentity);
  assert.equal(harness.observerInstances.length, 1);
  assert.equal(harness.documentTarget.addCount, 1);
  assert.equal(harness.documentTarget.listenerCount(), 1);

  harness.flushFrame(16);
  assert.equal(harness.pendingFrames(), 1);
  harness.flushFrame(32);
  assert.equal(harness.pendingFrames(), 1);

  controller.dispose();
  assert.equal(harness.pendingFrames(), 0);
  assert.equal(harness.observerInstances[0].disconnectCount, 1);
  assert.equal(harness.documentTarget.removeCount, 1);
  assert.equal(harness.documentTarget.listenerCount(), 0);
});

test('pauses while hidden, resumes when visible and reduced motion stays static', () => {
  const harness = createHarness({ width: 700, height: 360 });
  const controller = harness.create();
  assert.equal(harness.pendingFrames(), 1);

  harness.setHidden(true);
  assert.equal(harness.pendingFrames(), 0);
  const hiddenFrames = controller.getSnapshot().frameCount;
  harness.flushFrame(16);
  assert.equal(controller.getSnapshot().frameCount, hiddenFrames);

  harness.setHidden(false);
  assert.equal(harness.pendingFrames(), 1);

  controller.setRenderParameters({
    engineVisual: 'AGENT_PARTICLE',
    engineIdentity: 'AGENT',
    state: 'EVIDENCE',
    reducedMotion: true
  });
  assert.equal(harness.pendingFrames(), 0);
  const staticFrames = controller.getSnapshot().frameCount;
  controller.setRenderParameters({
    engineVisual: 'AGENT_PARTICLE',
    engineIdentity: 'AGENT',
    state: 'CONVERGING',
    reducedMotion: true
  });
  assert.equal(controller.getSnapshot().frameCount, staticFrames + 1);
  assert.equal(harness.pendingFrames(), 0);
  controller.dispose();
});

test('initialization and drawing failures clean up once and leave fallback local', () => {
  let initializationFailures = 0;
  const missingContext = createHarness({
    width: 640,
    height: 320,
    context: null
  });
  const unavailable = missingContext.create({
    onFailure: () => {
      initializationFailures += 1;
    }
  });
  assert.equal(unavailable, null);
  assert.equal(initializationFailures, 1);

  let drawFailures = 0;
  const context = createContext();
  const harness = createHarness({ width: 640, height: 320, context });
  const controller = harness.create({
    onFailure: () => {
      drawFailures += 1;
    }
  });
  context.failDrawing = true;
  harness.flushFrame(16);

  const failed = controller.getSnapshot();
  assert.equal(failed.failed, true);
  assert.equal(failed.running, false);
  assert.equal(failed.observerActive, false);
  assert.equal(failed.listenerActive, false);
  assert.equal(drawFailures, 1);
  assert.equal(harness.pendingFrames(), 0);
  assert.equal(harness.documentTarget.listenerCount(), 0);

  controller.setRenderParameters({ state: 'SUBMITTING' });
  assert.equal(drawFailures, 1);
  controller.dispose();
});

test('component boundary mounts one canvas and keeps phase-one static fallbacks', () => {
  const workspaceStart = appSource.indexOf('function ReviewImmersiveWorkspace');
  const workspaceEnd = appSource.indexOf('function CodeQualityReviewView', workspaceStart);
  const workspaceSource = appSource.slice(workspaceStart, workspaceEnd);

  assert.equal((workspaceSource.match(/<ReviewImmersiveCanvas/g) || []).length, 1);
  assert.match(
    workspaceSource,
    /key=\{`\$\{presentation\.selectedReviewKey[\s\S]*presentation\.engineVisual/
  );
  assert.match(workspaceSource, /<AgentReviewAnimation[\s\S]*reducedMotion/);
  assert.match(workspaceSource, /<StandardReviewAnimation[\s\S]*reducedMotion/);
  assert.match(componentSource, /createReviewCanvasController/);
  assert.match(componentSource, /controller\?\.dispose\(\)/);
  assert.match(componentSource, /data-review-canvas-fallback="true"/);
  assert.match(componentSource, /data-review-canvas-frame-count/);
  assert.match(componentSource, /data-review-canvas-average-draw-ms/);
  assert.match(componentSource, /data-review-canvas-max-draw-ms/);
  assert.match(componentSource, /data-review-canvas-particle-count/);
  assert.match(componentSource, /data-review-canvas-observer-active/);
  assert.match(componentSource, /data-review-canvas-listener-active/);
  assert.equal(componentSource.includes('setInterval'), false);
  assert.equal(componentSource.includes('fetch('), false);
});

function createHarness({
  width = 640,
  height = 360,
  dpr = 1,
  context = createContext()
} = {}) {
  let currentWidth = width;
  let currentHeight = height;
  let nextFrameId = 1;
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
  let clock = 0;
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
    container,
    context,
    documentTarget,
    observerInstances,
    create: options => createReviewCanvasController({
      canvas,
      container,
      environment,
      parameters: {
        engineVisual: 'AGENT_PARTICLE',
        engineIdentity: 'AGENT',
        state: 'ANALYZING'
      },
      ...options
    }),
    pendingFrames: () => frameCallbacks.size,
    flushFrame: timestamp => {
      const callbacks = [...frameCallbacks.values()];
      frameCallbacks.clear();
      for (const callback of callbacks) callback(timestamp);
    },
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
    addCount: 0,
    removeCount: 0,
    addEventListener(type, callback) {
      this.addCount += 1;
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(callback);
    },
    removeEventListener(type, callback) {
      this.removeCount += 1;
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

function createContext() {
  return {
    failDrawing: false,
    save() {},
    restore() {},
    setTransform() {},
    clearRect() {
      if (this.failDrawing) throw new Error('synthetic draw failure');
    },
    fillRect() {},
    beginPath() {},
    ellipse() {},
    stroke() {},
    arc() {},
    fill() {},
    moveTo() {},
    bezierCurveTo() {},
    createRadialGradient() {
      return { addColorStop() {} };
    }
  };
}
