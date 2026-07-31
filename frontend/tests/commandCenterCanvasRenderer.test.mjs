import assert from 'node:assert/strict';
import test from 'node:test';

import {
  COMMAND_CENTER_CANVAS_MAX_DPR,
  createCommandCenterCanvasController,
  normalizeCommandCenterScene,
  resolveCommandCenterCanvasFallback
} from '../src/command-center/commandCenterCanvasRenderer.js';
import {
  buildCommandCenterPresentation
} from '../src/command-center/commandCenterPresentation.js';


test('normalizes a stable static scene and rejects edges outside the presentation graph', () => {
  const scene = normalizeCommandCenterScene({
    id: 'static-scene',
    allowAnimation: true,
    nodes: [
      { id: 'a', columnKey: 'intake', x: -1, y: 0.5, flowCount: -2 },
      { id: 'b', columnKey: 'delivery', x: 2, y: 0.5, flowCount: 3 }
    ],
    edges: [
      { id: 'valid', from: 'a', to: 'b' },
      { id: 'invalid', from: 'a', to: 'missing' }
    ]
  });

  assert.equal(scene.allowAnimation, false);
  assert.deepEqual(
    scene.nodes.map(node => [node.id, node.x, node.y, node.flowCount]),
    [
      ['a', 0, 0.5, 0],
      ['b', 1, 0.5, 3]
    ]
  );
  assert.deepEqual(scene.edges, [{ id: 'valid', from: 'a', to: 'b' }]);
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


test('draws presentation nodes and edges once with capped DPR and no RAF loop', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: {
      activeFlows: [{
        id: '1:agent',
        taskId: 1,
        reviewKey: 'agent',
        displayName: 'Agent review',
        requestedEngine: 'AGENT',
        effectiveEngine: 'AGENT',
        fallback: false,
        status: 'RUNNING',
        stage: 'AGENT_ANALYZING',
        stageSource: 'PROGRESS'
      }]
    }
  });
  const harness = createHarness({ width: 960, height: 190, dpr: 4 });
  const controller = harness.create(presentation.topology.scene);

  assert.ok(controller);
  assert.equal(harness.canvas.width, 960 * COMMAND_CENTER_CANVAS_MAX_DPR);
  assert.equal(harness.canvas.height, 190 * COMMAND_CENTER_CANVAS_MAX_DPR);
  assert.equal(harness.pendingFrames(), 0);
  assert.equal(controller.getSnapshot().running, false);
  assert.equal(controller.getSnapshot().allowAnimation, false);
  assert.equal(controller.getSnapshot().nodeCount, 5);
  assert.equal(controller.getSnapshot().edgeCount, 4);
  assert.equal(controller.getSnapshot().frameCount, 1);
  assert.equal(harness.context.operations.filter(operation => operation === 'arc').length, 5);
  assert.equal(
    harness.context.operations.filter(operation => operation === 'bezierCurveTo').length,
    4
  );

  harness.resize(800, 190);
  assert.equal(controller.getSnapshot().frameCount, 2);
  assert.equal(harness.pendingFrames(), 0);

  controller.setScene(buildCommandCenterPresentation().topology.scene);
  assert.equal(controller.getSnapshot().frameCount, 3);
  assert.equal(harness.pendingFrames(), 0);
  controller.dispose();
  assert.equal(harness.observerInstances[0].disconnectCount, 1);
  assert.equal(harness.documentTarget.listenerCount(), 0);
});


test('keeps initialization and drawing failures inside the DOM fallback boundary', () => {
  let initializationFailures = 0;
  const unavailable = createHarness({ context: null }).create(
    buildCommandCenterPresentation().topology.scene,
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
    buildCommandCenterPresentation().topology.scene,
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
    resize: (nextWidth, nextHeight) => {
      currentWidth = nextWidth;
      currentHeight = nextHeight;
      observerInstances[0].emit(nextWidth, nextHeight);
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
