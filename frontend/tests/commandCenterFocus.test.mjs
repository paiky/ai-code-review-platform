import assert from 'node:assert/strict';
import test from 'node:test';

import {
  EMPTY_COMMAND_CENTER_FOCUS,
  flowsForCommandCenterTask,
  prioritizeSelectedFlow,
  reconcileCommandCenterFocus,
  resolveLifecycleNavigationTarget,
  selectCommandCenterFlow,
  selectCommandCenterTask
} from '../src/command-center/commandCenterFocus.js';


const runtime = {
  activeTasks: [
    { taskId: 41, projectName: 'alpha' },
    { taskId: 42, projectName: 'beta' }
  ],
  activeFlows: [
    { id: '41:standard-main', taskId: 41, reviewKey: 'standard-main' },
    { id: '41:agent-main', taskId: 41, reviewKey: 'agent-main' },
    { id: '42:standard-main', taskId: 42, reviewKey: 'standard-main' }
  ]
};


test('keeps multiple reviewKey branches independently focusable for one task', () => {
  assert.deepEqual(selectCommandCenterTask(41), { taskId: 41, flowId: null });
  assert.deepEqual(
    flowsForCommandCenterTask(runtime.activeFlows, 41).map(flow => flow.id),
    ['41:standard-main', '41:agent-main']
  );
  assert.deepEqual(selectCommandCenterFlow(runtime.activeFlows[1]), {
    taskId: 41,
    flowId: '41:agent-main'
  });
});


test('reconciles focus after polling without inventing task or flow state', () => {
  const focused = { taskId: 41, flowId: '41:agent-main' };
  assert.deepEqual(reconcileCommandCenterFocus(runtime, focused), focused);
  assert.deepEqual(
    reconcileCommandCenterFocus(
      { ...runtime, activeFlows: runtime.activeFlows.slice(0, 1) },
      focused
    ),
    { taskId: 41, flowId: null }
  );
  assert.equal(
    reconcileCommandCenterFocus({ activeTasks: [], activeFlows: [] }, focused),
    EMPTY_COMMAND_CENTER_FOCUS
  );
});


test('keeps a selected flow visible in bounded topology and Live Operations lists', () => {
  const flows = Array.from({ length: 25 }, (_, index) => ({
    id: `41:flow-${index}`,
    taskId: 41
  }));
  const selected = flows[24];

  assert.deepEqual(
    prioritizeSelectedFlow(flows, selected.id, 6).map(flow => flow.id),
    [selected.id, ...flows.slice(0, 5).map(flow => flow.id)]
  );
});


test('lifecycle drill-down resolves only existing task and quality routes', () => {
  assert.equal(resolveLifecycleNavigationTarget('intake', EMPTY_COMMAND_CENTER_FOCUS), '/tasks');
  assert.equal(resolveLifecycleNavigationTarget('rule', EMPTY_COMMAND_CENTER_FOCUS), '/tasks');
  assert.equal(resolveLifecycleNavigationTarget('execution', EMPTY_COMMAND_CENTER_FOCUS), '/review-quality');
  assert.equal(resolveLifecycleNavigationTarget('delivery', EMPTY_COMMAND_CENTER_FOCUS), '/review-quality');
  assert.equal(
    resolveLifecycleNavigationTarget('delivery', { taskId: 41, flowId: '41:failed' }),
    '/tasks/41'
  );
});
