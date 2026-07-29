import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildReviewHeroModel,
  buildStageAlertModel,
  isReviewJourneyDismissKey,
  isReviewStageActivationKey,
  resolveOpenReviewJourneyStage,
  reviewTimelineMode,
  reviewTimelineOrientation,
  shouldAnimateReview,
  visibleReviewJourneyStages
} from '../src/reviewJourneyPresentation.js';
import { buildReviewJourney } from '../src/reviewJourney.js';

const NOW = Date.parse('2026-07-29T12:00:00Z');

function review(engine, status, reviewKey = `${engine.toLowerCase()}-${status.toLowerCase()}`) {
  return {
    id: reviewKey,
    reviewKey,
    requestedEngine: engine,
    effectiveEngine: engine,
    provider: engine === 'AGENT' ? 'DeepSeek' : 'OpenAI',
    model: engine === 'AGENT' ? 'agent-model' : 'standard-model',
    status
  };
}

function event(id, reviewKey, phase, detail = '{}', level = 'INFO', createdAt = null) {
  return {
    id,
    reviewKey,
    phase,
    detail,
    level,
    createdAt: createdAt || `2026-07-29T10:0${id}:00Z`
  };
}

function stage(journey, stageId) {
  return journey.stages.find(item => item.id === stageId);
}

test('builds Agent and Standard Hero states for queued running and every terminal status', () => {
  for (const engine of ['AGENT', 'STANDARD']) {
    const reviewKey = `${engine.toLowerCase()}-hero`;
    const kind = engine === 'AGENT' ? 'BRAIN' : 'PROVIDER';
    const queuedPhase = engine === 'AGENT' ? 'AGENT_QUEUED' : 'QUEUED';
    const runningPhase = engine === 'AGENT' ? 'AGENT_ANALYZING' : 'PROVIDER_START';
    const runningDetail = engine === 'AGENT'
      ? '{"runId":4,"claimAttempt":1,"sequence":0}'
      : '{}';
    const scenarios = [
      {
        status: 'RUNNING',
        events: [event(1, reviewKey, queuedPhase)],
        expected: 'QUEUED'
      },
      {
        status: 'RUNNING',
        events: [event(2, reviewKey, runningPhase, runningDetail)],
        expected: 'ANALYZING'
      },
      { status: 'SUCCESS', events: [], expected: 'SUCCESS' },
      { status: 'FAILED', events: [], expected: 'FAILED' },
      { status: 'CANCELLED', events: [], expected: 'CANCELLED' },
      { status: 'SKIPPED', events: [], expected: 'SKIPPED' }
    ];

    for (const scenario of scenarios) {
      const journey = buildReviewJourney(
        review(engine, scenario.status, reviewKey),
        scenario.events,
        { now: NOW }
      );
      const hero = buildReviewHeroModel(journey);
      assert.equal(hero.kind, kind, `${engine} ${scenario.expected} kind`);
      assert.equal(hero.state, scenario.expected, `${engine} ${scenario.expected} state`);
      assert.match(hero.ariaLabel, /Review/);
      assert.equal(hero.ariaLabel.includes('SECRET'), false);
    }
  }
});

test('maps Agent analysis evidence convergence and submission without inventing progress', () => {
  const reviewKey = 'agent-substages';
  const phases = [
    ['AGENT_ANALYZING', 'ANALYZING'],
    ['AGENT_TOOL_ACTIVITY', 'EVIDENCE'],
    ['AGENT_CONVERGING', 'CONVERGING'],
    ['AGENT_SUBMITTING', 'SUBMITTING']
  ];

  phases.forEach(([phase, expected], index) => {
    const events = phases.slice(0, index + 1).map(([itemPhase], itemIndex) => (
      event(
        itemIndex + 1,
        reviewKey,
        itemPhase,
        JSON.stringify({
          runId: 7,
          claimAttempt: 1,
          sequence: itemIndex,
          prompt: 'SECRET_PROMPT',
          workerId: 'SECRET_WORKER'
        })
      )
    ));
    const journey = buildReviewJourney(
      review('AGENT', 'RUNNING', reviewKey),
      events,
      { now: NOW }
    );
    const hero = buildReviewHeroModel(journey);
    const subStages = stage(journey, 'model-review').subStages;

    assert.equal(hero.state, expected);
    assert.equal(subStages[index].status, 'ACTIVE');
    assert.equal(subStages.slice(index + 1).every(item => item.status === 'WAITING'), true);
    assert.doesNotMatch(JSON.stringify(journey), /SECRET_PROMPT|SECRET_WORKER/);
  });
});

test('shows explicit Agent to Standard fallback with a compact timeline', () => {
  const reviewKey = 'fallback-review';
  const journey = buildReviewJourney({
    ...review('AGENT', 'SUCCESS', reviewKey),
    effectiveEngine: 'STANDARD_FALLBACK'
  }, [
    event(1, reviewKey, 'AGENT_ANALYZING', '{"runId":8,"claimAttempt":1,"sequence":0}'),
    event(2, reviewKey, 'AGENT_FALLBACK', '{"runId":8,"claimAttempt":1,"failureMessage":"SECRET_EXCEPTION"}'),
    event(3, reviewKey, 'AGENT_FALLBACK_QUEUED'),
    event(4, reviewKey, 'OPENAI_REQUEST'),
    event(5, reviewKey, 'OPENAI_RESPONSE'),
    event(6, reviewKey, 'RESULT_SAVED'),
    event(7, reviewKey, 'FINISHED')
  ], { now: NOW });

  const hero = buildReviewHeroModel(journey);
  assert.equal(hero.state, 'FALLBACK');
  assert.equal(hero.kind, 'BRAIN');
  assert.equal(reviewTimelineMode(journey), 'COMPACT');
  assert.equal(stage(journey, 'terminal').status, 'WARNING');
  assert.match(stage(journey, 'terminal').warningSummary, /fallback/);
  assert.doesNotMatch(JSON.stringify(journey), /SECRET_EXCEPTION/);
});

test('switches between full and compact timelines and keeps visible stages clickable after polling', () => {
  const reviewKey = 'polling-review';
  const before = buildReviewJourney(
    review('AGENT', 'RUNNING', reviewKey),
    [event(1, reviewKey, 'AGENT_ANALYZING', '{"runId":9,"claimAttempt":1,"sequence":0}')],
    { now: NOW }
  );
  const openStage = resolveOpenReviewJourneyStage(before, 'model-review');
  assert.equal(reviewTimelineMode(before), 'FULL');
  assert.equal(openStage?.id, 'model-review');

  const after = buildReviewJourney(
    review('AGENT', 'RUNNING', reviewKey),
    [
      event(1, reviewKey, 'AGENT_ANALYZING', '{"runId":9,"claimAttempt":1,"sequence":0}'),
      event(2, reviewKey, 'AGENT_TOOL_ACTIVITY', '{"runId":9,"claimAttempt":1,"sequence":1}')
    ],
    { now: NOW }
  );
  assert.equal(resolveOpenReviewJourneyStage(after, openStage.id)?.id, 'model-review');
  assert.equal(stage(after, 'model-review').subStages[1].status, 'ACTIVE');

  const disappeared = buildReviewJourney(
    review('STANDARD', 'RUNNING', reviewKey),
    [],
    { now: NOW }
  );
  assert.equal(resolveOpenReviewJourneyStage(disappeared, openStage.id), null);
  assert.equal(visibleReviewJourneyStages(disappeared).length, 0);

  const terminal = buildReviewJourney(
    review('STANDARD', 'SUCCESS', reviewKey),
    [event(3, reviewKey, 'FINISHED')],
    { now: NOW }
  );
  assert.equal(reviewTimelineMode(terminal), 'COMPACT');
});

test('isolates alert actions and exposes only fixed warning and failure guidance', () => {
  const warningJourney = buildReviewJourney(
    review('STANDARD', 'RUNNING', 'warning-review'),
    [
      event(
        1,
        null,
        'DETERMINISTIC_PRECHECK_FAILED',
        '{"exception":"SECRET_STACK","path":"SECRET_PATH"}',
        'WARN'
      ),
      event(2, 'warning-review', 'PROVIDER_START')
    ],
    { now: NOW }
  );
  const warning = buildStageAlertModel(stage(warningJourney, 'preflight'));
  assert.equal(warning.status, 'WARNING');
  assert.match(warning.reason, /fail-open/);
  assert.doesNotMatch(JSON.stringify(warning), /SECRET_STACK|SECRET_PATH/);

  const failedJourney = buildReviewJourney(
    review('STANDARD', 'FAILED', 'failed-review'),
    [event(3, 'failed-review', 'SAVE_FAILED', '{damaged-detail', 'ERROR')],
    { now: NOW }
  );
  const failedStage = stage(failedJourney, 'parse-save');
  const failed = buildStageAlertModel(failedStage);
  assert.equal(failed.status, 'FAILED');
  assert.equal(failedStage.events[0].detailAvailable, false);
  assert.doesNotMatch(JSON.stringify(failed), /damaged-detail/);
});

test('supports keyboard dismissal activation reduced motion and narrow-screen orientation', () => {
  assert.equal(isReviewStageActivationKey('Enter'), true);
  assert.equal(isReviewStageActivationKey(' '), true);
  assert.equal(isReviewStageActivationKey('Spacebar'), true);
  assert.equal(isReviewStageActivationKey('Escape'), false);
  assert.equal(isReviewJourneyDismissKey('Escape'), true);
  assert.equal(isReviewJourneyDismissKey('Enter'), false);

  assert.equal(shouldAnimateReview({ state: 'EVIDENCE', reducedMotion: false }), true);
  assert.equal(shouldAnimateReview({ state: 'EVIDENCE', reducedMotion: true }), false);
  assert.equal(shouldAnimateReview({ state: 'SUCCESS', reducedMotion: false }), false);
  assert.equal(reviewTimelineOrientation(1440), 'HORIZONTAL');
  assert.equal(reviewTimelineOrientation(1024), 'HORIZONTAL');
  assert.equal(reviewTimelineOrientation(390), 'VERTICAL');
});
