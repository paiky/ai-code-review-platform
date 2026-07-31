import CommandCenterTopology from './CommandCenterTopology.jsx';
import GovernanceLoop from './GovernanceLoop.jsx';
import LiveOperationsRail from './LiveOperationsRail.jsx';
import SystemPulse from './SystemPulse.jsx';
import { useCommandCenterSnapshots } from './useCommandCenterSnapshots.js';
import './commandCenter.css';


export default function CommandCenterPage() {
  const {
    runtime,
    governance,
    loading,
    error,
    reload
  } = useCommandCenterSnapshots();

  return (
    <main className="command-center-page" data-command-center-phase="PHASE_0">
      <header className="command-center-hero">
        <div>
          <span className="command-center-hero-kicker">AI REVIEW COMMAND CENTER</span>
          <h1>Review Execution Core</h1>
          <p>
            从 GitLab 事件、规则分析与任务编排，到 Standard / Agent 执行、
            Finding 交付和反馈治理的统一运行入口。
          </p>
        </div>
        <div className="command-center-hero-actions">
          <span>READ-ONLY CONTROL PLANE</span>
          <button type="button" onClick={reload} disabled={loading}>
            {loading ? '正在刷新' : '刷新快照'}
          </button>
        </div>
      </header>

      {error && (
        <div className="command-center-error" role="alert">
          <strong>Command Center 数据暂不可用</strong>
          <span>{error}</span>
          <span>页面保留结构骨架，现有任务和治理功能不受影响。</span>
        </div>
      )}

      <SystemPulse
        runtime={runtime}
        governance={governance}
        loading={loading}
        error={error}
      />

      <div className="command-center-main-grid">
        <CommandCenterTopology runtime={runtime} />
        <LiveOperationsRail runtime={runtime} loading={loading} />
      </div>

      <GovernanceLoop governance={governance} />
    </main>
  );
}
