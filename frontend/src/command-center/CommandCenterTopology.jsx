import { prioritizeSelectedFlow } from './commandCenterFocus.js';


export default function CommandCenterTopology({
  topology,
  canvasActive = false,
  canvasContainerRef,
  canvasLayer = null,
  fallbackReason = null,
  focus,
  onActivateNode,
  onSelectFlow
}) {
  const columns = topology.columns || [];
  const visibleFlows = prioritizeSelectedFlow(topology.flows, focus?.flowId, 8);
  const selectedFlow = topology.flows.find(flow => flow.id === focus?.flowId) || null;
  return (
    <section
      className={[
        'command-center-topology',
        canvasActive ? 'is-canvas-active' : 'is-dom-fallback'
      ].join(' ')}
      aria-labelledby="execution-map-title"
      data-command-center-canvas={canvasActive ? 'active' : 'fallback'}
      data-command-center-canvas-fallback={fallbackReason || undefined}
    >
      <div className="command-center-section-heading">
        <div>
          <span className="command-center-section-kicker">REVIEW EXECUTION MAP</span>
          <h2 id="execution-map-title">Review 生命周期</h2>
        </div>
        <span className="command-center-phase-badge">
          {canvasActive ? 'PHASE 3 · LIVE CANVAS' : 'PHASE 3 · DOM FALLBACK'}
        </span>
      </div>

      <div
        className="command-center-topology-stage"
        data-command-center-dom-overlay="true"
        ref={canvasContainerRef}
      >
        {canvasLayer}
        <div className="command-center-flow" role="list" aria-label="AI Review 生命周期">
          {columns.map((column, index) => (
            <article
              className={`command-center-flow-node${selectedFlow?.columnKey === column.key ? ' is-focused-stage' : ''}`}
              role="listitem"
              key={column.key}
            >
              <button
                type="button"
                className="command-center-flow-node-overlay"
                onClick={() => onActivateNode?.(column.key)}
                aria-label={`进入${column.title}`}
              />
              <div className="command-center-flow-node-index">{String(index + 1).padStart(2, '0')}</div>
              <span>{column.eyebrow}</span>
              <h3>{column.title}</h3>
              <p>{column.description}</p>
              <div className="command-center-flow-reading">
                当前 Flow <strong>{topology.flowCountByColumn[column.key] ?? 0}</strong>
              </div>
              {index < columns.length - 1 && (
                <div className="command-center-flow-connector" aria-hidden="true" />
              )}
            </article>
          ))}
        </div>
      </div>

      <div className="command-center-engine-lanes" aria-label="Review 双引擎运行态">
        <div>
          <span>STANDARD FLOW</span>
          <strong>{topology.standardFlowCount}</strong>
          <small>配置驱动的 Provider Review</small>
        </div>
        <div>
          <span>AGENT FLOW</span>
          <strong>{topology.agentFlowCount}</strong>
          <small>独立 Worker 与工具调用链</small>
        </div>
        <div className={topology.fallbackFlowCount ? 'is-warning' : ''}>
          <span>EXPLICIT FALLBACK</span>
          <strong>{topology.fallbackFlowCount}</strong>
          <small>仅统计明确 STANDARD_FALLBACK</small>
        </div>
      </div>

      {topology.flows.length === 0 ? (
        <div className="command-center-deferred-note">
          当前没有活跃 Review Flow。拓扑保持静态，不生成模拟任务或本地阶段。
        </div>
      ) : (
        <div className="command-center-topology-flows" aria-label="拓扑 Review Flow 聚焦">
          {visibleFlows.map(flow => (
            <button
              type="button"
              aria-pressed={focus?.flowId === flow.id}
              className={`command-center-topology-flow is-${flow.stateToken}${focus?.flowId === flow.id ? ' is-selected' : ''}`}
              key={flow.id}
              onClick={() => onSelectFlow?.(flow)}
            >
              <span>{flow.engineKind}</span>
              <strong>{flow.displayName}</strong>
              <small>{flow.stageLabel} · {flow.stageSource}</small>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
