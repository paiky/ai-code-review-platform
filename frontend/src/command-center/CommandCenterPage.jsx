import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAppFrameOperations } from '../appFrameOperations.js';
import CommandCenterCanvas from './CommandCenterCanvas.jsx';
import CommandCenterFocusBar from './CommandCenterFocusBar.jsx';
import GovernanceLoop from './GovernanceLoop.jsx';
import LiveOperationsRail from './LiveOperationsRail.jsx';
import SystemPulse from './SystemPulse.jsx';
import {
  EMPTY_COMMAND_CENTER_FOCUS,
  reconcileCommandCenterFocus,
  resolveLifecycleNavigationTarget,
  selectCommandCenterFlow,
  selectCommandCenterTask
} from './commandCenterFocus.js';
import { buildCommandCenterPresentation } from './commandCenterPresentation.js';
import { useCommandCenterSnapshots } from './useCommandCenterSnapshots.js';
import './commandCenter.css';


export default function CommandCenterPage() {
  const navigate = useNavigate();
  const frameOperations = useAppFrameOperations();
  const [focus, setFocus] = useState(EMPTY_COMMAND_CENTER_FOCUS);
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

  useEffect(() => {
    setFocus(current => {
      const next = reconcileCommandCenterFocus(runtime, current);
      return next.taskId === current.taskId && next.flowId === current.flowId
        ? current
        : next;
    });
  }, [runtime]);

  const selectTask = useCallback(taskId => {
    setFocus(selectCommandCenterTask(taskId));
  }, []);
  const selectFlow = useCallback(flow => {
    setFocus(selectCommandCenterFlow(flow));
  }, []);
  const clearFocus = useCallback(() => {
    setFocus(EMPTY_COMMAND_CENTER_FOCUS);
  }, []);
  const activateLifecycleNode = useCallback(columnKey => {
    navigate(resolveLifecycleNavigationTarget(columnKey, focus));
  }, [focus, navigate]);

  return (
    <main
      className="command-center-page"
      data-command-center-phase="PHASE_3"
      data-command-center-focus-task={focus.taskId || undefined}
      data-command-center-focus-flow={focus.flowId || undefined}
    >
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

      <CommandCenterFocusBar
        tasks={presentation.topology.activeTasks}
        flows={presentation.topology.flows}
        focus={focus}
        onClear={clearFocus}
        onSelectTask={selectTask}
        onSelectFlow={selectFlow}
      />

      <div className="command-center-main-grid">
        <CommandCenterCanvas
          topology={presentation.topology}
          focus={focus}
          onActivateNode={activateLifecycleNode}
          onSelectFlow={selectFlow}
        />
        <LiveOperationsRail
          operations={presentation.operations}
          runtimeLoading={runtimeLoading}
          focus={focus}
          frameOperations={frameOperations}
          onSelectFlow={selectFlow}
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
