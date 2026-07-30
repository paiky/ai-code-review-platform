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
  return Math.min(
    REVIEW_CANVAS_MAX_DPR,
    Math.max(1, finiteNumber(value, 1))
  );
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
    controller.initialize();
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
    this.environment = normalizeEnvironment(options.environment);
    this.context = null;
    this.observer = null;
    this.rafId = null;
    this.parameters = resolveReviewCanvasRenderParameters(options.parameters);
    this.particles = [];
    this.width = 0;
    this.height = 0;
    this.dpr = 1;
    this.frameCount = 0;
    this.totalDrawMs = 0;
    this.maxDrawMs = 0;
    this.failed = false;
    this.disposed = false;
    this.listenerActive = false;
    this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
    this.handleResize = this.handleResize.bind(this);
    this.handleAnimationFrame = this.handleAnimationFrame.bind(this);
  }

  initialize() {
    if (!this.canvas || !this.container) {
      throw new Error('canvas target unavailable');
    }
    this.context = this.canvas.getContext?.('2d', { alpha: true });
    if (!this.context) throw new Error('canvas context unavailable');
    if (!this.environment.ResizeObserverCtor) {
      throw new Error('resize observer unavailable');
    }
    if (!this.environment.requestFrame || !this.environment.cancelFrame) {
      throw new Error('animation frame unavailable');
    }

    this.observer = new this.environment.ResizeObserverCtor(this.handleResize);
    this.observer.observe(this.container);
    this.environment.documentTarget?.addEventListener?.(
      'visibilitychange',
      this.handleVisibilityChange
    );
    this.listenerActive = Boolean(
      this.environment.documentTarget?.addEventListener
    );
    this.applySize(this.container.getBoundingClientRect?.());
  }

  setRenderParameters(parameters) {
    if (this.disposed || this.failed) return;
    this.parameters = resolveReviewCanvasRenderParameters(parameters);
    if (!this.hasValidSize() || this.isDocumentHidden()) {
      this.stopLoop();
      return;
    }
    this.drawCurrentFrame(this.environment.now());
    this.syncLoop();
  }

  handleResize(entries = []) {
    if (this.disposed || this.failed) return;
    const matchingEntry = entries.find(entry => entry?.target === this.container);
    this.applySize(
      matchingEntry?.contentRect || this.container.getBoundingClientRect?.()
    );
  }

  handleVisibilityChange() {
    if (this.disposed || this.failed) return;
    if (this.isDocumentHidden()) {
      this.stopLoop();
      return;
    }
    if (this.hasValidSize()) {
      this.drawCurrentFrame(this.environment.now());
      this.syncLoop();
    }
  }

  handleAnimationFrame(timestamp) {
    this.rafId = null;
    if (this.disposed || this.failed || !this.shouldAnimate()) return;
    this.drawCurrentFrame(timestamp);
    this.scheduleFrame();
  }

  applySize(rect) {
    if (this.disposed || this.failed) return;
    const width = finiteNumber(rect?.width, 0);
    const height = finiteNumber(rect?.height, 0);
    if (width <= 0 || height <= 0) {
      this.width = 0;
      this.height = 0;
      this.particles = [];
      this.stopLoop();
      return;
    }

    try {
      const dpr = normalizeReviewCanvasDpr(this.environment.getDevicePixelRatio());
      const nextWidth = Math.max(1, Math.round(width * dpr));
      const nextHeight = Math.max(1, Math.round(height * dpr));
      const particleLimit = resolveReviewCanvasParticleLimit(width);
      if (this.canvas.width !== nextWidth) this.canvas.width = nextWidth;
      if (this.canvas.height !== nextHeight) this.canvas.height = nextHeight;
      this.width = width;
      this.height = height;
      this.dpr = dpr;
      if (this.particles.length !== particleLimit) {
        this.particles = createDeterministicParticleLayout({
          seed: REVIEW_CANVAS_SEED,
          count: particleLimit
        });
      }
      if (!this.isDocumentHidden()) {
        this.drawCurrentFrame(this.environment.now());
      }
      this.syncLoop();
    } catch {
      this.fail();
    }
  }

  drawCurrentFrame(timestamp) {
    if (this.disposed || this.failed || !this.hasValidSize()) return;
    const startedAt = this.environment.now();
    try {
      drawReviewCanvasFrame({
        context: this.context,
        width: this.width,
        height: this.height,
        dpr: this.dpr,
        particles: this.particles,
        parameters: this.parameters,
        timestamp
      });
      const drawMs = Math.max(0, this.environment.now() - startedAt);
      this.frameCount += 1;
      this.totalDrawMs += drawMs;
      this.maxDrawMs = Math.max(this.maxDrawMs, drawMs);
    } catch {
      this.fail();
    }
  }

  syncLoop() {
    if (this.shouldAnimate()) {
      this.scheduleFrame();
    } else {
      this.stopLoop();
    }
  }

  shouldAnimate() {
    return (
      !this.disposed
      && !this.failed
      && this.hasValidSize()
      && !this.isDocumentHidden()
      && this.parameters.animated
    );
  }

  scheduleFrame() {
    if (this.rafId !== null || !this.shouldAnimate()) return;
    this.rafId = this.environment.requestFrame(this.handleAnimationFrame);
  }

  stopLoop() {
    if (this.rafId === null) return;
    this.environment.cancelFrame(this.rafId);
    this.rafId = null;
  }

  hasValidSize() {
    return this.width > 0 && this.height > 0;
  }

  isDocumentHidden() {
    const target = this.environment.documentTarget;
    return target?.hidden === true || target?.visibilityState === 'hidden';
  }

  fail() {
    if (this.failed || this.disposed) return;
    this.failed = true;
    this.cleanupRuntime();
    safelyNotifyFailure(this.onFailure);
  }

  cleanupRuntime() {
    this.stopLoop();
    this.observer?.disconnect?.();
    this.observer = null;
    if (this.listenerActive) {
      this.environment.documentTarget?.removeEventListener?.(
        'visibilitychange',
        this.handleVisibilityChange
      );
      this.listenerActive = false;
    }
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.cleanupRuntime();
    this.context = null;
    this.canvas = null;
    this.container = null;
    this.particles = [];
  }

  getSnapshot() {
    return {
      disposed: this.disposed,
      failed: this.failed,
      running: this.rafId !== null,
      width: this.width,
      height: this.height,
      dpr: this.dpr,
      particleCount: this.particles.length,
      frameCount: this.frameCount,
      averageDrawMs: this.frameCount > 0 ? this.totalDrawMs / this.frameCount : 0,
      maxDrawMs: this.maxDrawMs,
      observerActive: Boolean(this.observer),
      listenerActive: this.listenerActive
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

function normalizeEnvironment(environment = {}) {
  const root = typeof window === 'undefined' ? globalThis : window;
  const documentTarget = environment.documentTarget
    || (typeof document === 'undefined' ? null : document);
  const requestFrame = environment.requestFrame
    || root.requestAnimationFrame?.bind(root);
  const cancelFrame = environment.cancelFrame
    || root.cancelAnimationFrame?.bind(root);
  return {
    documentTarget,
    ResizeObserverCtor: environment.ResizeObserverCtor || root.ResizeObserver,
    requestFrame,
    cancelFrame,
    getDevicePixelRatio: environment.getDevicePixelRatio || (() => root.devicePixelRatio || 1),
    now: environment.now || (() => root.performance?.now?.() ?? Date.now())
  };
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
