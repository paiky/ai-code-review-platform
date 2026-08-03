import { createCanvasRuntime } from '../canvas/canvasRuntime.js';


export const PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY = '__platformRuntimeMapDiagnostics';
export const PLATFORM_RUNTIME_MAP_DRAW_BUDGET_MS = 8;
export const PLATFORM_RUNTIME_MAP_FRAME_INTERVAL_MS = 1000 / 30;


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
  reducedMotion = false,
  smallScreen = false,
  canvasFailed = false,
  canvasReady = false
} = {}) {
  if (smallScreen) return 'SMALL_SCREEN';
  if (reducedMotion) return 'REDUCED_MOTION';
  if (canvasFailed) return 'CANVAS_FAILED';
  if (!canvasReady) return 'CANVAS_LOADING';
  return null;
}


class PlatformRuntimeMapController {
  constructor(options) {
    this.canvas = options.canvas;
    this.container = options.container;
    this.scene = normalizeScene(options.scene);
    this.onFailure = options.onFailure;
    this.environment = options.environment;
    this.runtime = null;
    this.sceneUpdateCount = 1;
  }

  initialize() {
    this.runtime = createCanvasRuntime({
      canvas: this.canvas,
      container: this.container,
      environment: this.environment,
      drawBudgetMs: PLATFORM_RUNTIME_MAP_DRAW_BUDGET_MS,
      maxDpr: 2,
      isAnimationEnabled: () => hasAnimatedActivity(this.scene),
      getAnimationFrameInterval: () => PLATFORM_RUNTIME_MAP_FRAME_INTERVAL_MS,
      onDraw: frame => this.draw(frame),
      onStateChange: () => this.publishDiagnostics(),
      onFailure: () => safelyNotifyFailure(this.onFailure)
    });
    this.publishDiagnostics();
    return Boolean(this.runtime);
  }

  setScene(scene) {
    this.scene = normalizeScene(scene);
    this.sceneUpdateCount += 1;
    this.runtime?.refresh();
    this.publishDiagnostics();
  }

  draw({ context, width, height, dpr, timestamp }) {
    context.setTransform?.(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);
    drawDaylightTerrain(context, width, height);
    drawRoutes(context, width, height, this.scene);
    drawRuntimeActivity(context, width, height, this.scene, timestamp);
    this.publishDiagnostics();
  }

  publishDiagnostics() {
    const snapshot = this.runtime?.getSnapshot?.() || {};
    if (this.canvas) this.canvas[PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY] = snapshot;
    for (const [name, value] of Object.entries({
      'data-command-center-average-draw-ms': snapshot.averageDrawMs || 0,
      'data-command-center-max-draw-ms': snapshot.maxDrawMs || 0,
      'data-command-center-over-budget-frames': snapshot.overBudgetFrameCount || 0,
      'data-command-center-frame-count': snapshot.frameCount || 0,
      'data-command-center-scene-updates': this.sceneUpdateCount,
      'data-command-center-active-raf': snapshot.activeRafCount || 0,
      'data-command-center-animated-reviews': animatedReviewCount(this.scene),
      'data-command-center-online-workers': this.scene.workers.filter(worker => worker.online).length,
      'data-command-center-observer-registrations': snapshot.observerRegistrationCount || 0,
      'data-command-center-listener-registrations': snapshot.listenerRegistrationCount || 0
    })) this.canvas?.setAttribute?.(name, String(value));
  }

  getSnapshot() {
    return this.runtime?.getSnapshot?.() || {};
  }

  dispose() {
    this.runtime?.dispose();
    this.runtime = null;
    this.canvas = null;
    this.container = null;
  }
}


function normalizeScene(value) {
  const raw = value && typeof value === 'object' ? value : {};
  return {
    snapshotKey: String(raw.snapshotKey || 'EMPTY'),
    freshness: String(raw.freshness || 'EMPTY'),
    workers: normalizeWorkers(raw.workers),
    lanes: Array.isArray(raw.lanes) ? raw.lanes.slice(0, 2).map(lane => ({
      zoneKey: lane?.zoneKey === 'agent' ? 'agent' : 'standard',
      utilizationPercent: clamp(Number(lane?.utilizationPercent) || 0, 0, 100),
      queuedCount: Math.max(0, Number(lane?.queuedCount) || 0),
      runningItems: normalizeRunningItems(lane?.runningItems)
    })) : []
  };
}


function normalizeRunningItems(value) {
  return (Array.isArray(value) ? value : []).slice(0, 100).map(item => ({
    jobId: finiteNumber(item?.jobId),
    taskId: finiteNumber(item?.taskId),
    reviewKey: String(item?.reviewKey || ''),
    workerId: item?.workerId == null ? null : String(item.workerId),
    fallback: Boolean(item?.fallback),
    stage: String(item?.stage || 'RUNNING')
  }));
}


function normalizeWorkers(value) {
  return (Array.isArray(value) ? value : []).slice(0, 100).map(worker => ({
    workerId: String(worker?.workerId || ''),
    state: String(worker?.state || 'OFFLINE').toUpperCase(),
    online: Boolean(worker?.online),
    capacity: Math.max(0, Number(worker?.capacity) || 0),
    activeJobId: finiteNumber(worker?.activeJobId)
  }));
}


function drawDaylightTerrain(context, width, height) {
  context.fillStyle = '#eaf2f7';
  context.fillRect(0, 0, width, height);
  context.save();
  context.strokeStyle = 'rgba(50, 85, 120, 0.09)';
  context.lineWidth = 1;
  const grid = 34;
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
  context.fillStyle = 'rgba(255, 255, 255, 0.44)';
  context.beginPath();
  context.ellipse(width * 0.2, height * 0.5, width * 0.17, height * 0.3, 0, 0, Math.PI * 2);
  context.fill();
  context.restore();
}


function drawRoutes(context, width, height, scene) {
  const { queue, junction, routes } = routeGeometry(width, height);
  context.save();
  context.lineCap = 'round';
  context.lineJoin = 'round';
  context.beginPath();
  context.moveTo(queue.x, queue.y);
  context.lineTo(junction.x, junction.y);
  context.strokeStyle = '#d99a16';
  context.lineWidth = 13;
  context.globalAlpha = scene.freshness === 'STALE' ? 0.42 : 0.72;
  context.stroke();
  for (const route of routes) {
    const lane = scene.lanes.find(item => item.zoneKey === route.lane);
    context.beginPath();
    context.moveTo(junction.x, junction.y);
    context.bezierCurveTo(
      width * 0.5,
      junction.y,
      width * 0.55,
      route.target.y,
      route.target.x,
      route.target.y
    );
    context.strokeStyle = route.color;
    context.globalAlpha = lane?.queuedCount > 0 ? 0.68 : 0.38;
    context.lineWidth = 11;
    context.stroke();
    context.globalAlpha = 0.95;
    context.fillStyle = route.color;
    context.beginPath();
    context.arc(route.target.x, route.target.y, 5 + (lane?.utilizationPercent || 0) / 24, 0, Math.PI * 2);
    context.fill();
  }
  context.restore();
}


function drawRuntimeActivity(context, width, height, scene, timestamp = 0) {
  if (scene.freshness !== 'FRESH') return;
  const time = Math.max(0, Number(timestamp) || 0) / 1000;
  const geometry = routeGeometry(width, height);
  drawQueuePulse(context, geometry.queue, scene, time);
  for (const route of geometry.routes) {
    const lane = scene.lanes.find(item => item.zoneKey === route.lane);
    if (!lane) continue;
    drawLaneEnergy(context, geometry.junction, route, lane, time);
    drawReviewTokens(context, geometry.junction, route, lane, time);
  }
  drawWorkerTowers(context, width, height, scene.workers, time);
}


function drawQueuePulse(context, queue, scene, time) {
  const queuedCount = scene.lanes.reduce((total, lane) => total + lane.queuedCount, 0);
  if (queuedCount <= 0) return;
  context.save();
  context.strokeStyle = '#b87500';
  context.lineWidth = 2;
  for (let index = 0; index < 3; index += 1) {
    const progress = (time * 0.48 + index / 3) % 1;
    context.globalAlpha = (1 - progress) * 0.42;
    context.beginPath();
    context.arc(queue.x, queue.y, 10 + progress * 29, 0, Math.PI * 2);
    context.stroke();
  }
  context.restore();
}


function drawLaneEnergy(context, junction, route, lane, time) {
  if (lane.runningItems.length === 0) return;
  context.save();
  context.fillStyle = route.color;
  for (let index = 0; index < 4; index += 1) {
    const progress = (time * 0.22 + index / 4) % 1;
    const point = routePoint(junction, route.target, progress);
    context.globalAlpha = 0.22 + progress * 0.42;
    context.beginPath();
    context.arc(point.x, point.y, 2.2 + progress * 1.8, 0, Math.PI * 2);
    context.fill();
  }
  context.restore();
}


function drawReviewTokens(context, junction, route, lane, time) {
  lane.runningItems.forEach((item, index) => {
    const offset = stableFraction(`${item.jobId}:${item.taskId}:${item.reviewKey}`);
    const progress = (offset + time * (0.025 + (index % 3) * 0.004)) % 1;
    const point = routePoint(junction, route.target, 0.18 + progress * 0.78);
    const color = item.fallback ? '#b87500' : route.color;
    context.save();
    context.translate(point.x, point.y);
    context.rotate(Math.PI / 4);
    context.fillStyle = '#ffffff';
    context.strokeStyle = color;
    context.lineWidth = 2;
    context.globalAlpha = 0.96;
    context.fillRect(-5, -5, 10, 10);
    context.strokeRect(-5, -5, 10, 10);
    context.restore();
  });
}


function drawWorkerTowers(context, width, height, workers, time) {
  workers.slice(0, 8).forEach((worker, index) => {
    const column = index % 4;
    const row = Math.floor(index / 4);
    const x = width * 0.84 + column * Math.min(36, width * 0.026);
    const y = height * 0.69 + row * 34;
    const color = !worker.online ? '#91a4b3'
      : worker.state === 'BUSY' ? '#7056d8'
        : worker.state === 'DRAINING' ? '#b87500' : '#0f8fa3';
    context.save();
    context.fillStyle = '#ffffff';
    context.strokeStyle = color;
    context.lineWidth = 2;
    context.globalAlpha = worker.online ? 0.9 : 0.5;
    context.fillRect(x - 7, y - 10, 14, 20);
    context.strokeRect(x - 7, y - 10, 14, 20);
    context.beginPath();
    context.moveTo(x - 10, y - 10);
    context.lineTo(x, y - 18);
    context.lineTo(x + 10, y - 10);
    context.stroke();
    if (worker.online) {
      const heartbeat = (time * 0.9 + stableFraction(worker.workerId)) % 1;
      context.globalAlpha = (1 - heartbeat) * 0.45;
      context.beginPath();
      context.arc(x, y - 15, 5 + heartbeat * 12, 0, Math.PI * 2);
      context.stroke();
    }
    context.restore();
  });
}


function routeGeometry(width, height) {
  return {
    queue: { x: width * 0.27, y: height * 0.5 },
    junction: { x: width * 0.43, y: height * 0.5 },
    routes: [
      { target: { x: width * 0.67, y: height * 0.27 }, color: '#0796a5', lane: 'standard' },
      { target: { x: width * 0.67, y: height * 0.73 }, color: '#7556d9', lane: 'agent' }
    ]
  };
}


function routePoint(start, target, progress) {
  const control1 = { x: start.x + (target.x - start.x) * 0.3, y: start.y };
  const control2 = { x: start.x + (target.x - start.x) * 0.52, y: target.y };
  const inverse = 1 - progress;
  return {
    x: inverse ** 3 * start.x
      + 3 * inverse ** 2 * progress * control1.x
      + 3 * inverse * progress ** 2 * control2.x
      + progress ** 3 * target.x,
    y: inverse ** 3 * start.y
      + 3 * inverse ** 2 * progress * control1.y
      + 3 * inverse * progress ** 2 * control2.y
      + progress ** 3 * target.y
  };
}


function hasAnimatedActivity(scene) {
  return scene.freshness === 'FRESH' && (
    scene.lanes.some(lane => lane.queuedCount > 0 || lane.runningItems.length > 0)
    || scene.workers.some(worker => worker.online)
  );
}


function animatedReviewCount(scene) {
  if (scene.freshness !== 'FRESH') return 0;
  return scene.lanes.reduce((total, lane) => total + lane.runningItems.length, 0);
}


function stableFraction(value) {
  let hash = 2166136261;
  for (const character of String(value)) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}


function finiteNumber(value) {
  if (value == null || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}


function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}


function safelyNotifyFailure(callback) {
  try {
    callback?.();
  } catch {
    // Canvas failure must remain inside the DOM fallback boundary.
  }
}
