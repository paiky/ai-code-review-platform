import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  COMMAND_CENTER_M4_SCENARIOS,
  commandCenterGovernanceFixture,
  commandCenterRuntimeFixture
} from '../../scripts/command-center-m4-fixtures.mjs';
import { normalizeGovernanceSnapshot, normalizeRuntimeSnapshot } from '../src/command-center/commandCenterModel.js';
import { buildCommandCenterPresentation } from '../src/command-center/commandCenterPresentation.js';
import { commandCenterMotionScene } from '../src/command-center/commandCenterVisual.js';


const NOW = Date.parse('2026-08-05T02:00:00.000Z');


test('M4 fixtures drive every truthful activity state through normalize and Presentation', () => {
  const expectations = {
    idle: ['idle', 'idle', 'idle', false],
    'agent-queued': ['queued', 'queued', 'idle', false],
    'standard-queued': ['queued', 'idle', 'queued', false],
    'agent-running': ['running', 'running', 'idle', false],
    'standard-running': ['running', 'idle', 'running', false],
    'dual-running': ['running', 'running', 'running', false],
    'fallback-running': ['running', 'idle', 'running', true]
  };

  for (const [scenario, expected] of Object.entries(expectations)) {
    const presentation = present(scenario);
    const scene = commandCenterMotionScene(presentation);
    assert.deepEqual([
      scene.activity,
      scene.lanes.agent.activity,
      scene.lanes.standard.activity,
      scene.fallbackActive
    ], expected, scenario);
  }

  const fallback = commandCenterMotionScene(present('fallback-running'));
  assert.equal(fallback.connections['engine-agent'].activity, 'running');
  assert.equal(fallback.connections['engine-standard'].active, false);
  assert.equal(fallback.connections['agent-standard'].activity, 'running');
  assert.equal(fallback.connections['standard-result'].activity, 'running');
});


test('M4 stale and error resources pause all continuous motion', () => {
  const stale = commandCenterMotionScene(present('stale'));
  assert.equal(stale.activity, 'paused');
  assert.equal(Object.values(stale.connections).some(connection => connection.active), false);

  const errorEmpty = commandCenterMotionScene(buildCommandCenterPresentation({
    runtimeError: 'Synthetic Runtime failure'
  }));
  assert.equal(errorEmpty.activity, 'paused');

  const retained = commandCenterMotionScene(buildCommandCenterPresentation({
    runtime: normalizeRuntimeSnapshot(commandCenterRuntimeFixture('dual-running', NOW), { now: NOW }),
    runtimeError: 'Synthetic Runtime failure'
  }));
  assert.equal(retained.activity, 'paused');
});


test('M4 fixtures keep task bounds safe links and quality totals truthful', () => {
  const presentation = present('dual-running');
  assert.equal(presentation.taskQueue.visibleCount, 3);
  assert.equal(presentation.taskQueue.overflowCount, 1);
  assert.equal(presentation.taskQueue.items.every(item => item.externalUrl?.startsWith('https://')), true);
  assert.deepEqual(
    presentation.taskQueue.items.map(item => item.triggerLabel),
    ['Merge Request', 'Push', '手动审查']
  );
  assert.deepEqual({
    total: presentation.todayResults.totalCount,
    completed: presentation.todayResults.completedCount,
    success: presentation.todayResults.successCount,
    failure: presentation.todayResults.failureCount,
    skipped: presentation.todayResults.skippedCount,
    running: presentation.todayResults.runningCount
  }, { total: 31, completed: 27, success: 24, failure: 2, skipped: 1, running: 4 });
  assert.equal(presentation.qualityOutput.findingRisk.findingCount, 27);
  assert.equal(presentation.qualityOutput.findingRisk.affectedTaskCount, 11);
});


test('M4 mock server exposes only fixed scenario switching and read-only snapshot APIs', async () => {
  const source = await readFile(new URL('../../scripts/command-center-m4-mock-server.mjs', import.meta.url), 'utf8');
  assert.deepEqual(COMMAND_CENTER_M4_SCENARIOS, [
    'idle', 'agent-queued', 'standard-queued', 'agent-running', 'standard-running', 'dual-running',
    'fallback-running', 'stale', 'runtime-error', 'governance-error'
  ]);
  assert.equal(source.includes("request.method === 'POST' && scenarioMatch"), true);
  assert.equal(source.includes("url.pathname === '/api/command-center/runtime'"), true);
  assert.equal(source.includes("url.pathname === '/api/command-center/governance'"), true);
  assert.equal(source.includes("sendError(reply, 503, 'Synthetic Runtime failure')"), true);
  assert.equal(source.includes('database'), false);
});


function present(scenario) {
  return buildCommandCenterPresentation({
    runtime: normalizeRuntimeSnapshot(commandCenterRuntimeFixture(scenario, NOW), { now: NOW }),
    governance: normalizeGovernanceSnapshot(commandCenterGovernanceFixture(NOW), { now: NOW })
  });
}
