function GovernanceMetric({ label, value, scope }) {
  return (
    <div className="command-center-governance-metric">
      <span>{label}</span>
      <strong>{value ?? '—'}</strong>
      <small>{scope}</small>
    </div>
  );
}


export default function GovernanceLoop({ governance }) {
  return (
    <section className="command-center-governance" aria-labelledby="governance-loop-title">
      <div className="command-center-section-heading">
        <div>
          <span className="command-center-section-kicker">GOVERNANCE LOOP</span>
          <h2 id="governance-loop-title">质量治理回路</h2>
        </div>
        <span className="command-center-deferred-pill">非实时执行链路</span>
      </div>

      <div className="command-center-governance-grid">
        <GovernanceMetric
          label="Pending Feedback"
          value={governance?.feedback?.pendingCount}
          scope="CURRENT STATE"
        />
        <GovernanceMetric
          label="Evaluation Case"
          value={governance?.evaluation?.caseCount}
          scope="ALL TIME"
        />
        <GovernanceMetric label="Context Quality" value="待接入" scope="PHASE 1" />
        <GovernanceMetric label="Project Policy" value="待接入" scope="PHASE 1" />
        <GovernanceMetric label="Acceptance Gate" value="待接入" scope="PHASE 1" />
      </div>
    </section>
  );
}
