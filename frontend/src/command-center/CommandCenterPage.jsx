import { useCallback, useEffect, useMemo, useState } from 'react';
import { Select } from 'antd';
import { useNavigate } from 'react-router-dom';

import { useAppFrameOperations } from '../appFrameOperations.js';
import CommandCenterCanvas from './CommandCenterCanvas.jsx';
import {
  EMPTY_COMMAND_CENTER_FOCUS,
  flowsForCommandCenterTask,
  reconcileCommandCenterFocus,
  resolveLifecycleNavigationTarget,
  selectCommandCenterFlow,
  selectCommandCenterTask
} from './commandCenterFocus.js';
import { buildCommandCenterPresentation } from './commandCenterPresentation.js';
import { useCommandCenterRuntimeSnapshot } from './useCommandCenterSnapshots.js';
import './commandCenter.css';


export default function CommandCenterPage() {
  const navigate = useNavigate();
  const frameOperations = useAppFrameOperations();
  const [focus, setFocus] = useState(EMPTY_COMMAND_CENTER_FOCUS);
  const {
    runtime,
    runtimeLoading,
    runtimeError,
    reload
  } = useCommandCenterRuntimeSnapshot();
  const presentation = useMemo(
    () => buildCommandCenterPresentation({ runtime }),
    [runtime]
  );
  const tasks = presentation.topology.activeTasks;
  const flows = presentation.topology.flows;
  const visibleFlows = useMemo(
    () => flowsForCommandCenterTask(flows, focus.taskId),
    [flows, focus.taskId]
  );
  const selectedTask = tasks.find(task => task.taskId === focus.taskId) || null;
  const selectedFlow = flows.find(flow => flow.id === focus.flowId) || null;

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
  const selectFlow = useCallback(flowId => {
    const flow = flows.find(candidate => candidate.id === flowId);
    setFocus(flow ? selectCommandCenterFlow(flow) : EMPTY_COMMAND_CENTER_FOCUS);
  }, [flows]);
  const clearFocus = useCallback(() => {
    setFocus(EMPTY_COMMAND_CENTER_FOCUS);
  }, []);
  const activateLifecycleNode = useCallback(columnKey => {
    navigate(resolveLifecycleNavigationTarget(columnKey, focus));
  }, [focus, navigate]);

  const freshness = runtime?.freshness || (runtimeLoading ? 'LOADING' : 'EMPTY');
  const generatedAt = formatSnapshotTime(runtime?.generatedAt);

  return (
    <main
      className="command-center-page"
      data-command-center-phase="PHASE_4A"
      data-command-center-focus-task={focus.taskId || undefined}
      data-command-center-focus-flow={focus.flowId || undefined}
    >
      <section className="command-center-map-shell" aria-labelledby="command-center-title">
        <header className="command-center-map-toolbar">
          <div className="command-center-map-identity">
            <span className="command-center-kicker">AI REVIEW COMMAND CENTER</span>
            <h1 id="command-center-title">Review 生命周期地图</h1>
          </div>

          <div className="command-center-snapshot-state" aria-live="polite">
            <span className={`command-center-status-dot is-${freshness.toLowerCase()}`} aria-hidden="true" />
            <span>
              <strong>{freshnessLabel(freshness)}</strong>
              <small>{generatedAt}</small>
            </span>
          </div>

          <div className="command-center-focus-controls" aria-label="Task 与 Review Flow 聚焦">
            <Select
              className="command-center-select command-center-task-select"
              aria-label="选择活跃 Task"
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="全部 Task"
              value={focus.taskId || undefined}
              options={tasks.map(task => ({
                value: task.taskId,
                label: `#${task.taskId} · ${task.projectName}`
              }))}
              onChange={value => value ? selectTask(value) : clearFocus()}
              notFoundContent="当前无活跃 Task"
            />
            <Select
              className="command-center-select command-center-flow-select"
              aria-label="选择具体 Review Flow"
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={selectedTask ? '该 Task 的 Flow' : '全部 Review Flow'}
              value={focus.flowId || undefined}
              options={visibleFlows.map(flow => ({
                value: flow.id,
                label: `${flow.reviewKey} · ${flow.engineKind} · ${flow.stageLabel}`
              }))}
              onChange={value => value ? selectFlow(value) : setFocus(current => ({
                taskId: current.taskId,
                flowId: null
              }))}
              notFoundContent={selectedTask ? '该 Task 当前无活跃 Flow' : '当前无活跃 Review Flow'}
            />
          </div>

          <div className="command-center-toolbar-actions" aria-label="Command Center 操作">
            {(selectedTask || selectedFlow) && (
              <button type="button" className="is-quiet" onClick={clearFocus}>清除聚焦</button>
            )}
            <button type="button" onClick={reload} disabled={runtimeLoading}>
              {runtimeLoading ? '刷新中' : '刷新'}
            </button>
            <button
              type="button"
              aria-expanded={Boolean(frameOperations?.jobQueueOpen)}
              onClick={frameOperations?.openJobQueue}
            >
              Queue <span>{frameOperations?.jobQueue?.activeCount ?? 0}</span>
            </button>
            <button
              type="button"
              className={(frameOperations?.failureNotifications?.failureCount ?? 0) > 0 ? 'is-danger' : ''}
              aria-expanded={Boolean(frameOperations?.failureNotificationsOpen)}
              onClick={frameOperations?.openFailureNotifications}
            >
              Failure <span>{frameOperations?.failureNotifications?.failureCount ?? 0}</span>
            </button>
          </div>
        </header>

        {runtimeError && (
          <div className="command-center-runtime-error" role="alert">
            <strong>Runtime 快照暂不可用</strong>
            <span>{runtimeError}。页面保留最后一次成功快照。</span>
          </div>
        )}

        <CommandCenterCanvas
          topology={presentation.topology}
          focus={focus}
          onActivateNode={activateLifecycleNode}
        />

        <footer className="command-center-flow-dock" aria-label="当前 Review Flow">
          <div className="command-center-engine-legend" aria-label="Review Flow 类型图例">
            <EngineLegend label="Standard" value={presentation.topology.standardFlowCount} token="standard" />
            <EngineLegend label="Agent" value={presentation.topology.agentFlowCount} token="agent" />
            <EngineLegend label="Fallback" value={presentation.topology.fallbackFlowCount} token="fallback" />
          </div>

          {selectedFlow ? (
            <div className="command-center-selected-flow" aria-live="polite">
              <span className={`command-center-flow-state is-${selectedFlow.stateToken}`}>
                {flowStateLabel(selectedFlow)}
              </span>
              <div>
                <small>REVIEW FLOW · TASK #{selectedFlow.taskId}</small>
                <strong>{selectedFlow.reviewKey}</strong>
              </div>
              <dl>
                <div><dt>Engine</dt><dd>{selectedFlow.engineKind}</dd></div>
                <div><dt>Stage</dt><dd>{selectedFlow.stageLabel}</dd></div>
                <div><dt>Provider</dt><dd>{selectedFlow.providerModelLabel}</dd></div>
              </dl>
              <button type="button" onClick={() => navigate(`/tasks/${selectedFlow.taskId}`)}>
                查看任务详情
              </button>
            </div>
          ) : (
            <div className="command-center-flow-dock-empty">
              <strong>{runtimeLoading ? '正在读取 Runtime 快照' : '选择 Task / Flow 聚焦真实执行路径'}</strong>
              <span>地图只呈现真实运行数据；空闲态不会生成模拟任务或业务状态。</span>
            </div>
          )}
        </footer>
      </section>
    </main>
  );
}


function EngineLegend({ label, value, token }) {
  return (
    <div className={`command-center-legend-item is-${token}`}>
      <span aria-hidden="true" />
      <strong>{label}</strong>
      <small>{value}</small>
    </div>
  );
}


function freshnessLabel(value) {
  return {
    FRESH: 'Runtime 实时',
    STALE: 'Runtime 已过期',
    LOADING: 'Runtime 连接中',
    EMPTY: 'Runtime 暂无数据'
  }[value] || 'Runtime 状态未知';
}


function flowStateLabel(flow) {
  return {
    danger: 'FAILED',
    warning: flow.fallback ? 'FALLBACK' : 'STALE',
    queued: 'QUEUED',
    active: 'RUNNING',
    success: 'COMPLETED'
  }[flow.stateToken] || String(flow.status || 'UNKNOWN');
}


function formatSnapshotTime(value) {
  if (!value) return '等待首轮快照';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '快照时间未知';
  return `更新于 ${new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(date)}`;
}
