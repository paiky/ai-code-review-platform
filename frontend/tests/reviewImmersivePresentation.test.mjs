import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  buildReviewImmersivePresentation,
  deriveReviewWorkspaceMode,
  normalizeReviewWorkspaceMode,
  resolveReviewWorkspaceFrame
} from '../src/reviewImmersivePresentation.js';
import {
  buildReviewJourney,
  buildReviewJourneys,
  resolveReviewSelectionKey
} from '../src/reviewJourney.js';

const NOW = Date.parse('2026-07-30T08:00:00Z');
const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
const styleSource = await readFile(new URL('../src/styles.css', import.meta.url), 'utf8');

function review(engine, status, reviewKey) {
  return {
    id: reviewKey,
    reviewKey,
    requestedEngine: engine,
    effectiveEngine: engine,
    provider: engine === 'AGENT' ? 'DeepSeek' : 'OpenAI',
    model: engine === 'AGENT' ? 'agent-model' : 'standard-model',
    status,
    startedAt: '2026-07-30T07:58:00Z'
  };
}

function event(id, reviewKey, phase, detail = '{}', level = 'INFO') {
  return {
    id,
    reviewKey,
    phase,
    detail,
    level,
    createdAt: `2026-07-30T07:${String(58 + id).padStart(2, '0')}:00Z`
  };
}

function presentation(journey, options = {}) {
  return buildReviewImmersivePresentation({
    loaded: true,
    journey,
    taskSummary: {
      id: 42,
      title: '安全项目 · Merge Request',
      triggerLabel: 'Merge Request',
      targetLabel: '后端',
      taskStatusLabel: '审查中',
      eventAt: '2026-07-30T07:57:00Z',
      changedFileCount: 3
    },
    changedFilesSummary: { changedFileCount: 3 },
    now: NOW,
    ...options
  });
}

test('derives LOADING IMMERSIVE and RESULT without changing the Journey status', () => {
  const running = buildReviewJourney(
    review('AGENT', 'RUNNING', 'agent-running'),
    [event(1, 'agent-running', 'AGENT_ANALYZING', '{"runId":7,"claimAttempt":1}')],
    { now: NOW }
  );

  assert.equal(deriveReviewWorkspaceMode({ loaded: false, journey: running }), 'LOADING');
  assert.equal(deriveReviewWorkspaceMode({ loaded: true, journey: running }), 'IMMERSIVE');
  assert.equal(deriveReviewWorkspaceMode({
    loaded: true,
    journey: running,
    safeFallback: true
  }), 'RESULT');
  assert.equal(deriveReviewWorkspaceMode({ loaded: true, journey: null }), 'RESULT');
  assert.equal(running.status, 'RUNNING');
});

test('maps Agent and Standard queued running success failed cancelled and skipped', () => {
  for (const engine of ['AGENT', 'STANDARD']) {
    const queuedKey = `${engine.toLowerCase()}-queued`;
    const queuedPhase = engine === 'AGENT' ? 'AGENT_QUEUED' : 'QUEUED';
    const queued = buildReviewJourney(
      review(engine, 'RUNNING', queuedKey),
      [event(1, queuedKey, queuedPhase)],
      { now: NOW }
    );
    const runningKey = `${engine.toLowerCase()}-running`;
    const runningPhase = engine === 'AGENT' ? 'AGENT_ANALYZING' : 'PROVIDER_START';
    const running = buildReviewJourney(
      review(engine, 'RUNNING', runningKey),
      [event(1, runningKey, runningPhase, '{"runId":2,"claimAttempt":1}')],
      { now: NOW }
    );

    assert.equal(presentation(queued).mode, 'IMMERSIVE', `${engine} queued`);
    assert.equal(presentation(running).mode, 'IMMERSIVE', `${engine} running`);
    assert.equal(
      presentation(running).engineVisual,
      engine === 'AGENT' ? 'AGENT_PARTICLE' : 'STANDARD_FLOW'
    );

    for (const status of ['SUCCESS', 'FAILED', 'CANCELLED', 'SKIPPED']) {
      const key = `${engine.toLowerCase()}-${status.toLowerCase()}`;
      const terminal = buildReviewJourney(
        review(engine, status, key),
        [],
        { now: NOW }
      );
      assert.equal(presentation(terminal).mode, 'RESULT', `${engine} ${status}`);
      assert.equal(presentation(terminal).status, status);
    }
  }
});

test('uses Standard visual and fixed transfer copy while Agent fallback is running', () => {
  const reviewKey = 'fallback-running';
  const journey = buildReviewJourney({
    ...review('AGENT', 'RUNNING', reviewKey),
    effectiveEngine: 'STANDARD_FALLBACK'
  }, [
    event(1, reviewKey, 'AGENT_FALLBACK', '{"failureMessage":"SECRET_EXCEPTION"}'),
    event(2, reviewKey, 'AGENT_FALLBACK_QUEUED'),
    event(3, reviewKey, 'OPENAI_REQUEST')
  ], { now: NOW });
  const model = presentation(journey);

  assert.equal(model.mode, 'IMMERSIVE');
  assert.equal(model.engineVisual, 'STANDARD_FLOW');
  assert.match(model.fallbackTransfer.title, /Agent.*Standard/);
  assert.doesNotMatch(JSON.stringify(model), /SECRET_EXCEPTION/);
});

test('keeps historical and missing-field tasks in RESULT without inventing time', () => {
  const historical = buildReviewJourney(
    { id: 90, reviewKey: null, status: 'SUCCESS' },
    [],
    { now: NOW }
  );
  const historicalModel = presentation(historical);
  const missingModel = buildReviewImmersivePresentation({
    loaded: true,
    journey: null,
    now: NOW
  });
  const futureStart = presentation({
    ...historical,
    historical: false,
    status: 'RUNNING',
    statusLabel: '运行中',
    running: true,
    startedAt: '2026-07-31T08:00:00Z'
  });

  assert.equal(historicalModel.mode, 'RESULT');
  assert.equal(historicalModel.elapsedMs, null);
  assert.equal(missingModel.mode, 'RESULT');
  assert.equal(futureStart.startedAt, null);
  assert.equal(futureStart.elapsedMs, null);
});

test('uses only the selected reviewKey for mode across URL selection polling and reorder', () => {
  const initial = buildReviewJourneys([
    review('AGENT', 'RUNNING', 'review-running'),
    review('STANDARD', 'SUCCESS', 'review-terminal')
  ], [
    event(1, 'review-running', 'AGENT_ANALYZING')
  ], { now: NOW });
  const directSelection = resolveReviewSelectionKey(initial, {
    requestedReviewKey: 'review-terminal',
    preferRequested: true
  });
  assert.equal(directSelection, 'review-terminal');
  assert.equal(
    presentation(initial.find(item => item.selectorKey === directSelection)).mode,
    'RESULT'
  );

  const afterPolling = buildReviewJourneys([
    review('STANDARD', 'SUCCESS', 'review-terminal'),
    review('AGENT', 'RUNNING', 'review-running')
  ], [
    event(1, 'review-running', 'AGENT_ANALYZING'),
    event(2, 'review-running', 'AGENT_TOOL_ACTIVITY')
  ], { now: NOW });
  const preservedSelection = resolveReviewSelectionKey(afterPolling, {
    currentSelectionKey: directSelection,
    preferRequested: false
  });
  assert.equal(preservedSelection, 'review-terminal');
  assert.equal(
    presentation(afterPolling.find(item => item.selectorKey === preservedSelection)).mode,
    'RESULT'
  );
});

test('reuses whitelist stage details and never exposes raw progress detail', () => {
  const reviewKey = 'safe-agent';
  const journey = buildReviewJourney(
    review('AGENT', 'RUNNING', reviewKey),
    [
      event(
        1,
        reviewKey,
        'AGENT_TOOL_ACTIVITY',
        '{"runId":4,"claimAttempt":1,"sequence":1,"prompt":"SECRET_PROMPT","workerId":"SECRET_WORKER","filePath":"SECRET_PATH"}'
      )
    ],
    { now: NOW }
  );
  const model = presentation(journey);
  const serialized = JSON.stringify(model);

  assert.equal(model.stages[0], journey.stages.find(stage => stage.visible));
  assert.doesNotMatch(serialized, /SECRET_PROMPT|SECRET_WORKER|SECRET_PATH/);
  assert.equal(serialized.includes('"detail":'), false);
  assert.equal(model.elapsedMs, 120000);
});

test('AppFrame mode is route-scoped and invalid or departed routes restore the normal frame', () => {
  assert.equal(normalizeReviewWorkspaceMode('IMMERSIVE'), 'IMMERSIVE');
  assert.equal(normalizeReviewWorkspaceMode('BROKEN'), 'RESULT');
  assert.deepEqual(resolveReviewWorkspaceFrame('IMMERSIVE', true), {
    mode: 'IMMERSIVE',
    immersive: true
  });
  assert.equal(resolveReviewWorkspaceFrame('IMMERSIVE', false).immersive, false);
  assert.equal(resolveReviewWorkspaceFrame('RESULT', true).immersive, false);
  assert.equal(resolveReviewWorkspaceFrame('LOADING', true).immersive, false);

  assert.match(appSource, /ReviewWorkspaceModeContext\.Provider/);
  assert.match(appSource, /return \(\) => reportMode\('RESULT'\)/);
  assert.match(appSource, /!reviewWorkspaceFrame\.immersive && \(/);
  assert.match(appSource, /app-content-review-immersive/);
  assert.equal(appSource.includes('requestFullscreen'), false);
  assert.equal(appSource.includes('document.body.class'), false);
});

test('immersive workspace keeps semantic regions existing interactions and reduced motion', () => {
  const start = appSource.indexOf('function ReviewImmersiveWorkspace');
  const end = appSource.indexOf('function CodeQualityReviewView', start);
  const workspaceSource = appSource.slice(start, end);

  for (const marker of [
    '<header',
    '<main',
    '<nav',
    '<aside',
    '<footer',
    '<ReviewJourneyTimeline',
    '<AgentReviewAnimation',
    '<StandardReviewAnimation',
    'style="BRAIN"',
    '中断当前 Review',
    '任务信息',
    '安全活动摘要'
  ]) {
    assert.equal(workspaceSource.includes(marker), true, marker);
  }
  for (const prohibited of [
    'filePath',
    'toolArguments',
    'workerId',
    'rawResponse',
    'assistantMessage',
    'queryHash',
    'pathHash'
  ]) {
    assert.equal(workspaceSource.includes(prohibited), false, prohibited);
  }
  assert.match(styleSource, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(styleSource, /review-immersive-task-drawer-root[\s\S]*100dvh/);
  assert.match(styleSource, /review-immersive-main[\s\S]*grid-template-areas/);
});
