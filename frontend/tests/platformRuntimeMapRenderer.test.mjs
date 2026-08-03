import assert from 'node:assert/strict';
import test from 'node:test';

import {
  advancePlatformRuntimeMapDegradation,
  createPlatformRuntimeMapController,
  diffPlatformRuntimeMapScenes,
  measureOperationMapAnchors,
  PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY,
  PLATFORM_RUNTIME_MAP_VISUAL_TOKENS,
  resolvePlatformRuntimeMapFallback
} from '../src/command-center/platformRuntimeMapRenderer.js';


test('fresh idle owns one bounded RAF and stable resources across polling updates', () => {
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
  assert.equal(harness.pendingFrameCount(), 1);
  assert.equal(harness.canvas.attributes.get('data-command-center-anchor-count'), '5');
  assert.equal(harness.canvas.attributes.get('data-command-center-motion-state'), 'FRESH_IDLE');
  assert.equal(harness.canvas.attributes.get('data-command-center-environment-particles'), '8');

  for (let index = 0; index < 12; index += 1) controller.setScene(scene(`poll-${index}`));
  const afterPolling = controller.getSnapshot();
  assert.equal(afterPolling.observerRegistrationCount, 1);
  assert.equal(afterPolling.listenerRegistrationCount, 1);
  assert.equal(afterPolling.maxConcurrentRafCount, 1);
  assert.equal(afterPolling.activeRafCount, 1);
  assert.equal(harness.pendingFrameCount(), 1);
  assert.equal(harness.canvas.attributes.get('data-command-center-scene-updates'), '13');
  assert.equal(harness.canvas.attributes.get('data-command-center-max-concurrent-raf'), '1');
  assert.equal(PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.standard, '#c88a16');
  assert.equal(PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.agent, '#7056d8');

  controller.dispose();
  assert.equal(harness.documentTarget.listenerCount(), 0);
  assert.equal(harness.pendingFrameCount(), 0);
});


test('Runtime evidence produces only whitelisted and identity-bound effects', () => {
  const seen = new Set(['standard-a']);
  const previous = scene('previous', {
    queuedCount: 0,
    standard: lane('standard', {
      capacity: 4,
      utilizationPercent: 25,
      runningItems: [{ identity: 'standard-a', stage: 'PREFLIGHT' }]
    }),
    agent: lane('agent', {
      capacity: 2,
      utilizationPercent: 50,
      runningItems: [{ identity: 'agent-a', stage: 'AGENT_ANALYZING' }],
      workers: [{ identity: 'worker-a', state: 'IDLE' }]
    })
  });
  const next = scene('next', {
    queuedCount: 2,
    standard: lane('standard', {
      capacity: 4,
      queuedCount: 1,
      utilizationPercent: 50,
      nextQueuedIdentity: 'standard-next',
      runningItems: [
        { identity: 'standard-a', stage: 'MODEL_CALLING' },
        { identity: 'standard-b', stage: 'PREFLIGHT' }
      ]
    }),
    agent: lane('agent', {
      capacity: 2,
      queuedCount: 1,
      utilizationPercent: 50,
      nextQueuedIdentity: 'agent-next',
      runningItems: [{ identity: 'agent-a', stage: 'AGENT_ANALYZING' }],
      workers: [{ identity: 'worker-a', state: 'BUSY' }]
    })
  });

  const effects = diffPlatformRuntimeMapScenes(previous, next, {
    now: 100,
    seenDispatchIdentities: seen
  });
  assert.equal(effects.filter(item => item.type === 'dispatch').length, 1);
  assert.equal(effects.some(item => item.type === 'dispatch' && item.identity === 'standard-b'), true);
  assert.equal(effects.some(item => item.type === 'stage' && item.identity === 'standard-a'), true);
  assert.equal(effects.some(item => item.type === 'worker' && item.identity === 'worker-a'), true);
  assert.equal(effects.some(item => item.type === 'gate'), true);
  assert.equal(effects.filter(item => item.type === 'candidate').length, 2);
  assert.equal(effects.some(item => item.type === 'utilization' && item.lane === 'standard'), true);
  assert.equal(effects.some(item => item.type === 'beacon'), false);

  const disappearance = diffPlatformRuntimeMapScenes(next, scene('removed', {
    queuedCount: 2,
    standard: lane('standard', {
      capacity: 4,
      queuedCount: 1,
      utilizationPercent: 25,
      nextQueuedIdentity: 'standard-next',
      runningItems: [{ identity: 'standard-a', stage: 'MODEL_CALLING' }]
    }),
    agent: next.lanes[1]
  }), { now: 200, seenDispatchIdentities: seen });
  assert.equal(disappearance.some(item => item.type === 'dispatch'), false);
  assert.equal(disappearance.some(item => item.type === 'beacon'), false);
});


test('Standard and Agent entries remain independently reproducible Runtime events', () => {
  const baseline = scene('baseline', {
    standard: lane('standard', {
      capacity: 4,
      utilizationPercent: 25,
      runningItems: [{ identity: 'standard-a', stage: 'PREFLIGHT' }]
    }),
    agent: lane('agent', {
      capacity: 2,
      utilizationPercent: 50,
      runningItems: [{ identity: 'agent-a', stage: 'AGENT_ANALYZING' }]
    })
  });
  const seen = new Set(['standard-a', 'agent-a']);
  const standardEntry = diffPlatformRuntimeMapScenes(baseline, scene('standard-entry', {
    standard: lane('standard', {
      capacity: 4,
      utilizationPercent: 50,
      runningItems: [
        { identity: 'standard-a', stage: 'PREFLIGHT' },
        { identity: 'standard-b', stage: 'PREFLIGHT' }
      ]
    }),
    agent: baseline.lanes[1]
  }), { now: 100, seenDispatchIdentities: seen });
  const agentEntry = diffPlatformRuntimeMapScenes(baseline, scene('agent-entry', {
    standard: baseline.lanes[0],
    agent: lane('agent', {
      capacity: 2,
      utilizationPercent: 100,
      runningItems: [
        { identity: 'agent-a', stage: 'AGENT_ANALYZING' },
        { identity: 'agent-b', stage: 'AGENT_ANALYZING' }
      ]
    })
  }), { now: 200, seenDispatchIdentities: seen });

  assert.deepEqual(standardEntry.filter(item => item.type === 'dispatch').map(item => item.lane), ['standard']);
  assert.deepEqual(agentEntry.filter(item => item.type === 'dispatch').map(item => item.lane), ['agent']);
  assert.equal(standardEntry.some(item => item.type === 'beacon'), false);
  assert.equal(agentEntry.some(item => item.type === 'beacon'), false);
});


test('new Review stage and Worker changes animate locally then expire without Beacon arrival', () => {
  const harness = createHarness();
  harness.setReviewRect('standard-a', rect(540, 90, 90, 80));
  harness.setReviewRect('standard-b', rect(640, 90, 90, 80));
  harness.setWorkerRect('worker-a', rect(570, 360, 90, 50));
  const initialScene = scene('initial', {
    standard: lane('standard', {
      capacity: 4,
      utilizationPercent: 25,
      runningItems: [{ identity: 'standard-a', stage: 'PREFLIGHT' }]
    }),
    agent: lane('agent', {
      capacity: 2,
      workers: [{ identity: 'worker-a', state: 'IDLE' }]
    })
  });
  const controller = createPlatformRuntimeMapController({
    canvas: harness.canvas,
    container: harness.container,
    environment: harness.environment,
    scene: initialScene
  });

  controller.setScene(scene('changed', {
    standard: lane('standard', {
      capacity: 4,
      utilizationPercent: 50,
      runningItems: [
        { identity: 'standard-a', stage: 'MODEL_CALLING' },
        { identity: 'standard-b', stage: 'PREFLIGHT' }
      ]
    }),
    agent: lane('agent', {
      capacity: 2,
      workers: [{ identity: 'worker-a', state: 'BUSY' }]
    })
  }));

  assert.equal(harness.canvas.attributes.get('data-command-center-dispatch-cursors'), '1');
  assert.equal(harness.canvas.attributes.get('data-command-center-stage-feedbacks'), '1');
  assert.equal(harness.canvas.attributes.get('data-command-center-worker-feedbacks'), '1');
  assert.equal(harness.canvas.attributes.get('data-command-center-animated-reviews'), '2');
  assert.equal(harness.canvas.attributes.get('data-command-center-animated-workers'), '1');
  assert.equal(harness.canvas.attributes.get('data-command-center-beacon-events'), '0');

  harness.runFrame(1000);
  assert.equal(harness.canvas.attributes.get('data-command-center-dispatch-cursors'), '0');
  assert.equal(harness.canvas.attributes.get('data-command-center-stage-feedbacks'), '0');
  assert.equal(harness.canvas.attributes.get('data-command-center-worker-feedbacks'), '0');
  assert.equal(controller.getSnapshot().activeRafCount, 1);

  controller.setScene(scene('removed', {
    standard: lane('standard', {
      capacity: 4,
      utilizationPercent: 25,
      runningItems: [{ identity: 'standard-a', stage: 'MODEL_CALLING' }]
    }),
    agent: lane('agent', {
      capacity: 2,
      workers: [{ identity: 'worker-a', state: 'BUSY' }]
    })
  }));
  assert.equal(harness.canvas.attributes.get('data-command-center-beacon-events'), '0');

  controller.setScene(scene('reappeared', {
    standard: lane('standard', {
      capacity: 4,
      utilizationPercent: 50,
      runningItems: [
        { identity: 'standard-a', stage: 'MODEL_CALLING' },
        { identity: 'standard-b', stage: 'PREFLIGHT' }
      ]
    }),
    agent: lane('agent', {
      capacity: 2,
      workers: [{ identity: 'worker-a', state: 'BUSY' }]
    })
  }));
  assert.equal(harness.canvas.attributes.get('data-command-center-dispatch-cursors'), '0');
  controller.dispose();
});


test('stale error reduced motion hidden page and hidden updates keep RAF at zero', () => {
  const harness = createHarness();
  const controller = createPlatformRuntimeMapController({
    canvas: harness.canvas,
    container: harness.container,
    environment: harness.environment,
    scene: scene('reduced', { motionDisabled: true })
  });
  assert.equal(controller.getSnapshot().activeRafCount, 0);
  assert.equal(harness.pendingFrameCount(), 0);

  controller.setScene(scene('fresh'));
  assert.equal(controller.getSnapshot().activeRafCount, 1);
  controller.setScene(scene('stale', { freshness: 'STALE' }));
  assert.equal(controller.getSnapshot().activeRafCount, 0);
  assert.equal(harness.canvas.attributes.get('data-command-center-motion-state'), 'STALE');
  controller.setScene(scene('error', { runtimeError: true }));
  assert.equal(controller.getSnapshot().activeRafCount, 0);
  assert.equal(harness.canvas.attributes.get('data-command-center-motion-state'), 'RUNTIME_ERROR');

  controller.setScene(scene('visible'));
  assert.equal(controller.getSnapshot().activeRafCount, 1);
  harness.setHidden(true);
  assert.equal(controller.getSnapshot().activeRafCount, 0);
  controller.setScene(scene('hidden-update', {
    standard: lane('standard', {
      capacity: 2,
      utilizationPercent: 50,
      runningItems: [{ identity: 'hidden-review', stage: 'PREFLIGHT' }]
    })
  }));
  harness.setHidden(false);
  assert.equal(controller.getSnapshot().activeRafCount, 1);
  assert.equal(harness.canvas.attributes.get('data-command-center-dispatch-cursors'), '0');
  controller.dispose();
});


test('performance degradation order is particles then 12fps then static', () => {
  assert.equal(advancePlatformRuntimeMapDegradation(0), 1);
  assert.equal(advancePlatformRuntimeMapDegradation(1), 2);
  assert.equal(advancePlatformRuntimeMapDegradation(2), 3);
  assert.equal(advancePlatformRuntimeMapDegradation(3), 3);
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


test('Canvas initialization failure reports fallback and leaves no RAF behind', () => {
  const harness = createHarness();
  let failureCount = 0;
  harness.canvas.getContext = () => null;

  const controller = createPlatformRuntimeMapController({
    canvas: harness.canvas,
    container: harness.container,
    environment: harness.environment,
    scene: scene('canvas-failure'),
    onFailure: () => { failureCount += 1; }
  });

  assert.equal(controller, null);
  assert.equal(failureCount, 1);
  assert.equal(harness.pendingFrameCount(), 0);
});


function scene(snapshotKey, options = {}) {
  const standard = options.standard || lane('standard');
  const agent = options.agent || lane('agent');
  const runningCount = standard.runningItems.length + agent.runningItems.length;
  const capacity = standard.capacity + agent.capacity;
  return {
    snapshotKey,
    freshness: options.freshness || 'FRESH',
    runtimeError: Boolean(options.runtimeError),
    motionDisabled: Boolean(options.motionDisabled),
    runningCount,
    queuedCount: options.queuedCount ?? standard.queuedCount + agent.queuedCount,
    capacity,
    utilizationPercent: capacity > 0 ? Math.round(runningCount / capacity * 100) : 0,
    lanes: [standard, agent],
    connections: [
      { from: 'queue-gate', to: 'ai-review-core', token: 'queue' },
      { from: 'ai-review-core', to: 'standard', token: 'standard' },
      { from: 'ai-review-core', to: 'agent', token: 'agent' },
      { from: 'standard', to: 'result-beacon', token: 'standard' },
      { from: 'agent', to: 'result-beacon', token: 'agent' }
    ]
  };
}


function lane(zoneKey, options = {}) {
  return {
    zoneKey,
    capacity: options.capacity || 0,
    queuedCount: options.queuedCount || 0,
    utilizationPercent: options.utilizationPercent || 0,
    nextQueuedIdentity: options.nextQueuedIdentity || null,
    runningItems: options.runningItems || [],
    workers: options.workers || []
  };
}


function createHarness() {
  const listeners = new Set();
  const reviewRects = new Map();
  const workerRects = new Map();
  const documentTarget = {
    hidden: false,
    visibilityState: 'visible',
    addEventListener(name, listener) { if (name === 'visibilitychange') listeners.add(listener); },
    removeEventListener(name, listener) { if (name === 'visibilitychange') listeners.delete(listener); },
    emit() { for (const listener of listeners) listener(); },
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
  const namedRects = {
    '[data-command-center-core-anchor="true"]': rect(275, 175, 130, 130),
    '[data-command-center-gate-anchor="true"]': rect(70, 120, 80, 60),
    '[data-command-center-beacon-anchor="true"]': rect(830, 190, 100, 100),
    '[data-command-center-next-review="standard"]': rect(35, 300, 150, 35),
    '[data-command-center-next-review="agent"]': rect(35, 345, 150, 35)
  };
  const container = {
    getBoundingClientRect: () => rect(0, 0, 980, 500),
    querySelector(selector) {
      if (namedRects[selector]) return node(namedRects[selector]);
      const match = selector.match(/data-zone-key="([^"]+)"/);
      const value = match ? rects[match[1]] : null;
      return value ? node(value) : null;
    },
    querySelectorAll(selector) {
      if (selector.includes('worker-tower')) return [...workerRects].map(([identity, value]) => node(value, 'data-worker-identity', identity));
      if (selector.includes('review-marker')) return [...reviewRects].map(([identity, value]) => node(value, 'data-review-identity', identity));
      return [];
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
      now: () => now
    },
    pendingFrameCount: () => frames.size,
    runFrame(timestamp) {
      now = timestamp;
      const entry = frames.entries().next().value;
      assert.ok(entry, 'expected a pending animation frame');
      frames.delete(entry[0]);
      entry[1](timestamp);
    },
    setHidden(hidden) {
      documentTarget.hidden = hidden;
      documentTarget.visibilityState = hidden ? 'hidden' : 'visible';
      documentTarget.emit();
    },
    setReviewRect(identity, value) { reviewRects.set(identity, value); },
    setWorkerRect(identity, value) { workerRects.set(identity, value); }
  };
}


function node(value, attribute, identity) {
  return {
    getBoundingClientRect: () => value,
    getAttribute: name => name === attribute ? identity : null
  };
}


function rect(left, top, width, height) {
  return { left, top, right: left + width, bottom: top + height, width, height };
}
