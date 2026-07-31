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
    description: '规则识别与 Risk Card 聚合将在 Phase 1 接入。'
  },
  {
    key: 'orchestration',
    eyebrow: 'ORCHESTRATION',
    title: 'Review Execution Core',
    description: '任务、Preflight 与 Review Target 编排。'
  },
  {
    key: 'execution',
    eyebrow: 'EVIDENCE & EXECUTION',
    title: 'Standard / Agent',
    description: '双引擎 Flow、Worker 与 Provider 将在 Phase 1 接入。'
  },
  {
    key: 'delivery',
    eyebrow: 'RESULT & DELIVERY',
    title: 'Finding / Notification',
    description: '风险结果与通知状态将在 Phase 1 接入。'
  }
];


export default function CommandCenterTopology({ runtime }) {
  const activeTasks = runtime?.intake?.activeTaskCount;

  return (
    <section className="command-center-topology" aria-labelledby="execution-map-title">
      <div className="command-center-section-heading">
        <div>
          <span className="command-center-section-kicker">REVIEW EXECUTION MAP</span>
          <h2 id="execution-map-title">Review 生命周期</h2>
        </div>
        <span className="command-center-phase-badge">PHASE 0 · STATIC SKELETON</span>
      </div>

      <div className="command-center-flow" role="list" aria-label="AI Review 生命周期">
        {FLOW_COLUMNS.map((column, index) => (
          <article className="command-center-flow-node" role="listitem" key={column.key}>
            <div className="command-center-flow-node-index">{String(index + 1).padStart(2, '0')}</div>
            <span>{column.eyebrow}</span>
            <h3>{column.title}</h3>
            <p>{column.description}</p>
            {column.key === 'orchestration' && (
              <div className="command-center-flow-reading">
                活跃 Task <strong>{activeTasks ?? '—'}</strong>
              </div>
            )}
            {index < FLOW_COLUMNS.length - 1 && (
              <div className="command-center-flow-connector" aria-hidden="true" />
            )}
          </article>
        ))}
      </div>

      <div className="command-center-deferred-note">
        当前只展示真实生命周期边界；活跃 Flow、Fallback、Context、Provider 和 Finding
        状态将在 Phase 1 使用聚合数据接入。
      </div>
    </section>
  );
}
