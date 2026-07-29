import assert from 'node:assert/strict';
import test from 'node:test';

import {
  bytesToKilobytes,
  defaultAgentBudgets,
  formatAgentBudgetSummary,
  hasRaisedAgentBudget,
  kilobytesToBytes,
  normalizeAgentBudgets,
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
