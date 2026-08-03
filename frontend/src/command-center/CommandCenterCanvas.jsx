import { useEffect, useRef, useState } from 'react';

import {
  createPlatformRuntimeMapController,
  resolvePlatformRuntimeMapFallback
} from './platformRuntimeMapRenderer.js';


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
  const smallScreen = useSmallScreen();
  const [canvasReady, setCanvasReady] = useState(false);
  const [canvasFailed, setCanvasFailed] = useState(false);
  const shouldMountCanvas = !smallScreen && !canvasFailed;

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
    smallScreen,
    canvasFailed,
    canvasReady
  });
  const standardLane = map.lanes.find(lane => lane.zoneKey === 'standard');
  const agentLane = map.lanes.find(lane => lane.zoneKey === 'agent');

  return (
    <section
      className="command-center-runtime-map"
      data-zone-key={map.zoneKey}
      data-command-center-dom-overlay="true"
      data-command-center-canvas-fallback={fallbackReason || undefined}
      ref={containerRef}
      aria-label="AI Review Operation Map"
    >
      {shouldMountCanvas && (
        <canvas
          className="command-center-runtime-map-canvas"
          data-command-center-canvas-phase="EVOLUTION_PHASE_3A"
          ref={canvasRef}
          aria-hidden="true"
        />
      )}
      <div className="command-center-runtime-map-overlay">
        <QueueGate queueGate={map.queueGate} lanes={map.lanes} />
        <ReviewCore core={map.core} />
        <LaneStation
          lane={standardLane}
          visibleLimit={visibleLimit}
          onOpenReview={onOpenReview}
          onOpenOverflow={onOpenOverflow}
        />
        <LaneStation
          lane={agentLane}
          visibleLimit={visibleLimit}
          onOpenReview={onOpenReview}
          onOpenOverflow={onOpenOverflow}
        />
        <ResultBeacon beacon={map.resultBeacon} />
      </div>
    </section>
  );
}


function QueueGate({ queueGate, lanes }) {
  return (
    <article className="command-center-map-node command-center-queue-gate" data-zone-key={queueGate.zoneKey}>
      <div className="command-center-gate-hardware" aria-hidden="true">
        <span className="command-center-gate-pylon is-left" />
        <span className="command-center-gate-portal"><i /></span>
        <span className="command-center-gate-pylon is-right" />
      </div>
      <div className="command-center-zone-heading">
        <span className="command-center-zone-kicker">QUEUE GATE</span>
        <h2>Review 候场门</h2>
      </div>
      <div className="command-center-queue-summary">
        <strong>{queueGate.queuedCount}</strong>
        <span>条 Review 等待调度</span>
      </div>
      <div className="command-center-queue-split" aria-label="两条路线等待数">
        {lanes.map(lane => (
          <div key={lane.zoneKey} className={`is-${lane.colorToken}`}>
            <span>{lane.zoneKey === 'agent' ? 'Agent' : 'Standard'}</span>
            <strong>{lane.queuedCount}</strong>
          </div>
        ))}
      </div>
      <div className="command-center-next-reviews">
        {lanes.map(lane => <NextReview key={lane.zoneKey} lane={lane} />)}
      </div>
    </article>
  );
}


function ReviewCore({ core }) {
  return (
    <article className="command-center-map-node command-center-review-core" data-zone-key={core.zoneKey}>
      <span className="command-center-zone-kicker">SCHEDULING CORE</span>
      <div className="command-center-core-assembly" aria-hidden="true">
        <span className="command-center-core-ground" />
        <span className="command-center-core-outer-ring" />
        <span className="command-center-core-routing-ring">
          <i className="is-standard" />
          <i className="is-agent" />
        </span>
        <span className="command-center-core-crystal"><b>AI</b></span>
      </div>
      <h2>AI Review Core</h2>
      <p>统一接收并分流真实 Review</p>
      <div className="command-center-core-load">
        <strong>{core.runningCount}<small> / {core.capacity || '—'}</small></strong>
        <span>{core.utilizationPercent}% 平台占用</span>
      </div>
      <span className={`command-center-core-freshness is-${core.freshness.toLowerCase()}`}>
        {coreFreshnessLabel(core.freshness)}
      </span>
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


function LaneStation({ lane, visibleLimit, onOpenReview, onOpenOverflow }) {
  if (!lane) return null;
  const visibleItems = lane.runningItems.slice(0, visibleLimit);
  const hiddenCount = Math.max(0, lane.runningCount - visibleItems.length);
  return (
    <article className={`command-center-map-node command-center-lane-station is-${lane.colorToken}`} data-zone-key={lane.zoneKey}>
      <span className="command-center-lane-junction" aria-hidden="true" />
      <header>
        <div>
          <span className="command-center-zone-kicker">{lane.eyebrow} LANE</span>
          <h2>{lane.title}</h2>
          <p>{lane.description}</p>
        </div>
        <div className="command-center-lane-load" aria-label={`${lane.title}容量`}>
          <strong>{lane.runningCount}<small> / {lane.capacity || '—'}</small></strong>
          <span>{lane.utilizationPercent}% 占用 · 等待 {lane.queuedCount}</span>
        </div>
      </header>
      <CapacitySlots lane={lane} />
      <div className="command-center-lane-track">
        <span className="command-center-track-trench" aria-hidden="true" />
        <span className="command-center-track-roadbed" aria-hidden="true" />
        <span className="command-center-track-rail" aria-hidden="true" />
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
            <div className="command-center-lane-empty">路线当前空闲，等待下一次调度</div>
          )}
        </div>
      </div>
      {lane.zoneKey === 'agent' && <WorkerTowers workers={lane.workers} runningItems={lane.runningItems} />}
      <footer>
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
        <span key={index} className={index < lane.runningCount ? 'is-active' : ''}><i /></span>
      ))}
      {lane.capacity > displayedCapacity && <small>+{lane.capacity - displayedCapacity}</small>}
    </div>
  );
}


function WorkerTowers({ workers = [], runningItems = [] }) {
  if (workers.length === 0) return <div className="command-center-worker-empty">当前无 Worker 状态快照</div>;
  return (
    <div className="command-center-worker-towers" aria-label="Agent Worker 状态">
      {workers.slice(0, 8).map(worker => {
        const runningItem = runningItems.find(item => (
          (worker.workerId && item.workerId === worker.workerId)
          || (worker.activeJobId && String(item.jobId) === String(worker.activeJobId))
        ));
        return (
          <div key={worker.workerId} className={`is-${workerState(worker).toLowerCase()}`}>
            <span className="command-center-worker-spire" aria-hidden="true"><i /></span>
            <span className="command-center-worker-label">
              <strong>{worker.workerId || 'Worker'}</strong>
              <small>{runningItem ? `${workerState(worker)} · ${runningItem.projectName}` : workerState(worker)}</small>
            </span>
          </div>
        );
      })}
      {workers.length > 8 && <em>+{workers.length - 8} Worker</em>}
    </div>
  );
}


function ResultBeacon({ beacon }) {
  return (
    <article className="command-center-map-node command-center-result-beacon" data-zone-key={beacon.zoneKey}>
      <span className="command-center-zone-kicker">RESULT BEACON</span>
      <div className="command-center-result-platform" aria-hidden="true">
        <span className="command-center-result-merge-ring" />
        <span className="command-center-result-emblem"><i>✓</i></span>
      </div>
      <h2>{beacon.title}</h2>
      <p>{beacon.description}</p>
      <small>STRUCTURAL ENDPOINT</small>
    </article>
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
      <span className="command-center-review-tower" aria-hidden="true"><i /></span>
      <span className="command-center-review-label">
        <strong>{item.projectName}</strong>
        <span>{item.displayName}</span>
        <small>{item.providerModelLabel}</small>
        <em>{item.stageLabel}</em>
      </span>
    </button>
  );
}


function useSmallScreen() {
  const [smallScreen, setSmallScreen] = useState(readSmallScreen);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
    const query = window.matchMedia(SMALL_SCREEN_QUERY);
    const sync = () => setSmallScreen(query.matches);
    query.addEventListener?.('change', sync);
    sync();
    return () => query.removeEventListener?.('change', sync);
  }, []);
  return smallScreen;
}


function readSmallScreen() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(SMALL_SCREEN_QUERY).matches;
}


function workerState(worker) {
  if (!worker.online) return 'OFFLINE';
  return String(worker.state || 'IDLE').toUpperCase();
}


function coreFreshnessLabel(value) {
  return {
    FRESH: 'Runtime 实时',
    STALE: 'Runtime 已过期',
    EMPTY: '等待 Runtime 快照'
  }[value] || 'Runtime 状态未知';
}
