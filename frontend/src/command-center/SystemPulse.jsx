function formatGeneratedAt(value) {
  if (!value) return '等待首个快照';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间不可用';
  return date.toLocaleString();
}


function PulseMetric({ label, value, state = 'neutral' }) {
  return (
    <div className={`command-center-pulse-metric is-${state}`}>
      <span>{label}</span>
      <strong>{value ?? '—'}</strong>
    </div>
  );
}


export default function SystemPulse({ runtime, governance, loading, error }) {
  const activeJobs = runtime?.scheduler?.activeJobCount;
  const activeTasks = runtime?.intake?.activeTaskCount;
  const pendingFeedback = governance?.feedback?.pendingCount;
  const evaluationCases = governance?.evaluation?.caseCount;
  const dataState = error ? 'error' : loading ? 'loading' : runtime ? 'ready' : 'empty';

  return (
    <section className="command-center-pulse" aria-labelledby="system-pulse-title">
      <div className="command-center-pulse-heading">
        <div>
          <span className="command-center-section-kicker">SYSTEM PULSE</span>
          <h2 id="system-pulse-title">运行脉搏</h2>
        </div>
        <div className={`command-center-data-state is-${dataState}`}>
          <span aria-hidden="true" />
          {error ? '数据不可用' : loading ? '正在连接' : runtime ? '基础数据可用' : '暂无快照'}
        </div>
      </div>
      <div className="command-center-pulse-grid">
        <PulseMetric label="活跃 Task" value={activeTasks} state={activeTasks ? 'active' : 'neutral'} />
        <PulseMetric label="活跃 Review Job" value={activeJobs} state={activeJobs ? 'active' : 'neutral'} />
        <PulseMetric label="Pending Feedback" value={pendingFeedback} />
        <PulseMetric label="Evaluation Case" value={evaluationCases} />
        <PulseMetric
          label="快照时间"
          value={formatGeneratedAt(runtime?.generatedAt)}
          state={error ? 'error' : 'neutral'}
        />
      </div>
    </section>
  );
}
