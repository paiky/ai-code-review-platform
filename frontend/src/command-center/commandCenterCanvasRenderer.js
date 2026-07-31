import { createCanvasRuntime } from '../canvas/canvasRuntime.js';


export const COMMAND_CENTER_CANVAS_MAX_DPR = 2;
export const COMMAND_CENTER_PARTICLE_LIMIT = 48;
export const COMMAND_CENTER_PARTICLES_PER_FLOW = 4;
export const COMMAND_CENTER_TRANSITION_DURATION_MS = 900;

const COMMAND_CENTER_FLOW_PARTICLE_LIMIT = 12;
const TAU = Math.PI * 2;
const CONTINUOUS_VISUAL_STATES = new Set([
  'QUEUED',
  'RUNNING',
  'AGENT_ANALYZING',
  'AGENT_TOOL_ACTIVITY',
  'AGENT_CONVERGING',
  'AGENT_SUBMITTING'
]);
const SCENE_FRESHNESS = new Set(['FRESH', 'STALE', 'EMPTY']);
const FLOW_ENGINES = new Set(['STANDARD', 'AGENT', 'FALLBACK']);
const STATE_COLORS = Object.freeze({
  QUEUED: '#f3c875',
  RUNNING: '#62d9ff',
  AGENT_ANALYZING: '#9d8cff',
  AGENT_TOOL_ACTIVITY: '#8bc7ff',
  AGENT_CONVERGING: '#b89cff',
  AGENT_SUBMITTING: '#66edbe',
  FAILED: '#ff7184',
  FALLBACK: '#f3c875',
  COMPLETED: '#66edbe',
  STALE: '#7f8da3'
});
const EMPTY_SCENE = Object.freeze({
  id: 'review-lifecycle',
  snapshotKey: 'EMPTY',
  freshness: 'EMPTY',
  allowAnimation: false,
  nodes: Object.freeze([]),
  edges: Object.freeze([]),
  flows: Object.freeze([])
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
  const columnKeys = new Set(nodes.map(node => node.columnKey));
  const edges = (Array.isArray(input.edges) ? input.edges : [])
    .map(edge => normalizeSceneEdge(edge, nodeIds))
    .filter(Boolean);
  const freshnessCandidate = safeIdentifier(input.freshness, 'EMPTY').toUpperCase();
  const freshness = SCENE_FRESHNESS.has(freshnessCandidate)
    ? freshnessCandidate
    : 'EMPTY';
  const flows = (Array.isArray(input.flows) ? input.flows : [])
    .map(flow => normalizeSceneFlow(flow, columnKeys, freshness))
    .filter(Boolean);
  const allowAnimation = (
    freshness === 'FRESH'
    && input.allowAnimation === true
    && flows.some(flow => flow.motionMode === 'CONTINUOUS')
  );
  return Object.freeze({
    id: safeIdentifier(input.id, 'review-lifecycle'),
    snapshotKey: safeIdentifier(input.snapshotKey, 'EMPTY'),
    freshness,
    allowAnimation,
    nodes: Object.freeze(nodes),
    edges: Object.freeze(edges),
    flows: Object.freeze(flows)
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


export function deriveCommandCenterFlowSeed({
  taskId = 0,
  reviewKey = 'default'
} = {}) {
  return hashString(`${Math.max(0, Math.trunc(finiteNumber(taskId, 0)))}:${safeIdentifier(reviewKey, 'default')}`);
}


export function createCommandCenterParticleLayout(
  scene,
  { limit = COMMAND_CENTER_PARTICLE_LIMIT } = {}
) {
  const normalizedScene = normalizeCommandCenterScene(scene);
  const safeLimit = Math.max(
    0,
    Math.min(COMMAND_CENTER_PARTICLE_LIMIT, Math.trunc(finiteNumber(limit, 0)))
  );
  const flows = normalizedScene.flows.slice(0, COMMAND_CENTER_FLOW_PARTICLE_LIMIT);
  if (safeLimit === 0 || flows.length === 0) return Object.freeze([]);

  const perFlow = Math.max(
    1,
    Math.min(
      COMMAND_CENTER_PARTICLES_PER_FLOW,
      Math.floor(safeLimit / flows.length)
    )
  );
  const particles = [];
  for (const flow of flows) {
    const flowSeed = deriveCommandCenterFlowSeed({
      taskId: flow.taskId,
      reviewKey: flow.reviewKey
    });
    for (let index = 0; index < perFlow && particles.length < safeLimit; index += 1) {
      const random = mulberry32((flowSeed + Math.imul(index + 1, 0x9e3779b1)) >>> 0);
      particles.push(Object.freeze({
        id: `${flow.id}:particle:${index}`,
        flowId: flow.id,
        seed: flowSeed,
        offset: random(),
        laneOffset: random() * 2 - 1,
        speed: 0.055 + random() * 0.045,
        radius: 1.6 + random() * 1.4
      }));
    }
  }
  return Object.freeze(particles);
}


export function reconcileCommandCenterScenes(
  previousScene,
  nextScene,
  { initial = false } = {}
) {
  const previous = normalizeCommandCenterScene(previousScene);
  const next = normalizeCommandCenterScene(nextScene);
  if (
    initial
    || previous.snapshotKey === next.snapshotKey
    || previous.freshness !== 'FRESH'
    || next.freshness !== 'FRESH'
  ) {
    return Object.freeze([]);
  }

  const previousFlows = new Map(previous.flows.map(flow => [flow.id, flow]));
  const transitions = [];
  for (const flow of next.flows.slice(0, COMMAND_CENTER_FLOW_PARTICLE_LIMIT)) {
    if (!flow.stateRecognized) continue;
    const prior = previousFlows.get(flow.id);
    const entered = !prior;
    const stateChanged = (
      prior
      && (
        prior.visualState !== flow.visualState
        || prior.columnKey !== flow.columnKey
      )
    );
    if (!entered && !stateChanged) continue;
    const kind = entered ? 'FLOW_ENTERED' : 'STATE_CHANGED';
    transitions.push(Object.freeze({
      id: `transition:${flow.id}:${next.snapshotKey}:${kind}`,
      flowId: flow.id,
      kind,
      fromState: prior?.visualState || null,
      toState: flow.visualState,
      columnKey: flow.columnKey,
      engineKind: flow.engineKind
    }));
  }
  return Object.freeze(transitions);
}


export function drawCommandCenterCanvasFrame({
  context,
  width,
  height,
  dpr,
  scene,
  particles,
  transitions = [],
  transitionProgress = 1,
  timestamp = 0
}) {
  const canvasWidth = Math.max(0, finiteNumber(width, 0));
  const canvasHeight = Math.max(0, finiteNumber(height, 0));
  if (!context || canvasWidth <= 0 || canvasHeight <= 0) return;

  const normalizedScene = normalizeCommandCenterScene(scene);
  const particleLayout = Array.isArray(particles)
    ? particles
    : createCommandCenterParticleLayout(normalizedScene);
  const nodesById = new Map(normalizedScene.nodes.map(node => [node.id, node]));
  const flowsById = new Map(normalizedScene.flows.map(flow => [flow.id, flow]));
  const flowsByColumn = groupFlowsByColumn(normalizedScene.flows);
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
    drawSceneNode(
      context,
      node,
      geometry,
      flowsByColumn.get(node.columnKey) || []
    );
  }
  for (const particle of particleLayout) {
    const flow = flowsById.get(particle.flowId);
    if (!flow) continue;
    if (normalizedScene.allowAnimation && flow.motionMode === 'CONTINUOUS') {
      drawMovingFlowParticle(
        context,
        particle,
        flow,
        normalizedScene,
        geometry,
        timestamp
      );
    } else {
      drawStaticFlowParticle(context, particle, flow, normalizedScene, geometry);
    }
  }
  for (const transition of transitions) {
    drawSceneTransition(
      context,
      transition,
      flowsById.get(transition.flowId),
      normalizedScene,
      geometry,
      transitionProgress
    );
  }
  context.restore();
}


class CommandCenterCanvasController {
  constructor(options) {
    this.canvas = options.canvas;
    this.container = options.container;
    this.environment = options.environment;
    this.documentTarget = options.environment?.documentTarget
      || (typeof document === 'undefined' ? null : document);
    this.onFailure = options.onFailure;
    this.scene = normalizeCommandCenterScene(options.scene);
    this.particles = createCommandCenterParticleLayout(this.scene);
    this.transitions = Object.freeze([]);
    this.transitionStartedAt = null;
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
      onDraw: ({ context, width, height, dpr, timestamp }) => {
        const transitionFrame = this.resolveTransitionFrame(timestamp);
        drawCommandCenterCanvasFrame({
          context,
          width,
          height,
          dpr,
          timestamp,
          scene: this.scene,
          particles: this.particles,
          transitions: transitionFrame.transitions,
          transitionProgress: transitionFrame.progress
        });
        if (transitionFrame.complete) {
          this.transitions = Object.freeze([]);
          this.transitionStartedAt = null;
        }
      },
      isAnimationEnabled: () => this.shouldAnimate(),
      onFailure: this.handleRuntimeFailure
    });
    return Boolean(this.runtime);
  }

  setScene(scene) {
    if (this.disposed || this.failed) return;
    const nextScene = normalizeCommandCenterScene(scene);
    this.transitions = this.isDocumentHidden()
      ? Object.freeze([])
      : reconcileCommandCenterScenes(this.scene, nextScene);
    this.transitionStartedAt = null;
    this.scene = nextScene;
    this.particles = createCommandCenterParticleLayout(nextScene);
    this.runtime?.refresh();
  }

  shouldAnimate() {
    return (
      !this.disposed
      && !this.failed
      && (this.scene.allowAnimation || this.transitions.length > 0)
    );
  }

  isDocumentHidden() {
    return (
      this.documentTarget?.hidden === true
      || this.documentTarget?.visibilityState === 'hidden'
    );
  }

  resolveTransitionFrame(timestamp) {
    if (this.transitions.length === 0) {
      return { transitions: this.transitions, progress: 1, complete: false };
    }
    const frameTimestamp = Math.max(0, finiteNumber(timestamp, 0));
    if (this.transitionStartedAt === null) {
      this.transitionStartedAt = frameTimestamp;
    }
    const progress = clamp(
      (frameTimestamp - this.transitionStartedAt) / COMMAND_CENTER_TRANSITION_DURATION_MS,
      0,
      1
    );
    return {
      transitions: this.transitions,
      progress,
      complete: progress >= 1
    };
  }

  handleRuntimeFailure() {
    if (this.failed || this.disposed) return;
    this.failed = true;
    this.transitions = Object.freeze([]);
    this.transitionStartedAt = null;
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
    this.documentTarget = null;
    this.particles = Object.freeze([]);
    this.transitions = Object.freeze([]);
    this.transitionStartedAt = null;
  }

  getSnapshot() {
    const runtimeSnapshot = this.runtime?.getSnapshot() || this.lastRuntimeSnapshot || {};
    return {
      ...runtimeSnapshot,
      failed: this.failed || Boolean(runtimeSnapshot.failed),
      disposed: this.disposed || Boolean(runtimeSnapshot.disposed),
      allowAnimation: this.scene.allowAnimation,
      snapshotKey: this.scene.snapshotKey,
      freshness: this.scene.freshness,
      nodeCount: this.scene.nodes.length,
      edgeCount: this.scene.edges.length,
      flowCount: this.scene.flows.length,
      particleCount: this.particles.length,
      transitionCount: this.transitions.length
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


function normalizeSceneFlow(flow, columnKeys, freshness) {
  if (!flow || typeof flow !== 'object') return null;
  const id = safeIdentifier(flow.id, '');
  const columnKey = safeIdentifier(flow.columnKey, '');
  if (!id || !columnKeys.has(columnKey)) return null;
  const stateCandidate = safeIdentifier(flow.visualState, 'RUNNING').toUpperCase();
  const stateRecognized = (
    flow.stateRecognized !== false
    && Boolean(STATE_COLORS[stateCandidate])
  );
  const visualState = freshness === 'STALE'
    ? 'STALE'
    : STATE_COLORS[stateCandidate]
      ? stateCandidate
      : 'RUNNING';
  const engineCandidate = safeIdentifier(flow.engineKind, 'STANDARD').toUpperCase();
  const engineKind = FLOW_ENGINES.has(engineCandidate)
    ? engineCandidate
    : 'STANDARD';
  const continuous = (
    freshness === 'FRESH'
    && stateRecognized
    && flow.motionMode === 'CONTINUOUS'
    && CONTINUOUS_VISUAL_STATES.has(visualState)
  );
  return Object.freeze({
    id,
    seedKey: safeIdentifier(flow.seedKey, id),
    taskId: Math.max(0, Math.trunc(finiteNumber(flow.taskId, 0))),
    reviewKey: safeIdentifier(flow.reviewKey, 'default'),
    engineKind,
    columnKey,
    visualState,
    motionMode: continuous ? 'CONTINUOUS' : 'STATIC',
    stateRecognized,
    updatedAt: safeNullableIdentifier(flow.updatedAt)
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


function drawSceneNode(context, node, geometry, flows) {
  const center = nodePoint(node, geometry);
  const left = center.x - geometry.nodeWidth / 2;
  const top = center.y - geometry.nodeHeight / 2;
  const radius = Math.min(15, geometry.nodeWidth * 0.09);
  const active = node.flowCount > 0;
  const stateColor = resolveColumnStateColor(flows);

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
    ? stateColor
    : 'rgba(99, 154, 217, 0.3)';
  context.lineWidth = active ? 1.5 : 1;
  context.fill();
  context.stroke();

  context.beginPath();
  context.arc(left + 14, top + 14, active ? 3.5 : 2.5, 0, TAU);
  context.fillStyle = active ? stateColor : 'rgba(157, 140, 255, 0.68)';
  context.fill();
  context.restore();
}


function drawMovingFlowParticle(
  context,
  particle,
  flow,
  scene,
  geometry,
  timestamp
) {
  const progress = (
    particle.offset
    + Math.max(0, finiteNumber(timestamp, 0)) / 1000 * particle.speed
  ) % 1;
  const point = pointOnFlowPath(scene, flow, geometry, progress, particle.laneOffset);
  if (!point) return;

  context.save();
  context.beginPath();
  context.arc(point.x, point.y, particle.radius, 0, TAU);
  context.fillStyle = stateColor(flow);
  context.fill();
  context.restore();
}


function drawStaticFlowParticle(context, particle, flow, scene, geometry) {
  const target = targetNode(scene, flow);
  if (!target) return;
  const center = nodePoint(target, geometry);
  const angle = particle.offset * TAU;
  const orbitX = geometry.nodeWidth * 0.31;
  const orbitY = geometry.nodeHeight * 0.28;

  context.save();
  context.globalAlpha = flow.visualState === 'STALE' ? 0.42 : 0.72;
  context.beginPath();
  context.arc(
    center.x + Math.cos(angle) * orbitX,
    center.y + Math.sin(angle) * orbitY,
    Math.max(1.2, particle.radius * 0.78),
    0,
    TAU
  );
  context.fillStyle = stateColor(flow);
  context.fill();
  context.restore();
}


function drawSceneTransition(
  context,
  transition,
  flow,
  scene,
  geometry,
  progress
) {
  if (!flow) return;
  const safeProgress = clamp(finiteNumber(progress, 1), 0, 1);
  const target = targetNode(scene, flow);
  if (!target) return;
  const center = nodePoint(target, geometry);
  const color = stateColor(flow);

  context.save();
  context.globalAlpha = Math.max(0, 1 - safeProgress);
  context.beginPath();
  context.arc(center.x, center.y, 12 + safeProgress * 34, 0, TAU);
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.stroke();

  const movingPoint = pointOnFlowPath(scene, flow, geometry, safeProgress, 0);
  if (movingPoint) {
    context.beginPath();
    context.arc(movingPoint.x, movingPoint.y, 3.2, 0, TAU);
    context.fillStyle = color;
    context.fill();
  }
  context.restore();
}


function pointOnFlowPath(scene, flow, geometry, progress, laneOffset) {
  const orderedNodes = [...scene.nodes].sort((left, right) => left.x - right.x);
  const targetIndex = orderedNodes.findIndex(node => node.columnKey === flow.columnKey);
  if (targetIndex < 0) return null;
  const pathNodes = orderedNodes.slice(0, targetIndex + 1);
  if (pathNodes.length === 1) {
    const center = nodePoint(pathNodes[0], geometry);
    const angle = clamp(progress, 0, 1) * TAU;
    return {
      x: center.x + Math.cos(angle) * geometry.nodeWidth * 0.24,
      y: center.y + Math.sin(angle) * geometry.nodeHeight * 0.22
    };
  }

  const scaled = clamp(progress, 0, 0.999999) * (pathNodes.length - 1);
  const segmentIndex = Math.min(pathNodes.length - 2, Math.floor(scaled));
  const segmentProgress = scaled - segmentIndex;
  const start = nodePoint(pathNodes[segmentIndex], geometry);
  const end = nodePoint(pathNodes[segmentIndex + 1], geometry);
  return {
    x: start.x + (end.x - start.x) * segmentProgress,
    y: start.y + (end.y - start.y) * segmentProgress + laneOffset * 10
  };
}


function targetNode(scene, flow) {
  return scene.nodes.find(node => node.columnKey === flow.columnKey) || null;
}


function groupFlowsByColumn(flows) {
  const grouped = new Map();
  for (const flow of flows) {
    if (!grouped.has(flow.columnKey)) grouped.set(flow.columnKey, []);
    grouped.get(flow.columnKey).push(flow);
  }
  return grouped;
}


function resolveColumnStateColor(flows) {
  const priorities = [
    'FAILED',
    'FALLBACK',
    'AGENT_SUBMITTING',
    'AGENT_CONVERGING',
    'AGENT_TOOL_ACTIVITY',
    'AGENT_ANALYZING',
    'QUEUED',
    'RUNNING',
    'COMPLETED',
    'STALE'
  ];
  for (const state of priorities) {
    if (flows.some(flow => flow.visualState === state)) {
      return STATE_COLORS[state];
    }
  }
  return '#66edbe';
}


function stateColor(flow) {
  if (flow.engineKind === 'FALLBACK') return STATE_COLORS.FALLBACK;
  if (flow.visualState === 'RUNNING' && flow.engineKind === 'AGENT') {
    return STATE_COLORS.AGENT_ANALYZING;
  }
  return STATE_COLORS[flow.visualState] || STATE_COLORS.RUNNING;
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


function hashString(value) {
  let hash = 0x811c9dc5;
  for (const character of String(value)) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}


function mulberry32(seed) {
  let value = seed >>> 0;
  return () => {
    value += 0x6d2b79f5;
    let next = value;
    next = Math.imul(next ^ (next >>> 15), next | 1);
    next ^= next + Math.imul(next ^ (next >>> 7), next | 61);
    return ((next ^ (next >>> 14)) >>> 0) / 4294967296;
  };
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


function safeNullableIdentifier(value) {
  const normalized = String(value ?? '').trim();
  return normalized || null;
}


function safelyNotifyFailure(callback) {
  try {
    callback?.();
  } catch {
    // Canvas failure must stay inside the Command Center DOM fallback.
  }
}
