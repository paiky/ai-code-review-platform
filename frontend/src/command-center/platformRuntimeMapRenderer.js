import { createCanvasRuntime } from '../canvas/canvasRuntime.js';


export const PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY = '__platformRuntimeMapDiagnostics';
export const PLATFORM_RUNTIME_MAP_DRAW_BUDGET_MS = 8;
export const PLATFORM_RUNTIME_MAP_IDLE_FRAME_INTERVAL_MS = 1000 / 12;
export const PLATFORM_RUNTIME_MAP_EVENT_FRAME_INTERVAL_MS = 1000 / 30;

export const PLATFORM_RUNTIME_MAP_VISUAL_TOKENS = Object.freeze({
  terrain: '#e8f1f6',
  terrainInset: '#d8e7ef',
  trench: '#7891a3',
  roadbed: '#f8fcfe',
  queue: '#c48619',
  standard: '#c88a16',
  standardHighlight: '#f4c451',
  agent: '#7056d8',
  agentHighlight: '#a892ff',
  beacon: '#2baebb',
  neutral: '#587187'
});

const CONNECTION_COLORS = Object.freeze({
  queue: PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.queue,
  standard: PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.standard,
  agent: PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.agent,
  neutral: PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.neutral
});
const EFFECT_DURATION_MS = Object.freeze({
  reveal: 600,
  gate: 650,
  candidate: 300,
  dispatch: 900,
  stage: 450,
  worker: 520,
  utilization: 450
});
const MAX_EFFECTS = 32;
const MAX_DISPATCH_IDENTITIES = 200;


export function createPlatformRuntimeMapController(options = {}) {
  let controller = null;
  try {
    controller = new PlatformRuntimeMapController(options);
    return controller.initialize() ? controller : null;
  } catch {
    controller?.dispose();
    safelyNotifyFailure(options.onFailure);
    return null;
  }
}


export function resolvePlatformRuntimeMapFallback({
  smallScreen = false,
  canvasFailed = false,
  canvasReady = false
} = {}) {
  if (smallScreen) return 'SMALL_SCREEN';
  if (canvasFailed) return 'CANVAS_FAILED';
  if (!canvasReady) return 'CANVAS_LOADING';
  return null;
}


export function measureOperationMapAnchors(container, connections = []) {
  const containerRect = container?.getBoundingClientRect?.();
  if (!validRect(containerRect)) return [];
  const rects = new Map();
  const zoneKeys = new Set(connections.flatMap(connection => [connection.from, connection.to]));
  for (const zoneKey of zoneKeys) {
    const node = container.querySelector?.(`[data-zone-key="${zoneKey}"]`);
    const rect = node?.getBoundingClientRect?.();
    if (validRect(rect)) rects.set(zoneKey, relativeRect(rect, containerRect));
  }
  return connections.flatMap(connection => {
    const fromRect = rects.get(connection.from);
    const toRect = rects.get(connection.to);
    if (!fromRect || !toRect) return [];
    return [{
      ...connection,
      fromPoint: connectionPoint(fromRect, toRect),
      toPoint: connectionPoint(toRect, fromRect)
    }];
  });
}


export function diffPlatformRuntimeMapScenes(previousValue, nextValue, {
  now = 0,
  suppress = false,
  seenDispatchIdentities = new Set()
} = {}) {
  const previous = normalizeScene(previousValue);
  const next = normalizeScene(nextValue);
  if (suppress || !motionSceneIsFresh(previous) || !motionSceneIsFresh(next)) return [];

  const effects = [];
  if (previous.queuedCount === 0 && next.queuedCount > 0) {
    effects.push(effect('gate', now));
  }
  for (const lane of next.lanes) {
    const oldLane = previous.lanes.find(item => item.zoneKey === lane.zoneKey) || emptyLane(lane.zoneKey);
    if (oldLane.nextQueuedIdentity !== lane.nextQueuedIdentity) {
      effects.push(effect('candidate', now, { lane: lane.zoneKey }));
    }
    const oldItems = new Map(oldLane.runningItems.map(item => [item.identity, item]));
    const newItems = lane.runningItems.filter(item => !oldItems.has(item.identity));
    for (const item of newItems) {
      if (seenDispatchIdentities.has(item.identity)) continue;
      effects.push(effect('dispatch', now, { lane: lane.zoneKey, identity: item.identity }));
    }
    for (const item of lane.runningItems) {
      const oldItem = oldItems.get(item.identity);
      if (oldItem && oldItem.stage !== item.stage) {
        effects.push(effect('stage', now, { lane: lane.zoneKey, identity: item.identity }));
      }
    }
    const oldWorkers = new Map(oldLane.workers.map(worker => [worker.identity, worker]));
    for (const worker of lane.workers) {
      const oldWorker = oldWorkers.get(worker.identity);
      if (oldWorker && oldWorker.state !== worker.state) {
        effects.push(effect('worker', now, { identity: worker.identity }));
      }
    }
    if (oldLane.utilizationPercent !== lane.utilizationPercent) {
      effects.push(effect('utilization', now, {
        lane: lane.zoneKey,
        from: oldLane.utilizationPercent,
        to: lane.utilizationPercent
      }));
    }
  }

  const dispatchEffects = effects.filter(item => item.type === 'dispatch').slice(0, 2);
  return effects
    .filter(item => item.type !== 'dispatch')
    .concat(dispatchEffects)
    .slice(-MAX_EFFECTS);
}


export function advancePlatformRuntimeMapDegradation(level) {
  return Math.min(3, Math.max(0, Number(level) || 0) + 1);
}


class PlatformRuntimeMapController {
  constructor(options) {
    this.canvas = options.canvas;
    this.container = options.container;
    this.scene = normalizeScene(options.scene);
    this.onFailure = options.onFailure;
    this.environment = options.environment;
    this.documentTarget = options.environment?.documentTarget
      || (typeof document === 'undefined' ? null : document);
    this.now = options.environment?.now
      || (() => (typeof performance === 'undefined' ? Date.now() : performance.now()));
    this.runtime = null;
    this.sceneUpdateCount = 1;
    this.lastAnchorCount = 0;
    this.lastParticleCount = 0;
    this.effects = [];
    this.seenDispatchIdentities = new Set();
    this.seenDispatchOrder = [];
    this.previousScene = this.scene;
    this.hasSuccessfulSnapshot = sceneHasSnapshot(this.scene);
    this.performanceLevel = 0;
    this.overBudgetSince = null;
    if (this.hasSuccessfulSnapshot && !this.motionSuppressed(this.scene)) {
      this.effects.push(effect('reveal', this.now()));
    }
    if (this.hasSuccessfulSnapshot) this.rememberCurrentDispatchIdentities(this.scene);
  }

  initialize() {
    this.runtime = createCanvasRuntime({
      canvas: this.canvas,
      container: this.container,
      environment: this.environment,
      drawBudgetMs: PLATFORM_RUNTIME_MAP_DRAW_BUDGET_MS,
      maxDpr: 2,
      isAnimationEnabled: () => {
        const enabled = this.isAnimationEnabled();
        if (!enabled) this.publishDiagnostics();
        return enabled;
      },
      getAnimationFrameInterval: () => this.getFrameInterval(),
      onDraw: frame => this.draw(frame),
      onStateChange: () => this.publishDiagnostics(),
      onFailure: () => safelyNotifyFailure(this.onFailure)
    });
    this.publishDiagnostics();
    return Boolean(this.runtime);
  }

  setScene(scene) {
    const nextScene = normalizeScene(scene);
    const now = this.now();
    const suppressed = this.motionSuppressed(nextScene) || this.isDocumentHidden();
    if (!this.hasSuccessfulSnapshot && sceneHasSnapshot(nextScene)) {
      this.hasSuccessfulSnapshot = true;
      if (!suppressed) this.effects = [effect('reveal', now)];
      this.rememberCurrentDispatchIdentities(nextScene);
    } else {
      const changes = diffPlatformRuntimeMapScenes(this.previousScene, nextScene, {
        now,
        suppress: suppressed,
        seenDispatchIdentities: this.seenDispatchIdentities
      });
      this.rememberCurrentDispatchIdentities(nextScene);
      this.effects = suppressed ? [] : this.effects.concat(changes).slice(-MAX_EFFECTS);
    }
    this.previousScene = nextScene;
    this.scene = nextScene;
    if (suppressed) this.effects = [];
    this.sceneUpdateCount += 1;
    this.runtime?.refresh();
    this.publishDiagnostics();
  }

  draw({ context, width, height, dpr, timestamp }) {
    this.applyPerformanceGuard(timestamp);
    this.effects = activeEffects(this.effects, timestamp);
    const anchors = measureOperationMapAnchors(this.container, this.scene.connections);
    this.lastAnchorCount = anchors.length;
    const reveal = latestEffect(this.effects, 'reveal');
    const revealAlpha = reveal ? 0.5 + 0.5 * effectProgress(reveal, timestamp) : 1;

    context.setTransform?.(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);
    context.save();
    context.globalAlpha = revealAlpha;
    drawDaylightTerrain(context, width, height, this.scene.freshness);
    drawStaticConnections(context, anchors, this.scene.freshness);
    this.lastParticleCount = drawEnvironmentLife(context, width, height, timestamp, this.scene, this.performanceLevel);
    drawCoreMotion(context, this.container, this.scene, this.effects, timestamp);
    drawGateMotion(context, this.container, this.scene, this.effects, timestamp);
    drawBeaconStandby(context, this.container, this.scene);
    drawEventFeedback(context, this.container, anchors, this.effects, timestamp);
    context.restore();
    this.publishDiagnostics(timestamp);
  }

  applyPerformanceGuard(timestamp) {
    const snapshot = this.runtime?.getSnapshot?.() || {};
    if (snapshot.lastDrawMs > PLATFORM_RUNTIME_MAP_DRAW_BUDGET_MS) {
      if (this.overBudgetSince === null) this.overBudgetSince = timestamp;
      if (timestamp - this.overBudgetSince >= 3000) {
        this.performanceLevel = advancePlatformRuntimeMapDegradation(this.performanceLevel);
        this.overBudgetSince = timestamp;
        if (this.performanceLevel >= 3) this.effects = [];
      }
    } else {
      this.overBudgetSince = null;
    }
  }

  isAnimationEnabled() {
    return !this.motionSuppressed(this.scene)
      && !this.isDocumentHidden()
      && this.performanceLevel < 3;
  }

  getFrameInterval() {
    if (this.performanceLevel >= 2) return PLATFORM_RUNTIME_MAP_IDLE_FRAME_INTERVAL_MS;
    const hasPriorityEvent = this.effects.some(item => (
      item.type === 'dispatch' || item.type === 'stage' || item.type === 'worker'
    ));
    return hasPriorityEvent
      ? PLATFORM_RUNTIME_MAP_EVENT_FRAME_INTERVAL_MS
      : PLATFORM_RUNTIME_MAP_IDLE_FRAME_INTERVAL_MS;
  }

  motionSuppressed(scene) {
    return !motionSceneIsFresh(scene) || scene.motionDisabled || scene.runtimeError;
  }

  isDocumentHidden() {
    return this.documentTarget?.hidden === true || this.documentTarget?.visibilityState === 'hidden';
  }

  rememberCurrentDispatchIdentities(scene) {
    for (const lane of scene.lanes) {
      for (const item of lane.runningItems) {
        if (!item.identity || this.seenDispatchIdentities.has(item.identity)) continue;
        this.seenDispatchIdentities.add(item.identity);
        this.seenDispatchOrder.push(item.identity);
      }
    }
    while (this.seenDispatchOrder.length > MAX_DISPATCH_IDENTITIES) {
      const identity = this.seenDispatchOrder.shift();
      this.seenDispatchIdentities.delete(identity);
    }
  }

  publishDiagnostics(timestamp = this.now()) {
    const snapshot = this.runtime?.getSnapshot?.() || {};
    const effects = activeEffects(this.effects, timestamp);
    const reviewIdentities = new Set(effects
      .filter(item => item.type === 'dispatch' || item.type === 'stage')
      .map(item => item.identity));
    const workerIdentities = new Set(effects
      .filter(item => item.type === 'worker')
      .map(item => item.identity));
    const diagnostics = {
      ...snapshot,
      motionState: motionState(this.scene),
      performanceDegradationLevel: this.performanceLevel,
      animatedReviewCount: reviewIdentities.size,
      animatedWorkerCount: workerIdentities.size,
      environmentParticleCount: this.lastParticleCount,
      dispatchCursorCount: effects.filter(item => item.type === 'dispatch').length,
      stageFeedbackCount: effects.filter(item => item.type === 'stage').length,
      workerFeedbackCount: effects.filter(item => item.type === 'worker').length,
      beaconEventCount: 0
    };
    if (this.canvas) this.canvas[PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY] = diagnostics;
    for (const [name, value] of Object.entries({
      'data-command-center-average-draw-ms': snapshot.averageDrawMs || 0,
      'data-command-center-max-draw-ms': snapshot.maxDrawMs || 0,
      'data-command-center-over-budget-frames': snapshot.overBudgetFrameCount || 0,
      'data-command-center-frame-count': snapshot.frameCount || 0,
      'data-command-center-scene-updates': this.sceneUpdateCount,
      'data-command-center-active-raf': snapshot.activeRafCount || 0,
      'data-command-center-max-concurrent-raf': snapshot.maxConcurrentRafCount || 0,
      'data-command-center-motion-state': diagnostics.motionState,
      'data-command-center-motion-degradation': this.performanceLevel,
      'data-command-center-animated-reviews': diagnostics.animatedReviewCount,
      'data-command-center-animated-workers': diagnostics.animatedWorkerCount,
      'data-command-center-environment-particles': this.lastParticleCount,
      'data-command-center-dispatch-cursors': diagnostics.dispatchCursorCount,
      'data-command-center-stage-feedbacks': diagnostics.stageFeedbackCount,
      'data-command-center-worker-feedbacks': diagnostics.workerFeedbackCount,
      'data-command-center-beacon-events': 0,
      'data-command-center-anchor-count': this.lastAnchorCount,
      'data-command-center-observer-registrations': snapshot.observerRegistrationCount || 0,
      'data-command-center-listener-registrations': snapshot.listenerRegistrationCount || 0
    })) this.canvas?.setAttribute?.(name, String(value));
  }

  getSnapshot() {
    return {
      ...(this.runtime?.getSnapshot?.() || {}),
      motionState: motionState(this.scene),
      performanceDegradationLevel: this.performanceLevel,
      effectCount: this.effects.length
    };
  }

  dispose() {
    this.runtime?.dispose();
    this.runtime = null;
    this.effects = [];
    this.seenDispatchIdentities.clear();
    this.seenDispatchOrder = [];
    this.canvas = null;
    this.container = null;
  }
}


function normalizeScene(value) {
  const raw = value && typeof value === 'object' ? value : {};
  return {
    snapshotKey: String(raw.snapshotKey || 'EMPTY'),
    freshness: String(raw.freshness || 'EMPTY').toUpperCase(),
    runtimeError: Boolean(raw.runtimeError),
    motionDisabled: Boolean(raw.motionDisabled),
    runningCount: count(raw.runningCount),
    queuedCount: count(raw.queuedCount),
    capacity: count(raw.capacity),
    utilizationPercent: percent(raw.utilizationPercent),
    lanes: ['standard', 'agent'].map(zoneKey => normalizeLane(
      (Array.isArray(raw.lanes) ? raw.lanes : []).find(lane => lane?.zoneKey === zoneKey),
      zoneKey
    )),
    connections: (Array.isArray(raw.connections) ? raw.connections : [])
      .slice(0, 20)
      .flatMap(connection => {
        const from = String(connection?.from || '');
        const to = String(connection?.to || '');
        if (!from || !to) return [];
        return [{
          from,
          to,
          token: CONNECTION_COLORS[connection?.token] ? connection.token : 'neutral'
        }];
      })
  };
}


function normalizeLane(value, zoneKey) {
  const raw = value && typeof value === 'object' ? value : {};
  return {
    zoneKey,
    capacity: count(raw.capacity),
    runningCount: count(raw.runningCount),
    queuedCount: count(raw.queuedCount),
    utilizationPercent: percent(raw.utilizationPercent),
    nextQueuedIdentity: nullableText(raw.nextQueuedIdentity),
    runningItems: (Array.isArray(raw.runningItems) ? raw.runningItems : [])
      .slice(0, 100)
      .flatMap(item => {
        const identity = nullableText(item?.identity);
        return identity ? [{ identity, stage: String(item?.stage || 'RUNNING').toUpperCase() }] : [];
      }),
    workers: (Array.isArray(raw.workers) ? raw.workers : [])
      .slice(0, 100)
      .flatMap(worker => {
        const identity = nullableText(worker?.identity);
        return identity ? [{ identity, state: String(worker?.state || 'IDLE').toUpperCase() }] : [];
      })
  };
}


function emptyLane(zoneKey) {
  return normalizeLane(null, zoneKey);
}


function effect(type, now, data = {}) {
  return {
    type,
    startAt: Math.max(0, Number(now) || 0),
    duration: EFFECT_DURATION_MS[type] || 500,
    ...data
  };
}


function activeEffects(effects, timestamp) {
  return effects.filter(item => timestamp < item.startAt + item.duration);
}


function latestEffect(effects, type, lane = null) {
  return [...effects].reverse().find(item => item.type === type && (!lane || item.lane === lane));
}


function effectProgress(item, timestamp) {
  return Math.min(1, Math.max(0, (timestamp - item.startAt) / item.duration));
}


function motionSceneIsFresh(scene) {
  return scene.freshness === 'FRESH' && !scene.runtimeError;
}


function sceneHasSnapshot(scene) {
  return scene.snapshotKey !== 'EMPTY' && scene.freshness !== 'EMPTY';
}


function motionState(scene) {
  if (scene.runtimeError) return 'RUNTIME_ERROR';
  if (scene.freshness === 'STALE') return 'STALE';
  if (scene.motionDisabled) return 'REDUCED_MOTION';
  if (scene.freshness !== 'FRESH') return 'CONNECTING';
  const saturated = scene.lanes.some(lane => lane.capacity > 0 && lane.utilizationPercent >= 100);
  if (saturated) return 'SATURATED';
  if (scene.runningCount === 0 && scene.queuedCount === 0) return 'FRESH_IDLE';
  if (scene.runningCount === 0) return 'FRESH_QUEUED';
  if (scene.utilizationPercent < 25) return 'FRESH_LOW_LOAD';
  return 'FRESH_RUNNING';
}


function drawDaylightTerrain(context, width, height, freshness) {
  context.fillStyle = PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.terrain;
  context.fillRect(0, 0, width, height);
  context.save();
  context.globalAlpha = freshness === 'STALE' ? 0.55 : 1;
  context.fillStyle = 'rgba(255, 255, 255, 0.22)';
  context.fillRect(width * 0.04, height * 0.08, width * 0.92, height * 0.84);
  context.strokeStyle = 'rgba(50, 85, 120, 0.025)';
  context.lineWidth = 1;
  const grid = 38;
  for (let x = -height; x < width + height; x += grid) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x + height, height);
    context.stroke();
  }
  for (let x = 0; x < width + height * 2; x += grid) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x - height, height);
    context.stroke();
  }
  context.fillStyle = 'rgba(255, 255, 255, 0.21)';
  context.beginPath();
  context.ellipse(width * 0.52, height * 0.5, width * 0.29, height * 0.39, 0, 0, Math.PI * 2);
  context.fill();
  drawStaticTerrainPads(context, width, height);
  context.restore();
}


function drawStaticConnections(context, anchors, freshness) {
  context.save();
  context.lineCap = 'round';
  context.lineJoin = 'round';
  context.globalAlpha = freshness === 'STALE' ? 0.42 : 0.9;
  for (const anchor of anchors) {
    const color = CONNECTION_COLORS[anchor.token] || CONNECTION_COLORS.neutral;
    context.save();
    context.globalAlpha *= anchor.to === 'result-beacon' ? 0.28 : 0.15;
    traceConnection(context, anchor);
    context.strokeStyle = color;
    context.lineWidth = anchor.to === 'result-beacon' ? 44 : 39;
    context.stroke();
    context.restore();
    traceConnection(context, anchor);
    context.strokeStyle = 'rgba(56, 83, 103, 0.28)';
    context.lineWidth = anchor.token === 'queue' ? 34 : 30;
    context.stroke();
    traceConnection(context, anchor);
    context.strokeStyle = 'rgba(255, 255, 255, 0.94)';
    context.lineWidth = anchor.token === 'queue' ? 26 : 23;
    context.stroke();
    traceConnection(context, anchor);
    context.strokeStyle = color;
    context.lineWidth = anchor.token === 'queue' ? 7 : anchor.to === 'result-beacon' ? 8 : 6;
    context.stroke();
    context.save();
    context.globalAlpha *= 0.42;
    context.setLineDash?.([3, 12]);
    traceConnection(context, anchor);
    context.strokeStyle = '#ffffff';
    context.lineWidth = 2;
    context.stroke();
    context.restore();
    drawEndpoint(context, anchor.toPoint, color);
  }
  context.restore();
}


function drawEnvironmentLife(context, width, height, timestamp, scene, performanceLevel) {
  if (motionState(scene) !== 'FRESH_IDLE' || performanceLevel > 0) return 0;
  const particleCount = width >= 1200 ? 16 : 8;
  context.save();
  for (let index = 0; index < particleCount; index += 1) {
    const column = index % 8;
    const upper = index % 2 === 0;
    const x = width * (0.08 + column * 0.12) + ((index * 17) % 23);
    const y = height * (upper ? 0.13 : 0.87) + ((index * 11) % 13) - 6;
    const alpha = 0.1 + 0.12 * (0.5 + 0.5 * Math.sin(timestamp / 1300 + index * 1.7));
    context.globalAlpha = alpha;
    context.fillStyle = index % 3 === 0
      ? PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.beacon
      : PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.neutral;
    context.beginPath();
    context.arc(x, y, 1.5 + index % 2, 0, Math.PI * 2);
    context.fill();
  }
  context.restore();
  return particleCount;
}


function drawCoreMotion(context, container, scene, effects, timestamp) {
  const rect = measureNamedRect(container, '[data-command-center-core-anchor="true"]');
  if (!rect) return;
  const center = rectCenter(rect);
  const radius = Math.max(44, Math.min(rect.width, rect.height) * 0.48);
  const state = motionState(scene);
  if (state === 'CONNECTING' || state === 'STALE' || state === 'REDUCED_MOTION') return;
  context.save();
  if (state === 'RUNTIME_ERROR') {
    context.globalAlpha = 0.62;
    context.strokeStyle = PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.neutral;
    context.lineWidth = 5;
    context.setLineDash?.([18, 10]);
    context.beginPath();
    context.arc(center.x, center.y, radius + 10, 0.2, Math.PI * 1.75);
    context.stroke();
    context.restore();
    return;
  }

  const period = corePeriod(state);
  const breathing = 0.5 + 0.5 * Math.sin(timestamp / period * Math.PI * 2);
  const amplitude = state === 'FRESH_IDLE' ? 0.04 : 0.1;
  context.globalAlpha = 0.12 + breathing * amplitude;
  context.fillStyle = '#5fc9d4';
  context.beginPath();
  context.arc(center.x, center.y, radius + 14 + breathing * 5, 0, Math.PI * 2);
  context.fill();

  const standardUtilization = animatedUtilization(scene, effects, 'standard', timestamp);
  const agentUtilization = animatedUtilization(scene, effects, 'agent', timestamp);
  drawCoreSector(context, center, radius + 8, -Math.PI * 0.95, -Math.PI * 0.05,
    PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.standardHighlight, standardUtilization, state === 'SATURATED');
  drawCoreSector(context, center, radius + 8, Math.PI * 0.05, Math.PI * 0.95,
    PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.agentHighlight, agentUtilization, state === 'SATURATED');
  context.restore();
}


function drawCoreSector(context, center, radius, start, end, color, utilization, saturated) {
  context.globalAlpha = 0.16 + utilization / 100 * 0.46;
  context.strokeStyle = color;
  context.lineWidth = saturated && utilization >= 100 ? 8 : 5;
  context.beginPath();
  context.arc(center.x, center.y, radius, start, end);
  context.stroke();
}


function drawGateMotion(context, container, scene, effects, timestamp) {
  if (!motionSceneIsFresh(scene) || scene.motionDisabled) return;
  const rect = measureNamedRect(container, '[data-command-center-gate-anchor="true"]');
  if (!rect) return;
  const center = rectCenter(rect);
  const request = latestEffect(effects, 'gate');
  const queuedWave = scene.runningCount === 0 && scene.queuedCount > 0;
  if (!request && !queuedWave) return;
  const progress = request
    ? effectProgress(request, timestamp)
    : (timestamp % 6000) / 6000;
  context.save();
  context.globalAlpha = request ? 0.5 * (1 - progress) : 0.14 * (1 - progress);
  context.strokeStyle = PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.queue;
  context.lineWidth = 3;
  context.beginPath();
  context.arc(center.x, center.y, 22 + progress * 26, 0, Math.PI * 2);
  context.stroke();
  context.restore();
}


function drawBeaconStandby(context, container, scene) {
  const rect = measureNamedRect(container, '[data-command-center-beacon-anchor="true"]');
  if (!rect) return;
  const center = rectCenter(rect);
  context.save();
  context.globalAlpha = motionSceneIsFresh(scene) ? 0.22 : 0.1;
  context.strokeStyle = PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.beacon;
  context.lineWidth = 3;
  context.beginPath();
  context.arc(center.x, center.y, Math.min(rect.width, rect.height) * 0.48 + 5, 0, Math.PI * 2);
  context.stroke();
  context.restore();
}


function drawEventFeedback(context, container, anchors, effects, timestamp) {
  for (const item of effects) {
    if (item.type === 'dispatch') drawDispatchCursor(context, container, anchors, item, timestamp);
    if (item.type === 'stage') drawTargetFeedback(context, container, 'review', item, timestamp,
      item.lane === 'agent' ? PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.agentHighlight : PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.standardHighlight);
    if (item.type === 'worker') drawTargetFeedback(context, container, 'worker', item, timestamp,
      PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.agentHighlight);
    if (item.type === 'candidate') drawCandidateFeedback(context, container, item, timestamp);
  }
}


function drawDispatchCursor(context, container, anchors, item, timestamp) {
  const anchor = anchors.find(value => value.from === 'ai-review-core' && value.to === item.lane);
  if (!anchor) return;
  const targetRect = measureDataIdentityRect(container, 'review', item.identity);
  const target = targetRect ? rectCenter(targetRect) : anchor.toPoint;
  const progress = easeOutCubic(effectProgress(item, timestamp));
  const point = dispatchPoint(anchor, target, progress);
  const color = item.lane === 'agent'
    ? PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.agentHighlight
    : PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.standardHighlight;
  context.save();
  context.globalAlpha = Math.min(1, (1 - progress) * 1.4 + 0.2);
  context.strokeStyle = color;
  context.lineWidth = 4;
  context.beginPath();
  context.arc(point.x, point.y, 8, 0, Math.PI * 2);
  context.stroke();
  context.fillStyle = '#ffffff';
  context.beginPath();
  context.arc(point.x, point.y, 3, 0, Math.PI * 2);
  context.fill();
  context.restore();
}


function drawTargetFeedback(context, container, kind, item, timestamp, color) {
  const rect = measureDataIdentityRect(container, kind, item.identity);
  if (!rect) return;
  const center = rectCenter(rect);
  const progress = effectProgress(item, timestamp);
  context.save();
  context.globalAlpha = 0.68 * (1 - progress);
  context.strokeStyle = color;
  context.lineWidth = 3;
  context.beginPath();
  context.arc(center.x, center.y, Math.max(rect.width, rect.height) * 0.35 + progress * 16, 0, Math.PI * 2);
  context.stroke();
  context.restore();
}


function drawCandidateFeedback(context, container, item, timestamp) {
  const rect = measureNamedRect(container, `[data-command-center-next-review="${item.lane}"]`);
  if (!rect) return;
  const progress = effectProgress(item, timestamp);
  context.save();
  context.globalAlpha = 0.22 * Math.sin(progress * Math.PI);
  context.fillStyle = item.lane === 'agent'
    ? PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.agentHighlight
    : PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.standardHighlight;
  context.fillRect(rect.left - 4, rect.top - 4, rect.width + 8, rect.height + 8);
  context.restore();
}


function animatedUtilization(scene, effects, laneKey, timestamp) {
  const lane = scene.lanes.find(item => item.zoneKey === laneKey) || emptyLane(laneKey);
  const change = latestEffect(effects, 'utilization', laneKey);
  if (!change) return lane.utilizationPercent;
  const progress = easeOutCubic(effectProgress(change, timestamp));
  return change.from + (change.to - change.from) * progress;
}


function corePeriod(state) {
  if (state === 'FRESH_IDLE') return 6000;
  if (state === 'FRESH_LOW_LOAD') return 5400;
  if (state === 'SATURATED') return 4600;
  return 4200;
}


function dispatchPoint(anchor, target, progress) {
  if (progress <= 0.72) {
    return cubicPoint(anchor, progress / 0.72);
  }
  const localProgress = (progress - 0.72) / 0.28;
  return {
    x: anchor.toPoint.x + (target.x - anchor.toPoint.x) * localProgress,
    y: anchor.toPoint.y + (target.y - anchor.toPoint.y) * localProgress
  };
}


function cubicPoint(anchor, progress) {
  const distance = Math.abs(anchor.toPoint.x - anchor.fromPoint.x);
  const bend = Math.max(24, distance * 0.42);
  const inverse = 1 - progress;
  const p0 = anchor.fromPoint;
  const p1 = { x: p0.x + bend, y: p0.y };
  const p3 = anchor.toPoint;
  const p2 = { x: p3.x - bend, y: p3.y };
  return {
    x: inverse ** 3 * p0.x + 3 * inverse ** 2 * progress * p1.x
      + 3 * inverse * progress ** 2 * p2.x + progress ** 3 * p3.x,
    y: inverse ** 3 * p0.y + 3 * inverse ** 2 * progress * p1.y
      + 3 * inverse * progress ** 2 * p2.y + progress ** 3 * p3.y
  };
}


function drawEndpoint(context, point, color) {
  context.save();
  context.globalAlpha = 0.96;
  context.fillStyle = 'rgba(255, 255, 255, 0.95)';
  context.strokeStyle = color;
  context.lineWidth = 4;
  context.beginPath();
  context.arc(point.x, point.y, 9, 0, Math.PI * 2);
  context.fill();
  context.stroke();
  context.fillStyle = color;
  context.beginPath();
  context.arc(point.x, point.y, 3, 0, Math.PI * 2);
  context.fill();
  context.restore();
}


function drawStaticTerrainPads(context, width, height) {
  context.save();
  const pads = [
    [width * 0.1, height * 0.54, width * 0.085, height * 0.25],
    [width * 0.33, height * 0.55, width * 0.105, height * 0.3],
    [width * 0.64, height * 0.27, width * 0.19, height * 0.13],
    [width * 0.64, height * 0.73, width * 0.19, height * 0.13],
    [width * 0.92, height * 0.54, width * 0.065, height * 0.2]
  ];
  for (const [centerX, centerY, radiusX, radiusY] of pads) {
    context.fillStyle = 'rgba(72, 94, 108, 0.075)';
    context.beginPath();
    context.ellipse(centerX, centerY + 9, radiusX, radiusY, 0, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = 'rgba(218, 232, 239, 0.3)';
    context.beginPath();
    context.ellipse(centerX, centerY, radiusX, radiusY, 0, 0, Math.PI * 2);
    context.fill();
    context.strokeStyle = 'rgba(255, 255, 255, 0.34)';
    context.lineWidth = 2;
    context.beginPath();
    context.ellipse(centerX, centerY - 2, radiusX * 0.88, radiusY * 0.82, 0, Math.PI * 1.08, Math.PI * 1.92);
    context.stroke();
  }
  context.restore();
}


function traceConnection(context, anchor) {
  const distance = Math.abs(anchor.toPoint.x - anchor.fromPoint.x);
  const bend = Math.max(24, distance * 0.42);
  context.beginPath();
  context.moveTo(anchor.fromPoint.x, anchor.fromPoint.y);
  context.bezierCurveTo(
    anchor.fromPoint.x + bend,
    anchor.fromPoint.y,
    anchor.toPoint.x - bend,
    anchor.toPoint.y,
    anchor.toPoint.x,
    anchor.toPoint.y
  );
}


function measureNamedRect(container, selector) {
  const containerRect = container?.getBoundingClientRect?.();
  const rect = container?.querySelector?.(selector)?.getBoundingClientRect?.();
  return validRect(containerRect) && validRect(rect) ? relativeRect(rect, containerRect) : null;
}


function measureDataIdentityRect(container, kind, identity) {
  const selector = kind === 'worker'
    ? '[data-command-center-worker-tower="true"]'
    : '[data-command-center-review-marker="true"]';
  const attribute = kind === 'worker' ? 'data-worker-identity' : 'data-review-identity';
  const nodes = Array.from(container?.querySelectorAll?.(selector) || []);
  const target = nodes.find(node => node?.getAttribute?.(attribute) === identity);
  const containerRect = container?.getBoundingClientRect?.();
  const rect = target?.getBoundingClientRect?.();
  return validRect(containerRect) && validRect(rect) ? relativeRect(rect, containerRect) : null;
}


function relativeRect(rect, containerRect) {
  return {
    left: rect.left - containerRect.left,
    right: rect.right - containerRect.left,
    top: rect.top - containerRect.top,
    bottom: rect.bottom - containerRect.top,
    width: rect.width,
    height: rect.height
  };
}


function rectCenter(rect) {
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}


function connectionPoint(rect, otherRect) {
  const center = rectCenter(rect);
  const otherCenter = rectCenter(otherRect);
  if (Math.abs(otherCenter.x - center.x) >= Math.abs(otherCenter.y - center.y)) {
    return { x: otherCenter.x >= center.x ? rect.right : rect.left, y: center.y };
  }
  return { x: center.x, y: otherCenter.y >= center.y ? rect.bottom : rect.top };
}


function validRect(rect) {
  return Number.isFinite(rect?.left)
    && Number.isFinite(rect?.top)
    && Number.isFinite(rect?.width)
    && Number.isFinite(rect?.height)
    && rect.width > 0
    && rect.height > 0;
}


function count(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.floor(number) : 0;
}


function percent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(100, Math.max(0, number)) : 0;
}


function nullableText(value) {
  const text = String(value ?? '').trim();
  return text || null;
}


function easeOutCubic(value) {
  return 1 - (1 - value) ** 3;
}


function safelyNotifyFailure(callback) {
  try {
    callback?.();
  } catch {
    // Canvas failure must remain inside the DOM fallback boundary.
  }
}
