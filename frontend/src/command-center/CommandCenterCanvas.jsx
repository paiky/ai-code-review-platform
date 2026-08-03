import { useEffect, useRef, useState } from 'react';

import {
  createPlatformRuntimeMapController,
  resolvePlatformRuntimeMapFallback
} from './platformRuntimeMapRenderer.js';


const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';
const SMALL_SCREEN_QUERY = '(max-width: 700px)';


export default function CommandCenterCanvas({
  map,
  visibleLimit,
  onOpenReview,
  onOpenOverflow
}) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const controllerRef = useRef(null);
  const preferences = useCanvasPreferences();
  const [canvasReady, setCanvasReady] = useState(false);
  const [canvasFailed, setCanvasFailed] = useState(false);
  const shouldMountCanvas = !preferences.reducedMotion && !preferences.smallScreen && !canvasFailed;

  useEffect(() => {
    if (!shouldMountCanvas || !canvasRef.current || !containerRef.current) {
      setCanvasReady(false);
      return undefined;
    }
    const controller = createPlatformRuntimeMapController({
      canvas: canvasRef.current,
      container: containerRef.current,
      scene: map.scene,
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
    controllerRef.current?.setScene(map.scene);
  }, [map.scene]);

  const fallbackReason = resolvePlatformRuntimeMapFallback({
    ...preferences,
    canvasFailed,
    canvasReady
  });

  return (
    <section
      className="command-center-runtime-map"
      data-command-center-dom-overlay="true"
      data-command-center-canvas-fallback={fallbackReason || undefined}
      ref={containerRef}
      aria-label="平台 Review 运行地图"
    >
      {shouldMountCanvas && (
        <canvas
          className="command-center-runtime-map-canvas"
          data-command-center-canvas-phase="PHASE_5C"
          ref={canvasRef}
          aria-hidden="true"
        />
      )}
      <div className="command-center-runtime-map-overlay">
        <QueueCamp queue={map.queue} lanes={map.lanes} />
        {map.lanes.map(lane => (
          <LaneBase
            key={lane.zoneKey}
            lane={lane}
            visibleLimit={visibleLimit}
            onOpenReview={onOpenReview}
            onOpenOverflow={onOpenOverflow}
          />
        ))}
      </div>
    </section>
  );
}


function QueueCamp({ queue, lanes }) {
  return (
    <article className="command-center-queue-camp" data-zone-key={queue.zoneKey}>
      <span className="command-center-zone-kicker">SHARED STAGING AREA</span>
      <h2>Review 候场区</h2>
      <strong className="command-center-queue-total">{queue.queuedCount}</strong>
      <span className="command-center-queue-caption">条 Review 等待调度</span>
      <div className="command-center-queue-split" aria-label="两条路线等待数">
        {lanes.map(lane => (
          <div key={lane.zoneKey} className={`is-${lane.colorToken}`}>
            <span>{lane.zoneKey === 'agent' ? 'Agent' : 'Standard'}</span>
            <strong>{lane.queuedCount}</strong>
          </div>
        ))}
      </div>
      <div className="command-center-next-reviews">
        {lanes.map(lane => (
          <NextReview key={lane.zoneKey} lane={lane} />
        ))}
      </div>
    </article>
  );
}


function NextReview({ lane }) {
  const item = lane.nextQueued;
  return (
    <div className={`command-center-next-review is-${lane.colorToken}`}>
      <span>{lane.zoneKey === 'agent' ? 'Agent' : 'Standard'} 下一条</span>
      {item ? (
        <>
          <strong>{item.projectName}</strong>
          <small>{item.displayName} · {item.providerModelLabel}</small>
        </>
      ) : (
        <small>{lane.queuedCount > 0 ? 'Runtime v1 不提供顺序' : '当前无等待 Review'}</small>
      )}
    </div>
  );
}


function LaneBase({ lane, visibleLimit, onOpenReview, onOpenOverflow }) {
  const visibleItems = lane.runningItems.slice(0, visibleLimit);
  const hiddenCount = Math.max(0, lane.runningCount - visibleItems.length);
  return (
    <article className={`command-center-lane-base is-${lane.colorToken}`} data-zone-key={lane.zoneKey}>
      <header>
        <div>
          <span className="command-center-zone-kicker">{lane.eyebrow}</span>
          <h2>{lane.title}</h2>
          <p>{lane.description}</p>
        </div>
        <div className="command-center-lane-load" aria-label={`${lane.title}容量`}>
          <strong>{lane.runningCount}<small> / {lane.capacity || '—'}</small></strong>
          <span>{lane.utilizationPercent}% 占用</span>
        </div>
      </header>
      <CapacitySlots lane={lane} />
      <div className="command-center-running-items" aria-label={`${lane.title}运行中 Review`}>
        {visibleItems.map(item => (
          <ReviewMarker key={`${item.jobId}:${item.taskId}:${item.reviewKey}`} item={item} onOpen={onOpenReview} />
        ))}
        {hiddenCount > 0 && (
          <button
            type="button"
            className="command-center-overflow-tower"
            onClick={event => onOpenOverflow(lane, event.currentTarget)}
            aria-label={`查看${lane.title}另外 ${hiddenCount} 条运行 Review`}
          >
            <strong>+{hiddenCount}</strong>
            <span>全部运行项</span>
          </button>
        )}
        {lane.runningCount === 0 && (
          <div className="command-center-lane-empty">基地当前空闲，等待下一次调度</div>
        )}
      </div>
      <footer>
        <span>{lane.queuedCount} 条在前方队列</span>
        <span>{lane.zoneKey === 'agent' ? `${lane.capacity} 在线 Worker Capacity` : '共享 Provider Scheduler'}</span>
      </footer>
    </article>
  );
}


function CapacitySlots({ lane }) {
  const displayedCapacity = Math.min(Math.max(lane.capacity, lane.runningCount, 1), 10);
  return (
    <div className="command-center-capacity-slots" aria-hidden="true">
      {Array.from({ length: displayedCapacity }, (_, index) => (
        <span key={index} className={index < lane.runningCount ? 'is-active' : ''} />
      ))}
      {lane.capacity > displayedCapacity && <small>+{lane.capacity - displayedCapacity}</small>}
    </div>
  );
}


function ReviewMarker({ item, onOpen }) {
  return (
    <button
      type="button"
      className={`command-center-review-marker is-${item.engineToken}`}
      onClick={() => onOpen(item)}
      aria-label={`查看 ${item.projectName} 的 ${item.displayName}`}
    >
      <span className="command-center-review-beacon" aria-hidden="true" />
      <strong>{item.projectName}</strong>
      <span>{item.displayName}</span>
      <small>{item.providerModelLabel}</small>
      <em>{item.stageLabel}</em>
    </button>
  );
}


function useCanvasPreferences() {
  const [preferences, setPreferences] = useState(readCanvasPreferences);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
    const reduced = window.matchMedia(REDUCED_MOTION_QUERY);
    const small = window.matchMedia(SMALL_SCREEN_QUERY);
    const sync = () => setPreferences({ reducedMotion: reduced.matches, smallScreen: small.matches });
    reduced.addEventListener?.('change', sync);
    small.addEventListener?.('change', sync);
    sync();
    return () => {
      reduced.removeEventListener?.('change', sync);
      small.removeEventListener?.('change', sync);
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
