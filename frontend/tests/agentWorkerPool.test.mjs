import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildAgentQueueAlerts,
  formatAgentQueueSummary,
  formatQueueAge,
  formatWorkerActivity,
  normalizeAgentQueueMetrics,
  normalizeAgentWorkerPool,
  workerStateColor,
  workerStateLabel
} from '../src/agentWorkerPool.js';

test('normalizes registered worker pool counts and safe node fields', () => {
  const pool = normalizeAgentWorkerPool({
    workerStatus: 'ONLINE',
    workerPool: {
      onlineCount: 2,
      busyCount: 1,
      idleCount: 1,
      drainingCount: 0,
      totalCapacity: 2,
      totalCount: 2,
      nodes: [
        {
          workerId: 'agent-worker-a',
          workerVersion: 'worker-v2',
          cliVersion: '2.1.112',
          state: 'BUSY',
          capacity: 1,
          activeJobId: 8,
          activeRunId: 9,
          lastHeartbeatAt: '2026-07-29T12:00:00Z',
          online: true,
          source: 'SECRET_SOURCE'
        },
        {
          workerId: 'agent-worker-b',
          state: 'IDLE',
          capacity: 1,
          online: true
        }
      ]
    }
  });

  assert.equal(pool.status, 'ONLINE');
  assert.equal(pool.onlineCount, 2);
  assert.equal(pool.totalCapacity, 2);
  assert.equal(pool.onlineCapacity, 2);
  assert.equal(pool.busyCapacity, 1);
  assert.equal(pool.utilizationPercent, 50);
  assert.equal(formatWorkerActivity(pool.nodes[0]), 'Job #8 / Run #9');
  assert.equal(JSON.stringify(pool).includes('SECRET_SOURCE'), false);
  assert.deepEqual(Object.keys(pool.nodes[0]), [
    'workerId',
    'workerVersion',
    'cliVersion',
    'state',
    'capacity',
    'activeJobId',
    'activeRunId',
    'startedAt',
    'lastHeartbeatAt',
    'online',
    'legacy'
  ]);
});

test('keeps legacy singleton worker settings visible without registration rows', () => {
  const pool = normalizeAgentWorkerPool({
    workerStatus: 'ONLINE',
    workerId: 'legacy-worker-1',
    workerVersion: 'legacy-v1',
    cliVersion: '2.1.112',
    lastWorkerHeartbeatAt: '2026-07-29T12:00:00Z',
    workerPool: {
      onlineCount: 0,
      busyCount: 0,
      idleCount: 0,
      totalCapacity: 0,
      totalCount: 0,
      nodes: []
    }
  });

  assert.equal(pool.status, 'ONLINE');
  assert.equal(pool.onlineCount, 1);
  assert.equal(pool.totalCapacity, 1);
  assert.equal(pool.nodes[0].legacy, true);
});

test('formats worker states and never exposes activity for idle nodes', () => {
  assert.equal(workerStateLabel('IDLE'), '空闲');
  assert.equal(workerStateLabel('BUSY'), '忙碌');
  assert.equal(workerStateLabel('DRAINING'), '排空中');
  assert.equal(workerStateColor('BUSY', true), 'blue');
  assert.equal(workerStateColor('BUSY', false), 'default');
  assert.equal(formatWorkerActivity({ state: 'IDLE', activeJobId: 1 }), '-');
  assert.equal(formatWorkerActivity({ state: 'BUSY' }), '配置测试或任务启动中');
  assert.equal(formatWorkerActivity({ state: 'DRAINING' }), '排空中');
});

test('formats queue summary and calculates finite capacity utilization', () => {
  const settings = {
    workerPool: {
      onlineCount: 3,
      busyCount: 2,
      idleCount: 1,
      drainingCount: 0,
      totalCapacity: 3,
      onlineCapacity: 3,
      busyCapacity: 2,
      totalCount: 3,
      nodes: []
    },
    queueMetrics: {
      queued: 4,
      running: 2,
      expiredLease: 1,
      oldestQueuedSeconds: 125,
      onlineCapacity: 3,
      busyCapacity: 2,
      utilizationPercent: 67,
      drainingWorkers: 0,
      lastWorkerHeartbeatAt: '2026-07-29T12:00:00Z'
    }
  };

  const metrics = normalizeAgentQueueMetrics(settings);

  assert.deepEqual(metrics, {
    queued: 4,
    running: 2,
    expiredLease: 1,
    oldestQueuedSeconds: 125,
    onlineCapacity: 3,
    busyCapacity: 2,
    utilizationPercent: 67,
    drainingWorkers: 0,
    lastWorkerHeartbeatAt: '2026-07-29T12:00:00Z'
  });
  assert.equal(
    formatAgentQueueSummary(metrics),
    '排队 4 · 运行 2 · 过期租约 1 · 最老等待 2 分 5 秒'
  );
  assert.equal(formatQueueAge(3600), '1 小时');

  const zero = normalizeAgentQueueMetrics({
    queueMetrics: {
      onlineCapacity: 0,
      busyCapacity: 99,
      utilizationPercent: Number.POSITIVE_INFINITY
    }
  });
  assert.equal(zero.busyCapacity, 0);
  assert.equal(zero.utilizationPercent, 0);
});

test('builds draining offline saturated and backlog safety alerts', () => {
  const offline = buildAgentQueueAlerts({});
  assert.deepEqual(offline.map(item => item.key), ['offline']);

  const activeAlerts = buildAgentQueueAlerts({
    workerPool: {
      onlineCount: 2,
      busyCount: 1,
      idleCount: 0,
      drainingCount: 1,
      totalCapacity: 2,
      onlineCapacity: 1,
      busyCapacity: 1,
      totalCount: 2,
      nodes: []
    },
    queueMetrics: {
      queued: 3,
      running: 1,
      expiredLease: 1,
      oldestQueuedSeconds: 120,
      onlineCapacity: 1,
      busyCapacity: 1,
      utilizationPercent: 100,
      drainingWorkers: 1
    }
  });

  assert.deepEqual(
    activeAlerts.map(item => item.key),
    ['draining', 'expired-lease', 'saturated', 'backlog']
  );
  assert.equal(
    activeAlerts.find(item => item.key === 'saturated').description.includes('不会仅因 Worker 忙碌触发'),
    true
  );
});

test('keeps old backend responses without queue metrics compatible', () => {
  const settings = {
    workerStatus: 'ONLINE',
    workerId: 'legacy-worker-1',
    lastWorkerHeartbeatAt: '2026-07-29T12:00:00Z'
  };

  const metrics = normalizeAgentQueueMetrics(settings);

  assert.deepEqual(metrics, {
    queued: 0,
    running: 0,
    expiredLease: 0,
    oldestQueuedSeconds: 0,
    onlineCapacity: 1,
    busyCapacity: 0,
    utilizationPercent: 0,
    drainingWorkers: 0,
    lastWorkerHeartbeatAt: '2026-07-29T12:00:00Z'
  });
  assert.deepEqual(buildAgentQueueAlerts(settings), []);
});
