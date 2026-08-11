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

test('temporarily hides deferred product entries without deleting their capabilities', () => {
  for (const marker of [
    'const QUALITY_GOVERNANCE_NAV_VISIBLE = false',
    'const EVALUATION_CASE_ACTION_VISIBLE = false',
    'const FINDING_REFINEMENT_ACTION_VISIBLE = false',
    'const STANDARD_REVIEW_COMPARISON_ACTION_VISIBLE = false',
    'qualityGovernanceVisible: QUALITY_GOVERNANCE_NAV_VISIBLE',
    'EVALUATION_CASE_ACTION_VISIBLE &&',
    'FINDING_REFINEMENT_ACTION_VISIBLE &&',
    'STANDARD_REVIEW_COMPARISON_ACTION_VISIBLE'
  ]) {
    assert.equal(appSource.includes(marker), true, marker);
  }

  for (const preserved of [
    'function ReviewImmersiveWorkspace',
    'function EvaluationCaseControl',
    'function FindingRefinementControl',
    '追加普通 Review 对照',
    '<Route path={REVIEW_QUALITY_ROUTE}'
  ]) {
    assert.equal(appSource.includes(preserved), true, preserved);
  }

  for (const removedDescription of [
    '查看 GitLab MR、Push 和手动审查任务，按项目、端类型、触发类型和 Review 状态筛选。',
    '维护全局 Review 能力、项目组、端类型、模型 Provider、AI Review Profile 和 Push 审核策略。',
    '查看近期功能变化、部署注意和验证提示。',
    '按 GitLab Webhook、钉钉机器人、平台项目组、GitLab 项目和模型配置的顺序完成接入。'
  ]) {
    assert.equal(appSource.includes(removedDescription), false, removedDescription);
  }
});

test('removes the complete standalone page header from the primary utility pages', () => {
  const pageRanges = [
    ['function TaskList({', 'function ReviewFeedbackControl'],
    ['function TemplateConfig()', 'function TaskListPage()'],
    ['function ReleaseNotesPage()', 'function HelpImage'],
    ['function HelpPage()', 'function ReviewQualityDashboardPage']
  ];

  for (const [start, end] of pageRanges) {
    const pageSource = sourceBetween(start, end);
    assert.equal(pageSource.includes('<TaskWorkspaceShell>'), true, start);
    assert.equal(/<TaskWorkspaceShell\s+[^>]*title=/.test(pageSource), false, start);
  }

  const shellSource = sourceBetween(
    'function TaskWorkspaceShell',
    'function TaskList'
  );
  assert.equal(
    shellSource.includes('{(title || description || actions || leading) && <Paper'),
    true
  );
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

test('renders only bounded Agent submission diagnostics in both fallback alerts', () => {
  const diagnosticSource = sourceBetween(
    'function agentFallbackDiagnostic',
    'function StageAlertPopoverContent'
  );

  assert.equal(diagnosticSource.includes('formatAgentFailureChain'), true);
  assert.equal(diagnosticSource.includes('submitAttemptCount'), true);
  assert.equal(diagnosticSource.includes('maxSubmitAttempts'), true);
  assert.equal(diagnosticSource.includes('safeReviewErrorCode'), true);
  assert.equal(diagnosticSource.includes('rawCard'), false);
  assert.equal(diagnosticSource.includes('violations'), false);
  assert.equal((appSource.match(/agentFallbackDiagnostic\(/g) || []).length, 3);
});
