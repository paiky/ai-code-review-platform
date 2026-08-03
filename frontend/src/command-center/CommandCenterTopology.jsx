export default function CommandCenterTopology({
  topology,
  canvasActive = false,
  canvasContainerRef,
  canvasLayer = null,
  fallbackReason = null,
  focus,
  onActivateNode
}) {
  const columns = topology.columns || [];
  const selectedFlow = topology.flows.find(flow => flow.id === focus?.flowId) || null;
  const selectedColumnIndex = columns.findIndex(
    column => column.key === selectedFlow?.columnKey
  );

  return (
    <section
      className={[
        'command-center-topology',
        canvasActive ? 'is-canvas-active' : 'is-dom-fallback'
      ].join(' ')}
      aria-label="Review 生命周期五阶段地图"
      data-command-center-canvas={canvasActive ? 'active' : 'fallback'}
      data-command-center-canvas-fallback={fallbackReason || undefined}
    >
      <div
        className="command-center-topology-stage"
        data-command-center-dom-overlay="true"
        ref={canvasContainerRef}
      >
        {canvasLayer}
        <div className="command-center-flow" role="list" aria-label="AI Review 生命周期">
          {columns.map((column, index) => {
            const focused = selectedFlow?.columnKey === column.key;
            const onFocusedPath = selectedColumnIndex >= 0 && index <= selectedColumnIndex;
            const focusClassName = selectedFlow
              ? onFocusedPath ? ' is-focus-path' : ' is-focus-muted'
              : '';
            return (
              <article
                className={[
                  'command-center-flow-node',
                  focusClassName,
                  focused ? ' is-focused-stage' : '',
                  focused ? ` is-engine-${selectedFlow.engineKind.toLowerCase()}` : '',
                  focused ? ` is-state-${selectedFlow.stateToken}` : ''
                ].join(' ')}
                role="listitem"
                key={column.key}
              >
                <button
                  type="button"
                  className="command-center-flow-node-overlay"
                  onClick={() => onActivateNode?.(column.key)}
                  onKeyDown={event => {
                    if (event.key !== 'Enter' && event.key !== ' ') return;
                    event.preventDefault();
                    onActivateNode?.(column.key);
                  }}
                  aria-current={focused ? 'step' : undefined}
                  aria-label={`进入${column.title}${focused ? `，当前 Flow 状态为${selectedFlow.stageLabel}` : ''}`}
                />
                <div className="command-center-flow-node-header">
                  <span className="command-center-flow-node-index">{String(index + 1).padStart(2, '0')}</span>
                  <span className="command-center-flow-node-count">
                    {topology.flowCountByColumn[column.key] ?? 0} FLOW
                  </span>
                </div>
                <span className="command-center-flow-node-eyebrow">{column.eyebrow}</span>
                <h2>{column.title}</h2>
                <p>{column.description}</p>
                <div className="command-center-flow-reading">
                  {focused ? (
                    <>
                      <span>{selectedFlow.stageLabel}</span>
                      <strong>{selectedFlow.engineKind}</strong>
                      <small>{selectedFlow.stageSource}</small>
                    </>
                  ) : (
                    <>
                      <span>真实运行节点</span>
                      <strong>{topology.flowCountByColumn[column.key] ?? 0}</strong>
                    </>
                  )}
                </div>
                {index < columns.length - 1 && (
                  <div className="command-center-flow-connector" aria-hidden="true" />
                )}
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
