export default function LiveOperationsRail({ operations, runtimeLoading }) {
  const hasFlows = operations.flows.length > 0;

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
          <strong>{operations.scheduler.queuedJobCount ?? 0}</strong>
        </div>
        <div>
          <span>Running</span>
          <strong>{operations.scheduler.runningJobCount ?? 0}</strong>
        </div>
        <div>
          <span>Worker Online</span>
          <strong>{operations.workers.onlineCount ?? 0}</strong>
        </div>
        <div>
          <span>Lease Expired</span>
          <strong>{operations.queue.expiredLease ?? 0}</strong>
        </div>
      </div>

      <section className="command-center-rail-section">
        <h3>Active Flow</h3>
        {hasFlows ? operations.flows.slice(0, 6).map(flow => (
          <a className={`command-center-rail-row is-${flow.stateToken}`} href={`/tasks/${flow.taskId}`} key={flow.id}>
            <span>{flow.engineKind}</span>
            <strong>{flow.displayName}</strong>
            <small>{flow.stageLabel}</small>
          </a>
        )) : (
          <p>{runtimeLoading ? '正在读取运行快照' : '当前无活跃 Review Flow'}</p>
        )}
      </section>

      <section className="command-center-rail-section">
        <h3>Provider Observation</h3>
        {operations.providers.length ? operations.providers.slice(0, 5).map(provider => (
          <div className={`command-center-rail-row is-${provider.stateToken}`} key={provider.providerCode}>
            <span>{provider.defaultProvider ? 'DEFAULT' : provider.providerType}</span>
            <strong>{provider.providerName}</strong>
            <small>{provider.statusLabel}</small>
          </div>
        )) : <p>暂无已配置 Provider 观察数据</p>}
      </section>

      <section className="command-center-rail-section">
        <h3>Alerts</h3>
        {operations.alerts.length ? operations.alerts.slice(0, 6).map(alert => {
          const content = (
            <>
              <span>{alert.status}</span>
              <strong>{alert.typeLabel}</strong>
              <small>{alert.projectName || '平台运行态'}</small>
            </>
          );
          return alert.navigationTarget ? (
            <a className={`command-center-rail-row is-${alert.stateToken}`} href={alert.navigationTarget} key={alert.id}>
              {content}
            </a>
          ) : (
            <div className={`command-center-rail-row is-${alert.stateToken}`} key={alert.id}>
              {content}
            </div>
          );
        }) : <p>当前窗口内无运行告警</p>}
      </section>
    </aside>
  );
}
