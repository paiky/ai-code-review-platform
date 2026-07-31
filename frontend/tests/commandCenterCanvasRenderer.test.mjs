import assert from 'node:assert/strict';
import test from 'node:test';

import {
  COMMAND_CENTER_CANVAS_MAX_DPR,
  COMMAND_CENTER_PARTICLE_LIMIT,
  createCommandCenterCanvasController,
  createCommandCenterParticleLayout,
  deriveCommandCenterFlowSeed,
  normalizeCommandCenterScene,
  reconcileCommandCenterScenes,
  resolveCommandCenterCanvasFallback
} from '../src/command-center/commandCenterCanvasRenderer.js';
import {
  buildCommandCenterPresentation
} from '../src/command-center/commandCenterPresentation.js';


test('normalizes static topology and rejects invalid nodes edges and flows', () => {
  const scene = normalizeCommandCenterScene({
    id: 'snapshot-scene',
    snapshotKey: 'snapshot-1',
    freshness: 'FRESH',
    allowAnimation: true,
    nodes: [
      { id: 'a', columnKey: 'intake', x: -1, y: 0.5, flowCount: -2 },
      { id: 'b', columnKey: 'delivery', x: 2, y: 0.5, flowCount: 3 }
    ],
    edges: [
      { id: 'valid', from: 'a', to: 'b' },
      { id: 'invalid', from: 'a', to: 'missing' }
    ],
    flows: [
      {
        id: '1:valid',
        taskId: 1,
        reviewKey: 'valid',
        columnKey: 'delivery',
        visualState: 'RUNNING',
        motionMode: 'CONTINUOUS',
        stateRecognized: true
      },
      {
        id: '1:invalid',
        columnKey: 'future',
        visualState: 'RUNNING'
      },
      {
        id: '1:future',
        columnKey: 'delivery',
        visualState: 'THINKING',
        motionMode: 'CONTINUOUS',
        stateRecognized: true
      }
    ]
  });

  assert.equal(scene.snapshotKey, 'snapshot-1');
  assert.equal(scene.allowAnimation, true);
  assert.deepEqual(
    scene.nodes.map(node => [node.id, node.x, node.y, node.flowCount]),
    [
      ['a', 0, 0.5, 0],
      ['b', 1, 0.5, 3]
    ]
  );
  assert.deepEqual(scene.edges, [{ id: 'valid', from: 'a', to: 'b' }]);
  assert.equal(scene.flows.length, 2);
  assert.equal(scene.flows[0].id, '1:valid');
  assert.deepEqual(
    [scene.flows[1].visualState, scene.flows[1].motionMode, scene.flows[1].stateRecognized],
    ['RUNNING', 'STATIC', false]
  );
});


test('selects full DOM fallback for reduced motion small screens and Canvas failures', () => {
  assert.equal(
    resolveCommandCenterCanvasFallback({ reducedMotion: true, canvasReady: true }),
    'REDUCED_MOTION'
  );
  assert.equal(
    resolveCommandCenterCanvasFallback({ smallScreen: true, canvasReady: true }),
    'SMALL_SCREEN'
  );
  assert.equal(
    resolveCommandCenterCanvasFallback({ canvasFailed: true }),
    'CANVAS_FAILURE'
  );
  assert.equal(resolveCommandCenterCanvasFallback(), 'INITIALIZING');
  assert.equal(
    resolveCommandCenterCanvasFallback({ canvasReady: true }),
    null
  );
});


test('derives fixed seeds stable particle ids and a hard global particle cap', () => {
  const flows = Array.from({ length: 20 }, (_, index) => (
    flow(index + 1, `review-${index + 1}`, 'RUNNING', 'MODEL_CALLING')
  ));
  const scene = buildScene('2026-07-31T02:00:00Z', flows);
  const first = createCommandCenterParticleLayout(scene);
  const second = createCommandCenterParticleLayout(scene);

  assert.equal(first.length, COMMAND_CENTER_PARTICLE_LIMIT);
  assert.deepEqual(first, second);
  assert.equal(new Set(first.map(particle => particle.id)).size, first.length);
  assert.equal(
    deriveCommandCenterFlowSeed({ taskId: 1, reviewKey: 'review-1' }),
    deriveCommandCenterFlowSeed({ taskId: 1, reviewKey: 'review-1' })
  );
  assert.notEqual(
    deriveCommandCenterFlowSeed({ taskId: 1, reviewKey: 'review-1' }),
    deriveCommandCenterFlowSeed({ taskId: 1, reviewKey: 'review-2' })
  );
  assert.equal(first[0].id, '1:review-1:particle:0');
});


test('reconciles only real fresh snapshot changes and never replays initial history', () => {
  const running = buildScene(
    '2026-07-31T02:00:00Z',
    [flow(1, 'main', 'RUNNING', 'MODEL_CALLING')]
  );
  const sameState = buildScene(
    '2026-07-31T02:00:05Z',
    [flow(1, 'main', 'RUNNING', 'MODEL_CALLING', { updatedAt: '2026-07-31T02:00:05Z' })]
  );
  const failed = buildScene(
    '2026-07-31T02:00:10Z',
    [flow(1, 'main', 'FAILED', 'FAILED')]
  );
  const empty = buildScene('2026-07-31T01:59:55Z', []);
  const stale = buildScene(
    '2026-07-31T02:00:15Z',
    [flow(1, 'main', 'RUNNING', 'MODEL_CALLING')],
    'STALE'
  );

  assert.equal(reconcileCommandCenterScenes(running, sameState).length, 0);
  assert.equal(reconcileCommandCenterScenes(running, failed).length, 1);
  assert.deepEqual(
    reconcileCommandCenterScenes(running, failed)[0],
    {
      id: 'transition:1:main:2026-07-31T02:00:10Z:STATE_CHANGED',
      flowId: '1:main',
      kind: 'STATE_CHANGED',
      fromState: 'RUNNING',
      toState: 'FAILED',
      columnKey: 'delivery',
      engineKind: 'STANDARD'
    }
  );
  assert.equal(
    reconcileCommandCenterScenes(running, failed, { initial: true }).length,
    0
  );
  assert.equal(reconcileCommandCenterScenes(empty, running).length, 1);
  assert.equal(reconcileCommandCenterScenes(running, stale).length, 0);
});


test('keeps historical Failed and Fallback static on initial load', () => {
  const scene = buildScene('2026-07-31T02:00:00Z', [
    flow(1, 'failed', 'FAILED', 'FAILED'),
    flow(2, 'fallback', 'FALLBACK', 'FALLBACK', {
      fallback: true,
      requestedEngine: 'AGENT',
      effectiveEngine: 'STANDARD_FALLBACK'
    })
  ]);
  const harness = createHarness({ width: 960, height: 190, dpr: 4 });
  const controller = harness.create(scene);

  assert.ok(controller);
  assert.equal(harness.canvas.width, 960 * COMMAND_CENTER_CANVAS_MAX_DPR);
  assert.equal(harness.canvas.height, 190 * COMMAND_CENTER_CANVAS_MAX_DPR);
  assert.equal(harness.pendingFrames(), 0);
  assert.equal(controller.getSnapshot().running, false);
  assert.equal(controller.getSnapshot().allowAnimation, false);
  assert.equal(controller.getSnapshot().transitionCount, 0);
  assert.equal(controller.getSnapshot().particleCount, 8);
  assert.equal(controller.getSnapshot().frameCount, 1);

  harness.resize(800, 190);
  assert.equal(controller.getSnapshot().frameCount, 2);
  assert.equal(harness.pendingFrames(), 0);
  controller.dispose();
  assert.equal(harness.observerInstances[0].disconnectCount, 1);
  assert.equal(harness.documentTarget.listenerCount(), 0);
});


test('animates live state and stops after a one-time terminal transition', () => {
  const running = buildScene(
    '2026-07-31T02:00:00Z',
    [flow(1, 'main', 'RUNNING', 'MODEL_CALLING')]
  );
  const sameState = buildScene(
    '2026-07-31T02:00:05Z',
    [flow(1, 'main', 'RUNNING', 'MODEL_CALLING')]
  );
  const failed = buildScene(
    '2026-07-31T02:00:10Z',
    [flow(1, 'main', 'FAILED', 'FAILED')]
  );
  const harness = createHarness();
  const controller = harness.create(running);

  assert.ok(controller);
  assert.equal(controller.getSnapshot().allowAnimation, true);
  assert.equal(harness.pendingFrames(), 1);
  harness.flushFrame(16);
  assert.equal(harness.pendingFrames(), 1);

  controller.setScene(sameState);
  assert.equal(controller.getSnapshot().transitionCount, 0);
  assert.equal(harness.pendingFrames(), 1);

  controller.setScene(failed);
  assert.equal(controller.getSnapshot().allowAnimation, false);
  assert.equal(controller.getSnapshot().transitionCount, 1);
  assert.equal(harness.pendingFrames(), 1);

  harness.flushFrame(1_200);
  assert.equal(controller.getSnapshot().transitionCount, 0);
  assert.equal(controller.getSnapshot().running, false);
  assert.equal(harness.pendingFrames(), 0);
  controller.dispose();
});


test('does not replay snapshot changes received while hidden', () => {
  const running = buildScene(
    '2026-07-31T02:00:00Z',
    [flow(1, 'main', 'RUNNING', 'MODEL_CALLING')]
  );
  const failed = buildScene(
    '2026-07-31T02:00:05Z',
    [flow(1, 'main', 'FAILED', 'FAILED')]
  );
  const harness = createHarness();
  const controller = harness.create(running);

  assert.equal(harness.pendingFrames(), 1);
  harness.setHidden(true);
  assert.equal(harness.pendingFrames(), 0);
  controller.setScene(failed);
  assert.equal(controller.getSnapshot().transitionCount, 0);
  harness.setHidden(false);
  assert.equal(controller.getSnapshot().allowAnimation, false);
  assert.equal(harness.pendingFrames(), 0);
  controller.dispose();
});


test('stops for stale snapshots and keeps unknown states static', () => {
  const running = buildScene(
    '2026-07-31T02:00:00Z',
    [flow(1, 'main', 'RUNNING', 'MODEL_CALLING')]
  );
  const stale = buildScene(
    '2026-07-31T02:00:05Z',
    [flow(1, 'main', 'RUNNING', 'MODEL_CALLING')],
    'STALE'
  );
  const unknown = buildScene(
    '2026-07-31T02:00:10Z',
    [flow(1, 'main', 'RUNNING', 'UNKNOWN', {
      statusRecognized: false,
      stageRecognized: false
    })]
  );
  const harness = createHarness();
  const controller = harness.create(running);

  assert.equal(harness.pendingFrames(), 1);
  controller.setScene(stale);
  assert.equal(controller.getSnapshot().freshness, 'STALE');
  assert.equal(controller.getSnapshot().allowAnimation, false);
  assert.equal(controller.getSnapshot().transitionCount, 0);
  assert.equal(harness.pendingFrames(), 0);

  controller.setScene(unknown);
  assert.equal(controller.getSnapshot().allowAnimation, false);
  assert.equal(controller.getSnapshot().transitionCount, 0);
  assert.equal(harness.pendingFrames(), 0);
  controller.dispose();
});


test('keeps initialization and drawing failures inside the DOM fallback boundary', () => {
  let initializationFailures = 0;
  const unavailable = createHarness({ context: null }).create(
    buildScene('2026-07-31T02:00:00Z', []),
    () => {
      initializationFailures += 1;
    }
  );
  assert.equal(unavailable, null);
  assert.equal(initializationFailures, 1);

  let drawFailures = 0;
  const harness = createHarness();
  harness.context.failDrawing = true;
  const failed = harness.create(
    buildScene('2026-07-31T02:00:00Z', []),
    () => {
      drawFailures += 1;
    }
  );
  assert.ok(failed);
  assert.equal(failed.getSnapshot().failed, true);
  assert.equal(failed.getSnapshot().running, false);
  assert.equal(drawFailures, 1);
  assert.equal(harness.pendingFrames(), 0);
  assert.equal(harness.documentTarget.listenerCount(), 0);
  failed.dispose();
});


function buildScene(snapshotKey, flows, freshness = 'FRESH') {
  return buildCommandCenterPresentation({
    runtime: {
      freshness,
      generatedAt: snapshotKey,
      activeFlows: flows
    }
  }).topology.scene;
}


function flow(
  taskId,
  reviewKey,
  status,
  stage,
  overrides = {}
) {
  return {
    id: `${taskId}:${reviewKey}`,
    taskId,
    reviewKey,
    displayName: reviewKey,
    requestedEngine: 'STANDARD',
    effectiveEngine: 'STANDARD',
    fallback: false,
    status,
    statusRecognized: true,
    stage,
    stageRecognized: true,
    stageSource: 'PROGRESS',
    ...overrides
  };
}


function createHarness({
  width = 640,
  height = 190,
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
      clock += 0.2;
      return clock;
    }
  };

  return {
    canvas,
    context,
    documentTarget,
    observerInstances,
    create: (scene, onFailure) => createCommandCenterCanvasController({
      canvas,
      container,
      environment,
      scene,
      onFailure
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


function createContext() {
  return {
    failDrawing: false,
    operations: [],
    save() {
      this.operations.push('save');
    },
    restore() {
      this.operations.push('restore');
    },
    setTransform() {
      this.operations.push('setTransform');
    },
    clearRect() {
      if (this.failDrawing) throw new Error('synthetic draw failure');
      this.operations.push('clearRect');
    },
    beginPath() {
      this.operations.push('beginPath');
    },
    moveTo() {
      this.operations.push('moveTo');
    },
    lineTo() {
      this.operations.push('lineTo');
    },
    quadraticCurveTo() {
      this.operations.push('quadraticCurveTo');
    },
    bezierCurveTo() {
      this.operations.push('bezierCurveTo');
    },
    arc() {
      this.operations.push('arc');
    },
    fill() {
      this.operations.push('fill');
    },
    stroke() {
      this.operations.push('stroke');
    }
  };
}
