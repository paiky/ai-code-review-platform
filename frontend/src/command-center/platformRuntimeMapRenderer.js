import { createCanvasRuntime } from '../canvas/canvasRuntime.js';


export const PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY = '__platformRuntimeMapDiagnostics';
export const PLATFORM_RUNTIME_MAP_DRAW_BUDGET_MS = 8;


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
  }

  initialize() {
    this.runtime = createCanvasRuntime({
      canvas: this.canvas,
      container: this.container,
      environment: this.environment,
      drawBudgetMs: PLATFORM_RUNTIME_MAP_DRAW_BUDGET_MS,
      maxDpr: 2,
      isAnimationEnabled: () => false,
      onDraw: frame => this.draw(frame),
      onStateChange: () => this.publishDiagnostics(),
      onFailure: () => safelyNotifyFailure(this.onFailure)
    });
    this.publishDiagnostics();
    return Boolean(this.runtime);
  }

  setScene(scene) {
    this.scene = normalizeScene(scene);
    this.runtime?.refresh();
    this.publishDiagnostics();
  }

  draw({ context, width, height, dpr }) {
    context.setTransform?.(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);
    drawDaylightTerrain(context, width, height);
    drawRoutes(context, width, height, this.scene);
    this.publishDiagnostics();
  }

  publishDiagnostics() {
    const snapshot = this.runtime?.getSnapshot?.() || {};
    if (this.canvas) this.canvas[PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY] = snapshot;
    for (const [name, value] of Object.entries({
      'data-command-center-average-draw-ms': snapshot.averageDrawMs || 0,
      'data-command-center-max-draw-ms': snapshot.maxDrawMs || 0,
      'data-command-center-over-budget-frames': snapshot.overBudgetFrameCount || 0,
      'data-command-center-active-raf': snapshot.activeRafCount || 0,
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
    lanes: Array.isArray(raw.lanes) ? raw.lanes.slice(0, 2).map(lane => ({
      zoneKey: lane?.zoneKey === 'agent' ? 'agent' : 'standard',
      utilizationPercent: clamp(Number(lane?.utilizationPercent) || 0, 0, 100),
      queuedCount: Math.max(0, Number(lane?.queuedCount) || 0)
    })) : []
  };
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
  const queue = { x: width * 0.27, y: height * 0.5 };
  const junction = { x: width * 0.43, y: height * 0.5 };
  const routes = [
    { target: { x: width * 0.67, y: height * 0.27 }, color: '#0796a5', lane: 'standard' },
    { target: { x: width * 0.67, y: height * 0.73 }, color: '#7556d9', lane: 'agent' }
  ];
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
