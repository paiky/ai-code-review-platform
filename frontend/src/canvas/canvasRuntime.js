export const CANVAS_RUNTIME_DEFAULT_MAX_DPR = 2;


export function createCanvasRuntime(options = {}) {
  let runtime = null;
  try {
    runtime = new CanvasRuntime(options);
    runtime.initialize();
    return runtime;
  } catch {
    runtime?.dispose();
    safelyNotifyFailure(options.onFailure);
    return null;
  }
}


export function normalizeCanvasDpr(
  value,
  { maxDpr = CANVAS_RUNTIME_DEFAULT_MAX_DPR } = {}
) {
  const normalizedMax = Math.max(1, finiteNumber(maxDpr, 1));
  return Math.min(normalizedMax, Math.max(1, finiteNumber(value, 1)));
}


class CanvasRuntime {
  constructor(options) {
    this.canvas = options.canvas;
    this.container = options.container;
    this.onDraw = options.onDraw;
    this.onResize = options.onResize;
    this.isAnimationEnabled = options.isAnimationEnabled;
    this.onFailure = options.onFailure;
    this.maxDpr = options.maxDpr;
    this.contextOptions = options.contextOptions || { alpha: true };
    this.environment = normalizeCanvasEnvironment(options.environment);
    this.context = null;
    this.observer = null;
    this.rafId = null;
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
    this.context = this.canvas.getContext?.('2d', this.contextOptions);
    if (!this.context) throw new Error('canvas context unavailable');
    if (typeof this.onDraw !== 'function') {
      throw new Error('canvas draw callback unavailable');
    }
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

  refresh() {
    if (this.disposed || this.failed) return;
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
    this.refresh();
  }

  handleAnimationFrame(timestamp) {
    this.rafId = null;
    if (this.disposed || this.failed || !this.shouldAnimate()) return;
    this.drawCurrentFrame(timestamp);
    this.scheduleFrame();
  }

  applySize(rect) {
    if (this.disposed || this.failed) return;
    try {
      const width = finiteNumber(rect?.width, 0);
      const height = finiteNumber(rect?.height, 0);
      if (width <= 0 || height <= 0) {
        this.width = 0;
        this.height = 0;
        this.onResize?.({
          context: this.context,
          canvas: this.canvas,
          width: 0,
          height: 0,
          dpr: this.dpr
        });
        this.stopLoop();
        return;
      }

      const dpr = normalizeCanvasDpr(
        this.environment.getDevicePixelRatio(),
        { maxDpr: this.maxDpr }
      );
      const nextWidth = Math.max(1, Math.round(width * dpr));
      const nextHeight = Math.max(1, Math.round(height * dpr));
      if (this.canvas.width !== nextWidth) this.canvas.width = nextWidth;
      if (this.canvas.height !== nextHeight) this.canvas.height = nextHeight;
      this.width = width;
      this.height = height;
      this.dpr = dpr;
      this.onResize?.({
        context: this.context,
        canvas: this.canvas,
        width,
        height,
        dpr
      });
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
      this.onDraw({
        context: this.context,
        canvas: this.canvas,
        width: this.width,
        height: this.height,
        dpr: this.dpr,
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
      && this.isAnimationEnabled?.() === true
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
    this.onDraw = null;
    this.onResize = null;
    this.isAnimationEnabled = null;
  }

  getSnapshot() {
    return {
      disposed: this.disposed,
      failed: this.failed,
      running: this.rafId !== null,
      width: this.width,
      height: this.height,
      dpr: this.dpr,
      frameCount: this.frameCount,
      averageDrawMs: this.frameCount > 0 ? this.totalDrawMs / this.frameCount : 0,
      maxDrawMs: this.maxDrawMs,
      observerActive: Boolean(this.observer),
      listenerActive: this.listenerActive
    };
  }
}


function normalizeCanvasEnvironment(environment = {}) {
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
    getDevicePixelRatio: environment.getDevicePixelRatio
      || (() => root.devicePixelRatio || 1),
    now: environment.now || (() => root.performance?.now?.() ?? Date.now())
  };
}


function finiteNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}


function safelyNotifyFailure(callback) {
  try {
    callback?.();
  } catch {
    // Canvas failure must remain local to its fallback boundary.
  }
}
