import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildFindingRiskCounts,
  buildTerminalReviewResultPresentation,
  cleanFormalReviewSummary,
  highestRiskOriginalIndex,
  initializeFindingExpansionRegistry,
  isReviewFallback,
  mergeDeepLinkedFinding,
  resolveFindingDeepLink,
  resolveFormalReviewSummary,
  resolveInitialExpandedFindingIndexes,
  resolveReviewPresentationKey,
  setReviewExpandedFindingIndexes,
  severityWeight
} from '../src/reviewResultPresentation.js';

test('uses frozen severity weights without changing original finding order', () => {
  assert.deepEqual(
    ['CRITICAL', 'HIGH', 'MAJOR', 'MEDIUM', 'MINOR', 'LOW', 'UNKNOWN'].map(severityWeight),
    [4, 3, 3, 2, 2, 1, 0]
  );
  const findings = [
    { severity: 'LOW', title: 'first' },
    { severity: 'HIGH', title: 'second' },
    { severity: 'MAJOR', title: 'third' }
  ];
  const snapshot = structuredClone(findings);
  assert.equal(highestRiskOriginalIndex(findings), 1);
  assert.deepEqual(findings, snapshot);
});

test('counts every finding and keeps unknown severities visible', () => {
  assert.deepEqual(buildFindingRiskCounts([
    { severity: 'CRITICAL' },
    { severity: 'HIGH' },
    { severity: 'MAJOR' },
    { severity: 'MEDIUM' },
    { severity: 'MINOR' },
    { severity: 'LOW' },
    { severity: 'CUSTOM' },
    {}
  ]), {
    total: 8,
    critical: 1,
    high: 2,
    medium: 2,
    low: 1,
    unknown: 2
  });
});

test('uses only the formal summary and deterministic fallbacks', () => {
  assert.equal(cleanFormalReviewSummary('## **结论**\n- [`缓存`](https://example.invalid) 存在风险'), '结论\n缓存 存在风险');
  assert.equal(resolveFormalReviewSummary({ summary: '**Findings**' }, [{ severity: 'HIGH' }]), '本次 Review 共发现 1 个代码质量问题。');
  assert.equal(resolveFormalReviewSummary({ summary: '  ' }, []), '本次 Review 未发现需要报告的代码质量问题。');
  assert.equal(resolveFormalReviewSummary({ summary: '正式结论' }, [{ title: '不得据此生成摘要' }]), '正式结论');
});

test('recognizes fallback only from requested and effective engine fields', () => {
  assert.equal(isReviewFallback({ requestedEngine: 'AGENT', effectiveEngine: 'STANDARD_FALLBACK', status: 'SUCCESS' }), true);
  assert.equal(isReviewFallback({ requestedEngine: 'AGENT', effectiveEngine: 'AGENT', status: 'FALLBACK' }), false);
});

test('resolves review keys and finding deep links with original indexes', () => {
  assert.equal(resolveReviewPresentationKey({ reviewKey: 'review-a', id: 12 }, { selectorKey: 'selector-a' }), 'review-a');
  assert.equal(resolveReviewPresentationKey({ id: 12 }, { selectorKey: 'selector-a' }), 'selector-a');
  assert.deepEqual(resolveFindingDeepLink('#fix-preview-2', 3), { index: 2, kind: 'FIX_PREVIEW', targetId: 'fix-preview-2' });
  assert.deepEqual(resolveFindingDeepLink('#finding-1', 3), { index: 1, kind: 'FINDING', targetId: 'finding-1' });
  assert.equal(resolveFindingDeepLink('#fix-preview-3', 3), null);
  assert.equal(resolveFindingDeepLink('#fix-preview--1', 3), null);
});

test('initializes once from deep link or highest risk and merges later links', () => {
  const findings = [{ severity: 'LOW' }, { severity: 'CRITICAL' }, { severity: 'HIGH' }];
  assert.deepEqual(resolveInitialExpandedFindingIndexes(findings), [1]);
  assert.deepEqual(resolveInitialExpandedFindingIndexes(findings, '#fix-preview-2'), [2]);
  assert.deepEqual(resolveInitialExpandedFindingIndexes([], '#finding-0'), []);
  assert.deepEqual(mergeDeepLinkedFinding([1], '#finding-2', 3), [1, 2]);
  assert.deepEqual(mergeDeepLinkedFinding([1, 2], '#fix-preview-2', 3), [1, 2]);
});

test('isolates expansion by review key and polling never resets a manual choice', () => {
  const findings = [{ severity: 'LOW' }, { severity: 'HIGH' }];
  const initialized = initializeFindingExpansionRegistry({}, 'review-a', findings);
  assert.deepEqual(initialized, { 'review-a': [1] });

  const manuallyClosed = setReviewExpandedFindingIndexes(initialized, 'review-a', [], findings.length);
  const afterPolling = initializeFindingExpansionRegistry(
    manuallyClosed,
    'review-a',
    [{ severity: 'CRITICAL' }, { severity: 'LOW' }],
    '#finding-0'
  );
  assert.equal(afterPolling, manuallyClosed);
  assert.deepEqual(afterPolling['review-a'], []);

  const secondReview = initializeFindingExpansionRegistry(afterPolling, 'review-b', findings, '#fix-preview-0');
  assert.deepEqual(secondReview, { 'review-a': [], 'review-b': [0] });
});

test('builds truthful terminal result models and hides unreliable durations', () => {
  const review = {
    requestedEngine: 'AGENT',
    effectiveEngine: 'STANDARD_FALLBACK',
    status: 'SUCCESS',
    provider: 'DeepSeek',
    model: 'long-model',
    summary: '**Findings**',
    findings: [{ severity: 'HIGH' }],
    agentRunSummary: { runId: 19, durationMs: 180000 }
  };
  const result = buildTerminalReviewResultPresentation(review, {
    status: 'SUCCESS',
    engineLabel: 'Agent -> Standard fallback',
    providerModelLabel: 'DeepSeek / long-model',
    durationMs: 181000
  });
  assert.equal(result.title, 'Review 完成 · 已降级');
  assert.equal(result.reason, 'Standard Review 已接管并生成正式结果');
  assert.equal(result.issueCount, 1);
  assert.equal(result.durationMs, 181000);
  assert.equal(result.agentDurationMs, 180000);
  assert.equal(result.agentRunId, 19);

  const failed = buildTerminalReviewResultPresentation({ status: 'FAILED', findings: [], errorMessage: 'SECRET_STACK' }, { status: 'FAILED' });
  assert.equal(failed.reason, '本次 Review 未能成功完成。');
  assert.equal(JSON.stringify(failed).includes('SECRET_STACK'), false);
  assert.equal(failed.durationMs, null);
  assert.equal(failed.agentDurationMs, null);

  const failedFallback = buildTerminalReviewResultPresentation({
    requestedEngine: 'AGENT',
    effectiveEngine: 'STANDARD_FALLBACK',
    status: 'FAILED',
    findings: []
  }, { status: 'FAILED' });
  assert.equal(failedFallback.fallback, true);
  assert.equal(failedFallback.successfulFallback, false);
  assert.equal(failedFallback.title, 'Review 失败');
  assert.equal(failedFallback.reason, '本次 Review 未能成功完成。');

  const cancelled = buildTerminalReviewResultPresentation({ status: 'CANCELLED', findings: [] }, { status: 'CANCELLED' });
  assert.equal(cancelled.title, 'Review 已取消');
  assert.equal(cancelled.summary, '本次 Review 已取消。');

  const skipped = buildTerminalReviewResultPresentation({ status: 'SKIPPED', findings: [] }, { status: 'SKIPPED' });
  assert.equal(skipped.title, 'Review 已跳过');
  assert.equal(skipped.summary, '本次 Review 已跳过。');
});
