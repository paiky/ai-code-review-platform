import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
const stylesSource = await readFile(new URL('../src/styles.css', import.meta.url), 'utf8');

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
  assert.equal(appSource.includes('function CodeQualityProgressView'), false);
  assert.equal(appSource.includes('formatAgentTraceDetail'), false);
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

test('renders terminal reviews in result first order and keeps the running Hero path', () => {
  const codeQualitySource = sourceBetween(
    'function CodeQualityReviewView',
    'function reviewJourneyStatusColor'
  );
  const terminalStart = codeQualitySource.indexOf('const resultContent = terminalResult ? (');
  const runningStart = codeQualitySource.indexOf(') : (', terminalStart);
  assert.notEqual(terminalStart, -1);
  assert.notEqual(runningStart, -1);
  const terminalSource = codeQualitySource.slice(terminalStart, runningStart);
  const resultIndex = terminalSource.indexOf('<ReviewResultSummary');
  const findingsIndex = terminalSource.indexOf('{findingsSection}');
  const journeyIndex = terminalSource.indexOf('<ReviewJourneyTimeline');

  assert.equal(resultIndex >= 0, true);
  assert.equal(findingsIndex > resultIndex, true);
  assert.equal(journeyIndex > findingsIndex, true);
  assert.equal(terminalSource.includes('<ReviewStatusHero'), false);
  assert.equal(codeQualitySource.slice(runningStart).includes('<ReviewJourneyExperience'), true);
  assert.equal(codeQualitySource.includes('if (isTerminalReviewStatus(journey?.status))'), true);
  assert.equal(codeQualitySource.includes('missingReviewPresentation'), true);
});

test('keeps task metadata after Review results and exposes one explicit back action', () => {
  const taskDetailSource = sourceBetween(
    'function TaskDetail',
    'function AgentBudgetFieldCard'
  );
  assert.equal(taskDetailSource.indexOf('{qualityReviewContent}') < taskDetailSource.indexOf('className="task-metadata-collapse"'), true);
  assert.equal((taskDetailSource.match(/onClick=\{onBack\}/g) || []).length, 1);
  assert.equal(taskDetailSource.includes('className="task-detail-back-action"'), true);
});

test('aligns task status with header metadata and keeps primary result actions on one desktop row', () => {
  const taskDetailSource = sourceBetween(
    'function TaskDetail',
    'function AgentBudgetFieldCard'
  );
  const resultSummarySource = sourceBetween(
    'function ReviewResultSummary',
    'function CodeQualityReviewView'
  );

  assert.equal(taskDetailSource.includes('const taskHeaderStatus = detail ? ('), true);
  assert.equal(taskDetailSource.includes('actionMeta={taskHeaderStatus}'), true);
  assert.equal(appSource.includes("pt: { lg: leading ? 4 : 0 }"), true);
  assert.equal(resultSummarySource.includes('className="review-result-fact-controls"'), true);
  assert.equal(
    resultSummarySource.indexOf('className="review-result-journey-link"')
      < resultSummarySource.indexOf('className="review-result-fact-actions"'),
    true
  );
  assert.match(stylesSource, /\.review-result-fact-controls\s*\{[\s\S]*?display:\s*flex;/);
  assert.match(stylesSource, /@media \(max-width: 600px\)[\s\S]*?\.review-result-fact-controls\s*\{[\s\S]*?flex-direction:\s*column;/);
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
    shellSource.includes('{(title || description || actions || actionMeta || leading) && <Paper'),
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

test('renders the model Review Drawer from SafeTraceViewModel without parsing raw progress detail', () => {
  const safeTraceSource = sourceBetween(
    'const safeTraceJourneyPhases',
    'function ReviewStageDrawerContent'
  );
  const drawerSource = sourceBetween(
    'function ReviewStageDrawerContent',
    'function OtherReviewJourneyEvents'
  );

  for (const prohibited of [
    'formatAgentTraceDetail',
    'parseProgressDetailJson',
    'JSON.parse',
    'displayLabel',
    'queryHash',
    'pathSummary',
    'rawResponse',
    'failureMessage',
    'workerId'
  ]) {
    assert.equal(safeTraceSource.includes(prohibited), false, prohibited);
    assert.equal(drawerSource.includes(prohibited), false, `drawer: ${prohibited}`);
  }

  assert.equal(safeTraceSource.includes('safeTraceActivityLabel(event.activityType)'), true);
  assert.equal(safeTraceSource.includes('返回条目 {event.itemCount}'), true);
  assert.equal(safeTraceSource.includes('证据调用累计'), true);
  assert.equal(safeTraceSource.includes('最近心跳'), false);
  assert.equal(safeTraceSource.includes('defaultActiveKey'), false);
  assert.equal(drawerSource.includes('stage.details?.safeTrace'), true);
});

test('keeps Safe Trace single-column and full-width in the frozen mobile Drawer breakpoint', () => {
  const mobileStart = stylesSource.indexOf('@media (max-width: 600px)');
  const mobileEnd = stylesSource.indexOf('@media (prefers-reduced-motion: reduce)', mobileStart);
  assert.notEqual(mobileStart, -1);
  assert.notEqual(mobileEnd, -1);
  const mobileSource = stylesSource.slice(mobileStart, mobileEnd);

  assert.match(stylesSource, /\.safe-trace-event\s*\{[\s\S]*grid-template-columns:\s*18px minmax\(0, 1fr\)/);
  assert.match(stylesSource, /\.safe-trace-event-body\s*\{[\s\S]*min-width:\s*0/);
  assert.equal(mobileSource.includes('.safe-trace-quota-grid'), true);
  assert.equal(mobileSource.includes('grid-template-columns: minmax(0, 1fr);'), true);
  assert.equal(mobileSource.includes('width: 100vw !important;'), true);
});
