import {
  flowsForCommandCenterTask,
  prioritizeSelectedFlow
} from './commandCenterFocus.js';


export default function LiveOperationsRail({
  operations,
  runtimeLoading,
  focus,
  frameOperations,
  onSelectFlow
}) {
  const focusedFlows = flowsForCommandCenterTask(operations.flows, focus?.taskId);
  const visibleFlows = prioritizeSelectedFlow(focusedFlows, focus?.flowId, 6);
  const hasFlows = visibleFlows.length > 0;

  return (
    <aside className="command-center-live-rail" aria-labelledby="live-operations-title">
      <div className="command-center-section-heading">
        <div>
          <span className="command-center-section-kicker">LIVE OPERATIONS</span>
          <h2 id="live-operations-title">运行侧栏</h2>
        </div>
      </div>

      <div className="command-center-drawer-actions" aria-label="AppFrame 运行抽屉">
        <button
          type="button"
          aria-expanded={Boolean(frameOperations?.jobQueueOpen)}
          onClick={frameOperations?.openJobQueue}
        >
          打开 Queue
        </button>
        <button
          type="button"
          aria-expanded={Boolean(frameOperations?.failureNotificationsOpen)}
          onClick={frameOperations?.openFailureNotifications}
        >
          打开 Failure
        </button>
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
        {hasFlows ? visibleFlows.map(flow => (
          <button
            type="button"
            aria-pressed={focus?.flowId === flow.id}
            className={`command-center-rail-row is-${flow.stateToken}${focus?.flowId === flow.id ? ' is-selected' : ''}`}
            key={flow.id}
            onClick={() => onSelectFlow?.(flow)}
          >
            <span>{flow.engineKind}</span>
            <strong>{flow.displayName}</strong>
            <small>{flow.stageLabel}</small>
          </button>
        )) : (
          <p>{runtimeLoading ? '正在读取运行快照' : focus?.taskId ? '所选 Task 当前无活跃 Review Flow' : '当前无活跃 Review Flow'}</p>
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
        <div className="command-center-rail-section-heading">
          <h3>Alerts</h3>
          <button
            type="button"
            aria-expanded={Boolean(frameOperations?.failureNotificationsOpen)}
            onClick={frameOperations?.openFailureNotifications}
          >
            Failure Drawer
          </button>
        </div>
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
