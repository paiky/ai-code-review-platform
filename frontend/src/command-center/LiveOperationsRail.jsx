export default function LiveOperationsRail({ runtime, loading }) {
  const scheduler = runtime?.scheduler;
  const hasActiveJobs = Boolean(scheduler?.activeJobCount);

  return (
    <aside className="command-center-live-rail" aria-labelledby="live-operations-title">
      <div className="command-center-section-heading">
        <div>
          <span className="command-center-section-kicker">LIVE OPERATIONS</span>
          <h2 id="live-operations-title">运行侧栏</h2>
        </div>
      </div>

      <div className="command-center-rail-summary">
        <div>
          <span>Queued</span>
          <strong>{scheduler?.queuedJobCount ?? '—'}</strong>
        </div>
        <div>
          <span>Running</span>
          <strong>{scheduler?.runningJobCount ?? '—'}</strong>
        </div>
      </div>

      <div className="command-center-rail-empty">
        <span className={hasActiveJobs ? 'is-active' : ''} aria-hidden="true" />
        <h3>{loading ? '正在读取调度状态' : hasActiveJobs ? '存在活跃 Review Job' : '当前无活跃 Review Job'}</h3>
        <p>Flow 明细、失败、Fallback、Worker 与通知告警将在 Phase 1 接入。</p>
      </div>
    </aside>
  );
}
