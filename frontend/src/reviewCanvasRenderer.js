import {
  createCanvasRuntime,
  normalizeCanvasDpr
} from './canvas/canvasRuntime.js';


export const REVIEW_CANVAS_SEED = 0x50c0de;
export const REVIEW_CANVAS_MAX_DPR = 2;
export const REVIEW_CANVAS_PARTICLE_LIMITS = Object.freeze({
  MOBILE: 48,
  COMPACT: 80,
  DESKTOP: 120,
  STANDARD: 24
});

const TAU = Math.PI * 2;
const animatedStates = new Set([
  'QUEUED',
  'ANALYZING',
  'EVIDENCE',
  'CONVERGING',
  'SUBMITTING',
  'FALLBACK'
]);
const motionByState = Object.freeze({
  QUEUED: Object.freeze({
    speed: 0.08,
    intensity: 0.42,
    radialScale: 0.96,
    flowDirection: 1
  }),
  ANALYZING: Object.freeze({
    speed: 0.32,
    intensity: 0.72,
    radialScale: 1.04,
    flowDirection: 1
  }),
  EVIDENCE: Object.freeze({
    speed: 0.52,
    intensity: 0.86,
    radialScale: 1.08,
    flowDirection: 1
  }),
  CONVERGING: Object.freeze({
    speed: 0.24,
    intensity: 0.78,
    radialScale: 0.84,
    flowDirection: -1
  }),
  SUBMITTING: Object.freeze({
    speed: 0.4,
    intensity: 0.9,
    radialScale: 0.72,
    flowDirection: 1
  }),
  FALLBACK: Object.freeze({
    speed: 0.18,
    intensity: 0.64,
    radialScale: 0.9,
    flowDirection: 1
  })
});

export function createDeterministicParticleLayout({
  seed = REVIEW_CANVAS_SEED,
  count = REVIEW_CANVAS_PARTICLE_LIMITS.DESKTOP
} = {}) {
  const normalizedCount = clampInteger(
    count,
    0,
    REVIEW_CANVAS_PARTICLE_LIMITS.DESKTOP
  );
  const random = createSeededRandom(seed);
  return Array.from({ length: normalizedCount }, (_, index) => ({
    index,
    orbit: index % 3,
    lane: index % 4,
    angle: random() * TAU,
    phase: random(),
    radialOffset: (random() - 0.5) * 0.18,
    size: 0.72 + random() * 1.62,
    opacity: 0.32 + random() * 0.62,
    drift: 0.72 + random() * 0.7,
    direction: random() >= 0.5 ? 1 : -1
  }));
}

export function resolveReviewCanvasParticleLimit(width) {
  const normalizedWidth = finiteNumber(width, 0);
  if (normalizedWidth <= 480) return REVIEW_CANVAS_PARTICLE_LIMITS.MOBILE;
  if (normalizedWidth <= 1180) return REVIEW_CANVAS_PARTICLE_LIMITS.COMPACT;
  return REVIEW_CANVAS_PARTICLE_LIMITS.DESKTOP;
}

export function normalizeReviewCanvasDpr(value) {
  return normalizeCanvasDpr(value, { maxDpr: REVIEW_CANVAS_MAX_DPR });
}

export function resolveReviewCanvasRenderParameters(input = {}) {
  const stateCandidate = String(input.state || '').trim().toUpperCase();
  const state = motionByState[stateCandidate] ? stateCandidate : 'ANALYZING';
  const engineVisual = input.engineVisual === 'STANDARD_FLOW'
    ? 'STANDARD_FLOW'
    : 'AGENT_PARTICLE';
  const identityCandidate = String(input.engineIdentity || '').trim().toUpperCase();
  const engineIdentity = identityCandidate === 'FALLBACK'
    ? 'FALLBACK'
    : engineVisual === 'STANDARD_FLOW'
      ? 'STANDARD'
      : 'AGENT';
  const reducedMotion = Boolean(input.reducedMotion);
  const motion = motionByState[state];
  return Object.freeze({
    engineVisual,
    engineIdentity,
    state,
    currentStageId: safeStageId(input.currentStageId),
    reducedMotion,
    animated: animatedStates.has(state) && !reducedMotion,
    speed: reducedMotion ? 0 : motion.speed,
    intensity: motion.intensity,
    radialScale: motion.radialScale,
    flowDirection: motion.flowDirection
  });
}

export function createReviewCanvasController(options = {}) {
  let controller = null;
  try {
    controller = new ReviewCanvasController(options);
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

export function drawReviewCanvasFrame({
  context,
  width,
  height,
  dpr,
  particles,
  parameters,
  timestamp = 0
}) {
  const canvasWidth = finiteNumber(width, 0);
  const canvasHeight = finiteNumber(height, 0);
  if (!context || canvasWidth <= 0 || canvasHeight <= 0) return;

  const params = resolveReviewCanvasRenderParameters(parameters);
  const timeSeconds = params.reducedMotion
    ? 0
    : Math.max(0, finiteNumber(timestamp, 0)) / 1000;
  context.save();
  context.setTransform(normalizeReviewCanvasDpr(dpr), 0, 0, normalizeReviewCanvasDpr(dpr), 0, 0);
  context.clearRect(0, 0, canvasWidth, canvasHeight);
  if (params.engineVisual === 'STANDARD_FLOW') {
    drawStandardFlow(
      context,
      canvasWidth,
      canvasHeight,
      particles,
      params,
      timeSeconds
    );
  } else {
    drawAgentParticleCore(
      context,
      canvasWidth,
      canvasHeight,
      particles,
      params,
      timeSeconds
    );
  }
  context.restore();
}

class ReviewCanvasController {
  constructor(options) {
    this.canvas = options.canvas;
    this.container = options.container;
    this.onFailure = options.onFailure;
    this.environment = options.environment;
    this.runtime = null;
    this.lastRuntimeSnapshot = null;
    this.parameters = resolveReviewCanvasRenderParameters(options.parameters);
    this.particles = [];
    this.failed = false;
    this.disposed = false;
    this.handleRuntimeFailure = this.handleRuntimeFailure.bind(this);
  }

  initialize() {
    this.runtime = createCanvasRuntime({
      canvas: this.canvas,
      container: this.container,
      environment: this.environment,
      maxDpr: REVIEW_CANVAS_MAX_DPR,
      onResize: ({ width }) => {
        if (width <= 0) {
          this.particles = [];
          return;
        }
        const particleLimit = resolveReviewCanvasParticleLimit(width);
        if (this.particles.length !== particleLimit) {
          this.particles = createDeterministicParticleLayout({
            seed: REVIEW_CANVAS_SEED,
            count: particleLimit
          });
        }
      },
      onDraw: ({ context, width, height, dpr, timestamp }) => {
        drawReviewCanvasFrame({
          context,
          width,
          height,
          dpr,
          particles: this.particles,
          parameters: this.parameters,
          timestamp
        });
      },
      isAnimationEnabled: () => this.parameters.animated,
      onFailure: this.handleRuntimeFailure
    });
    return Boolean(this.runtime);
  }

  setRenderParameters(parameters) {
    if (this.disposed || this.failed) return;
    this.parameters = resolveReviewCanvasRenderParameters(parameters);
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
    this.particles = [];
  }

  getSnapshot() {
    const runtimeSnapshot = this.runtime?.getSnapshot() || this.lastRuntimeSnapshot || {};
    return {
      ...runtimeSnapshot,
      disposed: this.disposed || Boolean(runtimeSnapshot.disposed),
      failed: this.failed || Boolean(runtimeSnapshot.failed),
      particleCount: this.particles.length,
      frameCount: runtimeSnapshot.frameCount || 0,
      averageDrawMs: runtimeSnapshot.averageDrawMs || 0,
      maxDrawMs: runtimeSnapshot.maxDrawMs || 0,
      observerActive: Boolean(runtimeSnapshot.observerActive),
      listenerActive: Boolean(runtimeSnapshot.listenerActive)
    };
  }
}

function drawAgentParticleCore(context, width, height, particles, params, timeSeconds) {
  const centerX = width / 2;
  const centerY = height * 0.48;
  const scale = Math.min(width, height);
  const coreRadius = Math.max(18, scale * 0.075);
  const palette = {
    core: '#a897ff',
    edge: 'rgba(139, 124, 255, 0.32)',
    particle: '139, 124, 255',
    accent: '99, 215, 255'
  };
  const glow = context.createRadialGradient(
    centerX,
    centerY,
    coreRadius * 0.2,
    centerX,
    centerY,
    scale * 0.42
  );
  glow.addColorStop(0, `rgba(${palette.particle}, ${0.24 * params.intensity})`);
  glow.addColorStop(0.42, `rgba(${palette.accent}, ${0.08 * params.intensity})`);
  glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
  context.fillStyle = glow;
  context.fillRect(0, 0, width, height);

  context.lineWidth = 1;
  context.strokeStyle = palette.edge;
  for (let orbit = 0; orbit < 3; orbit += 1) {
    const radius = scale * (0.16 + orbit * 0.09) * params.radialScale;
    context.beginPath();
    context.ellipse(centerX, centerY, radius * 1.18, radius * 0.68, -0.18, 0, TAU);
    context.stroke();
  }

  context.globalCompositeOperation = 'lighter';
  for (const particle of particles) {
    const orbitRadius = scale
      * (0.16 + particle.orbit * 0.09 + particle.radialOffset)
      * params.radialScale;
    const angle = particle.angle
      + timeSeconds
        * params.speed
        * particle.drift
        * particle.direction
        * params.flowDirection;
    const x = centerX + Math.cos(angle) * orbitRadius * 1.18;
    const y = centerY + Math.sin(angle) * orbitRadius * 0.68;
    const opacity = particle.opacity * params.intensity;
    context.beginPath();
    context.fillStyle = particle.index % 7 === 0
      ? `rgba(${palette.accent}, ${opacity})`
      : `rgba(${palette.particle}, ${opacity})`;
    context.arc(x, y, particle.size, 0, TAU);
    context.fill();
  }

  const coreGlow = context.createRadialGradient(
    centerX,
    centerY,
    0,
    centerX,
    centerY,
    coreRadius * 2.3
  );
  coreGlow.addColorStop(0, 'rgba(235, 231, 255, 0.96)');
  coreGlow.addColorStop(0.28, 'rgba(168, 151, 255, 0.78)');
  coreGlow.addColorStop(1, 'rgba(139, 124, 255, 0)');
  context.fillStyle = coreGlow;
  context.beginPath();
  context.arc(centerX, centerY, coreRadius * 2.3, 0, TAU);
  context.fill();
  context.fillStyle = palette.core;
  context.beginPath();
  context.arc(centerX, centerY, coreRadius, 0, TAU);
  context.fill();
  context.globalCompositeOperation = 'source-over';
}

function drawStandardFlow(context, width, height, particles, params, timeSeconds) {
  const centerX = width / 2;
  const centerY = height * 0.48;
  const scale = Math.min(width, height);
  const inputX = width * 0.16;
  const outputX = width * 0.84;
  const nodeRadius = Math.max(16, scale * 0.065);
  const fallback = params.engineIdentity === 'FALLBACK';
  const primaryRgb = fallback ? '232, 156, 54' : '99, 215, 255';
  const secondaryRgb = fallback ? '255, 213, 157' : '128, 153, 255';

  const glow = context.createRadialGradient(
    centerX,
    centerY,
    nodeRadius,
    centerX,
    centerY,
    scale * 0.4
  );
  glow.addColorStop(0, `rgba(${primaryRgb}, ${0.18 * params.intensity})`);
  glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
  context.fillStyle = glow;
  context.fillRect(0, 0, width, height);

  context.lineWidth = 1.4;
  for (let lane = 0; lane < 3; lane += 1) {
    const offset = (lane - 1) * Math.max(22, height * 0.1);
    context.beginPath();
    context.moveTo(inputX, centerY + offset);
    context.bezierCurveTo(
      width * 0.32,
      centerY + offset,
      width * 0.36,
      centerY,
      centerX - nodeRadius,
      centerY
    );
    context.moveTo(centerX + nodeRadius, centerY);
    context.bezierCurveTo(
      width * 0.64,
      centerY,
      width * 0.68,
      centerY + offset,
      outputX,
      centerY + offset
    );
    context.strokeStyle = `rgba(${primaryRgb}, ${0.2 + lane * 0.06})`;
    context.stroke();
  }

  const flowParticles = particles.slice(0, REVIEW_CANVAS_PARTICLE_LIMITS.STANDARD);
  context.globalCompositeOperation = 'lighter';
  for (const particle of flowParticles) {
    const progress = moduloOne(
      particle.phase
      + timeSeconds * params.speed * 0.12 * particle.drift * params.flowDirection
    );
    const laneOffset = (particle.lane % 3 - 1) * Math.max(22, height * 0.1);
    const x = inputX + (outputX - inputX) * progress;
    const centerPull = Math.sin(progress * Math.PI);
    const y = centerY + laneOffset * (1 - centerPull);
    context.beginPath();
    context.fillStyle = `rgba(${particle.index % 5 === 0 ? secondaryRgb : primaryRgb}, ${particle.opacity * params.intensity})`;
    context.arc(x, y, particle.size + 0.3, 0, TAU);
    context.fill();
  }

  drawFlowNode(context, inputX, centerY, nodeRadius * 0.56, primaryRgb);
  drawFlowNode(context, centerX, centerY, nodeRadius, secondaryRgb);
  drawFlowNode(context, outputX, centerY, nodeRadius * 0.66, primaryRgb);
  context.globalCompositeOperation = 'source-over';
}

function drawFlowNode(context, x, y, radius, rgb) {
  context.beginPath();
  context.fillStyle = `rgba(${rgb}, 0.14)`;
  context.arc(x, y, radius * 1.8, 0, TAU);
  context.fill();
  context.beginPath();
  context.fillStyle = `rgba(${rgb}, 0.78)`;
  context.arc(x, y, radius, 0, TAU);
  context.fill();
}

function createSeededRandom(seed) {
  let value = Number(seed) >>> 0;
  return () => {
    value += 0x6d2b79f5;
    let result = value;
    result = Math.imul(result ^ (result >>> 15), result | 1);
    result ^= result + Math.imul(result ^ (result >>> 7), result | 61);
    return ((result ^ (result >>> 14)) >>> 0) / 4294967296;
  };
}

function safeStageId(value) {
  const text = String(value || '').trim().toLowerCase();
  return /^[a-z][a-z0-9-]{0,39}$/.test(text) ? text : null;
}

function clampInteger(value, min, max) {
  const number = Math.floor(finiteNumber(value, min));
  return Math.min(max, Math.max(min, number));
}

function finiteNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function moduloOne(value) {
  return ((value % 1) + 1) % 1;
}

function safelyNotifyFailure(callback) {
  try {
    callback?.();
  } catch {
    // A visual fallback callback must never affect Review state or polling.
  }
}
