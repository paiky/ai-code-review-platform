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


export default function SystemPulse({ pulse, runtimeLoading, runtimeError }) {
  const dataState = runtimeError
    ? 'error'
    : runtimeLoading
      ? 'loading'
      : pulse.runtimeFreshness === 'STALE'
        ? 'stale'
        : pulse.runtimeFreshness === 'FRESH'
          ? 'ready'
          : 'empty';

  return (
    <section className="command-center-pulse" aria-labelledby="system-pulse-title">
      <div className="command-center-pulse-heading">
        <div>
          <span className="command-center-section-kicker">SYSTEM PULSE</span>
          <h2 id="system-pulse-title">运行脉搏</h2>
        </div>
        <div className={`command-center-data-state is-${dataState}`}>
          <span aria-hidden="true" />
          {runtimeError
            ? 'Runtime 暂不可用'
            : runtimeLoading
              ? '正在连接'
              : pulse.runtimeFreshness === 'STALE'
                ? 'Runtime 快照已过期'
                : pulse.runtimeFreshness === 'FRESH'
                  ? 'Runtime 快照新鲜'
                  : '暂无快照'}
        </div>
      </div>
      <div className="command-center-pulse-grid">
        <PulseMetric label="活跃 Task" value={pulse.activeTasks} state={pulse.activeTasks ? 'active' : 'neutral'} />
        <PulseMetric label="活跃 Review Job" value={pulse.activeJobs} state={pulse.activeJobs ? 'active' : 'neutral'} />
        <PulseMetric label="Agent Queue" value={pulse.queueDepth} state={pulse.queueDepth ? 'queued' : 'neutral'} />
        <PulseMetric label="Online Worker" value={pulse.onlineWorkers} state={pulse.onlineWorkers ? 'success' : 'neutral'} />
        <PulseMetric label="Active Provider" value={pulse.activeProviders} state={pulse.activeProviders ? 'active' : 'neutral'} />
        <PulseMetric label="Critical Finding" value={pulse.criticalFindings} state={pulse.criticalFindings ? 'error' : 'neutral'} />
        <PulseMetric label="快照时间" value={formatGeneratedAt(pulse.generatedAt)} />
      </div>
    </section>
  );
}
