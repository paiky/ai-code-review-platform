import { useMemo } from 'react';

import CommandCenterCanvas from './CommandCenterCanvas.jsx';
import GovernanceLoop from './GovernanceLoop.jsx';
import LiveOperationsRail from './LiveOperationsRail.jsx';
import SystemPulse from './SystemPulse.jsx';
import { buildCommandCenterPresentation } from './commandCenterPresentation.js';
import { useCommandCenterSnapshots } from './useCommandCenterSnapshots.js';
import './commandCenter.css';


export default function CommandCenterPage() {
  const {
    runtime,
    governance,
    runtimeLoading,
    governanceLoading,
    runtimeError,
    governanceError,
    reload
  } = useCommandCenterSnapshots();
  const presentation = useMemo(
    () => buildCommandCenterPresentation({ runtime, governance }),
    [runtime, governance]
  );
  const loading = runtimeLoading || governanceLoading;

  return (
    <main className="command-center-page" data-command-center-phase="PHASE_2D">
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
          <span>READ-ONLY CONTROL PLANE · LIVE SNAPSHOTS</span>
          <button type="button" onClick={reload} disabled={loading}>
            {loading ? '正在刷新' : '刷新快照'}
          </button>
        </div>
      </header>

      {(runtimeError || governanceError) && (
        <div className="command-center-error" role="alert">
          <strong>部分 Command Center 数据暂不可用</strong>
          {runtimeError && <span>Runtime：{runtimeError}</span>}
          {governanceError && <span>Governance：{governanceError}</span>}
          <span>页面保留最后一次成功快照，现有 Review 功能不受影响。</span>
        </div>
      )}

      <SystemPulse
        pulse={presentation.pulse}
        runtimeLoading={runtimeLoading}
        runtimeError={runtimeError}
      />

      <div className="command-center-main-grid">
        <CommandCenterCanvas topology={presentation.topology} />
        <LiveOperationsRail
          operations={presentation.operations}
          runtimeLoading={runtimeLoading}
        />
      </div>

      <GovernanceLoop
        governance={presentation.governance}
        loading={governanceLoading}
        error={governanceError}
      />
    </main>
  );
}
