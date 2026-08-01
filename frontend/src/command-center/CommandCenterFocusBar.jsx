import {
  flowsForCommandCenterTask
} from './commandCenterFocus.js';


export default function CommandCenterFocusBar({
  tasks,
  flows,
  focus,
  onClear,
  onSelectTask,
  onSelectFlow
}) {
  const visibleFlows = flowsForCommandCenterTask(flows, focus.taskId);
  const selectedTask = tasks.find(task => task.taskId === focus.taskId) || null;
  const selectedFlow = flows.find(flow => flow.id === focus.flowId) || null;

  return (
    <section className="command-center-focus" aria-labelledby="command-center-focus-title">
      <div className="command-center-section-heading">
        <div>
          <span className="command-center-section-kicker">TASK / FLOW FOCUS</span>
          <h2 id="command-center-focus-title">运行聚焦</h2>
        </div>
        <div className="command-center-focus-current" aria-live="polite">
          <span>{selectedTask ? `Task #${selectedTask.taskId}` : '全部 Task'}</span>
          <strong>{selectedFlow?.reviewKey || '全部 Flow'}</strong>
          {(selectedTask || selectedFlow) && (
            <button type="button" onClick={onClear}>清除聚焦</button>
          )}
        </div>
      </div>

      <div className="command-center-focus-group" aria-label="选择活跃 Task">
        <span>Task</span>
        <div className="command-center-focus-options">
          {tasks.length ? tasks.map(task => (
            <button
              type="button"
              aria-pressed={focus.taskId === task.taskId}
              className={focus.taskId === task.taskId ? 'is-selected' : ''}
              key={task.taskId}
              onClick={() => onSelectTask(task.taskId)}
            >
              <strong>#{task.taskId}</strong>
              <small>{task.projectName}</small>
            </button>
          )) : <p>当前没有可聚焦的活跃 Task</p>}
        </div>
      </div>

      <div className="command-center-focus-group" aria-label="选择具体 Review Flow">
        <span>Review Flow</span>
        <div className="command-center-focus-options">
          {visibleFlows.length ? visibleFlows.map(flow => (
            <button
              type="button"
              aria-pressed={focus.flowId === flow.id}
              className={focus.flowId === flow.id ? 'is-selected' : ''}
              key={flow.id}
              onClick={() => onSelectFlow(flow)}
            >
              <strong>{flow.reviewKey}</strong>
              <small>{flow.engineKind} · {flow.stageLabel}</small>
            </button>
          )) : <p>{selectedTask ? '该 Task 当前没有活跃 Flow' : '先选择 Task，或从拓扑与 Live Operations 直接聚焦 Flow'}</p>}
        </div>
      </div>
    </section>
  );
}
