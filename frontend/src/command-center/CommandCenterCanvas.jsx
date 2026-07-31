import { useEffect, useRef, useState } from 'react';

import CommandCenterTopology from './CommandCenterTopology.jsx';
import {
  createCommandCenterCanvasController,
  resolveCommandCenterCanvasFallback
} from './commandCenterCanvasRenderer.js';


const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';
const SMALL_SCREEN_QUERY = '(max-width: 700px)';


export default function CommandCenterCanvas({ topology }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const controllerRef = useRef(null);
  const preferences = useCanvasPreferences();
  const [canvasReady, setCanvasReady] = useState(false);
  const [canvasFailed, setCanvasFailed] = useState(false);
  const shouldMountCanvas = (
    !preferences.reducedMotion
    && !preferences.smallScreen
    && !canvasFailed
  );

  useEffect(() => {
    if (!shouldMountCanvas || !canvasRef.current || !containerRef.current) {
      setCanvasReady(false);
      return undefined;
    }

    const controller = createCommandCenterCanvasController({
      canvas: canvasRef.current,
      container: containerRef.current,
      scene: topology.scene,
      onFailure: () => setCanvasFailed(true)
    });
    if (!controller) {
      setCanvasFailed(true);
      return undefined;
    }

    controllerRef.current = controller;
    setCanvasReady(true);
    return () => {
      controller.dispose();
      if (controllerRef.current === controller) controllerRef.current = null;
      setCanvasReady(false);
    };
  }, [shouldMountCanvas]);

  useEffect(() => {
    controllerRef.current?.setScene(topology.scene);
  }, [topology.scene]);

  const canvasActive = shouldMountCanvas && canvasReady;
  const fallbackReason = resolveCommandCenterCanvasFallback({
    ...preferences,
    canvasFailed,
    canvasReady
  });

  return (
    <CommandCenterTopology
      topology={topology}
      canvasActive={canvasActive}
      canvasContainerRef={containerRef}
      fallbackReason={fallbackReason}
      canvasLayer={shouldMountCanvas ? (
        <canvas
          className="command-center-topology-canvas"
          ref={canvasRef}
          aria-hidden="true"
        />
      ) : null}
    />
  );
}


function useCanvasPreferences() {
  const [preferences, setPreferences] = useState(() => readCanvasPreferences());

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const reducedMotionQuery = window.matchMedia(REDUCED_MOTION_QUERY);
    const smallScreenQuery = window.matchMedia(SMALL_SCREEN_QUERY);
    const syncPreferences = () => {
      setPreferences({
        reducedMotion: reducedMotionQuery.matches,
        smallScreen: smallScreenQuery.matches
      });
    };

    addMediaListener(reducedMotionQuery, syncPreferences);
    addMediaListener(smallScreenQuery, syncPreferences);
    syncPreferences();
    return () => {
      removeMediaListener(reducedMotionQuery, syncPreferences);
      removeMediaListener(smallScreenQuery, syncPreferences);
    };
  }, []);

  return preferences;
}


function readCanvasPreferences() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return { reducedMotion: false, smallScreen: false };
  }
  return {
    reducedMotion: window.matchMedia(REDUCED_MOTION_QUERY).matches,
    smallScreen: window.matchMedia(SMALL_SCREEN_QUERY).matches
  };
}


function addMediaListener(query, listener) {
  if (typeof query.addEventListener === 'function') {
    query.addEventListener('change', listener);
  } else {
    query.addListener?.(listener);
  }
}


function removeMediaListener(query, listener) {
  if (typeof query.removeEventListener === 'function') {
    query.removeEventListener('change', listener);
  } else {
    query.removeListener?.(listener);
  }
}
