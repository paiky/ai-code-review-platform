const FLOW_COLUMNS = [
  {
    key: 'intake',
    eyebrow: 'INTAKE',
    title: 'GitLab / Manual',
    description: '事件进入平台并创建 ReviewTask。'
  },
  {
    key: 'rule',
    eyebrow: 'RULE & DECISION',
    title: 'Rule Analysis',
    description: '规则识别与 Risk Card 聚合。'
  },
  {
    key: 'orchestration',
    eyebrow: 'ORCHESTRATION',
    title: 'Review Execution Core',
    description: 'Task、Preflight 与 Scheduler 编排。'
  },
  {
    key: 'execution',
    eyebrow: 'EVIDENCE & EXECUTION',
    title: 'Standard / Agent',
    description: 'Context、Provider、Agent Worker 双引擎执行。'
  },
  {
    key: 'delivery',
    eyebrow: 'RESULT & DELIVERY',
    title: 'Finding / Notification',
    description: 'Finding 风险判断与通知交付。'
  }
];


export default function CommandCenterTopology({ topology }) {
  return (
    <section className="command-center-topology" aria-labelledby="execution-map-title">
      <div className="command-center-section-heading">
        <div>
          <span className="command-center-section-kicker">REVIEW EXECUTION MAP</span>
          <h2 id="execution-map-title">Review 生命周期</h2>
        </div>
        <span className="command-center-phase-badge">PHASE 1 · LIVE STATIC TOPOLOGY</span>
      </div>

      <div className="command-center-flow" role="list" aria-label="AI Review 生命周期">
        {FLOW_COLUMNS.map((column, index) => (
          <article className="command-center-flow-node" role="listitem" key={column.key}>
            <div className="command-center-flow-node-index">{String(index + 1).padStart(2, '0')}</div>
            <span>{column.eyebrow}</span>
            <h3>{column.title}</h3>
            <p>{column.description}</p>
            <div className="command-center-flow-reading">
              当前 Flow <strong>{topology.flowCountByColumn[column.key] ?? 0}</strong>
            </div>
            {index < FLOW_COLUMNS.length - 1 && (
              <div className="command-center-flow-connector" aria-hidden="true" />
            )}
          </article>
        ))}
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
        <div className="command-center-topology-flows">
          {topology.flows.slice(0, 8).map(flow => (
            <a
              className={`command-center-topology-flow is-${flow.stateToken}`}
              href={`/tasks/${flow.taskId}`}
              key={flow.id}
            >
              <span>{flow.engineKind}</span>
              <strong>{flow.displayName}</strong>
              <small>{flow.stageLabel} · {flow.stageSource}</small>
            </a>
          ))}
        </div>
      )}
    </section>
  );
}
