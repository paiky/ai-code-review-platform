function GovernanceMetric({ metric }) {
  return (
    <a className="command-center-governance-metric" href={metric.href}>
      <span>{metric.label}</span>
      <strong>{metric.value}</strong>
      <small>{metric.scope}</small>
    </a>
  );
}


export default function GovernanceLoop({ governance, loading, error }) {
  return (
    <section className="command-center-governance" aria-labelledby="governance-loop-title">
      <div className="command-center-section-heading">
        <div>
          <span className="command-center-section-kicker">GOVERNANCE LOOP</span>
          <h2 id="governance-loop-title">质量治理回路</h2>
        </div>
        <span className="command-center-deferred-pill">
          {error
            ? '保留最后成功快照'
            : loading
              ? '正在刷新 Governance'
              : governance.coverage?.truncated
                ? 'BOUNDED COVERAGE'
                : 'WINDOW / ALL TIME'}
        </span>
      </div>

      <div className="command-center-governance-grid">
        {governance.metrics.map(metric => (
          <GovernanceMetric metric={metric} key={metric.label} />
        ))}
      </div>
    </section>
  );
}
