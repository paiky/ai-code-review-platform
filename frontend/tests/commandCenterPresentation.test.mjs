import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildCommandCenterPresentation,
  stageLabel,
  stateToken
} from '../src/command-center/commandCenterPresentation.js';


test('presentation keeps standard agent and fallback as explicit static lanes', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: {
      freshness: 'FRESH',
      generatedAt: '2026-07-31T02:00:00Z',
      intake: { activeTaskCount: 2 },
      scheduler: { activeJobCount: 3, queuedJobCount: 1, runningJobCount: 2 },
      activeTasks: [],
      activeFlows: [
        flow('standard-main', 'STANDARD', 'STANDARD', false, 'MODEL_CALLING'),
        flow('agent-main', 'AGENT', 'AGENT', false, 'AGENT_ANALYZING'),
        flow('fallback-main', 'AGENT', 'STANDARD_FALLBACK', true, 'FALLBACK')
      ],
      agent: {
        queueMetrics: { queued: 1 },
        workerPool: { onlineCount: 2 }
      },
      providersObserved: [{ providerCode: 'DS', providerName: 'DeepSeek', status: 'ACTIVE' }],
      alerts: []
    },
    governance: {
      freshness: 'FRESH',
      findingRisk: { severityCounts: { CRITICAL: 1 } },
      coverage: { truncated: false },
      ruleAnalysis: {},
      preflight: {},
      contextQuality: { statusCounts: {} },
      notifications: { statusCounts: {} },
      feedback: {},
      evaluation: { acceptance: {}, agentSampleGate: {} },
      policies: {}
    }
  });

  assert.equal(presentation.allowAnimation, false);
  assert.equal(presentation.topology.standardFlowCount, 1);
  assert.equal(presentation.topology.agentFlowCount, 1);
  assert.equal(presentation.topology.fallbackFlowCount, 1);
  assert.equal(
    presentation.topology.flows.find(item => item.reviewKey === 'fallback-main').engineKind,
    'FALLBACK'
  );
  assert.equal(presentation.pulse.onlineWorkers, 2);
  assert.equal(presentation.pulse.activeProviders, 1);
  assert.equal(presentation.pulse.criticalFindings, 1);
  assert.deepEqual(
    presentation.topology.scene.nodes.map(node => [
      node.id,
      node.x,
      node.y,
      node.flowCount
    ]),
    [
      ['lifecycle:intake', 0.1, 0.5, 0],
      ['lifecycle:rule', 0.3, 0.5, 0],
      ['lifecycle:orchestration', 0.5, 0.5, 0],
      ['lifecycle:execution', 0.7, 0.5, 3],
      ['lifecycle:delivery', 0.9, 0.5, 0]
    ]
  );
  assert.equal(presentation.topology.scene.allowAnimation, false);
  assert.equal(presentation.topology.scene.edges.length, 4);
});


test('presentation labels provider observations without health claims', () => {
  const presentation = buildCommandCenterPresentation({
    runtime: {
      activeFlows: [],
      activeTasks: [],
      providersObserved: [
        { providerCode: 'A', providerName: 'A', status: 'RECENT_SUCCESS' },
        { providerCode: 'B', providerName: 'B', status: 'RECENT_FAILURE' },
        { providerCode: 'C', providerName: 'C', status: 'NO_RECENT_DATA' }
      ],
      alerts: [],
      intake: {},
      scheduler: {},
      agent: { queueMetrics: {}, workerPool: {} }
    }
  });

  assert.deepEqual(
    presentation.operations.providers.map(provider => provider.statusLabel),
    ['最近成功', '最近失败', '暂无近期数据']
  );
  assert.equal(
    JSON.stringify(presentation).includes('HEALTHY'),
    false
  );
});


test('governance presentation preserves window and all-time scopes', () => {
  const presentation = buildCommandCenterPresentation({
    governance: {
      ruleAnalysis: { riskItemCount: 2, scope: 'WINDOW' },
      preflight: { findingCount: 1, scope: 'WINDOW' },
      contextQuality: { statusCounts: { INSUFFICIENT: 3 }, scope: 'WINDOW' },
      findingRisk: { severityCounts: { CRITICAL: 1 }, scope: 'WINDOW' },
      notifications: { statusCounts: { FAILED: 1 }, scope: 'WINDOW' },
      feedback: { pendingCount: 4, scope: 'ALL_TIME' },
      evaluation: {
        caseCount: 20,
        scope: 'ALL_TIME',
        acceptance: { totalCount: 2 },
        agentSampleGate: { annotatedSampleCount: 20, requiredSampleCount: 30 }
      },
      policies: { candidateCount: 5, scope: 'ALL_TIME' },
      coverage: { truncated: false }
    }
  });

  const metrics = Object.fromEntries(
    presentation.governance.metrics.map(metric => [metric.label, metric])
  );
  assert.equal(metrics['Rule Analysis'].scope, 'WINDOW');
  assert.equal(metrics['Pending Feedback'].scope, 'ALL_TIME');
  assert.equal(metrics['Agent Sample Gate'].value, '20/30');
  assert.equal(metrics['Acceptance Gate'].href, '/acceptance-gates');
});


test('state and stage labels use safe static tokens', () => {
  assert.equal(stateToken('FAILED'), 'danger');
  assert.equal(stateToken('FALLBACK'), 'warning');
  assert.equal(stateToken('THINKING'), 'neutral');
  assert.equal(stageLabel('AGENT_CONVERGING'), 'Agent 收敛');
  assert.equal(stageLabel('FUTURE_PHASE'), '运行中');
});


test('empty data keeps only the real static lifecycle scene without synthetic flows', () => {
  const presentation = buildCommandCenterPresentation();

  assert.equal(presentation.allowAnimation, false);
  assert.equal(presentation.topology.flows.length, 0);
  assert.equal(presentation.topology.columns.length, 5);
  assert.equal(presentation.topology.scene.nodes.length, 5);
  assert.equal(presentation.topology.scene.edges.length, 4);
  assert.deepEqual(
    presentation.topology.scene.nodes.map(node => node.flowCount),
    [0, 0, 0, 0, 0]
  );
});


function flow(reviewKey, requestedEngine, effectiveEngine, fallback, stage) {
  return {
    id: `1:${reviewKey}`,
    taskId: 1,
    reviewKey,
    displayName: reviewKey,
    requestedEngine,
    effectiveEngine,
    fallback,
    status: fallback ? 'FALLBACK' : 'RUNNING',
    stage,
    stageSource: fallback ? 'AI_RESULT' : 'PROGRESS'
  };
}
