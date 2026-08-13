import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildAgentBudgetOptions,
  bytesToKilobytes,
  defaultAgentBudgets,
  formatAgentBudgetSummary,
  hasRaisedAgentBudget,
  kilobytesToBytes,
  normalizeAgentBudgets,
  recommendedAgentBudgetValues,
  validateAgentBudgets
} from '../src/agentReviewBudgets.js';

test('uses server budgets and safely falls back to defaults', () => {
  assert.deepEqual(normalizeAgentBudgets({}), defaultAgentBudgets);
  assert.equal(normalizeAgentBudgets({
    budgets: { ...defaultAgentBudgets, maxTurns: 14 }
  }).maxTurns, 14);
  assert.equal(normalizeAgentBudgets({
    budgets: { ...defaultAgentBudgets, maxTurns: 'broken' }
  }).maxTurns, defaultAgentBudgets.maxTurns);
});

test('converts byte budgets to and from UI kilobytes', () => {
  assert.equal(bytesToKilobytes(200000), 200);
  assert.equal(kilobytesToBytes(200), 200000);
  assert.equal(kilobytesToBytes(10.5), 10500);
});

test('validates ranges and all cross-field constraints', () => {
  assert.equal(validateAgentBudgets(defaultAgentBudgets), null);
  assert.match(
    validateAgentBudgets({ ...defaultAgentBudgets, maxTurns: 19 }),
    /maxTurns/
  );
  assert.match(
    validateAgentBudgets({
      ...defaultAgentBudgets,
      maxEvidenceCalls: 10,
      convergeAtCalls: 9
    }),
    /收敛起点/
  );
  assert.match(
    validateAgentBudgets({
      ...defaultAgentBudgets,
      maxTurns: 12,
      submitByTurn: 10
    }),
    /提交回合/
  );
  assert.match(
    validateAgentBudgets({
      ...defaultAgentBudgets,
      maxToolCalls: 10,
      maxEvidenceCalls: 10
    }),
    /工具调用/
  );
});

test('builds bounded recommended options and preserves server defaults plus custom values', () => {
  const settings = {
    budgetDefaults: { ...defaultAgentBudgets, timeoutSeconds: 300 },
    budgetLimits: {
      maxTurns: { min: 9, max: 16 },
      timeoutSeconds: { min: 60, max: 600 }
    }
  };
  const customBudgets = {
    ...defaultAgentBudgets,
    maxTurns: 15,
    timeoutSeconds: 450
  };
  const turnOptions = buildAgentBudgetOptions('maxTurns', customBudgets, settings);
  const timeoutOptions = buildAgentBudgetOptions('timeoutSeconds', customBudgets, settings);

  assert.deepEqual(
    turnOptions.map(option => option.value),
    [9, 12, 14, 15, 16]
  );
  assert.equal(turnOptions.find(option => option.value === 15)?.isCurrentCustom, true);
  assert.equal(timeoutOptions.find(option => option.value === 300)?.isDefault, true);
  assert.equal(timeoutOptions.find(option => option.value === 450)?.isCurrentCustom, true);
  assert.equal(timeoutOptions.some(option => option.value === 900), false);
  assert.deepEqual(recommendedAgentBudgetValues.maxSourceBytes, [
    10_000,
    50_000,
    100_000,
    200_000,
    300_000
  ]);
});

test('disables recommended choices that violate cross-field constraints', () => {
  const turnOptions = buildAgentBudgetOptions('maxTurns', defaultAgentBudgets, {});
  const toolOptions = buildAgentBudgetOptions('maxToolCalls', defaultAgentBudgets, {});
  const evidenceOptions = buildAgentBudgetOptions('maxEvidenceCalls', defaultAgentBudgets, {});
  const convergeOptions = buildAgentBudgetOptions('convergeAtCalls', defaultAgentBudgets, {});
  const submitOptions = buildAgentBudgetOptions('submitByTurn', defaultAgentBudgets, {});

  assert.match(turnOptions.find(option => option.value === 9)?.disabledReason, /提交回合/);
  assert.match(toolOptions.find(option => option.value === 10)?.disabledReason, /工具调用/);
  assert.match(evidenceOptions.find(option => option.value === 8)?.disabledReason, /收敛起点/);
  assert.match(convergeOptions.find(option => option.value === 10)?.disabledReason, /收敛起点/);
  assert.match(submitOptions.find(option => option.value === 12)?.disabledReason, /提交回合/);
  assert.equal(turnOptions.find(option => option.value === 12)?.disabled, false);
});

test('detects raised budgets and keeps task detail compatible without snapshots', () => {
  assert.equal(hasRaisedAgentBudget(defaultAgentBudgets), false);
  assert.equal(
    hasRaisedAgentBudget({ ...defaultAgentBudgets, maxTurns: 14 }),
    true
  );
  assert.equal(formatAgentBudgetSummary(undefined), '');
  assert.equal(formatAgentBudgetSummary({ maxTurns: 12 }), '');
  assert.match(formatAgentBudgetSummary(defaultAgentBudgets), /12 turns/);
});
