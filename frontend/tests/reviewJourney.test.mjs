import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildReviewJourney,
  buildReviewJourneys,
  buildTaskDeterministicCheckSummary,
  resolveReviewSelectionKey,
  REVIEW_JOURNEY_STAGE_DEFINITIONS,
  REVIEW_JOURNEY_STAGE_STATUSES
} from '../src/reviewJourney.js';

const NOW = Date.parse('2026-07-29T12:00:00Z');

function review(engine, status, reviewKey = `${engine.toLowerCase()}-review`) {
  return {
    id: `${engine}-${status}`,
    reviewKey,
    requestedEngine: engine,
    effectiveEngine: engine,
    provider: engine === 'AGENT' ? 'DeepSeek' : 'OpenAI',
    model: engine === 'AGENT' ? 'agent-model' : 'standard-model',
    status
  };
}

function progress(id, reviewKey, phase, createdAt, detail = '{}', level = 'INFO') {
  return { id, reviewKey, phase, createdAt, detail, level };
}

function stage(journey, id) {
  return journey.stages.find(item => item.id === id);
}

test('uses the fixed six stages and allowed stage statuses', () => {
  const journey = buildReviewJourney(
    review('STANDARD', 'RUNNING'),
    [progress(1, 'standard-review', 'PROVIDER_START', '2026-07-29T10:00:00Z')],
    { now: NOW }
  );

  assert.deepEqual(
    journey.stages.map(item => item.id),
    REVIEW_JOURNEY_STAGE_DEFINITIONS.map(item => item.id)
  );
  assert.equal(journey.stages.length, 6);
  journey.stages.forEach(item => {
    assert.equal(REVIEW_JOURNEY_STAGE_STATUSES.includes(item.status), true);
  });
});

test('normalizes Agent and Standard queued, running, success, failed, cancelled and skipped states', () => {
  for (const engine of ['AGENT', 'STANDARD']) {
    const reviewKey = `${engine.toLowerCase()}-state`;
    const scenarios = [
      {
        expected: 'QUEUED',
        reviewStatus: 'RUNNING',
        events: [progress(
          1,
          reviewKey,
          engine === 'AGENT' ? 'AGENT_QUEUED' : 'QUEUED',
          '2026-07-29T09:00:00Z'
        )],
        stageId: 'scheduling',
        stageStatus: 'ACTIVE'
      },
      {
        expected: 'RUNNING',
        reviewStatus: 'RUNNING',
        events: [progress(
          2,
          reviewKey,
          engine === 'AGENT' ? 'AGENT_ANALYZING' : 'PROVIDER_START',
          '2026-07-29T09:01:00Z',
          engine === 'AGENT' ? '{"runId":7,"claimAttempt":1,"sequence":0}' : '{}'
        )],
        stageId: 'model-review',
        stageStatus: 'ACTIVE'
      },
      {
        expected: 'SUCCESS',
        reviewStatus: 'SUCCESS',
        events: [progress(
          3,
          reviewKey,
          engine === 'AGENT' ? 'AGENT_FINISHED' : 'FINISHED',
          '2026-07-29T09:02:00Z',
          engine === 'AGENT' ? '{"runId":7,"claimAttempt":1}' : '{}'
        )],
        stageId: 'terminal',
        stageStatus: 'SUCCESS'
      },
      {
        expected: 'FAILED',
        reviewStatus: 'FAILED',
        events: [progress(4, reviewKey, 'FAILED', '2026-07-29T09:03:00Z', '{}', 'ERROR')],
        stageId: 'terminal',
        stageStatus: 'FAILED'
      },
      {
        expected: 'CANCELLED',
        reviewStatus: 'SKIPPED',
        events: [progress(
          5,
          reviewKey,
          engine === 'AGENT' ? 'AGENT_CANCELLED' : 'JOB_INTERRUPTED',
          '2026-07-29T09:04:00Z',
          engine === 'AGENT' ? '{"runId":7,"claimAttempt":1}' : '{}',
          'WARNING'
        )],
        stageId: 'terminal',
        stageStatus: 'CANCELLED'
      },
      {
        expected: 'SKIPPED',
        reviewStatus: 'SKIPPED',
        events: [],
        stageId: 'terminal',
        stageStatus: 'SKIPPED'
      }
    ];

    for (const scenario of scenarios) {
      const journey = buildReviewJourney(
        review(engine, scenario.reviewStatus, reviewKey),
        scenario.events,
        { now: NOW }
      );
      assert.equal(journey.status, scenario.expected, `${engine} ${scenario.expected}`);
      assert.equal(stage(journey, scenario.stageId).status, scenario.stageStatus);
      assert.equal(stage(journey, scenario.stageId).visible, true);
      assert.equal(
        journey.engineLabel,
        engine === 'AGENT' ? 'Agent Review' : 'Standard Review'
      );
    }
  }
});

test('keeps Agent to Standard fallback explicit without reporting Agent success', () => {
  const reviewKey = 'agent-fallback';
  const journey = buildReviewJourney({
    ...review('AGENT', 'SUCCESS', reviewKey),
    effectiveEngine: 'STANDARD_FALLBACK',
    provider: 'DeepSeek',
    model: 'fallback-model'
  }, [
    progress(1, reviewKey, 'AGENT_ANALYZING', '2026-07-29T09:00:00Z', '{"runId":8,"claimAttempt":1,"sequence":0}'),
    progress(2, reviewKey, 'AGENT_FALLBACK', '2026-07-29T09:01:00Z', '{"runId":8,"claimAttempt":1}'),
    progress(3, reviewKey, 'AGENT_FALLBACK_QUEUED', '2026-07-29T09:02:00Z'),
    progress(4, reviewKey, 'DEEPSEEK_REQUEST', '2026-07-29T09:03:00Z'),
    progress(5, reviewKey, 'DEEPSEEK_RESPONSE', '2026-07-29T09:04:00Z'),
    progress(6, reviewKey, 'JSON_PARSE_START', '2026-07-29T09:05:00Z'),
    progress(7, reviewKey, 'DEEPSEEK_PARSED', '2026-07-29T09:06:00Z'),
    progress(8, reviewKey, 'RESULT_SAVED', '2026-07-29T09:07:00Z'),
    progress(9, reviewKey, 'FINISHED', '2026-07-29T09:08:00Z')
  ], { now: NOW });

  assert.equal(journey.engineLabel, 'Agent -> Standard fallback');
  assert.equal(journey.engineKind, 'FALLBACK');
  assert.equal(journey.status, 'SUCCESS');
  assert.equal(journey.statusLabel, '已完成');
  assert.equal(stage(journey, 'terminal').status, 'WARNING');
  assert.equal(JSON.stringify(journey).includes('Agent Review 完成'), false);
});

test('isolates reviewKey events and merges only task-level AUTO_PREFLIGHT allowlist events', () => {
  const reviews = [
    review('STANDARD', 'SUCCESS', 'review-a'),
    review('STANDARD', 'SUCCESS', 'review-b')
  ];
  const events = [
    progress(1, null, 'DETERMINISTIC_PRECHECK_STARTED', '2026-07-29T08:00:00Z'),
    progress(2, null, 'DETERMINISTIC_PRECHECK_COMPLETED', '2026-07-29T08:01:00Z'),
    progress(3, null, 'STARTED', '2026-07-29T08:02:00Z'),
    progress(4, 'review-a', 'PROVIDER_START', '2026-07-29T08:03:00Z'),
    progress(5, 'review-b', 'PROVIDER_START', '2026-07-29T08:04:00Z'),
    progress(6, 'review-a', 'DETERMINISTIC_PRECHECK_REUSED', '2026-07-29T08:05:00Z'),
    progress(7, null, 'DETERMINISTIC_PRECHECK_REUSED', '2026-07-29T08:06:00Z')
  ];
  const [journeyA, journeyB] = buildReviewJourneys(reviews, events, { now: NOW });
  const idsA = journeyA.stages.flatMap(item => item.events.map(event => event.id));
  const idsB = journeyB.stages.flatMap(item => item.events.map(event => event.id));

  assert.deepEqual(idsA.sort((left, right) => left - right), [1, 2, 4, 6]);
  assert.deepEqual(idsB.sort((left, right) => left - right), [1, 2, 5]);
  assert.deepEqual(
    stage(journeyA, 'preflight').events.filter(event => event.shared).map(event => event.id),
    [1, 2]
  );
  assert.equal(idsA.includes(3), false);
  assert.equal(idsB.includes(3), false);
  assert.equal(idsA.includes(7), false);
  assert.equal(idsB.includes(7), false);
});

test('preserves URL direct selection and the current choice across polling', () => {
  const initial = buildReviewJourneys([
    review('STANDARD', 'RUNNING', 'review-a'),
    review('AGENT', 'RUNNING', 'review-b')
  ], [], { now: NOW });
  const fromUrl = resolveReviewSelectionKey(initial, {
    requestedReviewKey: 'review-b',
    preferRequested: true
  });
  assert.equal(fromUrl, 'review-b');

  const afterPolling = buildReviewJourneys([
    review('AGENT', 'SUCCESS', 'review-b'),
    review('STANDARD', 'SUCCESS', 'review-a')
  ], [], { now: NOW });
  assert.equal(resolveReviewSelectionKey(afterPolling, {
    requestedReviewKey: 'review-a',
    currentSelectionKey: fromUrl,
    preferRequested: false
  }), 'review-b');
  assert.equal(resolveReviewSelectionKey(
    afterPolling.filter(item => item.reviewKey !== 'review-b'),
    {
      currentSelectionKey: fromUrl,
      preferRequested: false
    }
  ), 'review-a');
  assert.equal(resolveReviewSelectionKey(afterPolling, {
    requestedReviewKey: 'review-a',
    currentSelectionKey: fromUrl,
    preferRequested: true
  }), 'review-a');
});

test('uses only the latest Agent run and claim attempt after lease recovery', () => {
  const reviewKey = 'agent-reclaimed';
  const journey = buildReviewJourney(
    review('AGENT', 'RUNNING', reviewKey),
    [
      progress(1, reviewKey, 'AGENT_ANALYZING', '2026-07-29T09:00:00Z', '{"runId":10,"claimAttempt":1,"sequence":0}'),
      progress(2, reviewKey, 'AGENT_TOOL_ACTIVITY', '2026-07-29T09:01:00Z', '{"runId":10,"claimAttempt":1,"sequence":1}'),
      progress(3, reviewKey, 'AGENT_RECLAIMED', '2026-07-29T09:02:00Z', '{"runId":10,"claimAttempt":2,"reasonCode":"LEASE_EXPIRED"}'),
      progress(4, reviewKey, 'AGENT_ANALYZING', '2026-07-29T09:03:00Z', '{"runId":10,"claimAttempt":2,"sequence":0}'),
      progress(5, reviewKey, 'AGENT_HEARTBEAT', '2026-07-29T09:04:00Z', '{"runId":10,"claimAttempt":2,"heartbeatSequence":0}'),
      progress(6, reviewKey, 'AGENT_FINISHED', '2026-07-29T09:05:00Z', '{"runId":10,"claimAttempt":1}')
    ],
    { now: NOW }
  );
  const modelEvents = stage(journey, 'model-review').events;

  assert.deepEqual(modelEvents.map(event => event.id), [3, 4, 5]);
  assert.equal(modelEvents.find(event => event.id === 5).auxiliary, true);
  assert.equal(stage(journey, 'terminal').events.length, 0);
  assert.equal(journey.currentStageId, 'model-review');
  assert.equal(journey.agentSummary.runId, 10);
  assert.equal(journey.agentSummary.claimAttempt, 2);
  assert.equal(journey.agentSummary.lastHeartbeatAt, '2026-07-29T09:04:00.000Z');
  assert.equal(
    stage(journey, 'model-review').safeMetrics.some(metric => metric.value === '第 2 次'),
    true
  );
  assert.equal(Object.hasOwn(modelEvents[0], 'detail'), false);
});

test('safely handles historical results, missing fields, damaged detail and invalid time data', () => {
  const historical = buildReviewJourney(
    { id: 90, reviewKey: null, status: 'SUCCESS' },
    [],
    { now: NOW }
  );
  assert.equal(historical.engineLabel, '历史任务未记录');
  assert.equal(historical.status, 'SUCCESS');
  assert.equal(historical.providerModelLabel, 'Provider/model 未记录');
  assert.equal(historical.startedAt, null);
  assert.equal(historical.finishedAt, null);
  assert.equal(historical.durationMs, null);
  assert.equal(historical.stages.every(item => item.visible === false), true);

  const damaged = buildReviewJourney(
    review('STANDARD', 'RUNNING', 'damaged'),
    [
      progress(10, 'damaged', 'JSON_PARSE_START', 'not-a-time', '{broken-detail'),
      progress(8, 'damaged', 'STARTED', '2026-07-29T08:00:00Z'),
      progress(9, 'damaged', 'PROVIDER_START', '2026-07-29T09:00:00Z'),
      progress(11, 'damaged', 'OUTPUT_EXTRACTED', '2026-07-29T10:00:00Z'),
      progress(12, 'damaged', 'RESULT_SAVED', '2026-07-30T10:00:00Z')
    ],
    { now: NOW }
  );
  assert.equal(damaged.currentStageId, 'parse-save');
  assert.equal(stage(damaged, 'parse-save').status, 'ACTIVE');
  assert.equal(stage(damaged, 'parse-save').finishedAt, null);
  assert.equal(stage(damaged, 'parse-save').durationMs, null);
  assert.equal(JSON.stringify(damaged).includes('broken-detail'), false);

  const reversedReviewTimes = buildReviewJourney({
    ...review('STANDARD', 'SUCCESS', 'reversed'),
    startedAt: '2026-07-29T10:00:00Z',
    finishedAt: '2026-07-29T09:00:00Z'
  }, [], { now: NOW });
  assert.equal(reversedReviewTimes.startedAt, '2026-07-29T10:00:00.000Z');
  assert.equal(reversedReviewTimes.finishedAt, null);
  assert.equal(reversedReviewTimes.durationMs, null);
});

test('does not share unscoped legacy events across multiple results missing reviewKey', () => {
  const journeys = buildReviewJourneys([
    { id: 1, status: 'SUCCESS' },
    { id: 2, status: 'FAILED' }
  ], [
    progress(1, null, 'STARTED', '2026-07-29T08:00:00Z'),
    progress(2, null, 'FINISHED', '2026-07-29T08:01:00Z')
  ], { now: NOW });

  assert.deepEqual(journeys.map(item => item.selectorKey), ['legacy:1', 'legacy:2']);
  assert.equal(journeys.every(item => item.engineLabel === '历史任务未记录'), true);
  assert.equal(journeys.every(item => item.stages.every(value => value.events.length === 0)), true);
  assert.equal(journeys.every(item => item.stages.every(value => value.visible === false)), true);
});

test('derives the complete high-accuracy context summary from strict safe fields', () => {
  const reviewKey = 'context-complete';
  const contextDetail = {
    summary: {
      changedFileCount: 3,
      diffBytes: 2048,
      plannerSignalCount: 4,
      plannerTargetType: 'BACKEND',
      detectedLanguages: ['Java', 'Kotlin'],
      plannerSignalTypeCounts: [
        { type: 'DTO_FIELD_CHANGED', count: 2 },
        { type: 'CACHE_KEY_CHANGED', count: 2 }
      ],
      retrieverSupportedSignalTypes: ['DTO_FIELD_CHANGED'],
      retrieverUnsupportedSignalTypeCounts: [{ type: 'CACHE_KEY_CHANGED', count: 2 }],
      localRepository: { enabled: true, status: 'PREPARED', ignored: 'DO_NOT_RENDER' },
      localReferenceSearch: {
        status: 'COMPLETED',
        queryCount: 2,
        matchedFileCount: 3,
        includedSnippetCount: 4,
        ignored: 'DO_NOT_RENDER'
      },
      requestedContextAvailability: {
        available: 1,
        unavailable: 1,
        items: [
          { type: 'DTO_USAGE_CONTEXT', available: true, signalCount: 2, priority: 'HIGH' },
          { type: 'CACHE_USAGE_CONTEXT', available: false, signalCount: 2, reasonCode: 'UNSUPPORTED_SIGNAL' }
        ]
      },
      budgetCutSummary: {
        truncated: true,
        changedFilesExcluded: 1,
        sameFileSourceSnippetsRemoved: 2,
        localReferenceSnippetsRemoved: 3,
        protectedSignalTypes: ['DTO_FIELD_CHANGED'],
        notInjectedEvidence: [
          { matchedFileCount: 2, cutSnippetCount: 3, ignored: 'DO_NOT_RENDER' }
        ]
      },
      ruleGapSummary: { total: 2 },
      ruleGapItems: [
        { gapType: 'UNSUPPORTED_PLANNER_SIGNAL', ignored: 'DO_NOT_RENDER' },
        { gapType: 'BUDGET_CUT', ignored: 'DO_NOT_RENDER' }
      ]
    },
    meta: { truncated: true }
  };
  const journey = buildReviewJourney({
    ...review('STANDARD', 'SUCCESS', reviewKey),
    findings: [
      { refinementOverlay: { status: 'COMPLETED', ignored: 'DO_NOT_RENDER' } },
      { refinementOverlay: { status: 'FAILED', ignored: 'DO_NOT_RENDER' } }
    ]
  }, [
    progress(1, reviewKey, 'CONTEXT_PACK_BUILT', '2026-07-29T08:00:00Z', JSON.stringify(contextDetail)),
    progress(2, reviewKey, 'LOCAL_REPO_PREPARED', '2026-07-29T08:01:00Z', '{"status":"PREPARED"}'),
    progress(3, reviewKey, 'LOCAL_CONTEXT_RETRIEVED', '2026-07-29T08:02:00Z', '{"status":"COMPLETED","queryCount":2,"matchedFileCount":3,"includedSnippetCount":4}')
  ], { now: NOW });
  const contextStage = stage(journey, 'context');
  const details = contextStage.details.context;

  assert.equal(contextStage.visible, true);
  assert.equal(contextStage.status, 'SUCCESS');
  assert.equal(details.detailState, 'AVAILABLE');
  assert.deepEqual(details.contextPack, {
    built: true,
    changedFileCount: 3,
    truncated: true
  });
  assert.equal('diffBytes' in details.contextPack, false);
  assert.deepEqual(details.repository, { status: 'PREPARED', enabled: true });
  assert.equal(details.retriever.status, 'COMPLETED');
  assert.equal(details.retriever.requestCount, 2);
  assert.equal(details.requestedContext.items.length, 2);
  assert.equal(details.budgetCuts.notInjectedEvidenceCount, 1);
  assert.equal(details.budgetCuts.cutSnippetCount, 3);
  assert.deepEqual(details.refinement, { total: 2, completed: 1, failed: 1 });
  assert.deepEqual(details.ruleGaps.typeCounts, [
    { type: 'UNSUPPORTED_PLANNER_SIGNAL', count: 1 },
    { type: 'BUDGET_CUT', count: 1 }
  ]);
  assert.equal(JSON.stringify(details).includes('DO_NOT_RENDER'), false);
});

test('keeps repository and retriever failures as context warnings and safely handles damaged detail', () => {
  const failed = buildReviewJourney(
    review('STANDARD', 'SUCCESS', 'context-failed'),
    [
      progress(1, 'context-failed', 'LOCAL_REPO_PREPARE_FAILED', '2026-07-29T08:00:00Z', '{damaged'),
      progress(2, 'context-failed', 'LOCAL_CONTEXT_RETRIEVE_FAILED', '2026-07-29T08:01:00Z', '{damaged')
    ],
    { now: NOW }
  );
  const failedStage = stage(failed, 'context');

  assert.equal(failedStage.status, 'WARNING');
  assert.equal(failedStage.details.context.detailState, 'UNAVAILABLE');
  assert.equal(failedStage.details.context.repository.status, 'UNAVAILABLE');
  assert.equal(failedStage.details.context.retriever.status, 'UNAVAILABLE');
  assert.equal(JSON.stringify(failed).includes('{damaged'), false);

  const absent = buildReviewJourney(
    review('STANDARD', 'SUCCESS', 'context-absent'),
    [],
    { now: NOW }
  );
  assert.equal(stage(absent, 'context').visible, false);
  assert.equal(stage(absent, 'context').details.context, null);
});

test('separates AUTO_PREFLIGHT from the task-level latest record and preserves reuse isolation', () => {
  const checks = {
    latestRun: {
      id: 91,
      checkType: 'SECRET_SCAN',
      status: 'COMPLETED',
      configSnapshot: {
        trigger: 'MANUAL',
        freshness: 'CURRENT_TASK_INPUT',
        scope: 'DIFF_ADDED_LINES'
      },
      resultSummary: {
        scannedFileCount: 5,
        addedLineCount: 12,
        findingCount: 1,
        truncated: false,
        ruleTypeCounts: { CREDENTIAL_PATTERN: 1 }
      },
      findings: [{ ignored: 'DO_NOT_RENDER' }],
      failureReason: 'DO_NOT_RENDER',
      durationMs: 42,
      startedAt: '2026-07-29T08:10:00Z',
      finishedAt: '2026-07-29T08:10:01Z'
    }
  };
  const journeys = buildReviewJourneys([
    review('STANDARD', 'SUCCESS', 'preflight-a'),
    review('STANDARD', 'SUCCESS', 'preflight-b')
  ], [
    progress(1, null, 'DETERMINISTIC_PRECHECK_STARTED', '2026-07-29T08:00:00Z', '{"runId":7,"checkType":"SECRET_SCAN","trigger":"AUTO_PREFLIGHT"}'),
    progress(2, null, 'DETERMINISTIC_PRECHECK_COMPLETED', '2026-07-29T08:01:00Z', '{"runId":7,"checkType":"SECRET_SCAN","trigger":"AUTO_PREFLIGHT","findingCount":2}'),
    progress(3, 'preflight-a', 'DETERMINISTIC_PRECHECK_REUSED', '2026-07-29T08:02:00Z', '{"runId":7,"status":"COMPLETED","freshness":"CURRENT_TASK_INPUT"}')
  ], { now: NOW, deterministicChecks: checks });
  const first = stage(journeys[0], 'preflight').details.preflight;
  const second = stage(journeys[1], 'preflight').details.preflight;

  assert.equal(first.auto.shared, true);
  assert.equal(first.auto.reused, true);
  assert.equal(first.auto.runId, 7);
  assert.equal(first.auto.findingCount, 2);
  assert.equal(second.auto.shared, true);
  assert.equal(second.auto.reused, false);
  assert.equal(first.taskLatest.trigger, 'MANUAL');
  assert.equal(first.taskLatest.findingCount, 1);
  assert.deepEqual(first.taskLatest.ruleTypeCounts, [{ type: 'CREDENTIAL_PATTERN', count: 1 }]);
  assert.equal(JSON.stringify(first).includes('DO_NOT_RENDER'), false);
});

test('keeps preflight failure fail-open and never lets manual history create a Review stage', () => {
  const failed = buildReviewJourney(
    review('STANDARD', 'SUCCESS', 'preflight-failed'),
    [
      progress(
        1,
        null,
        'DETERMINISTIC_PRECHECK_FAILED',
        '2026-07-29T08:00:00Z',
        '{"runId":8,"checkType":"SECRET_SCAN","trigger":"AUTO_PREFLIGHT","status":"FAILED","failureReason":"DO_NOT_RENDER"}',
        'WARN'
      )
    ],
    { now: NOW }
  );
  const auto = stage(failed, 'preflight').details.preflight.auto;
  assert.equal(stage(failed, 'preflight').status, 'WARNING');
  assert.equal(auto.status, 'FAILED');
  assert.equal(auto.failOpen, true);
  assert.equal(JSON.stringify(auto).includes('DO_NOT_RENDER'), false);

  const manualOnly = buildReviewJourney(
    review('STANDARD', 'SUCCESS', 'manual-only'),
    [],
    {
      now: NOW,
      deterministicChecks: {
        latestRun: {
          id: 9,
          checkType: 'SECRET_SCAN',
          status: 'COMPLETED',
          configSnapshot: { trigger: 'MANUAL' },
          resultSummary: { findingCount: 0 }
        }
      }
    }
  );
  const manualStage = stage(manualOnly, 'preflight');
  assert.equal(manualStage.visible, false);
  assert.equal(manualStage.status, 'WAITING');
  assert.equal(manualStage.startedAt, null);
  assert.equal(manualStage.finishedAt, null);
  assert.equal(manualStage.durationMs, null);
  assert.equal(manualStage.details.preflight.auto, null);
  assert.equal(manualStage.details.preflight.taskLatest.trigger, 'MANUAL');
});

test('publishes only allowlisted fixed other execution records', () => {
  const journey = buildReviewJourney(
    review('AGENT', 'RUNNING', 'other-events'),
    [
      progress(1, 'other-events', 'AGENT_SENSITIVE_PATHS_EXCLUDED', '2026-07-29T08:00:00Z', '{"ignored":"DO_NOT_RENDER"}'),
      progress(2, 'other-events', 'PROMPT_METADATA', '2026-07-29T08:01:00Z', '{"ignored":"DO_NOT_RENDER"}'),
      progress(3, 'other-events', 'CODEX_OUTPUT', '2026-07-29T08:02:00Z', 'DO_NOT_RENDER')
    ],
    { now: NOW }
  );

  assert.deepEqual(journey.otherEvents.map(item => item.phase), ['AGENT_SENSITIVE_PATHS_EXCLUDED']);
  assert.equal(JSON.stringify(journey.otherEvents).includes('DO_NOT_RENDER'), false);
});

test('sanitizes standalone task-level deterministic summaries', () => {
  assert.equal(buildTaskDeterministicCheckSummary(null, NOW), null);
  const summary = buildTaskDeterministicCheckSummary({
    latestRun: {
      id: -1,
      checkType: 'SECRET_SCAN',
      status: 'COMPLETED',
      configSnapshot: { trigger: 'UNKNOWN_TRIGGER', scope: 'DIFF_ADDED_LINES' },
      resultSummary: { findingCount: 2, ruleTypeCounts: { SAFE_ENUM: 2, 'not safe': 4 } },
      finishedAt: '2099-01-01T00:00:00Z'
    }
  }, NOW);

  assert.equal(summary.runId, null);
  assert.equal(summary.trigger, null);
  assert.equal(summary.findingCount, 2);
  assert.deepEqual(summary.ruleTypeCounts, [{ type: 'SAFE_ENUM', count: 2 }]);
  assert.equal(summary.finishedAt, null);
});
