export default function CommandCenterCanvas({
  presentation,
  runtimeLoading,
  onOpenReview,
  onOpenOverflow,
  onOpenResult
}) {
  const {
    intake,
    engineSelection,
    agentLane,
    standardLane,
    fallback,
    resultPersistence
  } = presentation;

  return (
    <section
      className="command-center-runtime-map"
      aria-label="AI Review 当前执行拓扑"
      data-command-center-renderer="DOM_SVG_STATIC"
      data-command-center-canvas-mounted="false"
    >
      <svg
        className="command-center-static-connections"
        viewBox="0 0 1200 440"
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <marker id="cc-arrow-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#2787f5" />
          </marker>
          <marker id="cc-arrow-agent" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#6f3df4" />
          </marker>
          <marker id="cc-arrow-standard" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#f07818" />
          </marker>
        </defs>
        <path className="is-intake" d="M 154 220 H 238" markerEnd="url(#cc-arrow-blue)" />
        <path className="is-agent" d="M 390 220 C 430 220 422 104 476 104" markerEnd="url(#cc-arrow-agent)" />
        <path className="is-standard" d="M 390 220 C 430 220 422 336 476 336" markerEnd="url(#cc-arrow-standard)" />
        <path className="is-agent" d="M 995 104 C 1038 104 1028 220 1064 220" markerEnd="url(#cc-arrow-agent)" />
        <path className="is-standard" d="M 995 336 C 1038 336 1028 220 1064 220" markerEnd="url(#cc-arrow-standard)" />
        <path className="is-fallback" d="M 744 194 C 744 220 780 220 780 246" markerEnd="url(#cc-arrow-standard)" />
      </svg>

      <div className="command-center-map-grid">
        <ReviewIntake intake={intake} />
        <EngineSelection engineSelection={engineSelection} />
        <ReviewModule
          lane={agentLane}
          runtimeLoading={runtimeLoading}
          onOpenReview={onOpenReview}
          onOpenOverflow={onOpenOverflow}
        />
        <FallbackRelation fallback={fallback} />
        <ReviewModule
          lane={standardLane}
          runtimeLoading={runtimeLoading}
          onOpenReview={onOpenReview}
          onOpenOverflow={onOpenOverflow}
        />
        <ResultPersistence resultPersistence={resultPersistence} onOpen={onOpenResult} />
      </div>
    </section>
  );
}


function ReviewIntake({ intake }) {
  return (
    <article className="command-center-intake command-center-map-node" data-zone-key={intake.zoneKey}>
      <NodeHeading eyebrow="TRIGGER INPUT" title={intake.title} subtitle="触发入口" />
      <div className="command-center-intake-list">
        {intake.items.map(item => (
          <div key={item.key} className={`command-center-intake-item is-${item.key.toLowerCase()}`}>
            <span aria-hidden="true">{intakeIcon(item.key)}</span>
            <span>
              <strong>{item.label}</strong>
              <small>{item.description}</small>
            </span>
          </div>
        ))}
      </div>
    </article>
  );
}


function EngineSelection({ engineSelection }) {
  return (
    <article className="command-center-engine command-center-map-node" data-zone-key={engineSelection.zoneKey}>
      <div className="command-center-engine-ring" aria-hidden="true">
        <i />
        <b>AI</b>
      </div>
      <NodeHeading eyebrow="POLICY ROUTER" title={engineSelection.title} subtitle="策略路由 · 可用性检查 · 安全门禁" />
      <div className="command-center-engine-routes">
        {engineSelection.routes.map(route => (
          <span key={route.key} className={`is-${route.key.toLowerCase()}`}>
            <i aria-hidden="true" />
            {route.label}
          </span>
        ))}
      </div>
      <p>{engineSelection.automaticAgentUnavailableDescription}</p>
    </article>
  );
}


function ReviewModule({ lane, runtimeLoading, onOpenReview, onOpenOverflow }) {
  const isAgent = lane.engine === 'AGENT';
  const nextQueued = lane.nextQueued;
  const observedProvider = lane.providers[0];
  return (
    <article
      className={`command-center-review-module is-${lane.colorToken} command-center-map-node`}
      data-zone-key={lane.zoneKey}
    >
      <header>
        <span className="command-center-module-icon" aria-hidden="true">{isAgent ? '⌘' : '▤'}</span>
        <span>
          <small>{lane.eyebrow}</small>
          <h2>{lane.title}</h2>
          <p>{lane.description}</p>
        </span>
        <em>{runtimeLoading ? '同步中' : '当前快照'}</em>
      </header>

      <div className="command-center-module-metrics">
        <ModuleMetric label="Queued Jobs" value={lane.queued} />
        <ModuleMetric label="Running Jobs" value={lane.running} />
        {isAgent ? (
          <ModuleMetric label="Online Capacity" value={lane.onlineCapacity || '—'} />
        ) : (
          <ModuleMetric label="Provider Slots" value={`${lane.running} / ${lane.capacity || '—'}`} />
        )}
        {isAgent ? (
          <WorkerSummary summary={lane.workerSummary} />
        ) : (
          <ModuleMetric
            label="Observed Provider / Model"
            value={observedProvider?.label || '暂无活跃 Provider'}
            compact
          />
        )}
        <ModuleMetric
          label="Next Queued"
          value={nextQueued ? nextQueued.displayName : '当前无等待 Review'}
          detail={nextQueued ? nextQueued.projectName : null}
          compact
        />
        <RunningItems
          lane={lane}
          onOpenReview={onOpenReview}
          onOpenOverflow={onOpenOverflow}
        />
      </div>
    </article>
  );
}


function ModuleMetric({ label, value, detail, compact = false }) {
  return (
    <div className={`command-center-module-metric${compact ? ' is-compact' : ''}`}>
      <small>{label}</small>
      <strong>{value}</strong>
      {detail && <em>{detail}</em>}
    </div>
  );
}


function WorkerSummary({ summary }) {
  const rows = [
    ['IDLE', summary?.idle || 0],
    ['BUSY', summary?.busy || 0],
    ['DRAINING', summary?.draining || 0],
    ['OFFLINE', summary?.offline || 0]
  ];
  return (
    <div className="command-center-module-metric is-worker-summary">
      <small>Worker Summary</small>
      <span>
        {rows.map(([label, value]) => (
          <i key={label} className={`is-${label.toLowerCase()}`}>
            <b aria-hidden="true" />{label}<em>{value}</em>
          </i>
        ))}
      </span>
    </div>
  );
}


function RunningItems({ lane, onOpenReview, onOpenOverflow }) {
  const visibleItems = lane.runningItems.slice(0, 4);
  const visible = visibleItems.length;
  const total = lane.totalRunningItemCount;
  const hasOverflow = lane.runningItems.length > visible
    || lane.runningItemsTruncated
    || total > visible;
  return (
    <div className="command-center-module-metric is-running-items">
      <small>Running Items</small>
      <strong>显示 {visible} / 共 {total}</strong>
      <span className="command-center-running-markers" aria-label={`当前展示 ${visible} 个，共 ${total} 个运行项`}>
        {visibleItems.map(item => (
          item.navigationTarget ? (
            <button
              key={item.motionIdentity}
              type="button"
              className="command-center-running-marker"
              data-command-center-action="open-running-review"
              data-review-identity={item.motionIdentity}
              title={`${item.projectName} · ${item.displayName} · ${item.stageLabel}`}
              aria-label={`打开 ${item.projectName} 的 ${item.displayName}`}
              onClick={() => onOpenReview(item)}
            />
          ) : (
            <i key={item.motionIdentity} className="command-center-running-marker is-disabled" />
          )
        ))}
      </span>
      {hasOverflow && (
        <button
          type="button"
          className="command-center-running-overflow"
          data-command-center-action={`open-${lane.engine.toLowerCase()}-overflow`}
          onClick={event => onOpenOverflow(lane, event.currentTarget)}
          aria-label={`查看 ${lane.title} 运行项列表`}
        >
          查看运行项
        </button>
      )}
    </div>
  );
}


function FallbackRelation({ fallback }) {
  return (
    <aside className="command-center-fallback" aria-label="Agent 到 Standard 的结构性降级关系">
      <strong>Fallback · 结构性关系</strong>
      <span>{fallback.description}</span>
    </aside>
  );
}


function ResultPersistence({ resultPersistence, onOpen }) {
  return (
    <article className="command-center-result command-center-map-node" data-zone-key={resultPersistence.zoneKey}>
      <NodeHeading eyebrow="STRUCTURAL ONLY" title={resultPersistence.title} subtitle="结果落库" />
      <div className="command-center-result-icon" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      <strong>Task Detail / Notification</strong>
      <p>{resultPersistence.description}</p>
      <button
        type="button"
        className="command-center-result-route"
        data-command-center-action="open-review-tasks"
        onClick={() => onOpen(resultPersistence.navigationTarget)}
      >
        查看 Review 任务
      </button>
    </article>
  );
}


function NodeHeading({ eyebrow, title, subtitle }) {
  return (
    <header className="command-center-node-heading">
      <small>{eyebrow}</small>
      <h2>{title}</h2>
      <p>{subtitle}</p>
    </header>
  );
}


function intakeIcon(key) {
  return {
    MANUAL: '○',
    MERGE_REQUEST: '⑂',
    PUSH: '</>',
    RETRY: '↻'
  }[key] || '•';
}
