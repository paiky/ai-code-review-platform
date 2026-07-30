import { useEffect, useRef, useState } from 'react';
import { createReviewCanvasController } from './reviewCanvasRenderer.js';

export default function ReviewImmersiveCanvas({
  presentation,
  reducedMotion,
  fallback
}) {
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const controllerRef = useRef(null);
  const mountedRef = useRef(false);
  const [failed, setFailed] = useState(false);
  const diagnostics = controllerRef.current?.getSnapshot();

  useEffect(() => {
    mountedRef.current = true;
    const controller = createReviewCanvasController({
      canvas: canvasRef.current,
      container: containerRef.current,
      parameters: {
        engineVisual: presentation.engineVisual,
        engineIdentity: presentation.engineIdentity,
        state: presentation.heroState,
        currentStageId: presentation.currentStageId,
        reducedMotion
      },
      onFailure: () => {
        if (mountedRef.current) setFailed(true);
      }
    });
    controllerRef.current = controller;
    if (!controller) setFailed(true);
    return () => {
      mountedRef.current = false;
      controller?.dispose();
      controllerRef.current = null;
    };
  }, []);

  useEffect(() => {
    controllerRef.current?.setRenderParameters({
      engineVisual: presentation.engineVisual,
      engineIdentity: presentation.engineIdentity,
      state: presentation.heroState,
      currentStageId: presentation.currentStageId,
      reducedMotion
    });
  }, [
    presentation.engineVisual,
    presentation.engineIdentity,
    presentation.heroState,
    presentation.currentStageId,
    reducedMotion
  ]);

  if (failed) {
    return (
      <div className="review-immersive-canvas-fallback" data-review-canvas-fallback="true">
        {fallback}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="review-immersive-canvas-shell"
      data-review-canvas-identity={presentation.engineIdentity}
      data-review-canvas-running={diagnostics ? String(diagnostics.running) : undefined}
      data-review-canvas-frame-count={diagnostics?.frameCount}
      data-review-canvas-average-draw-ms={diagnostics?.averageDrawMs}
      data-review-canvas-max-draw-ms={diagnostics?.maxDrawMs}
      data-review-canvas-particle-count={diagnostics?.particleCount}
      data-review-canvas-dpr={diagnostics?.dpr}
      data-review-canvas-observer-active={diagnostics ? String(diagnostics.observerActive) : undefined}
      data-review-canvas-listener-active={diagnostics ? String(diagnostics.listenerActive) : undefined}
    >
      <canvas
        ref={canvasRef}
        className="review-immersive-canvas"
        role="img"
        aria-label={presentation.ariaLabel}
      />
    </div>
  );
}
