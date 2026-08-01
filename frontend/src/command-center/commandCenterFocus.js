const TASK_ROUTE = '/tasks';
const QUALITY_ROUTE = '/review-quality';
const QUALITY_COLUMNS = new Set(['execution', 'delivery']);


export const EMPTY_COMMAND_CENTER_FOCUS = Object.freeze({
  taskId: null,
  flowId: null
});


export function reconcileCommandCenterFocus(runtime, focus = EMPTY_COMMAND_CENTER_FOCUS) {
  const flows = Array.isArray(runtime?.activeFlows) ? runtime.activeFlows : [];
  const tasks = Array.isArray(runtime?.activeTasks) ? runtime.activeTasks : [];
  const selectedFlow = flows.find(flow => flow.id === focus.flowId) || null;
  if (selectedFlow) {
    return {
      taskId: selectedFlow.taskId,
      flowId: selectedFlow.id
    };
  }
  const selectedTask = tasks.find(task => task.taskId === focus.taskId) || null;
  return selectedTask
    ? { taskId: selectedTask.taskId, flowId: null }
    : EMPTY_COMMAND_CENTER_FOCUS;
}


export function selectCommandCenterTask(taskId) {
  const normalizedTaskId = positiveInteger(taskId);
  return normalizedTaskId
    ? { taskId: normalizedTaskId, flowId: null }
    : EMPTY_COMMAND_CENTER_FOCUS;
}


export function selectCommandCenterFlow(flow) {
  const taskId = positiveInteger(flow?.taskId);
  const flowId = typeof flow?.id === 'string' && flow.id.trim()
    ? flow.id.trim()
    : null;
  return taskId && flowId
    ? { taskId, flowId }
    : EMPTY_COMMAND_CENTER_FOCUS;
}


export function flowsForCommandCenterTask(flows, taskId) {
  const safeFlows = Array.isArray(flows) ? flows : [];
  const normalizedTaskId = positiveInteger(taskId);
  return normalizedTaskId
    ? safeFlows.filter(flow => flow.taskId === normalizedTaskId)
    : safeFlows;
}


export function prioritizeSelectedFlow(flows, flowId, limit = 6) {
  const safeFlows = Array.isArray(flows) ? flows : [];
  const boundedLimit = Math.max(0, Math.trunc(Number(limit) || 0));
  const selected = safeFlows.find(flow => flow.id === flowId);
  if (!selected) return safeFlows.slice(0, boundedLimit);
  return [selected, ...safeFlows.filter(flow => flow.id !== flowId)]
    .slice(0, boundedLimit);
}


export function resolveLifecycleNavigationTarget(columnKey, focus) {
  const taskId = positiveInteger(focus?.taskId);
  if (taskId) return `${TASK_ROUTE}/${taskId}`;
  return QUALITY_COLUMNS.has(columnKey) ? QUALITY_ROUTE : TASK_ROUTE;
}


function positiveInteger(value) {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}
