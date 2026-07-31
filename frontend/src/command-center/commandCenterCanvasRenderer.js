import { createCanvasRuntime } from '../canvas/canvasRuntime.js';


export const COMMAND_CENTER_CANVAS_MAX_DPR = 2;

const EMPTY_SCENE = Object.freeze({
  id: 'review-lifecycle',
  allowAnimation: false,
  nodes: Object.freeze([]),
  edges: Object.freeze([])
});


export function createCommandCenterCanvasController(options = {}) {
  let controller = null;
  try {
    controller = new CommandCenterCanvasController(options);
    if (!controller.initialize()) {
      controller.dispose();
      return null;
    }
    return controller;
  } catch {
    controller?.dispose();
    safelyNotifyFailure(options.onFailure);
    return null;
  }
}


export function normalizeCommandCenterScene(input) {
  if (!input || typeof input !== 'object') return EMPTY_SCENE;
  const nodes = (Array.isArray(input.nodes) ? input.nodes : [])
    .map(node => normalizeSceneNode(node))
    .filter(Boolean);
  const nodeIds = new Set(nodes.map(node => node.id));
  const edges = (Array.isArray(input.edges) ? input.edges : [])
    .map(edge => normalizeSceneEdge(edge, nodeIds))
    .filter(Boolean);
  return Object.freeze({
    id: safeIdentifier(input.id, 'review-lifecycle'),
    allowAnimation: false,
    nodes: Object.freeze(nodes),
    edges: Object.freeze(edges)
  });
}


export function resolveCommandCenterCanvasFallback({
  reducedMotion = false,
  smallScreen = false,
  canvasFailed = false,
  canvasReady = false
} = {}) {
  if (reducedMotion) return 'REDUCED_MOTION';
  if (smallScreen) return 'SMALL_SCREEN';
  if (canvasFailed) return 'CANVAS_FAILURE';
  if (!canvasReady) return 'INITIALIZING';
  return null;
}


export function drawCommandCenterCanvasFrame({
  context,
  width,
  height,
  dpr,
  scene
}) {
  const canvasWidth = Math.max(0, finiteNumber(width, 0));
  const canvasHeight = Math.max(0, finiteNumber(height, 0));
  if (!context || canvasWidth <= 0 || canvasHeight <= 0) return;

  const normalizedScene = normalizeCommandCenterScene(scene);
  const nodesById = new Map(normalizedScene.nodes.map(node => [node.id, node]));
  const geometry = resolveSceneGeometry(canvasWidth, canvasHeight);

  context.save();
  context.setTransform(
    Math.max(1, finiteNumber(dpr, 1)),
    0,
    0,
    Math.max(1, finiteNumber(dpr, 1)),
    0,
    0
  );
  context.clearRect(0, 0, canvasWidth, canvasHeight);
  drawSceneGrid(context, canvasWidth, canvasHeight);
  for (const edge of normalizedScene.edges) {
    drawSceneEdge(context, edge, nodesById, geometry);
  }
  for (const node of normalizedScene.nodes) {
    drawSceneNode(context, node, geometry);
  }
  context.restore();
}


class CommandCenterCanvasController {
  constructor(options) {
    this.canvas = options.canvas;
    this.container = options.container;
    this.environment = options.environment;
    this.onFailure = options.onFailure;
    this.scene = normalizeCommandCenterScene(options.scene);
    this.runtime = null;
    this.lastRuntimeSnapshot = null;
    this.failed = false;
    this.disposed = false;
    this.handleRuntimeFailure = this.handleRuntimeFailure.bind(this);
  }

  initialize() {
    this.runtime = createCanvasRuntime({
      canvas: this.canvas,
      container: this.container,
      environment: this.environment,
      maxDpr: COMMAND_CENTER_CANVAS_MAX_DPR,
      onDraw: ({ context, width, height, dpr }) => {
        drawCommandCenterCanvasFrame({
          context,
          width,
          height,
          dpr,
          scene: this.scene
        });
      },
      isAnimationEnabled: () => false,
      onFailure: this.handleRuntimeFailure
    });
    return Boolean(this.runtime);
  }

  setScene(scene) {
    if (this.disposed || this.failed) return;
    this.scene = normalizeCommandCenterScene(scene);
    this.runtime?.refresh();
  }

  handleRuntimeFailure() {
    if (this.failed || this.disposed) return;
    this.failed = true;
    safelyNotifyFailure(this.onFailure);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    const runtime = this.runtime;
    runtime?.dispose();
    this.lastRuntimeSnapshot = runtime?.getSnapshot() || this.lastRuntimeSnapshot;
    this.runtime = null;
    this.canvas = null;
    this.container = null;
  }

  getSnapshot() {
    const runtimeSnapshot = this.runtime?.getSnapshot() || this.lastRuntimeSnapshot || {};
    return {
      ...runtimeSnapshot,
      failed: this.failed || Boolean(runtimeSnapshot.failed),
      disposed: this.disposed || Boolean(runtimeSnapshot.disposed),
      allowAnimation: false,
      nodeCount: this.scene.nodes.length,
      edgeCount: this.scene.edges.length
    };
  }
}


function normalizeSceneNode(node) {
  if (!node || typeof node !== 'object') return null;
  const id = safeIdentifier(node.id, '');
  if (!id) return null;
  return Object.freeze({
    id,
    columnKey: safeIdentifier(node.columnKey, 'unknown'),
    x: clamp(finiteNumber(node.x, 0.5), 0, 1),
    y: clamp(finiteNumber(node.y, 0.5), 0, 1),
    flowCount: Math.max(0, Math.trunc(finiteNumber(node.flowCount, 0)))
  });
}


function normalizeSceneEdge(edge, nodeIds) {
  if (!edge || typeof edge !== 'object') return null;
  const from = safeIdentifier(edge.from, '');
  const to = safeIdentifier(edge.to, '');
  if (!from || !to || !nodeIds.has(from) || !nodeIds.has(to)) return null;
  return Object.freeze({
    id: safeIdentifier(edge.id, `${from}->${to}`),
    from,
    to
  });
}


function resolveSceneGeometry(width, height) {
  const horizontalInset = Math.max(18, Math.min(46, width * 0.035));
  const verticalInset = Math.max(12, Math.min(28, height * 0.12));
  const usableWidth = Math.max(1, width - horizontalInset * 2);
  const usableHeight = Math.max(1, height - verticalInset * 2);
  return {
    horizontalInset,
    verticalInset,
    usableWidth,
    usableHeight,
    nodeWidth: Math.max(76, Math.min(150, usableWidth / 5.7)),
    nodeHeight: Math.max(88, Math.min(158, usableHeight * 0.78))
  };
}


function nodePoint(node, geometry) {
  return {
    x: geometry.horizontalInset + geometry.usableWidth * node.x,
    y: geometry.verticalInset + geometry.usableHeight * node.y
  };
}


function drawSceneGrid(context, width, height) {
  context.save();
  context.strokeStyle = 'rgba(98, 217, 255, 0.045)';
  context.lineWidth = 1;
  for (let x = 0.5; x < width; x += 32) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
  context.restore();
}


function drawSceneEdge(context, edge, nodesById, geometry) {
  const from = nodesById.get(edge.from);
  const to = nodesById.get(edge.to);
  if (!from || !to) return;
  const start = nodePoint(from, geometry);
  const end = nodePoint(to, geometry);
  const startX = start.x + geometry.nodeWidth / 2;
  const endX = end.x - geometry.nodeWidth / 2;
  const controlOffset = Math.max(10, (endX - startX) * 0.42);

  context.save();
  context.beginPath();
  context.moveTo(startX, start.y);
  context.bezierCurveTo(
    startX + controlOffset,
    start.y,
    endX - controlOffset,
    end.y,
    endX,
    end.y
  );
  context.strokeStyle = 'rgba(98, 217, 255, 0.46)';
  context.lineWidth = 1.25;
  context.stroke();
  context.restore();
}


function drawSceneNode(context, node, geometry) {
  const center = nodePoint(node, geometry);
  const left = center.x - geometry.nodeWidth / 2;
  const top = center.y - geometry.nodeHeight / 2;
  const radius = Math.min(15, geometry.nodeWidth * 0.09);
  const active = node.flowCount > 0;

  context.save();
  context.beginPath();
  roundedRectPath(
    context,
    left,
    top,
    geometry.nodeWidth,
    geometry.nodeHeight,
    radius
  );
  context.fillStyle = active
    ? 'rgba(19, 72, 105, 0.34)'
    : 'rgba(13, 26, 48, 0.48)';
  context.strokeStyle = active
    ? 'rgba(102, 237, 190, 0.5)'
    : 'rgba(99, 154, 217, 0.3)';
  context.lineWidth = active ? 1.5 : 1;
  context.fill();
  context.stroke();

  context.beginPath();
  context.arc(left + 14, top + 14, active ? 3.5 : 2.5, 0, Math.PI * 2);
  context.fillStyle = active
    ? 'rgba(102, 237, 190, 0.92)'
    : 'rgba(157, 140, 255, 0.68)';
  context.fill();
  context.restore();
}


function roundedRectPath(context, x, y, width, height, radius) {
  const right = x + width;
  const bottom = y + height;
  context.moveTo(x + radius, y);
  context.lineTo(right - radius, y);
  context.quadraticCurveTo(right, y, right, y + radius);
  context.lineTo(right, bottom - radius);
  context.quadraticCurveTo(right, bottom, right - radius, bottom);
  context.lineTo(x + radius, bottom);
  context.quadraticCurveTo(x, bottom, x, bottom - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
}


function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}


function finiteNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}


function safeIdentifier(value, fallback) {
  const normalized = String(value ?? '').trim();
  return normalized || fallback;
}


function safelyNotifyFailure(callback) {
  try {
    callback?.();
  } catch {
    // Canvas failure must stay inside the Command Center DOM fallback.
  }
}
