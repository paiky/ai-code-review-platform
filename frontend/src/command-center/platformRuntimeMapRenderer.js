import { createCanvasRuntime } from '../canvas/canvasRuntime.js';


export const PLATFORM_RUNTIME_MAP_DIAGNOSTICS_KEY = '__platformRuntimeMapDiagnostics';
export const PLATFORM_RUNTIME_MAP_DRAW_BUDGET_MS = 8;

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


class PlatformRuntimeMapController {
  constructor(options) {
    this.canvas = options.canvas;
    this.container = options.container;
    this.scene = normalizeScene(options.scene);
    this.onFailure = options.onFailure;
    this.environment = options.environment;
    this.runtime = null;
    this.sceneUpdateCount = 1;
    this.lastAnchorCount = 0;
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
    this.sceneUpdateCount += 1;
    this.runtime?.refresh();
    this.publishDiagnostics();
  }

  draw({ context, width, height, dpr }) {
    context.setTransform?.(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);
    drawDaylightTerrain(context, width, height, this.scene.freshness);
    const anchors = measureOperationMapAnchors(this.container, this.scene.connections);
    this.lastAnchorCount = anchors.length;
    drawStaticConnections(context, anchors, this.scene.freshness);
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
      'data-command-center-animated-reviews': 0,
      'data-command-center-animated-workers': 0,
      'data-command-center-environment-particles': 0,
      'data-command-center-anchor-count': this.lastAnchorCount,
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
    freshness: String(raw.freshness || 'EMPTY').toUpperCase(),
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


function drawDaylightTerrain(context, width, height, freshness) {
  context.fillStyle = PLATFORM_RUNTIME_MAP_VISUAL_TOKENS.terrain;
  context.fillRect(0, 0, width, height);
  context.save();
  context.globalAlpha = freshness === 'STALE' ? 0.55 : 1;
  context.fillStyle = 'rgba(255, 255, 255, 0.34)';
  context.fillRect(width * 0.04, height * 0.08, width * 0.92, height * 0.84);
  context.strokeStyle = 'rgba(50, 85, 120, 0.07)';
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
  context.strokeStyle = 'rgba(53, 100, 127, 0.1)';
  context.lineWidth = 2;
  context.strokeRect(width * 0.045, height * 0.085, width * 0.91, height * 0.83);
  context.fillStyle = 'rgba(255, 255, 255, 0.3)';
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
    context.lineWidth = anchor.token === 'queue' ? 7 : 6;
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
  context.fillStyle = 'rgba(205, 222, 232, 0.32)';
  context.strokeStyle = 'rgba(61, 99, 122, 0.09)';
  context.lineWidth = 2;
  const pads = [
    [width * 0.02, height * 0.18, width * 0.17, height * 0.64],
    [width * 0.22, height * 0.11, width * 0.22, height * 0.78],
    [width * 0.47, height * 0.07, width * 0.36, height * 0.4],
    [width * 0.47, height * 0.53, width * 0.36, height * 0.4],
    [width * 0.86, height * 0.2, width * 0.12, height * 0.6]
  ];
  for (const [x, y, padWidth, padHeight] of pads) {
    context.fillRect(x, y, padWidth, padHeight);
    context.strokeRect(x, y, padWidth, padHeight);
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


function connectionPoint(rect, otherRect) {
  const center = {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2
  };
  const otherCenter = {
    x: otherRect.left + otherRect.width / 2,
    y: otherRect.top + otherRect.height / 2
  };
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


function safelyNotifyFailure(callback) {
  try {
    callback?.();
  } catch {
    // Canvas failure must remain inside the DOM fallback boundary.
  }
}
