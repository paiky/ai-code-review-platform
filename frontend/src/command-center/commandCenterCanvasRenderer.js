import { createCanvasRuntime } from '../canvas/canvasRuntime.js';


export const COMMAND_CENTER_CANVAS_MAX_DPR = 2;
export const COMMAND_CENTER_DRAW_BUDGET_MS = 8;
export const COMMAND_CENTER_PARTICLE_LIMIT = 120;
export const COMMAND_CENTER_PARTICLE_LIMITS = Object.freeze({
  compact: 48,
  medium: 80,
  wide: 120
});
export const COMMAND_CENTER_INDEPENDENT_FLOW_LIMIT = 20;
export const COMMAND_CENTER_PARTICLES_PER_FLOW = 6;
export const COMMAND_CENTER_TRANSITION_DURATION_MS = 900;
export const COMMAND_CENTER_AMBIENT_FRAME_INTERVAL_MS = 1000 / 30;

export const COMMAND_CENTER_CANVAS_DIAGNOSTICS_KEY = '__commandCenterCanvasDiagnostics';

const COMMAND_CENTER_COMPACT_VIEWPORT_MAX = 700;
const COMMAND_CENTER_MEDIUM_VIEWPORT_MAX = 1100;
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
const FLOW_STATE_PRIORITY = Object.freeze([
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
]);
const STATE_COLORS = Object.freeze({
  QUEUED: '#ffd166',
  RUNNING: '#27e9ff',
  AGENT_ANALYZING: '#a86bff',
  AGENT_TOOL_ACTIVITY: '#c08cff',
  AGENT_CONVERGING: '#d6a8ff',
  AGENT_SUBMITTING: '#39ffb6',
  FAILED: '#ff4d6d',
  FALLBACK: '#ffd166',
  COMPLETED: '#39ffb6',
  STALE: '#b59a63'
});
let commandCenterControllerSerial = 0;
const EMPTY_SCENE = Object.freeze({
  id: 'review-lifecycle',
  snapshotKey: 'EMPTY',
  freshness: 'EMPTY',
  allowAnimation: false,
  ambientAnimation: false,
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
  const ambientAnimation = input.ambientAnimation === true;
  return Object.freeze({
    id: safeIdentifier(input.id, 'review-lifecycle'),
    snapshotKey: safeIdentifier(input.snapshotKey, 'EMPTY'),
    freshness,
    allowAnimation,
    ambientAnimation,
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


export function resolveCommandCenterParticleLimit(viewportWidth) {
  const width = finiteNumber(viewportWidth, COMMAND_CENTER_MEDIUM_VIEWPORT_MAX + 1);
  if (width <= COMMAND_CENTER_COMPACT_VIEWPORT_MAX) {
    return COMMAND_CENTER_PARTICLE_LIMITS.compact;
  }
  if (width <= COMMAND_CENTER_MEDIUM_VIEWPORT_MAX) {
    return COMMAND_CENTER_PARTICLE_LIMITS.medium;
  }
  return COMMAND_CENTER_PARTICLE_LIMITS.wide;
}


export function createCommandCenterFlowRenderingPlan(
  scene,
  { independentLimit = COMMAND_CENTER_INDEPENDENT_FLOW_LIMIT } = {}
) {
  const normalizedScene = normalizeCommandCenterScene(scene);
  const safeIndependentLimit = Math.max(
    0,
    Math.min(
      COMMAND_CENTER_INDEPENDENT_FLOW_LIMIT,
      Math.trunc(finiteNumber(independentLimit, 0))
    )
  );
  const independentFlows = normalizedScene.flows.slice(0, safeIndependentLimit);
  const overflowFlows = normalizedScene.flows.slice(safeIndependentLimit);
  const overflowByColumn = groupFlowsByColumn(overflowFlows);
  const aggregateFlows = [];

  for (const node of normalizedScene.nodes) {
    const groupedFlows = overflowByColumn.get(node.columnKey) || [];
    if (groupedFlows.length === 0) continue;
    const representative = selectAggregateRepresentative(groupedFlows);
    aggregateFlows.push(Object.freeze({
      id: `aggregate:${node.columnKey}`,
      seedKey: `aggregate:${node.columnKey}`,
      taskId: 0,
      reviewKey: `aggregate:${node.columnKey}`,
      engineKind: resolveAggregateEngineKind(groupedFlows, representative),
      columnKey: node.columnKey,
      visualState: representative.visualState,
      motionMode: representative.motionMode,
      stateRecognized: true,
      updatedAt: representative.updatedAt,
      aggregate: true,
      aggregateCount: groupedFlows.length
    }));
  }

  return Object.freeze({
    independentFlows: Object.freeze(independentFlows),
    aggregateFlows: Object.freeze(aggregateFlows),
    renderFlows: Object.freeze([...independentFlows, ...aggregateFlows]),
    independentFlowCount: independentFlows.length,
    aggregatedFlowCount: overflowFlows.length,
    aggregateGroupCount: aggregateFlows.length
  });
}


export function deriveCommandCenterFlowSeed({
  taskId = 0,
  reviewKey = 'default'
} = {}) {
  return hashString(`${Math.max(0, Math.trunc(finiteNumber(taskId, 0)))}:${safeIdentifier(reviewKey, 'default')}`);
}


export function resolveCommandCenterFlowVisualLanguage(flow = {}) {
  const state = safeIdentifier(flow.visualState, 'RUNNING').toUpperCase();
  const engine = safeIdentifier(flow.engineKind, 'STANDARD').toUpperCase();
  if (state === 'FAILED') {
    return Object.freeze({ color: STATE_COLORS.FAILED, core: 'BROKEN', trail: 'STATIC', signature: 'CROSS' });
  }
  if (state === 'FALLBACK' || engine === 'FALLBACK') {
    return Object.freeze({ color: STATE_COLORS.FALLBACK, core: 'SINGLE', trail: 'DASHED', signature: 'DASHED_RING' });
  }
  if (state === 'COMPLETED') {
    return Object.freeze({ color: STATE_COLORS.COMPLETED, core: 'SETTLED', trail: 'STATIC', signature: 'RING' });
  }
  if (state === 'STALE') {
    return Object.freeze({ color: STATE_COLORS.STALE, core: 'DIMMED', trail: 'DASHED', signature: 'STALE_LINE' });
  }
  if (state === 'QUEUED') {
    return Object.freeze({ color: STATE_COLORS.QUEUED, core: 'PULSE', trail: 'SHORT', signature: 'NONE' });
  }
  if (engine === 'AGENT') {
    return Object.freeze({ color: STATE_COLORS.AGENT_ANALYZING, core: 'DOUBLE', trail: 'LONG', signature: 'NONE' });
  }
  return Object.freeze({
    color: STATE_COLORS[state] || STATE_COLORS.RUNNING,
    core: 'SINGLE',
    trail: 'SOLID',
    signature: 'NONE'
  });
}


export function createCommandCenterParticleLayout(
  scene,
  {
    limit = COMMAND_CENTER_PARTICLE_LIMIT,
    renderingPlan
  } = {}
) {
  const normalizedScene = normalizeCommandCenterScene(scene);
  const safeLimit = Math.max(
    0,
    Math.min(COMMAND_CENTER_PARTICLE_LIMIT, Math.trunc(finiteNumber(limit, 0)))
  );
  const flowPlan = renderingPlan
    || createCommandCenterFlowRenderingPlan(normalizedScene);
  const flows = flowPlan.renderFlows;
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
        radius: 1.6 + random() * 1.4,
        aggregateCount: flow.aggregateCount || 0
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
  for (const flow of next.flows.slice(0, COMMAND_CENTER_INDEPENDENT_FLOW_LIMIT)) {
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
  renderingPlan,
  transitions = [],
  transitionProgress = 1,
  focusFlowId = null,
  timestamp = 0
}) {
  const canvasWidth = Math.max(0, finiteNumber(width, 0));
  const canvasHeight = Math.max(0, finiteNumber(height, 0));
  if (!context || canvasWidth <= 0 || canvasHeight <= 0) return;

  const normalizedScene = normalizeCommandCenterScene(scene);
  const flowPlan = renderingPlan
    || createCommandCenterFlowRenderingPlan(normalizedScene);
  const particleLayout = Array.isArray(particles)
    ? particles
    : createCommandCenterParticleLayout(normalizedScene, {
      renderingPlan: flowPlan
    });
  const nodesById = new Map(normalizedScene.nodes.map(node => [node.id, node]));
  const flowsById = new Map(flowPlan.renderFlows.map(flow => [flow.id, flow]));
  const flowsByColumn = groupFlowsByColumn(normalizedScene.flows);
  const geometry = resolveSceneGeometry(canvasWidth, canvasHeight);
  const focusedFlow = normalizedScene.flows.find(flow => flow.id === focusFlowId) || null;
  const focusPath = resolveFocusedPath(normalizedScene, focusedFlow);

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
  drawAmbientEnvironment(
    context,
    canvasWidth,
    canvasHeight,
    timestamp,
    normalizedScene.ambientAnimation
  );
  drawSceneGrid(context, canvasWidth, canvasHeight, timestamp);
  for (const edge of normalizedScene.edges) {
    drawSceneEdge(context, edge, nodesById, geometry, {
      focused: focusPath.edgeIds.has(edge.id),
      dimmed: Boolean(focusedFlow) && !focusPath.edgeIds.has(edge.id),
      timestamp
    });
  }
  for (const node of normalizedScene.nodes) {
    drawSceneNode(
      context,
      node,
      geometry,
      flowsByColumn.get(node.columnKey) || [],
      {
        focused: focusPath.nodeIds.has(node.id),
        current: focusedFlow?.columnKey === node.columnKey,
        dimmed: Boolean(focusedFlow) && !focusPath.nodeIds.has(node.id),
        timestamp
      }
    );
  }
  for (const particle of particleLayout) {
    const flow = flowsById.get(particle.flowId);
    if (!flow) continue;
    const focusAlpha = focusedFlow
      ? flow.id === focusedFlow.id ? 1 : 0.16
      : 1;
    if (normalizedScene.allowAnimation && flow.motionMode === 'CONTINUOUS') {
      drawMovingFlowParticle(
        context,
        particle,
        flow,
        normalizedScene,
        geometry,
        timestamp,
        focusAlpha
      );
    } else {
      drawStaticFlowParticle(
        context,
        particle,
        flow,
        normalizedScene,
        geometry,
        focusAlpha
      );
    }
  }
  for (const aggregateFlow of flowPlan.aggregateFlows) {
    drawAggregateFlowMarker(
      context,
      aggregateFlow,
      normalizedScene,
      geometry,
      focusedFlow ? 0.18 : 1
    );
  }
  for (const transition of transitions) {
    drawSceneTransition(
      context,
      transition,
      flowsById.get(transition.flowId),
      normalizedScene,
      geometry,
      transitionProgress,
      focusedFlow ? transition.flowId === focusedFlow.id ? 1 : 0.2 : 1
    );
  }
  context.restore();
}


class CommandCenterCanvasController {
  constructor(options) {
    this.instanceId = ++commandCenterControllerSerial;
    this.canvas = options.canvas;
    this.container = options.container;
    this.environment = options.environment;
    this.documentTarget = options.environment?.documentTarget
      || (typeof document === 'undefined' ? null : document);
    this.onFailure = options.onFailure;
    this.scene = normalizeCommandCenterScene(options.scene);
    this.viewportWidth = readCommandCenterViewportWidth(
      this.environment,
      this.container
    );
    this.particleLimit = resolveCommandCenterParticleLimit(this.viewportWidth);
    this.renderingPlan = createCommandCenterFlowRenderingPlan(this.scene);
    this.particles = createCommandCenterParticleLayout(this.scene, {
      limit: this.particleLimit,
      renderingPlan: this.renderingPlan
    });
    this.particleLayoutRevision = 1;
    this.focusFlowId = null;
    this.focusRevision = 0;
    this.setFocusCallCount = 0;
    this.transitions = Object.freeze([]);
    this.transitionStartedAt = null;
    this.runtime = null;
    this.lastRuntimeSnapshot = null;
    this.failed = false;
    this.disposed = false;
    this.diagnosticReader = () => this.getSnapshot();
    this.handleRuntimeFailure = this.handleRuntimeFailure.bind(this);
    this.attachDiagnostics();
    this.updateDiagnosticAttributes();
  }

  initialize() {
    this.runtime = createCanvasRuntime({
      canvas: this.canvas,
      container: this.container,
      environment: this.environment,
      maxDpr: COMMAND_CENTER_CANVAS_MAX_DPR,
      drawBudgetMs: COMMAND_CENTER_DRAW_BUDGET_MS,
      onResize: ({ width }) => this.handleCanvasResize(width),
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
          renderingPlan: this.renderingPlan,
          transitions: transitionFrame.transitions,
          transitionProgress: transitionFrame.progress,
          focusFlowId: this.focusFlowId
        });
        if (transitionFrame.complete) {
          this.transitions = Object.freeze([]);
          this.transitionStartedAt = null;
        }
      },
      isAnimationEnabled: () => this.shouldAnimate(),
      getAnimationFrameInterval: () => this.resolveAnimationFrameInterval(),
      onStateChange: () => this.updateDiagnosticAttributes(),
      onFailure: this.handleRuntimeFailure
    });
    this.updateDiagnosticAttributes();
    return Boolean(this.runtime);
  }

  setScene(scene) {
    if (this.disposed || this.failed) return;
    const nextScene = normalizeCommandCenterScene(scene);
    if (nextScene.snapshotKey === this.scene.snapshotKey) return;
    this.transitions = this.isDocumentHidden()
      ? Object.freeze([])
      : reconcileCommandCenterScenes(this.scene, nextScene);
    this.transitionStartedAt = null;
    this.scene = nextScene;
    this.renderingPlan = createCommandCenterFlowRenderingPlan(nextScene);
    this.particles = createCommandCenterParticleLayout(nextScene, {
      limit: this.particleLimit,
      renderingPlan: this.renderingPlan
    });
    this.particleLayoutRevision += 1;
    if (!nextScene.flows.some(flow => flow.id === this.focusFlowId)) {
      this.focusFlowId = null;
    }
    this.updateDiagnosticAttributes();
    this.runtime?.refresh();
  }

  setFocus(flowId) {
    if (this.disposed || this.failed) return;
    this.setFocusCallCount += 1;
    const candidate = safeNullableIdentifier(flowId);
    const nextFocusFlowId = candidate && this.scene.flows.some(flow => flow.id === candidate)
      ? candidate
      : null;
    if (nextFocusFlowId === this.focusFlowId) {
      this.updateDiagnosticAttributes();
      return;
    }
    this.focusFlowId = nextFocusFlowId;
    this.focusRevision += 1;
    this.updateDiagnosticAttributes();
    this.runtime?.refresh();
  }

  handleCanvasResize(width) {
    if (this.disposed || this.failed) return;
    const nextViewportWidth = readCommandCenterViewportWidth(
      this.environment,
      this.container,
      width
    );
    const nextParticleLimit = resolveCommandCenterParticleLimit(nextViewportWidth);
    this.viewportWidth = nextViewportWidth;
    if (nextParticleLimit === this.particleLimit) {
      this.updateDiagnosticAttributes();
      return;
    }
    this.particleLimit = nextParticleLimit;
    this.particles = createCommandCenterParticleLayout(this.scene, {
      limit: this.particleLimit,
      renderingPlan: this.renderingPlan
    });
    this.particleLayoutRevision += 1;
    this.updateDiagnosticAttributes();
  }

  shouldAnimate() {
    return (
      !this.disposed
      && !this.failed
      && (
        this.scene.ambientAnimation
        || this.scene.allowAnimation
        || this.transitions.length > 0
      )
    );
  }

  resolveAnimationFrameInterval() {
    return this.scene.allowAnimation || this.transitions.length > 0
      ? 0
      : COMMAND_CENTER_AMBIENT_FRAME_INTERVAL_MS;
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
    this.updateDiagnosticAttributes();
    safelyNotifyFailure(this.onFailure);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    const runtime = this.runtime;
    const canvas = this.canvas;
    runtime?.dispose();
    this.lastRuntimeSnapshot = runtime?.getSnapshot() || this.lastRuntimeSnapshot;
    this.runtime = null;
    this.canvas = null;
    this.container = null;
    this.documentTarget = null;
    this.particles = Object.freeze([]);
    this.transitions = Object.freeze([]);
    this.transitionStartedAt = null;
    this.focusFlowId = null;
    if (canvas?.[COMMAND_CENTER_CANVAS_DIAGNOSTICS_KEY] === this.diagnosticReader) {
      try {
        delete canvas[COMMAND_CENTER_CANVAS_DIAGNOSTICS_KEY];
      } catch {
        canvas[COMMAND_CENTER_CANVAS_DIAGNOSTICS_KEY] = undefined;
      }
    }
  }

  getSnapshot() {
    const runtimeSnapshot = this.runtime?.getSnapshot() || this.lastRuntimeSnapshot || {};
    return {
      ...runtimeSnapshot,
      failed: this.failed || Boolean(runtimeSnapshot.failed),
      disposed: this.disposed || Boolean(runtimeSnapshot.disposed),
      controllerInstanceId: this.instanceId,
      allowAnimation: this.scene.allowAnimation,
      ambientAnimation: this.scene.ambientAnimation,
      snapshotKey: this.scene.snapshotKey,
      freshness: this.scene.freshness,
      nodeCount: this.scene.nodes.length,
      edgeCount: this.scene.edges.length,
      flowCount: this.scene.flows.length,
      viewportWidth: this.viewportWidth,
      particleLimit: this.particleLimit,
      particleCount: this.particles.length,
      particleLayoutRevision: this.particleLayoutRevision,
      independentFlowCount: this.renderingPlan.independentFlowCount,
      aggregatedFlowCount: this.renderingPlan.aggregatedFlowCount,
      aggregateGroupCount: this.renderingPlan.aggregateGroupCount,
      renderFlowCount: this.renderingPlan.renderFlows.length,
      transitionCount: this.transitions.length,
      focusFlowId: this.focusFlowId,
      focusRevision: this.focusRevision,
      setFocusCallCount: this.setFocusCallCount,
      animationFrameIntervalMs: this.resolveAnimationFrameInterval()
    };
  }

  attachDiagnostics() {
    if (!this.canvas) return;
    try {
      this.canvas[COMMAND_CENTER_CANVAS_DIAGNOSTICS_KEY] = this.diagnosticReader;
    } catch {
      // Diagnostics are optional; Canvas rendering must remain available.
    }
  }

  updateDiagnosticAttributes() {
    const runtimeSnapshot = this.runtime?.getSnapshot?.() || {};
    this.canvas?.setAttribute?.(
      'data-command-center-controller-instance',
      String(this.instanceId)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-particle-limit',
      String(this.particleLimit)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-independent-flows',
      String(this.renderingPlan.independentFlowCount)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-aggregated-flows',
      String(this.renderingPlan.aggregatedFlowCount)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-focus-flow',
      this.focusFlowId || ''
    );
    this.canvas?.setAttribute?.(
      'data-command-center-focus-revision',
      String(this.focusRevision)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-particle-layout-revision',
      String(this.particleLayoutRevision)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-animation-fps',
      this.resolveAnimationFrameInterval() > 0 ? '30' : '60'
    );
    this.canvas?.setAttribute?.(
      'data-command-center-canvas-health',
      this.failed ? 'failed' : 'ready'
    );
    this.canvas?.setAttribute?.(
      'data-command-center-frame-count',
      String(runtimeSnapshot.frameCount || 0)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-average-draw-ms',
      String(runtimeSnapshot.averageDrawMs || 0)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-max-draw-ms',
      String(runtimeSnapshot.maxDrawMs || 0)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-over-budget-frames',
      String(runtimeSnapshot.overBudgetFrameCount || 0)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-active-raf',
      String(runtimeSnapshot.activeRafCount || 0)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-observer-registrations',
      String(runtimeSnapshot.observerRegistrationCount || 0)
    );
    this.canvas?.setAttribute?.(
      'data-command-center-listener-registrations',
      String(runtimeSnapshot.listenerRegistrationCount || 0)
    );
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


function drawAmbientEnvironment(context, width, height, timestamp, enabled) {
  if (!enabled) return;
  const time = Math.max(0, finiteNumber(timestamp, 0));
  const phase = (time / 4200) % 1;
  const horizon = height * 0.58;

  context.save();
  context.globalAlpha = 0.32;
  context.strokeStyle = '#27e9ff';
  context.lineWidth = 0.7;
  for (let index = -5; index <= 5; index += 1) {
    context.beginPath();
    context.moveTo(width * 0.5, horizon);
    context.lineTo(width * 0.5 + index * width * 0.16, height);
    context.stroke();
  }

  for (let index = 0; index < 7; index += 1) {
    const normalized = ((index / 7) + phase) % 1;
    const y = horizon + normalized * normalized * (height - horizon);
    context.globalAlpha = 0.08 + normalized * 0.2;
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }

  const scanY = (time / 26) % Math.max(1, height);
  context.globalAlpha = 0.1;
  context.fillStyle = '#ff3dc8';
  context.shadowColor = '#ff3dc8';
  context.shadowBlur = 18;
  context.fillRect?.(0, scanY, width, 2);

  context.globalAlpha = 0.15 + Math.sin(time / 1500) * 0.04;
  context.strokeStyle = '#a86bff';
  context.shadowColor = '#a86bff';
  context.shadowBlur = 28;
  context.beginPath();
  context.arc(width * 0.72, height * 1.08, width * 0.46, Math.PI * 1.08, Math.PI * 1.92);
  context.stroke();
  context.restore();
}


function drawSceneGrid(context, width, height, timestamp = 0) {
  const offset = (Math.max(0, finiteNumber(timestamp, 0)) / 90) % 32;
  context.save();
  context.strokeStyle = 'rgba(39, 233, 255, 0.075)';
  context.lineWidth = 1;
  for (let x = 0.5 + offset; x < width; x += 32) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
  context.restore();
}


function drawSceneEdge(
  context,
  edge,
  nodesById,
  geometry,
  { focused = false, dimmed = false, timestamp = 0 } = {}
) {
  const from = nodesById.get(edge.from);
  const to = nodesById.get(edge.to);
  if (!from || !to) return;
  const start = nodePoint(from, geometry);
  const end = nodePoint(to, geometry);
  const startX = start.x + geometry.nodeWidth / 2;
  const endX = end.x - geometry.nodeWidth / 2;
  const controlOffset = Math.max(10, (endX - startX) * 0.42);

  context.save();
  context.globalAlpha = dimmed ? 0.22 : 1;
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
  context.strokeStyle = focused ? '#ff3dc8' : 'rgba(39, 233, 255, 0.66)';
  context.lineWidth = focused ? 2.8 : 1.5;
  context.shadowColor = focused ? '#ff3dc8' : '#27e9ff';
  context.shadowBlur = focused ? 18 : 10;
  context.stroke();

  const energyProgress = (Math.max(0, finiteNumber(timestamp, 0)) / 1700) % 1;
  const energyX = startX + (endX - startX) * energyProgress;
  context.globalAlpha = dimmed ? 0.08 : focused ? 0.95 : 0.48;
  context.beginPath();
  context.arc(energyX, start.y, focused ? 3.2 : 2.1, 0, TAU);
  context.fillStyle = focused ? '#ff3dc8' : '#27e9ff';
  context.fill();
  context.restore();
}


function drawSceneNode(
  context,
  node,
  geometry,
  flows,
  { focused = false, current = false, dimmed = false, timestamp = 0 } = {}
) {
  const center = nodePoint(node, geometry);
  const left = center.x - geometry.nodeWidth / 2;
  const top = center.y - geometry.nodeHeight / 2;
  const radius = Math.min(15, geometry.nodeWidth * 0.09);
  const active = node.flowCount > 0;
  const stateColor = resolveColumnStateColor(flows);
  const pulse = 0.5 + Math.sin(Math.max(0, finiteNumber(timestamp, 0)) / 620) * 0.5;

  context.save();
  context.globalAlpha = dimmed ? 0.3 : 1;
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
  context.strokeStyle = current
    ? '#ff3dc8'
    : focused
      ? '#27e9ff'
      : active
        ? stateColor
        : 'rgba(39, 233, 255, 0.38)';
  context.lineWidth = current ? 2.8 : focused || active ? 1.7 : 1;
  context.shadowColor = current ? '#ff3dc8' : focused ? '#27e9ff' : stateColor;
  context.shadowBlur = current ? 22 + pulse * 9 : focused || active ? 10 + pulse * 5 : 0;
  context.fill();
  context.stroke();

  context.beginPath();
  context.arc(left + 14, top + 14, active ? 3.5 : 2.5, 0, TAU);
  context.fillStyle = current
    ? '#ff3dc8'
    : active ? stateColor : 'rgba(168, 107, 255, 0.72)';
  context.fill();
  context.restore();
}


function drawMovingFlowParticle(
  context,
  particle,
  flow,
  scene,
  geometry,
  timestamp,
  focusAlpha = 1
) {
  const progress = (
    particle.offset
    + Math.max(0, finiteNumber(timestamp, 0)) / 1000 * particle.speed
  ) % 1;
  const point = pointOnFlowPath(scene, flow, geometry, progress, particle.laneOffset);
  if (!point) return;
  const visualLanguage = resolveCommandCenterFlowVisualLanguage(flow);
  const tailPoint = pointOnFlowPath(
    scene,
    flow,
    geometry,
    Math.max(0, progress - (visualLanguage.trail === 'LONG' ? 0.07 : 0.04)),
    particle.laneOffset
  );
  const color = stateColor(flow);

  context.save();
  context.globalAlpha = clamp(focusAlpha, 0, 1);
  if (tailPoint) {
    context.beginPath();
    context.moveTo(tailPoint.x, tailPoint.y);
    context.lineTo(point.x, point.y);
    context.strokeStyle = color;
    context.lineWidth = visualLanguage.trail === 'LONG' ? 2.2 : 1.4;
    context.shadowColor = color;
    context.shadowBlur = 12;
    if (visualLanguage.trail === 'DASHED') context.setLineDash?.([4, 5]);
    context.stroke();
    context.setLineDash?.([]);
  }
  if (visualLanguage.core === 'DOUBLE') {
    context.globalAlpha = clamp(focusAlpha * 0.48, 0, 1);
    context.beginPath();
    context.arc(point.x, point.y, particle.radius * 2.5, 0, TAU);
    context.strokeStyle = '#a86bff';
    context.lineWidth = 1;
    context.stroke();
  }
  context.globalAlpha = clamp(focusAlpha, 0, 1);
  context.beginPath();
  context.arc(point.x, point.y, particle.radius, 0, TAU);
  context.fillStyle = color;
  context.shadowColor = color;
  context.shadowBlur = 15;
  context.fill();
  context.restore();
}


function drawStaticFlowParticle(
  context,
  particle,
  flow,
  scene,
  geometry,
  focusAlpha = 1
) {
  const target = targetNode(scene, flow);
  if (!target) return;
  const center = nodePoint(target, geometry);
  const angle = particle.offset * TAU;
  const orbitX = geometry.nodeWidth * 0.31;
  const orbitY = geometry.nodeHeight * 0.28;

  context.save();
  context.globalAlpha = (flow.visualState === 'STALE' ? 0.36 : 0.72) * focusAlpha;
  if (flow.visualState === 'STALE') context.setLineDash?.([2, 5]);
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
  context.setLineDash?.([]);

  if (particle.id.endsWith(':particle:0')) {
    drawTerminalStateSignature(context, flow, center, geometry, focusAlpha);
  }
  context.restore();
}


function drawAggregateFlowMarker(context, flow, scene, geometry, opacity = 1) {
  const target = targetNode(scene, flow);
  if (!target || flow.aggregateCount <= 0) return;
  const center = nodePoint(target, geometry);
  const x = center.x + geometry.nodeWidth * 0.34;
  const y = center.y - geometry.nodeHeight * 0.34;
  const radius = clamp(9 + Math.log2(flow.aggregateCount + 1) * 1.4, 10, 16);

  context.save();
  context.globalAlpha = clamp(opacity, 0, 1);
  context.beginPath();
  context.arc(x, y, radius, 0, TAU);
  context.fillStyle = 'rgba(5, 12, 26, 0.92)';
  context.fill();
  context.strokeStyle = stateColor(flow);
  context.lineWidth = 1.5;
  context.stroke();
  if (typeof context.fillText === 'function') {
    context.fillStyle = '#eaf2ff';
    context.font = '600 9px ui-monospace, SFMono-Regular, Menlo, monospace';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(`+${flow.aggregateCount}`, x, y + 0.5);
  }
  context.restore();
}


function drawSceneTransition(
  context,
  transition,
  flow,
  scene,
  geometry,
  progress,
  opacity = 1
) {
  if (!flow) return;
  const safeProgress = clamp(finiteNumber(progress, 1), 0, 1);
  const target = targetNode(scene, flow);
  if (!target) return;
  const center = nodePoint(target, geometry);
  const color = stateColor(flow);

  context.save();
  context.globalAlpha = Math.max(0, 1 - safeProgress) * clamp(opacity, 0, 1);
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


function drawTerminalStateSignature(context, flow, center, geometry, opacity) {
  const color = stateColor(flow);
  const alpha = clamp(opacity, 0, 1);
  const radius = Math.min(geometry.nodeWidth, geometry.nodeHeight) * 0.19;

  context.save();
  context.globalAlpha = alpha * 0.86;
  context.strokeStyle = color;
  context.fillStyle = color;
  context.shadowColor = color;
  context.shadowBlur = 16;
  context.lineWidth = 1.8;

  if (flow.visualState === 'FAILED') {
    context.beginPath();
    context.moveTo(center.x - radius, center.y - radius);
    context.lineTo(center.x + radius, center.y + radius);
    context.moveTo(center.x + radius, center.y - radius);
    context.lineTo(center.x - radius, center.y + radius);
    context.stroke();
  } else if (flow.visualState === 'COMPLETED') {
    context.beginPath();
    context.arc(center.x, center.y, radius, 0, TAU);
    context.stroke();
    context.beginPath();
    context.arc(center.x, center.y, Math.max(2, radius * 0.24), 0, TAU);
    context.fill();
  } else if (flow.visualState === 'FALLBACK') {
    context.setLineDash?.([7, 6]);
    context.beginPath();
    context.arc(center.x, center.y, radius * 1.08, 0, TAU);
    context.stroke();
    context.setLineDash?.([]);
  } else if (flow.visualState === 'STALE') {
    context.setLineDash?.([3, 5]);
    context.beginPath();
    context.moveTo(center.x - radius * 1.3, center.y);
    context.lineTo(center.x + radius * 1.3, center.y);
    context.stroke();
    context.setLineDash?.([]);
  }
  context.restore();
}


function resolveFocusedPath(scene, focusedFlow) {
  if (!focusedFlow) {
    return { nodeIds: new Set(), edgeIds: new Set() };
  }
  const orderedNodes = [...scene.nodes].sort((left, right) => left.x - right.x);
  const targetIndex = orderedNodes.findIndex(
    node => node.columnKey === focusedFlow.columnKey
  );
  if (targetIndex < 0) {
    return { nodeIds: new Set(), edgeIds: new Set() };
  }
  const pathNodeIds = new Set(
    orderedNodes.slice(0, targetIndex + 1).map(node => node.id)
  );
  const pathEdgeIds = new Set(
    scene.edges
      .filter(edge => pathNodeIds.has(edge.from) && pathNodeIds.has(edge.to))
      .map(edge => edge.id)
  );
  return { nodeIds: pathNodeIds, edgeIds: pathEdgeIds };
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


function selectAggregateRepresentative(flows) {
  for (const state of FLOW_STATE_PRIORITY) {
    const match = flows.find(flow => flow.visualState === state);
    if (match) return match;
  }
  return flows[0];
}


function resolveAggregateEngineKind(flows, representative) {
  const engines = new Set(flows.map(flow => flow.engineKind));
  return engines.size === 1
    ? flows[0].engineKind
    : representative.engineKind;
}


function resolveColumnStateColor(flows) {
  for (const state of FLOW_STATE_PRIORITY) {
    if (flows.some(flow => flow.visualState === state)) {
      return STATE_COLORS[state];
    }
  }
  return '#66edbe';
}


function stateColor(flow) {
  return resolveCommandCenterFlowVisualLanguage(flow).color;
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


function readCommandCenterViewportWidth(
  environment,
  container,
  fallbackWidth = 0
) {
  let environmentWidth = 0;
  try {
    environmentWidth = finiteNumber(environment?.getViewportWidth?.(), 0);
  } catch {
    environmentWidth = 0;
  }
  if (environmentWidth > 0) return environmentWidth;

  const rootWidth = typeof window === 'undefined'
    ? 0
    : finiteNumber(window.innerWidth, 0);
  if (rootWidth > 0) return rootWidth;

  const containerWidth = finiteNumber(
    container?.getBoundingClientRect?.()?.width,
    0
  );
  return Math.max(0, containerWidth, finiteNumber(fallbackWidth, 0));
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
