import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');

function sourceBetween(start, end) {
  const startIndex = appSource.indexOf(start);
  const endIndex = appSource.indexOf(end, startIndex + start.length);
  assert.notEqual(startIndex, -1, `missing source marker: ${start}`);
  assert.notEqual(endIndex, -1, `missing source marker: ${end}`);
  return appSource.slice(startIndex, endIndex);
}

test('removes the old Review segmented navigation and top-level deterministic tab', () => {
  assert.equal(appSource.includes('const codeQualityViewOptions'), false);
  assert.equal(appSource.includes('<CodeQualityViewSwitcher'), false);
  assert.equal(appSource.includes("<HighAccuracyFlowView"), false);
  assert.equal(appSource.includes("<CodeQualityProgressView"), false);
  assert.equal(appSource.includes("<DeterministicChecksPanel"), false);
  assert.equal(
    /\{\s*key:\s*['"]deterministic['"]\s*,\s*label:\s*['"]确定性检查['"]/.test(appSource),
    false
  );
});

test('renders code quality directly without obsolete task tabs or a duplicate single-review identity row', () => {
  const taskDetailSource = sourceBetween(
    'function TaskDetail',
    'function AgentBudgetFieldCard'
  );
  const singleReviewSource = sourceBetween(
    'if (reviewItems.length <= 1)',
    'return ('
  );

  assert.equal(taskDetailSource.includes('const tabItems'), false);
  assert.equal(taskDetailSource.includes("label: '提醒卡片'"), false);
  assert.equal(taskDetailSource.includes("label: '分析结果'"), false);
  assert.equal(taskDetailSource.includes("label: '原始事件摘要'"), false);
  assert.equal(taskDetailSource.includes('<CodeQualityReviewsPanel'), true);
  assert.equal(taskDetailSource.includes('task-push-gate-collapse'), true);
  assert.equal(singleReviewSource.includes('<ReviewSelectorIdentity'), false);
});

test('keeps every migrated capability on an explicit Journey or finding entry', () => {
  for (const marker of [
    'ContextStageDrawerDetails',
    'PreflightStageDrawerDetails',
    '任务级确定性检查',
    '打开规则缺口诊断',
    '其它执行记录',
    'DiffViewerModal',
    'FixPreviewModal',
    'FindingRefinementControl',
    'ReviewFeedbackControl',
    'EvaluationCaseControl',
    '中断 AI Review',
    '重试 AI Review'
  ]) {
    assert.equal(appSource.includes(marker), true, marker);
  }
});

test('the migrated context and preflight drawers render only safe derived fields', () => {
  const contextSource = sourceBetween(
    'function ContextStageDrawerDetails',
    'function PreflightStageDrawerDetails'
  );
  const preflightSource = sourceBetween(
    'function PreflightStageDrawerDetails',
    'function ReviewStageDrawerContent'
  );
  const prohibitedFields = [
    'failureReason',
    'topRelativePaths',
    'remoteUrl',
    'filePath',
    'querySummary',
    'toolArguments',
    'workerId',
    'rawResponse'
  ];

  prohibitedFields.forEach(field => {
    assert.equal(contextSource.includes(field), false, `context: ${field}`);
    assert.equal(preflightSource.includes(field), false, `preflight: ${field}`);
  });
});
